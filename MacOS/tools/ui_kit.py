"""
Fixelect UI kit — theme, DPI scaling and components shared by Windows and macOS.

Design goals:
  * One calm graphite palette with the brand blue / coral as the only accents.
  * Every pixel dimension goes through px(), so layouts stay proportional on
    125-200 % Windows scaling (fonts scale automatically; fixed-pixel widgets
    used to clip their own labels on high-DPI laptops).
  * Rounded shapes are supersampled with Pillow on Windows (Tk's canvas does
    not anti-alias there) and drawn as smooth vector polygons on macOS, where
    Tk renders through CoreGraphics and stays sharp on Retina displays.
"""

import sys
import tkinter as tk
import tkinter.font as tkfont

from PIL import Image, ImageDraw, ImageTk

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

BG = "#0B0D12"
SURFACE = "#12151C"
SURFACE_2 = "#181C25"
SURFACE_3 = "#1F2430"
SURFACE_4 = "#272D3B"
FIELD = "#0E1117"
BORDER = "#222835"
BORDER_STRONG = "#303849"
TEXT = "#ECEEF2"
TEXT_2 = "#A3AAB8"
TEXT_3 = "#687084"
ACCENT = "#3D7BFF"
ACCENT_HOVER = "#5A8FFF"
ACCENT_PRESS = "#2F66E0"
ACCENT_SOFT = "#15203A"
CORAL = "#FF5A6E"
CORAL_HOVER = "#FF7486"
CORAL_PRESS = "#E54A5E"
CORAL_SOFT = "#2A1519"
GREEN = "#34D399"
GREEN_SOFT = "#0F2A22"
AMBER = "#FBBF24"
AMBER_SOFT = "#2B230F"
RED = "#F87171"
RED_SOFT = "#2C1416"

# ---------------------------------------------------------------------------
# Scaling & fonts
# ---------------------------------------------------------------------------

_S = 1.0
FONTS = {}
_ready = False


def px(v):
    return int(round(v * _S))


def init(root):
    """Compute the DPI scale and pick fonts. Call once per Tk interpreter."""
    global _S, _ready
    if IS_WIN:
        try:
            _S = max(1.0, root.winfo_fpixels("1i") / 96.0)
        except Exception:
            _S = 1.0
    else:
        _S = 1.0
    fams = set(tkfont.families(root))

    def pick(*names):
        for n in names:
            if n in fams:
                return n
        return names[-1]

    if IS_MAC:
        ui = pick(".AppleSystemUIFont", "SF Pro Text", "Helvetica Neue", "Helvetica")
        semi, mono, k = ui, pick("SF Mono", "Menlo"), 1.3
        wb = "bold"
    else:
        ui = pick("Segoe UI Variable Text", "Segoe UI")
        semi = pick("Segoe UI Semibold", ui)
        mono = pick("Cascadia Mono", "Consolas")
        k = 1.0
        wb = "normal" if semi != ui else "bold"

    def f(fam, size, weight="normal"):
        return (fam, int(round(size * k)), weight)

    FONTS.update(
        display=f(semi, 17, wb),
        title=f(semi, 12, wb),
        body=f(ui, 10),
        body_b=f(semi, 10, wb),
        small=f(ui, 9),
        small_b=f(semi, 9, wb),
        caption=f(ui, 8),
        key=f(semi, 9, wb),
        mono=f(mono, 9),
    )
    root.option_add("*Font", FONTS["body"])
    _ready = True


def measure(font, text):
    try:
        return tkfont.Font(font=font).measure(text)
    except Exception:
        return len(text) * 7


def line_height(font):
    try:
        return tkfont.Font(font=font).metrics("linespace")
    except Exception:
        return 16


# ---------------------------------------------------------------------------
# Rounded shapes
# ---------------------------------------------------------------------------

def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _image_cache(widget):
    root = widget._root()
    cache = getattr(root, "_fx_images", None)
    if cache is None:
        cache = {}
        root._fx_images = cache
    if len(cache) > 400:
        cache.clear()
    return cache


def draw_round_rect(canvas, x, y, w, h, r, fill, outline=None, width=1, tag="shape", bg=None):
    """Draw an anti-aliased rounded rectangle onto `canvas` under `tag`."""
    canvas.delete(tag)
    if w < 2 or h < 2:
        return
    r = max(0, min(r, w // 2, h // 2))
    if IS_WIN:
        bg = bg or canvas.cget("bg")
        key = ("rr", w, h, r, fill, outline, width, bg)
        cache = _image_cache(canvas)
        photo = cache.get(key)
        if photo is None:
            ss = 4
            img = Image.new("RGB", (w * ss, h * ss), _hex(bg))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle(
                [0, 0, w * ss - 1, h * ss - 1], radius=r * ss, fill=_hex(fill),
                outline=_hex(outline) if outline else None, width=width * ss if outline else 0,
            )
            photo = ImageTk.PhotoImage(img.resize((w, h), Image.Resampling.LANCZOS), master=canvas)
            cache[key] = photo
        canvas.create_image(x, y, image=photo, anchor="nw", tags=tag)
    else:
        x2, y2 = x + w, y + h
        pts = [x + r, y, x2 - r, y, x2, y, x2, y + r, x2, y2 - r, x2, y2,
               x2 - r, y2, x + r, y2, x, y2, x, y2 - r, x, y + r, x, y]
        canvas.create_polygon(pts, smooth=True, fill=fill, outline=outline or fill,
                              width=width if outline else 0, tags=tag)
    canvas.tag_lower(tag)


_VK_EVENTS = {67: "<<Copy>>", 86: "<<Paste>>", 88: "<<Cut>>"}


def layout_independent_shortcuts(widget):
    """Make Ctrl+C/V/X/A work in Tk text fields under non-Latin keyboard layouts.

    Tk matches shortcuts by keysym, so with a Cyrillic (or Greek, Arabic...)
    layout Ctrl+V produces no <<Paste>> at all. Native apps match the virtual
    key code instead; on Windows Tk's `keycode` is that VK, so do the same."""
    if not IS_WIN:
        return

    def on_key(e):
        if e.keysym.lower() in ("c", "v", "x", "a"):
            return None  # Latin layout: Tk's own bindings already handle it
        if e.keycode in _VK_EVENTS:
            e.widget.event_generate(_VK_EVENTS[e.keycode])
            return "break"
        if e.keycode == 65:  # A
            if isinstance(e.widget, tk.Text):
                e.widget.tag_add("sel", "1.0", "end-1c")
            else:
                e.widget.select_range(0, "end")
            return "break"
        return None

    widget.bind("<Control-KeyPress>", on_key, add="+")


def bind_tree(widget, sequence, func, marker=None):
    """Bind `func` on a widget and all descendants. With `marker`, widgets that
    already carry it are skipped, so re-binding after a rebuild never stacks."""
    if marker is None or not getattr(widget, marker, False):
        widget.bind(sequence, func, add="+")
    for child in widget.winfo_children():
        bind_tree(child, sequence, func, marker)


def recolor_tree(widget, old, new):
    for child in widget.winfo_children():
        try:
            if child.cget("bg") == old:
                child.configure(bg=new)
        except tk.TclError:
            pass
        if isinstance(child, (Card, Button, Pill, Toggle)):
            if hasattr(child, "set_parent_bg"):
                child.set_parent_bg(new)
            continue
        recolor_tree(child, old, new)


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

class Card(tk.Canvas):
    """Rounded surface whose content goes into `card.body` (a normal Frame)."""

    def __init__(self, parent, fill=SURFACE, border=BORDER, radius=12, pad=16,
                 padx=None, pady=None, command=None, hover_fill=None, fit_width=False):
        self.parent_bg = parent.cget("bg")
        super().__init__(parent, bg=self.parent_bg, highlightthickness=0, bd=0, height=px(40))
        self.fill, self.border, self.radius = fill, border, px(radius)
        self.padx = px(pad if padx is None else padx)
        self.pady = px(pad if pady is None else pady)
        self.hover_fill = hover_fill
        self.fit_width = fit_width
        self.command = command
        self._hover = False
        self.body = tk.Frame(self, bg=fill)
        self._win = self.create_window(self.padx, self.pady, window=self.body, anchor="nw")
        self.bind("<Configure>", self._on_canvas)
        self.body.bind("<Configure>", self._on_body)
        if command:
            self.after_idle(self._make_clickable)

    def _make_clickable(self):
        def click(_e):
            if self.command:
                self.command()
        m = f"_fx_card_{id(self)}"
        bind_tree(self, "<Button-1>", click, m)
        bind_tree(self, "<Enter>", lambda e: self._set_hover(True), m)
        bind_tree(self, "<Leave>", lambda e: self.after(15, self._check_leave), m)

        def mark(w):
            setattr(w, m, True)
            try:
                if not isinstance(w, (tk.Entry, tk.Text)):
                    w.configure(cursor="hand2")
            except tk.TclError:
                pass
            for c in w.winfo_children():
                mark(c)
        mark(self)

    def rebind(self):
        if self.command:
            self._make_clickable()

    def _check_leave(self):
        try:
            x, y = self.winfo_pointerxy()
            inside = (self.winfo_rootx() <= x < self.winfo_rootx() + self.winfo_width()
                      and self.winfo_rooty() <= y < self.winfo_rooty() + self.winfo_height())
        except tk.TclError:
            return
        if not inside:
            self._set_hover(False)

    def _set_hover(self, flag):
        if self._hover == flag or not self.hover_fill:
            return
        self._hover = flag
        self._apply_fill(self.hover_fill if flag else self.fill)

    def _apply_fill(self, fill):
        old = self.body.cget("bg")
        if old != fill:
            self.body.configure(bg=fill)
            recolor_tree(self.body, old, fill)
        self._redraw(fill=fill)

    def set_style(self, fill=None, border=None):
        if fill is not None:
            self.fill = fill
        if border is not None:
            self.border = border
        self._apply_fill(self.hover_fill if (self._hover and self.hover_fill) else self.fill)

    def set_parent_bg(self, color):
        self.parent_bg = color
        self.configure(bg=color)
        self._redraw()

    def _on_canvas(self, e):
        self.itemconfigure(self._win, width=max(1, e.width - 2 * self.padx))
        self._redraw()

    def _on_body(self, _e):
        h = self.body.winfo_reqheight() + 2 * self.pady
        if int(float(self.cget("height"))) != h:
            self.configure(height=h)
        if self.fit_width:
            w = self.body.winfo_reqwidth() + 2 * self.padx
            if int(float(self.cget("width"))) != w:
                self.configure(width=w)
        self._redraw()

    def _redraw(self, fill=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        draw_round_rect(self, 0, 0, w, h, self.radius, fill or self.body.cget("bg"),
                        outline=self.border, bg=self.parent_bg)


_VARIANTS = {
    #            fill,       hover,        press,        text,     outline
    "primary":   (ACCENT,    ACCENT_HOVER, ACCENT_PRESS, "#FFFFFF", None),
    "coral":     (CORAL,     CORAL_HOVER,  CORAL_PRESS,  "#FFFFFF", None),
    "secondary": (SURFACE_3, SURFACE_4,    SURFACE_2,    TEXT,      BORDER_STRONG),
    "ghost":     (None,      SURFACE_3,    SURFACE_2,    TEXT_2,    None),
    "tab":       (None,      SURFACE_2,    SURFACE_3,    TEXT_2,    None),
    "tab_on":    (SURFACE_3, SURFACE_3,    SURFACE_3,    TEXT,      None),
    "danger":    (None,      RED_SOFT,     RED_SOFT,     RED,       None),
}


class Button(tk.Canvas):
    def __init__(self, parent, text="", command=None, variant="primary", width=None,
                 height=34, radius=9, font=None, padx=16):
        self.parent_bg = parent.cget("bg")
        self.font = font or FONTS["body_b"]
        self.text, self.command, self.variant = text, command, variant
        self._auto_w = width is None
        self._padx = px(padx)
        self._bw = self._text_width() if width is None else px(width)
        self._bh = px(height)
        self._r = px(radius)
        self._state = "normal"
        self._pressed = False
        self._hover = False
        self._focus = False
        super().__init__(parent, width=self._bw, height=self._bh, bg=self.parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=1)
        self._text_id = self.create_text(self._bw // 2, self._bh // 2, text=text, font=self.font)
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False, pressed=False))
        self.bind("<ButtonPress-1>", lambda e: self._set(pressed=True))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda e: self._set(focus=True))
        self.bind("<FocusOut>", lambda e: self._set(focus=False))
        self.bind("<Return>", lambda e: self.invoke())
        self.bind("<space>", lambda e: self.invoke())
        self._draw()

    def _text_width(self):
        return measure(self.font, self.text) + 2 * self._padx

    def _release(self, e):
        was = self._pressed
        self._set(pressed=False)
        if was and 0 <= e.x <= self._bw and 0 <= e.y <= self._bh:
            self.invoke()

    def invoke(self):
        if self._state == "normal" and self.command:
            self.command()

    def _set(self, **kw):
        for k, v in kw.items():
            setattr(self, "_" + k, v)
        self._draw()

    def _draw(self):
        fill, hover, press, fg, outline = _VARIANTS[self.variant]
        base = fill or self.parent_bg
        if self._state == "disabled":
            color, fg, outline = (SURFACE_2 if fill else self.parent_bg), TEXT_3, None
        elif self._pressed:
            color = press
        elif self._hover:
            color = hover
        else:
            color = base
        if self._focus and self._state == "normal":
            outline = ACCENT_HOVER
        draw_round_rect(self, 0, 0, self._bw, self._bh, self._r, color, outline=outline, bg=self.parent_bg)
        self.itemconfigure(self._text_id, text=self.text, fill=fg, font=self.font)
        self.coords(self._text_id, self._bw // 2, self._bh // 2)
        self.tag_raise(self._text_id)

    def set_text(self, text):
        self.text = text
        if self._auto_w:
            self._bw = self._text_width()
            self.configure(width=self._bw)
        self._draw()

    def set_variant(self, variant):
        self.variant = variant
        self._draw()

    def set_state(self, state):
        self._state = "disabled" if state in ("disabled", tk.DISABLED) else "normal"
        self.configure(cursor="arrow" if self._state == "disabled" else "hand2")
        self._draw()

    def set_parent_bg(self, color):
        self.parent_bg = color
        self.configure(bg=color)
        self._draw()


class Pill(tk.Canvas):
    """Small rounded label: status, sizes, tags, key caps."""

    def __init__(self, parent, text="", fg=TEXT_2, fill=SURFACE_3, border=None,
                 height=22, font=None, padx=9, radius=None, dot=None):
        self.parent_bg = parent.cget("bg")
        self.font = font or FONTS["small_b"]
        self._bh, self._padx = px(height), px(padx)
        self._r = px(radius) if radius is not None else self._bh // 2
        super().__init__(parent, height=self._bh, width=10, bg=self.parent_bg, highlightthickness=0, bd=0)
        self._tid = self.create_text(0, self._bh // 2, anchor="w", font=self.font)
        self.set(text, fg, fill, border, dot)

    def set(self, text=None, fg=None, fill=None, border=None, dot=None):
        if text is not None:
            self.text = text
        if fg is not None:
            self.fg = fg
        if fill is not None:
            self.fill = fill
        self.border = border if border is not None else getattr(self, "border", None)
        self.dot = dot if dot is not None else getattr(self, "dot", None)
        dot_w = px(12) if self.dot else 0
        w = measure(self.font, self.text) + 2 * self._padx + dot_w
        self.configure(width=w)
        self._bw = w
        draw_round_rect(self, 0, 0, w, self._bh, self._r, self.fill, outline=self.border, bg=self.parent_bg)
        self.delete("dot")
        if self.dot:
            d = px(6)
            cx, cy = self._padx + d // 2, self._bh // 2
            self.create_oval(cx - d // 2, cy - d // 2, cx + d // 2, cy + d // 2,
                             fill=self.dot, outline=self.dot, tags="dot")
        self.coords(self._tid, self._padx + dot_w, self._bh // 2)
        self.itemconfigure(self._tid, text=self.text, fill=self.fg)
        self.tag_raise(self._tid)

    def set_parent_bg(self, color):
        self.parent_bg = color
        self.configure(bg=color)
        self.set()


def keycaps(parent, keys, bg=None):
    """A row of key-cap pills, e.g. ["Ctrl", "Alt", "F"]."""
    row = tk.Frame(parent, bg=bg or parent.cget("bg"))
    for i, k in enumerate(keys):
        if i:
            tk.Label(row, text="+" if keys[i - 1] != k else "", fg=TEXT_3, bg=row.cget("bg"),
                     font=FONTS["small"]).pack(side="left", padx=px(2))
        Pill(row, k, fg=TEXT, fill=SURFACE_4, border=BORDER_STRONG, height=24,
             font=FONTS["key"], padx=8, radius=6).pack(side="left")
    return row


class Toggle(tk.Canvas):
    """iOS-style switch bound to a BooleanVar."""

    def __init__(self, parent, variable, command=None):
        self.parent_bg = parent.cget("bg")
        self.var, self.command = variable, command
        self._bw, self._bh = px(38), px(22)
        super().__init__(parent, width=self._bw, height=self._bh, bg=self.parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=1)
        self._pos = 1.0 if variable.get() else 0.0
        self.bind("<Button-1>", lambda e: self.toggle())
        self.bind("<space>", lambda e: self.toggle())
        self._draw()

    def toggle(self):
        self.var.set(not self.var.get())
        self._animate(1.0 if self.var.get() else 0.0)
        if self.command:
            self.command()

    def _animate(self, target, steps=6):
        start = self._pos

        def step(i):
            self._pos = start + (target - start) * (i / steps)
            self._draw()
            if i < steps:
                self.after(12, step, i + 1)
        step(1)

    def _draw(self):
        on = self._pos > 0.5
        track = ACCENT if on else SURFACE_4
        draw_round_rect(self, 0, 0, self._bw, self._bh, self._bh // 2, track, bg=self.parent_bg)
        self.delete("knob")
        m = px(3)
        d = self._bh - 2 * m
        x = m + (self._bw - 2 * m - d) * self._pos
        self.create_oval(x, m, x + d, m + d, fill="#FFFFFF", outline="#FFFFFF", tags="knob")

    def set_parent_bg(self, color):
        self.parent_bg = color
        self.configure(bg=color)
        self._draw()


class ProgressBar(tk.Canvas):
    def __init__(self, parent, height=6, color=ACCENT):
        self.parent_bg = parent.cget("bg")
        self._bh, self.color, self.frac = px(height), color, 0.0
        super().__init__(parent, height=self._bh, bg=self.parent_bg, highlightthickness=0, bd=0)
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, frac):
        self.frac = max(0.0, min(1.0, frac))
        self._draw()

    def _draw(self):
        w = self.winfo_width()
        if w < 4:
            return
        draw_round_rect(self, 0, 0, w, self._bh, self._bh // 2, SURFACE_4, tag="track", bg=self.parent_bg)
        fw = int(w * self.frac)
        self.delete("fill")
        if fw >= self._bh:
            draw_round_rect(self, 0, 0, fw, self._bh, self._bh // 2, self.color, tag="fill", bg=SURFACE_4)
            self.tag_raise("fill")


class TextBox(Card):
    """Multi-line text field on a rounded surface, with an accent focus ring."""

    def __init__(self, parent, height=4, readonly=False, placeholder=""):
        super().__init__(parent, fill=FIELD, border=BORDER, radius=10, padx=12, pady=10)
        self.readonly, self.placeholder = readonly, placeholder
        self.text = tk.Text(
            self.body, height=height, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
            bd=0, highlightthickness=0, wrap="word", font=FONTS["body"], padx=0, pady=0,
            selectbackground=ACCENT_PRESS, selectforeground="#FFFFFF", undo=not readonly,
            spacing1=px(1), spacing3=px(1), cursor="xterm",
        )
        self.text.pack(fill="both", expand=True)
        layout_independent_shortcuts(self.text)
        self.text.tag_configure("placeholder", foreground=TEXT_3)
        self.text.tag_configure("changed", foreground=GREEN)
        self.text.bind("<FocusIn>", lambda e: self.set_style(border=ACCENT))
        self.text.bind("<FocusOut>", lambda e: self.set_style(border=BORDER))
        if readonly:
            self.text.configure(state="disabled", cursor="arrow")
        self.show_placeholder()

    def get(self):
        if self.text.tag_ranges("placeholder"):
            return ""
        return self.text.get("1.0", "end-1c")

    def set(self, value, highlight_words=None):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if highlight_words is None:
            self.text.insert("1.0", value)
        else:
            for chunk, changed in highlight_words:
                self.text.insert("end", chunk, ("changed",) if changed else ())
        if self.readonly:
            self.text.configure(state="disabled")

    def show_placeholder(self):
        if self.placeholder and not self.get().strip():
            self.set("")
            self.text.configure(state="normal")
            self.text.insert("1.0", self.placeholder, ("placeholder",))
            if self.readonly:
                self.text.configure(state="disabled")


class ShortcutRecorder(Button):
    """Click, press a key combination, done. Esc cancels."""

    _MODS = {
        "Control_L": "Ctrl", "Control_R": "Ctrl",
        "Alt_L": "Option" if IS_MAC else "Alt", "Alt_R": "Option" if IS_MAC else "Alt",
        "Option_L": "Option", "Option_R": "Option",
        "Shift_L": "Shift", "Shift_R": "Shift",
        "Win_L": "Win", "Win_R": "Win", "Super_L": "Win", "Super_R": "Win",
        "Meta_L": "Cmd", "Meta_R": "Cmd", "Command": "Cmd",
    }
    _ORDER = ["Ctrl", "Alt", "Option", "Shift", "Win", "Cmd"]

    def __init__(self, parent, value, on_record, on_start=None, on_end=None, width=190):
        self.value, self.on_record = value, on_record
        self.on_start, self.on_end = on_start, on_end
        self._recording = False
        self._held = set()
        super().__init__(parent, text=self._pretty(value), command=self._begin,
                         variant="secondary", width=width, height=32, font=FONTS["key"])
        self.bind("<KeyPress>", self._key_down)
        self.bind("<KeyRelease>", self._key_up)
        self.bind("<FocusOut>", lambda e: self._end(None), add="+")

    @staticmethod
    def _pretty(combo):
        return "  +  ".join(p.strip() for p in (combo or "").split("+") if p.strip()) or "Click to record"

    def _begin(self):
        if self._recording:
            return
        self._recording = True
        self._held.clear()
        if self.on_start:
            self.on_start()
        self.set_variant("primary")
        self.set_text("Press shortcut…  (Esc to cancel)")
        self.focus_set()

    def _end(self, combo):
        if not self._recording:
            return
        self._recording = False
        self._held.clear()
        self.set_variant("secondary")
        if combo:
            self.value = combo
        self.set_text(self._pretty(self.value))
        if self.on_end:
            self.on_end()
        if combo:
            self.on_record(combo)

    def _key_down(self, e):
        if not self._recording:
            return None
        sym = e.keysym
        if sym in self._MODS:
            self._held.add(self._MODS[sym])
            live = [m for m in self._ORDER if m in self._held]
            self.set_text("  +  ".join(live) + "  + …")
            return "break"
        if sym == "Escape":
            self._end(None)
            return "break"
        key = None
        if len(sym) == 1 and sym.isalnum():
            key = sym.upper()
        elif sym.lower() == "space":
            key = "Space"
        elif sym.upper().startswith("F") and sym[1:].isdigit() and 1 <= int(sym[1:]) <= 12:
            key = sym.upper()
        if key:
            mods = [m for m in self._ORDER if m in self._held]
            self._end("+".join(mods + [key]))
        return "break"

    def _key_up(self, e):
        if self._recording and e.keysym in self._MODS:
            self._held.discard(self._MODS[e.keysym])
        return "break" if self._recording else None


class ScrollArea(tk.Frame):
    """Vertical scroll container with smooth wheel/touchpad scrolling and a draggable thumb.

    The wheel handler is bound once on the toplevel (every descendant carries
    the toplevel in its bindtags) and scrolls only when the pointer is over this
    area. The old Enter/Leave toggling unbound the wheel whenever the pointer
    moved from the list onto a card, so scrolling worked only in the gaps.
    """

    STEP = 64          # px per wheel notch
    EASE = 0.28        # fraction of the remaining distance covered per frame
    FRAME_MS = 12

    def __init__(self, parent, height):
        bg = parent.cget("bg")
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, height=px(height),
                                yscrollincrement=1)
        self.bar = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, width=px(6), cursor="hand2")
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._win = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.bar.pack(side="right", fill="y", padx=(px(6), 0))
        self.canvas.bind("<Configure>", self._resize)
        self.inner.bind("<Configure>", lambda e: self._update())
        self.canvas.configure(yscrollcommand=lambda a, b: self._thumb(float(a), float(b)))
        self.bar.bind("<ButtonPress-1>", self._drag_start)
        self.bar.bind("<B1-Motion>", self._drag)
        self._target = None
        self._animating = False
        self._frac = 0.0     # a touchpad sends many tiny deltas; keep the remainder
        self._drag_from = None
        top = self.winfo_toplevel()
        self._bindings = [
            (seq, top.bind(seq, self._on_wheel, add="+"))
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>")
        ]
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, e):
        if e.widget is not self:
            return
        top = self.winfo_toplevel()
        for seq, funcid in self._bindings:
            try:
                top.unbind(seq, funcid)
            except tk.TclError:
                pass

    # -- geometry ------------------------------------------------------------

    def _resize(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        self._update()

    def _update(self):
        self.canvas.configure(scrollregion=(0, 0, self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()))

    def _content_h(self):
        return self.inner.winfo_reqheight()

    def _max_y(self):
        return max(0, self._content_h() - self.canvas.winfo_height())

    def _top(self):
        return self.canvas.canvasy(0)

    def _scroll_to(self, y):
        h = self._content_h()
        if h > 0:
            self.canvas.yview_moveto(max(0.0, min(y, self._max_y())) / h)

    def _thumb(self, a, b):
        self.bar.delete("all")
        if b - a >= 0.999:
            return
        h = self.bar.winfo_height()
        y1, y2 = int(a * h), max(int(a * h) + px(24), int(b * h))
        draw_round_rect(self.bar, 0, y1, px(6), y2 - y1, px(3), SURFACE_4, tag="thumb")

    # -- wheel ---------------------------------------------------------------

    def _pointer_inside(self, e):
        try:
            x, y = e.x_root, e.y_root
            cx, cy = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
            return (cx <= x < cx + self.canvas.winfo_width() + self.bar.winfo_width() + px(6)
                    and cy <= y < cy + self.canvas.winfo_height())
        except tk.TclError:
            return False

    def _on_wheel(self, e):
        if not self.winfo_exists() or not self.winfo_ismapped() or not self._pointer_inside(e):
            return None
        if self._max_y() <= 0:
            return "break"
        if e.num == 4:
            notches = 1.0
        elif e.num == 5:
            notches = -1.0
        elif IS_MAC:
            notches = e.delta / 3.0     # Tk on macOS reports small, already-scaled deltas
        else:
            notches = e.delta / 120.0   # precision touchpads send fractions of a notch
        self._frac += -notches * px(self.STEP)
        step, self._frac = int(self._frac), self._frac - int(self._frac)
        if step:
            base = self._target if self._target is not None else self._top()
            self._target = max(0, min(base + step, self._max_y()))
            if not self._animating:
                self._animating = True
                self._animate()
        return "break"

    def _animate(self):
        if self._target is None or not self.winfo_exists():
            self._animating = False
            return
        cur = self._top()
        diff = self._target - cur
        if abs(diff) < 1:
            self._scroll_to(self._target)
            self._target = None
            self._animating = False
            return
        move = diff * self.EASE
        if abs(move) < 1:
            move = 1 if diff > 0 else -1
        self._scroll_to(cur + move)
        self.after(self.FRAME_MS, self._animate)

    # -- thumb drag ------------------------------------------------------------

    def _drag_start(self, e):
        self._target = None
        self._drag_from = (e.y, self._top())

    def _drag(self, e):
        if not self._drag_from or self.bar.winfo_height() <= 0:
            return
        y0, top0 = self._drag_from
        ratio = self._content_h() / self.bar.winfo_height()
        self._scroll_to(top0 + (e.y - y0) * ratio)


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------

def label(parent, text, font="body", fg=TEXT, wrap=None, **kw):
    return tk.Label(parent, text=text, font=FONTS[font], fg=fg, bg=parent.cget("bg"),
                    justify="left", anchor="w", wraplength=px(wrap) if wrap else 0, **kw)


def spacer(parent, h):
    f = tk.Frame(parent, bg=parent.cget("bg"), height=px(h))
    f.pack(fill="x")
    return f


def style_titlebar(win):
    """Dark, borderless-looking title bar that blends into the window (Windows 10/11)."""
    if not IS_WIN:
        return
    try:
        import ctypes
        win.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), 4) != 0:
            dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(on), 4)
        r, g, b = _hex(BG)
        caption = ctypes.c_int(r | (g << 8) | (b << 16))
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption), 4)  # caption colour (Win11)
        r, g, b = _hex(BORDER)
        border = ctypes.c_int(r | (g << 8) | (b << 16))
        dwm.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(border), 4)   # border colour (Win11)
    except Exception:
        pass


def center(win, w, h):
    win.update_idletasks()
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    h = min(h, sh - px(80))
    win.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 2 - px(20))}")


def activate(win):
    """Bring a window to the front, even when the app has no Dock/taskbar focus."""
    try:
        win.deiconify()
        win.lift()
        win.attributes("-topmost", True)
        win.after(250, lambda: win.attributes("-topmost", False))
        win.focus_force()
    except tk.TclError:
        return
    if IS_WIN:
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or win.winfo_id()
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass
    elif IS_MAC:
        try:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        except Exception:
            pass
