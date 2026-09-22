"""
On-screen feedback for Windows: a small status card near the text caret and
the Polish preview. Both live on the UIManager's Tk thread; the worker only
posts requests.

The status card is a WS_EX_NOACTIVATE tool window, so it never takes focus
from the app you are typing in, and its buttons (Undo, Cancel) can still be
clicked. The Polish preview does take focus (it needs Enter / Esc); focus is
handed back to your app before the text is pasted.
"""

import ctypes
import tkinter as tk
from ctypes import wintypes as w

import ui_kit as K
from ui_kit import (
    SURFACE, SURFACE_3, BORDER_STRONG, TEXT, TEXT_2, TEXT_3, ACCENT, CORAL, GREEN, AMBER, RED,
    px, Button, TextBox, label, draw_round_rect,
)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

_user32.GetForegroundWindow.restype = w.HWND
_user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
_user32.GetWindowThreadProcessId.restype = w.DWORD
_user32.AttachThreadInput.argtypes = [w.DWORD, w.DWORD, w.BOOL]
_user32.SetForegroundWindow.argtypes = [w.HWND]
_user32.BringWindowToTop.argtypes = [w.HWND]
_user32.SetFocus.argtypes = [w.HWND]
_user32.ClientToScreen.argtypes = [w.HWND, ctypes.POINTER(w.POINT)]
_user32.MonitorFromPoint.argtypes = [w.POINT, w.DWORD]
_user32.MonitorFromPoint.restype = w.HANDLE
_user32.GetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int]
_user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowLongPtrW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
_user32.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.UINT]
_user32.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
_user32.IsWindow.argtypes = [w.HWND]
_kernel32.GetCurrentThreadId.restype = w.DWORD

GWL_EXSTYLE = -20
WS_EX_TOPMOST, WS_EX_TOOLWINDOW, WS_EX_NOACTIVATE = 0x8, 0x80, 0x08000000
HWND_TOPMOST = w.HWND(-1)
SWP_NOSIZE, SWP_NOMOVE, SWP_NOACTIVATE, SWP_SHOWWINDOW = 0x1, 0x2, 0x10, 0x40

_KEY = "#010203"  # transparent key colour for rounded corners


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("flags", w.DWORD), ("hwndActive", w.HWND), ("hwndFocus", w.HWND),
                ("hwndCapture", w.HWND), ("hwndMenuOwner", w.HWND), ("hwndMoveSize", w.HWND),
                ("hwndCaret", w.HWND), ("rcCaret", w.RECT)]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("rcMonitor", w.RECT), ("rcWork", w.RECT), ("dwFlags", w.DWORD)]


_user32.GetGUIThreadInfo.argtypes = [w.DWORD, ctypes.POINTER(GUITHREADINFO)]
_user32.GetMonitorInfoW.argtypes = [w.HANDLE, ctypes.POINTER(MONITORINFO)]


# ---------------------------------------------------------------------------
# Win32 helpers
# ---------------------------------------------------------------------------

def caret_point():
    """Screen position just below the text caret, or the mouse pointer when the
    app does not expose a system caret (Chrome, Electron, Word)."""
    try:
        fg = _user32.GetForegroundWindow()
        tid = _user32.GetWindowThreadProcessId(fg, None)
        info = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
        if tid and _user32.GetGUIThreadInfo(tid, ctypes.byref(info)) and info.hwndCaret:
            rc = info.rcCaret
            if rc.bottom > rc.top:
                pt = w.POINT(rc.left, rc.bottom)
                if _user32.ClientToScreen(info.hwndCaret, ctypes.byref(pt)):
                    return pt.x, pt.y, True
    except Exception:
        pass
    pt = w.POINT()
    _user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y, False


def work_area(x, y):
    try:
        mon = _user32.MonitorFromPoint(w.POINT(x, y), 2)  # MONITOR_DEFAULTTONEAREST
        mi = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        if _user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            r = mi.rcWork
            return r.left, r.top, r.right, r.bottom
    except Exception:
        pass
    return 0, 0, _user32.GetSystemMetrics(0), _user32.GetSystemMetrics(1)


def force_foreground(hwnd):
    """Make `hwnd` the active window even though another process owns the
    foreground (joining the foreground thread's input queue lifts the lock)."""
    if not hwnd or not _user32.IsWindow(hwnd):
        return False
    fg = _user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    me = _kernel32.GetCurrentThreadId()
    other = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and _user32.AttachThreadInput(me, other, True))
    try:
        _user32.BringWindowToTop(hwnd)
        _user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            _user32.AttachThreadInput(me, other, False)
    return _user32.GetForegroundWindow() == hwnd


def _frame(win):
    win.update_idletasks()
    try:
        return int(win.wm_frame(), 16)
    except Exception:
        return _user32.GetParent(win.winfo_id()) or win.winfo_id()


def _no_activate(win):
    hwnd = _frame(win)
    style = _user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    _user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
    _user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE)
    return hwnd


# ---------------------------------------------------------------------------
# Status card
# ---------------------------------------------------------------------------

_KIND = {
    "working": (ACCENT, None),
    "success": (GREEN, "✓"),
    "info": (AMBER, "!"),
    "error": (RED, "×"),
    "polish": (CORAL, "✓"),
}


class Hud:
    """One reusable status card. show() replaces whatever is on screen."""

    WIDTH_MIN, WIDTH_MAX = 240, 440

    def __init__(self, root):
        self.root = root
        self.win = None
        self._hide_job = None
        self._spin_job = None
        self._spin = 0
        self._hover = False
        self._timeout = None
        self._alpha_job = None
        self.token = 0

    def _build(self):
        self.win = tk.Toplevel(self.root, bg=_KEY)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=SURFACE)
        self.canvas.create_window(px(14), px(11), window=self.body, anchor="nw", tags="body")
        self.win.bind("<Enter>", lambda e: self._set_hover(True))
        self.win.bind("<Leave>", lambda e: self._set_hover(False))
        self.win.update_idletasks()
        self.hwnd = _no_activate(self.win)

    def _set_hover(self, flag):
        self._hover = flag
        if not flag and self._timeout:
            self._schedule_hide(self._timeout)

    def show(self, kind, title, detail="", actions=(), timeout=None, progress=None, anchor=None):
        """kind: working | success | info | error | polish. actions: [(label, callback)]."""
        if self.win is None:
            self._build()
        self.token += 1
        sig = (kind, tuple(a[0] for a in actions), progress is None, bool(detail))
        if (kind == "working" and getattr(self, "_sig", None) == sig and self.win.winfo_viewable()
                and self._title.winfo_exists()):
            self._title.configure(text=title)
            if detail and self._detail is not None:
                self._detail.configure(text=detail)
            if progress is not None and self._bar is not None:
                self._bar.set(progress)
            return
        self._sig = sig
        self._detail = self._bar = None
        for job in (self._hide_job, self._spin_job):
            if job:
                self.win.after_cancel(job)
        self._hide_job = self._spin_job = None
        for child in self.body.winfo_children():
            child.destroy()

        color, glyph = _KIND.get(kind, _KIND["info"])
        row = tk.Frame(self.body, bg=SURFACE)
        row.pack(fill="x")
        icon = tk.Canvas(row, width=px(20), height=px(20), bg=SURFACE, highlightthickness=0, bd=0)
        icon.pack(side="left", anchor="n", padx=(0, px(10)), pady=(px(1), 0))
        if glyph:
            icon.create_oval(px(1), px(1), px(19), px(19), fill=color, outline=color)
            icon.create_text(px(10), px(10), text=glyph, fill=K.BG, font=K.FONTS["small_b"])
        else:
            self._icon = icon
            self._spin_color = color
            self._spinner()

        txt = tk.Frame(row, bg=SURFACE)
        txt.pack(side="left", fill="x", expand=True)
        self._title = label(txt, title, "body_b", TEXT)
        self._title.pack(fill="x")
        if detail:
            self._detail = label(txt, detail, "small", TEXT_2, wrap=self.WIDTH_MAX - 120)
            self._detail.pack(fill="x", pady=(px(1), 0))
        if progress is not None:
            bar = K.ProgressBar(txt, height=4, color=color)
            bar.pack(fill="x", pady=(px(7), px(1)))
            bar.configure(width=px(200))
            self._bar = bar
            self.win.after(20, lambda b=bar, p=progress: b.set(p))

        if actions:
            # Long text and several buttons don't fit on one line at WIDTH_MAX (the last
            # button was cut off): put the buttons on their own row under the text.
            stacked = len(actions) > 1 and len(detail) > 40
            if stacked:
                box = tk.Frame(self.body, bg=SURFACE)
                box.pack(side="top", anchor="e", pady=(px(10), 0))
            else:
                box = tk.Frame(row, bg=SURFACE)
                box.pack(side="right", anchor="center", padx=(px(12), 0))
            for i, (text, cb) in enumerate(actions):
                variant = "secondary" if i == len(actions) - 1 else "ghost"
                Button(box, text, (lambda c=cb: self._run_action(c)), variant, height=28,
                       font=K.FONTS["small_b"], padx=11).pack(side="left", padx=(px(6) if i else 0, 0))

        self._layout(anchor)
        self._timeout = timeout
        if timeout:
            self._schedule_hide(timeout)

    def _run_action(self, cb):
        self.hide()
        try:
            cb()
        except Exception as e:
            print(f"  (hud action failed: {e})")

    def _spinner(self):
        if self.win is None or not getattr(self, "_icon", None) or not self._icon.winfo_exists():
            return
        c = self._icon
        c.delete("spin")
        s = px(20)
        c.create_oval(px(2), px(2), s - px(2), s - px(2), outline=SURFACE_3, width=px(2), tags="spin")
        c.create_arc(px(2), px(2), s - px(2), s - px(2), start=-self._spin, extent=100,
                     style="arc", outline=self._spin_color, width=px(2), tags="spin")
        self._spin = (self._spin + 18) % 360
        self._spin_job = self.win.after(30, self._spinner)

    def _layout(self, anchor):
        self.win.update_idletasks()
        bw = max(px(self.WIDTH_MIN), min(px(self.WIDTH_MAX), self.body.winfo_reqwidth() + px(28)))
        bh = self.body.winfo_reqheight() + px(22)
        self.canvas.itemconfigure("body", width=bw - px(28))
        self.canvas.configure(width=bw, height=bh)
        draw_round_rect(self.canvas, 0, 0, bw, bh, px(12), SURFACE, outline=BORDER_STRONG, bg=_KEY, tag="bg")
        x, y, exact = anchor or caret_point()
        left, top, right, bottom = work_area(x, y)
        gx = min(max(left + px(8), x - px(18)), right - bw - px(8))
        gy = y + px(10) if exact else y + px(22)
        if gy + bh > bottom - px(8):
            gy = max(top + px(8), y - bh - px(34))
        self.win.geometry(f"{bw}x{bh}+{gx}+{gy}")
        if not self.win.winfo_viewable():
            self.win.attributes("-alpha", 0.0)
            self.win.deiconify()
            _user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                 SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_SHOWWINDOW)
            self._fade(0.0, 0.97, 7)

    def _fade(self, start, end, steps, then=None):
        if self._alpha_job:
            self.win.after_cancel(self._alpha_job)

        def step(i):
            try:
                self.win.attributes("-alpha", start + (end - start) * i / steps)
            except tk.TclError:
                return
            if i < steps:
                self._alpha_job = self.win.after(16, step, i + 1)
            else:
                self._alpha_job = None
                if then:
                    then()
        step(1)

    def _schedule_hide(self, ms):
        if self._hide_job:
            self.win.after_cancel(self._hide_job)
        self._hide_job = self.win.after(ms, self._auto_hide)

    def _auto_hide(self):
        self._hide_job = None
        if self._hover:
            return  # hide when the pointer leaves
        self.hide()

    def hide(self, token=None):
        if self.win is None or (token is not None and token != self.token):
            return
        self._timeout = None
        for job in (self._hide_job, self._spin_job):
            if job:
                self.win.after_cancel(job)
        self._hide_job = self._spin_job = None
        if self.win.winfo_viewable():
            self._fade(0.97, 0.0, 6, then=self.win.withdraw)


# ---------------------------------------------------------------------------
# Polish preview
# ---------------------------------------------------------------------------

class PolishPreview:
    """Shows the polished text before it replaces yours.

    Enter = Replace, Esc = Cancel, R = Try again, 1-5 = pick a style.
    `on_decision(action, value)` is called on the UI thread with
    ("accept", text) | ("cancel", None) | ("retry", style)."""

    WIDTH = 560

    def __init__(self, root, styles, style, on_decision):
        self.root, self.styles, self.style = root, styles, style
        self.on_decision = on_decision
        self.result = ""
        self.busy = False
        self.alive = True

        self.win = tk.Toplevel(root, bg=_KEY)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        body = tk.Frame(self.canvas, bg=SURFACE)
        self.body = body
        self.canvas.create_window(px(20), px(16), window=body, anchor="nw", tags="body")

        head = tk.Frame(body, bg=SURFACE)
        head.pack(fill="x")
        dot = tk.Canvas(head, width=px(8), height=px(8), bg=SURFACE, highlightthickness=0)
        dot.create_oval(0, 0, px(8), px(8), fill=CORAL, outline=CORAL)
        dot.pack(side="left", padx=(0, px(8)))
        label(head, "Polish", "body_b").pack(side="left")
        self.status = label(head, "", "small", TEXT_3)
        self.status.pack(side="left", padx=(px(10), 0))
        close = Button(head, "×", self.cancel, "ghost", width=28, height=26, font=K.FONTS["body_b"], padx=0)
        close.pack(side="right")

        chips = tk.Frame(body, bg=SURFACE)
        chips.pack(fill="x", pady=(px(12), px(10)))
        self.chip = {}
        for i, (key, spec) in enumerate(styles.items(), 1):
            b = Button(chips, spec["label"], (lambda k=key: self.pick(k)), "tab", height=28,
                       font=K.FONTS["small_b"], padx=11)
            b.pack(side="left", padx=(0, px(4)))
            self.chip[key] = b

        self.box = TextBox(body, height=3, readonly=True)
        self.box.pack(fill="x")
        self.box.text.tag_configure("changed", foreground=CORAL)
        self.box.text.configure(width=1)

        foot = tk.Frame(body, bg=SURFACE)
        foot.pack(fill="x", pady=(px(12), 0))
        label(foot, "Enter  replace  ·  R  try again  ·  Esc  cancel", "caption", TEXT_3).pack(side="left")
        self.btn_ok = Button(foot, "Replace", self.accept, "coral", height=32, padx=16)
        self.btn_ok.pack(side="right")
        self.btn_retry = Button(foot, "Try again", self.retry, "secondary", height=32, padx=14)
        self.btn_retry.pack(side="right", padx=(0, px(8)))

        self.win.bind("<Return>", lambda e: self.accept())
        self.win.bind("<KP_Enter>", lambda e: self.accept())
        self.win.bind("<Escape>", lambda e: self.cancel())
        self.win.bind("<KeyPress>", self._key)
        self._paint_chips()
        self.set_busy("Rewriting…")

    def _key(self, e):
        if e.keycode == 82 and not (e.state & 0x4):  # R, any keyboard layout
            self.retry()
        elif 49 <= e.keycode <= 48 + len(self.styles):  # 1..5
            self.pick(list(self.styles)[e.keycode - 49])
        elif e.keycode == 67 and (e.state & 0x4) and self.result:  # Ctrl+C
            self.win.clipboard_clear()
            self.win.clipboard_append(self.result)

    def _paint_chips(self):
        for key, b in self.chip.items():
            b.set_variant("tab_on" if key == self.style else "tab")

    def present(self, anchor=None):
        self._anchor = anchor or caret_point()
        self.canvas.itemconfigure("body", width=px(self.WIDTH) - px(40))
        self.body.bind("<Configure>", lambda e: self._fit())
        self._fit()
        self.win.deiconify()
        self.win.lift()
        force_foreground(_frame(self.win))
        self.win.focus_force()

    def _fit(self):
        """Size the card to its content (the text box grows after it is laid out)."""
        if not self.alive:
            return
        bw = px(self.WIDTH)
        bh = self.body.winfo_reqheight() + px(32)
        if getattr(self, "_fitted", None) == bh:
            return
        self._fitted = bh
        self.canvas.configure(width=bw, height=bh)
        draw_round_rect(self.canvas, 0, 0, bw, bh, px(14), SURFACE, outline=BORDER_STRONG, bg=_KEY, tag="bg")
        x, y, exact = self._anchor
        left, top, right, bottom = work_area(x, y)
        gx = min(max(left + px(12), x - px(40)), right - bw - px(12))
        gy = y + px(14) if exact else y + px(24)
        if gy + bh > bottom - px(12):
            gy = max(top + px(12), y - bh - px(36))
        self.win.geometry(f"{bw}x{bh}+{gx}+{gy}")

    def set_busy(self, text):
        self.busy = True
        self.status.configure(text=text)
        self.btn_ok.set_state("disabled")
        self.btn_retry.set_state("disabled")

    def show_result(self, before, after, note=""):
        from ui import diff_chunks
        self.busy = False
        self.result = after
        self.box.set(after, highlight_words=diff_chunks(before, after))
        try:  # fit the text area to the result: 2 to 12 lines
            self.box.text.update_idletasks()
            lines = self.box.text.count("1.0", "end", "displaylines")
            lines = lines[0] if isinstance(lines, tuple) else lines
            self.box.text.configure(height=max(2, min(12, int(lines or 2))))
        except tk.TclError:
            pass
        self.status.configure(text=note, fg=AMBER if note else TEXT_3)
        self.btn_ok.set_state("normal")
        self.btn_retry.set_state("normal")

    def show_error(self, message):
        self.busy = False
        self.result = ""
        self.box.set(message)
        self.status.configure(text="", fg=TEXT_3)
        self.btn_retry.set_state("normal")

    def pick(self, key):
        if self.busy or key == self.style:
            return
        self.style = key
        self._paint_chips()
        self.set_busy("Rewriting…")
        self.on_decision("retry", key)

    def retry(self):
        if self.busy:
            return
        self.set_busy("Trying another version…")
        self.on_decision("retry", self.style)

    def accept(self):
        if self.busy or not self.result:
            return
        self._close()
        self.on_decision("accept", self.result)

    def cancel(self):
        self._close()
        self.on_decision("cancel", None)

    def _close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass


# ---------------------------------------------------------------------------
# Quick-action menu (Ctrl+Alt+Space)
# ---------------------------------------------------------------------------

class ActionMenu:
    """Fix, Polish, Translate and the user's own actions in one keyboard-first list.

    1-9 or ↑/↓ + Enter choose, → opens a submenu, ← / Backspace go back, Esc or a
    click elsewhere closes. `on_choice(item | None)` is called once, on the UI
    thread. Like the preview it takes focus; the app gives it back before pasting."""

    WIDTH = 320
    ROW = 30

    def __init__(self, root, items, submenu, on_choice):
        self.root, self.submenu, self.on_choice = root, submenu, on_choice
        self.stack = [("Fixelect", list(items))]
        self.index = 0
        self.alive = True
        self._armed = False
        self.rows = []

        self.win = tk.Toplevel(root, bg=_KEY)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-transparentcolor", _KEY)
        except tk.TclError:
            pass
        self.canvas = tk.Canvas(self.win, bg=_KEY, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=SURFACE)
        self.canvas.create_window(px(10), px(10), window=self.body, anchor="nw", tags="body")

        for seq, fn in (("<Up>", lambda e: self.move(-1)), ("<Down>", lambda e: self.move(1)),
                        ("<Return>", lambda e: self.choose(self.index)),
                        ("<KP_Enter>", lambda e: self.choose(self.index)),
                        ("<Right>", lambda e: self.choose(self.index)),
                        ("<Left>", lambda e: self.back()), ("<BackSpace>", lambda e: self.back()),
                        ("<Escape>", lambda e: self.cancel())):
            self.win.bind(seq, fn)
        self.win.bind("<KeyPress>", self._key)
        self.win.bind("<FocusIn>", lambda e: setattr(self, "_armed", True))
        self.win.bind("<FocusOut>", lambda e: self.win.after(200, self._focus_lost))
        self._render()

    def _key(self, e):
        if 49 <= e.keycode <= 57:        # 1-9, any keyboard layout
            self.choose(e.keycode - 49)
        elif 97 <= e.keycode <= 105:     # keypad 1-9
            self.choose(e.keycode - 97)

    def _render(self):
        for child in self.body.winfo_children():
            child.destroy()
        title, items = self.stack[-1]
        label(self.body, title, "small_b", TEXT_2).pack(fill="x", padx=px(10), pady=(px(4), px(6)))
        self.rows = []
        for i, item in enumerate(items):
            row = tk.Frame(self.body, bg=SURFACE, height=px(self.ROW), width=px(self.WIDTH - 20))
            row.pack(fill="x")
            row.pack_propagate(False)
            parts = [row, label(row, str(i + 1) if i < 9 else "", "small", TEXT_3),
                     label(row, item["label"], "body", TEXT)]
            parts[1].pack(side="left", padx=(px(12), px(10)))
            parts[2].pack(side="left")
            if self.submenu(item):
                arrow = label(row, "›", "body_b", TEXT_3)
                arrow.pack(side="right", padx=px(12))
                parts.append(arrow)
            for w in parts:
                w.bind("<Button-1>", lambda e, i=i: self.choose(i))
                w.bind("<Enter>", lambda e, i=i: self._hover(i))
            self.rows.append(parts)
        hint = "1–9 or ↑↓ Enter  ·  " + ("← back  ·  " if len(self.stack) > 1 else "") + "Esc close"
        label(self.body, hint, "caption", TEXT_3).pack(fill="x", padx=px(10), pady=(px(8), px(4)))
        self._paint()
        self._fit()

    def _paint(self):
        for i, parts in enumerate(self.rows):
            bg = K.ACCENT_SOFT if i == self.index else SURFACE
            for w in parts:
                w.configure(bg=bg)

    def _hover(self, i):
        if i != self.index:
            self.index = i
            self._paint()

    def move(self, step):
        if self.rows:
            self.index = (self.index + step) % len(self.rows)
            self._paint()

    def present(self, anchor=None):
        self._anchor = anchor or caret_point()
        self._fit()
        self.win.deiconify()
        self.win.lift()
        force_foreground(_frame(self.win))
        self.win.focus_force()

    def _fit(self):
        if not self.alive:
            return
        self.win.update_idletasks()
        bw = px(self.WIDTH)
        bh = self.body.winfo_reqheight() + px(20)
        self.canvas.itemconfigure("body", width=bw - px(20))
        self.canvas.configure(width=bw, height=bh)
        draw_round_rect(self.canvas, 0, 0, bw, bh, px(12), SURFACE, outline=BORDER_STRONG, bg=_KEY, tag="bg")
        x, y, exact = getattr(self, "_anchor", None) or caret_point()
        left, top, right, bottom = work_area(x, y)
        gx = min(max(left + px(8), x - px(24)), right - bw - px(8))
        gy = y + px(10) if exact else y + px(22)
        if gy + bh > bottom - px(8):
            gy = max(top + px(8), y - bh - px(34))
        self.win.geometry(f"{bw}x{bh}+{gx}+{gy}")

    def _focus_lost(self):
        # A click in another window closes the menu (only once it had focus).
        if self.alive and self._armed and self.win.focus_get() is None:
            self.cancel()

    def choose(self, i):
        if not self.alive:
            return
        items = self.stack[-1][1]
        if not 0 <= i < len(items):
            return
        sub = self.submenu(items[i])
        if sub:
            self.stack.append((items[i]["label"].rstrip("…"), sub))
            self.index = 0
            self._render()
            return
        self._close()
        self.on_choice(items[i])

    def back(self):
        if not self.alive:
            return
        if len(self.stack) > 1:
            self.stack.pop()
            self.index = 0
            self._render()
        else:
            self.cancel()

    def cancel(self):
        if not self.alive:
            return
        self._close()
        self.on_choice(None)

    def _close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
