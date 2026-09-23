"""
Fixelect windows: Dashboard, first-run Setup + tutorial, macOS Permissions and Privacy.

Threading model
  * Windows: UIManager owns ONE long-lived Tk interpreter on a dedicated UI
    thread. Tray clicks, hotkeys and a second app launch only *post* requests
    to it, so no Tk call ever happens on a foreign thread. The on-screen status
    card and the Polish preview live on the same thread.
  * macOS: Cocoa requires UI on the main thread, so each window runs in its own
    short-lived process via run_standalone(); the menu-bar daemon never imports Tk.

This file is shared by both platforms (see shared/).
"""

import difflib
import os
import pathlib
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk

from PIL import Image, ImageTk

_tools_dir = pathlib.Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

import ui_kit as K  # noqa: E402
from ui_kit import (  # noqa: E402
    BG, SURFACE, SURFACE_2, SURFACE_3, FIELD, BORDER, TEXT, TEXT_2, TEXT_3, ACCENT, ACCENT_SOFT,
    CORAL, GREEN, GREEN_SOFT, AMBER, AMBER_SOFT, RED, RED_SOFT, IS_MAC, px,
    Button, Card, Pill, Toggle, ProgressBar, TextBox, ShortcutRecorder, ScrollArea, Segmented, Chips,
    keycaps, label, spacer, style_titlebar, center, activate,
)
from version import APP_VERSION, RELEASES_URL  # noqa: E402

if IS_MAC:
    import config_mac as C
    import downloader_mac as D
    import hardware_mac as H
    import apps_mac as A
else:
    import config as C
    import downloader as D
    import hardware as H
    import apps_win as A

MOD = "Cmd" if IS_MAC else "Ctrl"

PRESETS_WIN = [
    ("double_tap", "Double-tap", "Recommended", "Alt Alt to fix  ·  Ctrl Ctrl to polish"),
    ("alt_space", "Alt + Space", "", "Alt Space to fix  ·  Alt Shift Space to polish"),
    ("classic", "Classic", "", "Ctrl Alt F to fix  ·  Ctrl Alt P to polish"),
    ("custom", "Custom", "", "Record your own shortcuts"),
]
PRESETS_MAC = [
    ("double_tap", "Double-tap", "Recommended", "⌥ ⌥ to fix  ·  ⇧ ⇧ to polish"),
    ("option_space", "Option + Space", "", "⌥ Space to fix  ·  ⌥ ⇧ Space to polish"),
    ("classic", "Classic", "", "⌘ ⌥ F to fix  ·  ⌘ ⌥ P to polish"),
    ("custom", "Custom", "", "Record your own shortcuts"),
]

SAMPLE = "tobehonest its kinda really strannge an i dont know what s hapenning with teh project"
TUTORIAL_TEXT = "i dont know wher we shoud meet tomorow, can you send me the adress"
IDLE_OPTIONS = [(10, "10 min"), (30, "30 min"), (60, "1 hour"), (0, "Never")]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resource(*candidates):
    for c in candidates:
        p = C.get_resource_path(c)
        if p.is_file():
            return p
    return None


def _logo(height, master):
    path = _resource("resources/brand_logo.png", "resources/brand_logo_dashboard.png")
    if not path:
        return None
    try:
        img = Image.open(path).convert("RGBA")
        bbox = img.getbbox()
        if bbox:
            img = img.crop(bbox)
        w = int(img.width * height / img.height)
        return ImageTk.PhotoImage(img.resize((w, height), Image.Resampling.LANCZOS), master=master)
    except Exception:
        return None


def _set_default_icon(root):
    if IS_MAC:
        return
    ico = _resource("resources/app_icon.ico")
    if ico:
        try:
            root.iconbitmap(default=str(ico))
        except Exception:
            pass


def _open_path(path):
    try:
        if IS_MAC:
            subprocess.Popen(["open", str(path)])
        else:
            os.startfile(str(path))  # noqa: S606 - opens a folder or URL the app chose
    except Exception:
        pass


def diff_chunks(before, after):
    """Split `after` into (chunk, changed) runs so edits can be highlighted."""
    a = re.findall(r"\S+|\s+", before)
    b = re.findall(r"\S+|\s+", after)
    out = []
    for tag, _i1, _i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "delete":
            continue
        chunk = "".join(b[j1:j2])
        out.append((chunk, tag != "equal" and bool(chunk.strip())))
    return out


def _hw_line(hw):
    parts = [hw.get("gpu_name") or "CPU"]
    if hw.get("vram_gb") and not IS_MAC:
        parts.append(f"{hw['vram_gb']:g} GB VRAM")
    parts.append(f"{hw.get('ram_gb', 0):g} GB RAM")
    parts.append((hw.get("backend") or "cpu").upper())
    return "  ·  ".join(parts)


def _store_install():
    """Installed from the Microsoft Store: the Store handles updates."""
    if IS_MAC:
        return False
    try:
        import packaged
        return packaged.is_packaged()
    except Exception:
        return False


def _styles():
    from check_guard import POLISH_STYLES
    return POLISH_STYLES


class LocalServices:
    """Services for a window running without the daemon in-process
    (Windows `--dashboard`, every macOS window process)."""

    platform = "mac" if IS_MAC else "win"

    def __init__(self):
        self._fix = None
        self._lock = threading.Lock()
        self._state = {"state": "idle", "detail": "", "backend": "", "model": ""}
        self._update = None

    def fix(self, text, mode="fix", style=None):
        from check_guard import load_pipeline
        import chunking
        with self._lock:
            if self._fix is None:
                self._state.update(state="loading")
                try:
                    self._fix = load_pipeline("qwen2.5", fast=False, beams=1,
                                              engine_type=C.load_config().get("engine", "embedded"))
                except Exception as e:
                    self._state.update(state="error", detail=str(e))
                    raise
                self._state.update(state="ready", model=C.load_config().get("model_profile", ""))
            fn = self._fix
        cfg = C.load_config()
        opts = dict(style=style or cfg.get("polish_style", "professional"),
                    custom=cfg.get("custom_instruction", "") if mode == "polish" else "",
                    multilingual=bool(cfg.get("multilingual", True)))
        return chunking.process(text, lambda t: fn(t, mode=mode, **opts), mode=mode)

    def status(self):
        return dict(self._state)

    def quit(self):
        if IS_MAC:
            try:
                import signal
                pid = int((C.get_config_dir() / "fixelect.lock").read_text().strip() or 0)
                if pid and pid != os.getpid():
                    os.kill(pid, signal.SIGTERM)
            except Exception:
                pass

    def hotkeys_changed(self):
        pass  # the macOS daemon watches config.json

    def hotkey_errors(self):
        return []

    def suspend_hotkeys(self, flag):
        pass

    def model_changed(self, profile):
        pass

    def prefs_changed(self):
        pass

    def check_updates(self):
        import updater
        try:
            self._update = updater.check()
            C.update_config(last_update_check=time.time())
            return self._update, None
        except Exception:
            return None, "Couldn't reach GitHub. Check your connection and try again."

    def update_info(self):
        return self._update

    def install_update(self, info, progress, cancel):
        _open_path(info.get("url") or RELEASES_URL)
        return False

    def diagnostics(self):
        import diagnostics
        return diagnostics.report({"Window process": "standalone"})


# ---------------------------------------------------------------------------
# Window base
# ---------------------------------------------------------------------------

class _Window:
    def __init__(self, master, title, width, height, on_close=None):
        self.alive = True
        self._on_close_cb = on_close
        self.win = tk.Toplevel(master, bg=BG)
        self.win.withdraw()
        self.win.title(title)
        self.win.resizable(False, False)
        self._size = (px(width), px(height))
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Escape>", lambda e: self.close())

    def present(self):
        center(self.win, *self._size)
        self.win.deiconify()
        style_titlebar(self.win)
        activate(self.win)

    def after(self, ms, fn):
        if self.alive:
            try:
                self.win.after(ms, lambda: self.alive and fn())
            except tk.TclError:
                pass

    def close(self):
        if not self.alive:
            return
        self.alive = False
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        if self._on_close_cb:
            self._on_close_cb()


def _pref_row(parent, var, title, desc, command, first=False, bg=SURFACE):
    if not first:
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")
    r = tk.Frame(parent, bg=bg)
    r.pack(fill="x", pady=px(10))
    Toggle(r, var, command=command).pack(side="right", padx=(px(12), 0))
    txt = tk.Frame(r, bg=bg)
    txt.pack(side="left", fill="x", expand=True)
    label(txt, title, "body_b").pack(fill="x")
    if desc:
        label(txt, desc, "small", TEXT_2, wrap=440).pack(fill="x", pady=(px(2), 0))
    return r


def _radio(canvas, sel, size=16):
    canvas.delete("all")
    s, m = px(size), px(2)
    canvas.create_oval(m, m, s - m, s - m, outline=ACCENT if sel else K.BORDER_STRONG, width=px(2))
    if sel:
        i = px(size * 5 // 16)
        canvas.create_oval(i, i, s - i, s - i, fill=ACCENT, outline=ACCENT)


# ---------------------------------------------------------------------------
# Model picker (shared by Setup and the Model tab)
# ---------------------------------------------------------------------------

class ModelPicker:
    def __init__(self, parent, window, services, list_height, setup_mode=False, on_ready=None):
        self.window, self.services = window, services
        self.setup_mode, self.on_ready = setup_mode, on_ready
        self.hw = H.detect_hardware()
        cfg = C.load_config()
        self.active = cfg.get("model_profile") or self.hw.get("recommended_model", "3b")
        if setup_mode and not D.resolve_model(self.active):
            self.active = self.hw.get("recommended_model", self.active)
        self.selected = self.active
        self.cancel_event = None
        self.rows = {}

        self.frame = tk.Frame(parent, bg=parent.cget("bg"))
        self.scroll = ScrollArea(self.frame, list_height)
        self.scroll.pack(fill="x")
        for key, spec in D.MODELS.items():
            self._build_row(key, spec)

        spacer(self.frame, 14)
        bar = tk.Frame(self.frame, bg=self.frame.cget("bg"))
        bar.pack(fill="x")
        self.action = Button(bar, "Download", self._on_action, width=210, height=38)
        self.action.pack(side="right")
        info = tk.Frame(bar, bg=bar.cget("bg"))
        info.pack(side="left", fill="x", expand=True, padx=(0, px(16)))
        self.info = label(info, "", "small", TEXT_2)
        self.info.pack(fill="x")
        self.progress = ProgressBar(info)
        self._refresh()

    def pack(self, **kw):
        self.frame.pack(**kw)

    def _build_row(self, key, spec):
        card = Card(self.scroll.inner, fill=SURFACE, border=BORDER, radius=12, padx=14, pady=12,
                    hover_fill=SURFACE_2, command=lambda k=key: self._select(k))
        card.pack(fill="x", pady=(0, px(8)))
        b = card.body
        b.grid_columnconfigure(1, weight=1)
        dot = tk.Canvas(b, width=px(18), height=px(18), bg=SURFACE, highlightthickness=0, bd=0)
        dot.grid(row=0, column=0, rowspan=2, sticky="n", padx=(0, px(12)), pady=(px(2), 0))
        label(b, spec["short_name"], "body_b").grid(row=0, column=1, sticky="w")
        label(b, spec.get("desc", ""), "small", TEXT_2, wrap=330).grid(row=1, column=1, sticky="w", pady=(px(2), 0))
        tags = tk.Frame(b, bg=SURFACE)
        tags.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(px(10), 0))
        self.rows[key] = {"card": card, "dot": dot, "tags": tags}

    def _select(self, key):
        if self.cancel_event is not None:
            return
        self.selected = key
        self._refresh()

    def _refresh(self):
        rec = self.hw.get("recommended_model")
        for key, row in self.rows.items():
            sel = key == self.selected
            row["card"].fill = ACCENT_SOFT if sel else SURFACE
            row["card"].hover_fill = ACCENT_SOFT if sel else SURFACE_2
            row["card"].set_style(border=ACCENT if sel else BORDER)
            _radio(row["dot"], sel, 18)
            for w in row["tags"].winfo_children():
                w.destroy()
            bg = row["tags"].cget("bg")
            spec = D.MODELS[key]
            items = [(spec.get("badge_size", ""), TEXT_2, SURFACE_3)]
            if key == rec:
                items.insert(0, ("Recommended", ACCENT, K.ACCENT_SOFT if bg != K.ACCENT_SOFT else SURFACE_3))
            if spec.get("tag"):
                items.insert(0, (spec["tag"], CORAL, K.CORAL_SOFT))
            if not self.setup_mode and key == self.active and D.resolve_model(key):
                items.insert(0, ("In use", GREEN, GREEN_SOFT))
            elif D.resolve_model(key):
                items.insert(0, ("Downloaded", TEXT_2, SURFACE_3))
            for text, fg, fill in items:
                Pill(row["tags"], text, fg=fg, fill=fill, height=22).pack(anchor="e", pady=(0, px(4)))
            row["card"].rebind()
        self._refresh_action()

    def _refresh_action(self):
        spec = D.MODELS[self.selected]
        on_disk = D.resolve_model(self.selected) is not None
        self.progress.pack_forget()
        if self.cancel_event is not None:
            self.action.set_text("Cancel")
            self.action.set_variant("secondary")
            self.action.set_state("normal")
            self.progress.pack(fill="x", pady=(px(6), 0))
            return
        self.action.set_variant("primary")
        self.action.set_state("normal")
        if not on_disk:
            self.action.set_text(f"Download  ·  {spec['badge_size']}")
            self.info.configure(text=f"{spec['short_name']} will be downloaded once and verified.", fg=TEXT_2)
        elif self.setup_mode:
            self.action.set_text("Start Fixelect")
            self.info.configure(text=f"{spec['short_name']} is ready on this computer.", fg=GREEN)
        elif self.selected == self.active:
            self.action.set_text("In use")
            self.action.set_state("disabled")
            self.info.configure(text="This model handles every fix and polish.", fg=TEXT_2)
        else:
            self.action.set_text("Use this model")
            self.info.configure(text="Switching takes a few seconds while the model loads.", fg=TEXT_2)

    def _on_action(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
            return
        if D.resolve_model(self.selected):
            self._use(self.selected)
        else:
            self._download(self.selected)

    def _use(self, key):
        C.update_config(model_profile=key)
        self.active = key
        if not self.setup_mode:
            self.services.model_changed(key)
        self._refresh()
        if self.on_ready:
            self.on_ready(key)

    def _download(self, key):
        self.cancel_event = threading.Event()
        cancel = self.cancel_event
        self.info.configure(text="Connecting…", fg=TEXT_2)
        self.progress.set(0)
        self._refresh_action()
        post = self.window.post

        def progress(done, total, speed):
            def upd():
                frac = done / total if total else 0
                eta = (total - done) / speed if speed else 0
                eta_s = f"{int(eta // 60)}m {int(eta % 60)}s left" if eta >= 60 else f"{int(eta)}s left"
                self.info.configure(text=f"{done / 1048576:,.0f} of {total / 1048576:,.0f} MB  ·  "
                                         f"{speed / 1048576:.1f} MB/s  ·  {eta_s}", fg=TEXT_2)
                self.progress.set(frac)
            post(upd)

        def work():
            try:
                D.download_model(profile=key, progress_callback=progress, cancel_event=cancel)
                post(lambda: self._download_done(key, None))
            except Exception as e:
                msg = "Download paused. Resume any time." if cancel.is_set() else str(e)
                post(lambda: self._download_done(key, msg))

        threading.Thread(target=work, daemon=True).start()

    def _download_done(self, key, error):
        self.cancel_event = None
        if not self.window.alive:
            # Settings was closed while the download ran on: still switch to the
            # model (refreshing the destroyed widgets failed before the switch).
            if not error and not self.setup_mode:
                C.update_config(model_profile=key)
                self.services.model_changed(key)
            return
        self._refresh()
        if error:
            self.info.configure(text=error, fg=RED if "paused" not in error else TEXT_2)
        else:
            self._use(key)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

HELP_ITEMS = [
    ("Nothing happened",
     "Select the text first, or put the cursor at the end of the line you typed. Some fields (passwords, some "
     "games and remote desktops) block copying, so Fixelect can't read them."),
    ("How do I get my original text back?",
     "Click Undo on the card, or press Ctrl+Z (⌘Z on a Mac) in your app. Later on, open History: every change "
     "is listed there with Copy original."),
    ("“Fixelect is off in this app”",
     "You (or the defaults) turned it off for that app. Remove the app under General → Turned off in."),
    ("It said “Looks good” but there is a mistake",
     "Fixelect only makes changes it is sure about and never rewrites correct words, names or code. "
     "Polish rewrites more freely — try the other shortcut."),
    ("A language isn't supported",
     "Fixelect fixes English, Spanish, French, German, Portuguese, Italian, Russian and Ukrainian. "
     "Uzbek (beta) works with the Gemma 4 model. Other languages are left unchanged on purpose."),
    ("How do I translate, or use my own actions?",
     "Select text and press the quick-action shortcut (double-tap Shift on Windows, ⌃⇧Space on a Mac; "
     "change it under Actions), then press a number: Translate… lists the languages. Add your own actions, "
     "like “Reply politely”, under Actions."),
    ("The shortcut doesn't work",
     "Another app may use the same keys. Pick a different preset in Shortcuts; the status line there shows conflicts."),
    ("The first fix after a break is slow",
     "Fixelect frees the model's memory when you haven't used it for a while. Change this under General."),
]


class Dashboard(_Window):
    TABS = ("Playground", "History", "Shortcuts", "Writing", "Actions", "Model", "General", "Help")

    def __init__(self, master, services, post, on_close=None, page=None):
        super().__init__(master, "Fixelect", 660, 700, on_close)
        self.services, self.post = services, post
        self.pages, self.tab_buttons = {}, {}
        self.current = None
        self._busy = False

        outer = tk.Frame(self.win, bg=BG, padx=px(26), pady=px(22))
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x")
        self._logo = _logo(px(26), self.win)
        if self._logo:
            tk.Label(header, image=self._logo, bg=BG).pack(side="left")
        else:
            label(header, "Fixelect", "display").pack(side="left")
        self.status_pill = Pill(header, "Starting…", fg=AMBER, fill=AMBER_SOFT, dot=AMBER, height=26)
        self.status_pill.pack(side="right")

        spacer(outer, 18)
        self.tabs_row = tk.Frame(outer, bg=BG)
        self.tabs_row.pack(fill="x")
        for name in self.TABS:
            b = Button(self.tabs_row, name, lambda n=name: self.show(n), variant="tab", height=32,
                       font=K.FONTS["body_b"], padx=11)
            b.pack(side="left", padx=(0, px(2)))
            self.tab_buttons[name] = b
        self.rule = tk.Frame(outer, bg=BORDER, height=1)
        self.rule.pack(fill="x", pady=(px(12), px(18)))

        self.content = tk.Frame(outer, bg=BG)
        self.content.pack(fill="both", expand=True)

        self.show(page if page in self.TABS or page == "Welcome" else "Playground")
        self._poll_status()
        self.present()

    def request_focus(self, page=None):
        if self.alive:
            if page:
                self.show(page)
            activate(self.win)

    # -- navigation -------------------------------------------------------------

    def show(self, name):
        if self.current == name:
            return
        if self.current:
            self.pages[self.current].pack_forget()
            if self.current in self.tab_buttons:
                self.tab_buttons[self.current].set_variant("tab")
        if name not in self.pages:
            page = tk.Frame(self.content, bg=BG)
            getattr(self, "_build_" + name.lower())(page)
            self.pages[name] = page
        elif name == "History":
            self._render_history()  # changes made since the tab was last open
        self.pages[name].pack(fill="both", expand=True)
        if name in self.tab_buttons:
            self.tab_buttons[name].set_variant("tab_on")
        self.current = name

    def _scroll_page(self, page, height=520):
        area = ScrollArea(page, height)
        area.pack(fill="both", expand=True)
        return area.inner

    def _poll_status(self):
        st = self.services.status() or {}
        state = st.get("state", "idle")
        model = D.MODELS.get(st.get("model") or C.load_config().get("model_profile", ""), {}).get("short_name", "")
        if state == "ready":
            text = "Ready" + (f"  ·  {model}" if model else "")
            self.status_pill.set(text, GREEN, GREEN_SOFT, dot=GREEN)
        elif state == "sleeping":
            self.status_pill.set("Resting  ·  wakes on use", TEXT_2, SURFACE_2, dot=GREEN)
        elif state == "busy":
            self.status_pill.set("Working…", ACCENT, K.ACCENT_SOFT, dot=ACCENT)
        elif state == "loading":
            self.status_pill.set("Loading model…", AMBER, AMBER_SOFT, dot=AMBER)
        elif state == "error":
            self.status_pill.set("Engine offline", RED, RED_SOFT, dot=RED)
        else:
            self.status_pill.set("On-device  ·  Private", TEXT_2, SURFACE_2, dot=GREEN)
        self.after(700, self._poll_status)

    # -- Welcome (interactive tutorial) --------------------------------------------

    def _build_welcome(self, page):
        fix_keys = C.get_hotkey_label("fix")
        pol_keys = C.get_hotkey_label("polish")
        label(page, "Let's try it once", "display").pack(fill="x")
        label(page, "Fixelect works in every app — here is a safe place to practise. Takes 20 seconds.",
              "body", TEXT_2, wrap=580).pack(fill="x", pady=(px(4), px(16)))

        self._tut_steps = []
        for n, (title, how) in enumerate((
            ("Fix the typos", f"Select all the text in the box ({MOD}+A), then press {fix_keys}."),
            ("Polish it", f"Select it again and press {pol_keys}. A preview opens — press Enter to replace."),
        ), 1):
            card = Card(page, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=12)
            card.pack(fill="x", pady=(0, px(8)))
            row = tk.Frame(card.body, bg=SURFACE)
            row.pack(fill="x")
            badge = Pill(row, str(n), fg=ACCENT, fill=K.ACCENT_SOFT, height=24)
            badge.pack(side="left", padx=(0, px(12)))
            txt = tk.Frame(row, bg=SURFACE)
            txt.pack(side="left", fill="x", expand=True)
            label(txt, title, "body_b").pack(fill="x")
            note = label(txt, how, "small", TEXT_2, wrap=500)
            note.pack(fill="x", pady=(px(2), 0))
            self._tut_steps.append((badge, note))

        self.tut_box = TextBox(page, height=4)
        self.tut_box.set(TUTORIAL_TEXT)
        self.tut_box.pack(fill="x", pady=(px(8), 0))
        self._tut_last = TUTORIAL_TEXT
        self._tut_stage = 0

        foot = tk.Frame(page, bg=BG)
        foot.pack(side="bottom", fill="x")
        Button(foot, "Skip", self._finish_tutorial, "ghost", height=36).pack(side="left")
        self.tut_done = Button(foot, "Start using Fixelect", self._finish_tutorial, "primary", height=36)
        self.tut_done.pack(side="right")
        self.tut_hint = label(foot, "", "small", TEXT_2)
        self.tut_hint.pack(side="right", padx=px(12))
        self._paint_tutorial()
        self.after(400, self._watch_tutorial)
        self.after(600, lambda: self.tut_box.text.focus_set())

    def _paint_tutorial(self):
        for i, (badge, _note) in enumerate(self._tut_steps):
            if i < self._tut_stage:
                badge.set("✓", GREEN, GREEN_SOFT)
            elif i == self._tut_stage:
                badge.set(str(i + 1), ACCENT, K.ACCENT_SOFT)
            else:
                badge.set(str(i + 1), TEXT_3, SURFACE_3)

    def _watch_tutorial(self):
        if self.current == "Welcome":
            now = self.tut_box.get()
            if now != self._tut_last and now.strip() and self._tut_stage < 2:
                self._tut_last = now
                self._tut_stage += 1
                self._paint_tutorial()
                self.tut_hint.configure(
                    text="Nice — fixed in place." if self._tut_stage == 1 else "Perfect. You're ready.", fg=GREEN)
        self.after(400, self._watch_tutorial)

    def _finish_tutorial(self):
        C.update_config(onboarding_done=True)
        self.show("Playground")

    # -- Playground ---------------------------------------------------------------

    def _build_playground(self, page):
        label(page, "Try it", "title").pack(fill="x")
        label(page, "Paste any text, then fix or polish it. Nothing leaves this computer.", "small",
              TEXT_2).pack(fill="x", pady=(px(3), px(12)))
        self.input = TextBox(page, height=6)
        self.input.set(SAMPLE)
        self.input.pack(fill="x")
        mod = "Command" if IS_MAC else "Control"
        self.input.text.bind(f"<{mod}-Return>", lambda e: (self._run("fix"), "break")[1])
        self.input.text.bind(f"<{mod}-Shift-Return>", lambda e: (self._run("polish"), "break")[1])

        row = tk.Frame(page, bg=BG)
        row.pack(fill="x", pady=px(12))
        self.btn_fix = Button(row, "Fix", lambda: self._run("fix"), "primary", width=110, height=36)
        self.btn_fix.pack(side="left")
        self.btn_pol = Button(row, "Polish", lambda: self._run("polish"), "coral", width=110, height=36)
        self.btn_pol.pack(side="left", padx=(px(8), 0))
        self.meta = label(row, f"{MOD}+Enter to fix  ·  {MOD}+Shift+Enter to polish", "small", TEXT_3)
        self.meta.pack(side="right")

        self.output = TextBox(page, height=8, readonly=True, placeholder="Your corrected text appears here.")
        self.output.pack(fill="x")
        foot = tk.Frame(page, bg=BG)
        foot.pack(fill="x", pady=(px(8), 0))
        self.changes = label(foot, "", "small", TEXT_3)
        self.changes.pack(side="left")
        self.btn_copy = Button(foot, "Copy result", self._copy, "ghost", height=30, font=K.FONTS["small_b"], padx=12)
        self.btn_copy.pack(side="right")
        self.btn_copy.set_state("disabled")

    def _run(self, mode):
        text = self.input.get().strip("\n")
        if self._busy or not text.strip():
            return
        self._busy = True
        for b in (self.btn_fix, self.btn_pol, self.btn_copy):
            b.set_state("disabled")
        style = _styles().get(C.load_config().get("polish_style", "professional"), {}).get("label", "")
        self.meta.configure(text="Working…" if mode == "fix" else f"Polishing ({style})…", fg=TEXT_2)
        started = time.time()

        def work():
            try:
                result, err = self.services.fix(text, mode), None
            except Exception as e:
                result, err = None, str(e) or type(e).__name__
            ms = (time.time() - started) * 1000
            self.post(lambda: self._show_result(text, result, err, ms, mode))

        threading.Thread(target=work, daemon=True).start()

    def _show_result(self, before, after, err, ms, mode):
        if not self.alive:
            return
        self._busy = False
        self.btn_fix.set_state("normal")
        self.btn_pol.set_state("normal")
        if err:
            self.output.set(err)
            self.output.text.configure(state="normal")
            self.output.text.tag_add("placeholder", "1.0", "end")
            self.output.text.configure(state="disabled")
            self.meta.configure(text="Couldn't reach the AI engine", fg=RED)
            self.changes.configure(text="")
            return
        chunks = diff_chunks(before, after)
        self.output.set(after, highlight_words=chunks)
        self.output.text.tag_configure("changed", foreground=GREEN if mode == "fix" else CORAL)
        n = sum(1 for _c, ch in chunks if ch)
        self.changes.configure(text="No changes needed" if n == 0 else f"{n} edit{'s' if n != 1 else ''} highlighted")
        self.meta.configure(text=f"{ms:,.0f} ms", fg=TEXT_3)
        self.btn_copy.set_state("normal")
        self._last_result = after

    def _copy(self):
        value = getattr(self, "_last_result", "")
        if value:
            self.win.clipboard_clear()
            self.win.clipboard_append(value)
            self.btn_copy.set_text("Copied")
            self.after(1200, lambda: self.btn_copy.set_text("Copy result"))

    # -- Shortcuts ------------------------------------------------------------------

    def _build_shortcuts(self, page):
        cfg = C.load_config()
        summary = tk.Frame(page, bg=BG)
        summary.pack(fill="x")
        summary.grid_columnconfigure(0, weight=1, uniform="s")
        summary.grid_columnconfigure(1, weight=1, uniform="s")
        self._summary = {}
        for col, (mode, title, desc, color) in enumerate((
            ("fix", "Fix", "Typos and grammar. Keeps your voice.", ACCENT),
            ("polish", "Polish", "Rewrites in your chosen style, with a preview.", CORAL),
        )):
            card = Card(summary, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=14)
            card.grid(row=0, column=col, sticky="ew", padx=(0, px(6)) if col == 0 else (px(6), 0))
            head = tk.Frame(card.body, bg=SURFACE)
            head.pack(fill="x")
            dot = tk.Canvas(head, width=px(8), height=px(8), bg=SURFACE, highlightthickness=0)
            dot.create_oval(0, 0, px(8), px(8), fill=color, outline=color)
            dot.pack(side="left", padx=(0, px(8)))
            label(head, title, "body_b").pack(side="left")
            holder = tk.Frame(card.body, bg=SURFACE)
            holder.pack(fill="x", pady=(px(10), px(8)))
            label(card.body, desc, "small", TEXT_2, wrap=240).pack(fill="x")
            self._summary[mode] = holder
        self._render_summary(cfg)

        label(page, "Trigger", "small_b", TEXT_2).pack(fill="x", pady=(px(20), px(8)))
        self.trigger = cfg.get("trigger_mode", "double_tap")
        self._options = {}
        for key, title, badge, sub in (PRESETS_MAC if IS_MAC else PRESETS_WIN):
            card = Card(page, fill=SURFACE, border=BORDER, radius=10, padx=14, pady=11,
                        hover_fill=SURFACE_2, command=lambda k=key: self._choose_trigger(k))
            card.pack(fill="x", pady=(0, px(6)))
            b = card.body
            dot = tk.Canvas(b, width=px(16), height=px(16), bg=SURFACE, highlightthickness=0, bd=0)
            dot.pack(side="left", padx=(0, px(12)))
            label(b, title, "body_b").pack(side="left")
            if badge:
                Pill(b, badge, fg=ACCENT, fill=K.ACCENT_SOFT, height=20, font=K.FONTS["caption"]).pack(side="left", padx=(px(8), 0))
            label(b, sub, "small", TEXT_2).pack(side="right")
            self._options[key] = (card, dot)

        self.custom_panel = tk.Frame(page, bg=BG)
        for mode, name in (("fix", "Fix"), ("polish", "Polish")):
            r = tk.Frame(self.custom_panel, bg=BG)
            r.pack(fill="x", pady=(px(4), 0))
            label(r, name, "body", TEXT_2, width=8).pack(side="left", padx=(px(30), 0))
            rec = ShortcutRecorder(
                r, cfg.get(f"custom_{mode}", ""), lambda combo, m=mode: self._save_custom(m, combo),
                on_start=lambda: self.services.suspend_hotkeys(True),
                on_end=lambda: self.services.suspend_hotkeys(False),
            )
            rec.pack(side="left")
        self.shortcut_status = label(page, "", "small", TEXT_2, wrap=580)
        self.shortcut_status.pack(fill="x", pady=(px(12), 0))
        note = "Quit from the menu bar icon." if IS_MAC else "Ctrl + Alt + Q quits Fixelect from anywhere."
        label(page, note, "caption", TEXT_3).pack(side="bottom", fill="x")
        self._paint_options()
        self.after(300, self._check_hotkeys)

    def _render_summary(self, cfg):
        for mode, holder in self._summary.items():
            for w in holder.winfo_children():
                w.destroy()
            keycaps(holder, C.get_hotkey_keycaps(mode, cfg)).pack(anchor="w")

    def _paint_options(self):
        for key, (card, dot) in self._options.items():
            sel = key == self.trigger
            card.fill = ACCENT_SOFT if sel else SURFACE
            card.hover_fill = ACCENT_SOFT if sel else SURFACE_2
            card.set_style(border=ACCENT if sel else BORDER)
            _radio(dot, sel)
        if self.trigger == "custom":
            self.custom_panel.pack(fill="x", after=self._options["custom"][0])
        else:
            self.custom_panel.pack_forget()

    def _choose_trigger(self, key):
        self.trigger = key
        cfg = C.update_config(trigger_mode=key)
        self._paint_options()
        self._apply_hotkeys(cfg)

    def _save_custom(self, mode, combo):
        validate = getattr(C, "validate_hotkey", lambda c: (True, ""))
        ok, msg = validate(combo)
        if not ok:
            self.shortcut_status.configure(text=msg, fg=RED)
            return
        cfg = C.update_config(**{f"custom_{mode}": combo, "trigger_mode": "custom"})
        self._apply_hotkeys(cfg)

    def _apply_hotkeys(self, cfg):
        self.services.hotkeys_changed()
        self._render_summary(cfg)
        self.shortcut_status.configure(text="Applying…", fg=TEXT_2)
        self.after(450, self._check_hotkeys)

    def _check_hotkeys(self):
        errors = self.services.hotkey_errors()
        if errors:
            self.shortcut_status.configure(text="  ".join(errors), fg=RED)
        else:
            self.shortcut_status.configure(text="✓  Shortcuts are active in every app.", fg=GREEN)

    # -- Writing ----------------------------------------------------------------------

    def _build_writing(self, page):
        body = self._scroll_page(page)
        cfg = C.load_config()
        label(body, "Polish style", "title").pack(fill="x")
        label(body, "How Polish rewrites your text. You can also switch styles in the preview.", "small",
              TEXT_2).pack(fill="x", pady=(px(3), px(10)))
        self._style = cfg.get("polish_style", "professional")
        self._style_cards = {}
        for key, spec in _styles().items():
            card = Card(body, fill=SURFACE, border=BORDER, radius=10, padx=14, pady=10,
                        hover_fill=SURFACE_2, command=lambda k=key: self._choose_style(k))
            card.pack(fill="x", pady=(0, px(6)))
            dot = tk.Canvas(card.body, width=px(16), height=px(16), bg=SURFACE, highlightthickness=0, bd=0)
            dot.pack(side="left", padx=(0, px(12)))
            label(card.body, spec["label"], "body_b").pack(side="left")
            label(card.body, spec["desc"], "small", TEXT_2).pack(side="right")
            self._style_cards[key] = (card, dot)
        self._paint_styles()

        note = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=14)
        note.pack(fill="x", pady=(px(10), 0))
        nhead = tk.Frame(note.body, bg=SURFACE)
        nhead.pack(fill="x")
        label(nhead, "Your style note", "body_b").pack(side="left")
        self.custom_status = label(nhead, "", "small", TEXT_3)
        self.custom_status.pack(side="right")
        label(note.body, "Optional. Applied to every polish, e.g. “Use British spelling” or “Keep it upbeat”.",
              "small", TEXT_2, wrap=520).pack(fill="x", pady=(px(2), px(10)))
        field = Card(note.body, fill=FIELD, border=BORDER, radius=8, padx=10, pady=7)
        field.pack(fill="x")
        self.custom_entry = tk.Entry(field.body, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                                     bd=0, highlightthickness=0, font=K.FONTS["body"])
        self.custom_entry.insert(0, cfg.get("custom_instruction", ""))
        self.custom_entry.pack(fill="x")
        K.layout_independent_shortcuts(self.custom_entry)
        self.custom_entry.bind("<FocusIn>", lambda e: field.set_style(border=ACCENT))
        self.custom_entry.bind("<FocusOut>", lambda e: (field.set_style(border=BORDER), self._save_custom_note()))
        self.custom_entry.bind("<Return>", lambda e: self._save_custom_note())

        prefs = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=6)
        prefs.pack(fill="x", pady=(px(10), 0))
        langs = "Spanish, French, German, Portuguese, Italian, Russian and Ukrainian"
        self._wvars = {}
        for i, (key, title, desc) in enumerate((
            ("polish_preview", "Preview before replacing", "See the polished text first. Enter replaces, Esc cancels."),
            ("fix_without_selection", "Fix without selecting",
             "Nothing selected? The shortcut fixes the line you're typing, from its start to the cursor."),
            ("multilingual", "Other languages",
             f"Also fix {langs}. Uzbek (beta) needs the Gemma 4 model. English uses the most thorough checks."),
            ("keep_formatting", "Keep formatting", "Bold, links and fonts survive in Word, Outlook, Docs and Gmail."),
            ("hud_enabled", "On-screen feedback", "A small card near your text shows progress, results and Undo."),
        )):
            var = tk.BooleanVar(master=self.win, value=bool(cfg.get(key, True)))
            self._wvars[key] = var
            _pref_row(prefs.body, var, title, desc, lambda k=key: self._save_bool(k, self._wvars[k]), first=i == 0)

    def _paint_styles(self):
        for key, (card, dot) in self._style_cards.items():
            sel = key == self._style
            card.fill = ACCENT_SOFT if sel else SURFACE
            card.hover_fill = ACCENT_SOFT if sel else SURFACE_2
            card.set_style(border=ACCENT if sel else BORDER)
            _radio(dot, sel)

    def _choose_style(self, key):
        self._style = key
        C.update_config(polish_style=key)
        self._paint_styles()
        self.services.prefs_changed()

    def _save_custom_note(self):
        from check_guard import MAX_CUSTOM_INSTRUCTION
        value = " ".join(self.custom_entry.get().split())[:MAX_CUSTOM_INSTRUCTION]
        if value != C.load_config().get("custom_instruction", ""):
            C.update_config(custom_instruction=value)
            self.custom_status.configure(text="Saved." if value else "Cleared.", fg=GREEN)
            self.after(1500, lambda: self.custom_status.configure(text=""))

    def _save_bool(self, key, var):
        C.update_config(**{key: bool(var.get())})
        self.services.prefs_changed()

    # -- Actions (quick-action menu) ----------------------------------------------------

    def _build_actions(self, page):
        cfg = C.load_config()
        label(page, "Quick actions", "title").pack(fill="x")
        label(page, "Select text in any app and press the shortcut: a menu offers Fix, Polish in any style, "
                    "Translate and the actions below. Press a number to choose.",
              "small", TEXT_2, wrap=580).pack(fill="x", pady=(px(4), px(10)))
        sc = tk.Frame(page, bg=BG)
        sc.pack(fill="x")
        label(sc, "Shortcut", "small_b", TEXT_2).pack(side="left", padx=(0, px(10)))
        self.menu_caps = tk.Frame(sc, bg=BG)
        self.menu_caps.pack(side="left")
        Button(sc, "Reset", self._reset_menu_hotkey, "ghost", height=30, font=K.FONTS["small_b"],
               padx=10).pack(side="right")
        ShortcutRecorder(sc, "", self._save_menu_hotkey, on_start=lambda: self.services.suspend_hotkeys(True),
                         on_end=lambda: self.services.suspend_hotkeys(False), width=150).pack(side="right",
                                                                                            padx=(0, px(6)))
        self.menu_status = label(page, "", "small", TEXT_2, wrap=580)
        self.menu_status.pack(fill="x", pady=(px(6), px(10)))
        self._render_menu_shortcut()

        foot = tk.Frame(page, bg=BG)
        foot.pack(side="bottom", fill="x", pady=(px(10), 0))
        Button(foot, "Restore examples", self._restore_actions, "ghost", height=32).pack(side="left")
        self.act_status = label(foot, "", "small", TEXT_2)
        self.act_status.pack(side="right")

        editor = Card(page, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=12)
        editor.pack(side="bottom", fill="x", pady=(px(10), 0))
        self.act_title = label(editor.body, "Add an action", "body_b")
        self.act_title.pack(fill="x")
        self.act_name = self._action_entry(editor.body, "Name, e.g. Reply politely")
        self.act_prompt = self._action_entry(
            editor.body, "What it should do, e.g. Write a short, friendly reply to this message.")
        row = tk.Frame(editor.body, bg=SURFACE)
        row.pack(fill="x", pady=(px(10), 0))
        self.act_save = Button(row, "Add action", self._save_action, "primary", height=32)
        self.act_save.pack(side="right")
        self.act_cancel = Button(row, "Cancel", self._cancel_action_edit, "ghost", height=32)
        self._act_edit = None

        label(page, "Your actions", "small_b", TEXT_2).pack(fill="x", pady=(0, px(6)))
        self.act_list = self._scroll_page(page, 230)
        self._render_actions()

    def _render_menu_shortcut(self, note=None):
        for w in self.menu_caps.winfo_children():
            w.destroy()
        keycaps(self.menu_caps, C.get_menu_keycaps()).pack(anchor="w")
        default = "double-tap Shift" if not IS_MAC else "⌃⇧Space"
        self.menu_status.configure(
            text=note or f"Click the button to record a different shortcut. Reset goes back to {default}.",
            fg=TEXT_3)

    def _save_menu_hotkey(self, combo):
        validate = getattr(C, "validate_hotkey", lambda c: (True, ""))
        ok, msg = validate(combo)
        if not ok:
            self.menu_status.configure(text=msg, fg=RED)
            return
        C.update_config(menu_hotkey=combo)
        self._menu_hotkey_applied()

    def _reset_menu_hotkey(self):
        C.update_config(menu_hotkey=C.MENU_DEFAULT_HOTKEY)
        self._menu_hotkey_applied()

    def _menu_hotkey_applied(self):
        self.services.hotkeys_changed()
        self._render_menu_shortcut("Applying…")
        self.after(500, self._check_menu_hotkey)

    def _check_menu_hotkey(self):
        label_text = C.get_menu_label()
        clash = [e for e in (self.services.hotkey_errors() or []) if label_text.replace(" ", "") in e.replace(" ", "")
                 or "Quick actions" in e]
        if clash:
            self.menu_status.configure(text="  ".join(clash) + " Record a different shortcut.", fg=RED)
        else:
            self.menu_status.configure(text=f"✓  {label_text} opens quick actions in every app.", fg=GREEN)

    def _action_entry(self, parent, hint):
        label(parent, hint, "small", TEXT_2).pack(fill="x", pady=(px(8), px(4)))
        field = Card(parent, fill=FIELD, border=BORDER, radius=8, padx=10, pady=6)
        field.pack(fill="x")
        entry = tk.Entry(field.body, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                         bd=0, highlightthickness=0, font=K.FONTS["body"])
        entry.pack(fill="x")
        K.layout_independent_shortcuts(entry)
        entry.bind("<FocusIn>", lambda e: field.set_style(border=ACCENT))
        entry.bind("<FocusOut>", lambda e: field.set_style(border=BORDER))
        entry.bind("<Return>", lambda e: self._save_action())
        return entry

    def _render_actions(self):
        import actions as ACT
        for w in self.act_list.winfo_children():
            w.destroy()
        acts = ACT.custom_actions(C.load_config())
        if not acts:
            label(self.act_list, "No actions yet. Add one below.", "small", TEXT_3).pack(fill="x", pady=px(6))
        first = len(ACT.menu_items({"custom_actions": []}))   # Fix, Polish, styles, Translate come first
        for i, a in enumerate(acts):
            card = Card(self.act_list, fill=SURFACE, border=BORDER, radius=10, padx=14, pady=10)
            card.pack(fill="x", pady=(0, px(6)))
            top = tk.Frame(card.body, bg=SURFACE)
            top.pack(fill="x")
            if first + i < 9:
                Pill(top, str(first + i + 1), fg=ACCENT, fill=K.ACCENT_SOFT, height=22).pack(
                    side="left", padx=(0, px(10)))
            label(top, a["name"], "body_b").pack(side="left")
            Button(top, "Delete", lambda i=i: self._delete_action(i), "ghost", height=26,
                   font=K.FONTS["small_b"], padx=10).pack(side="right")
            Button(top, "Edit", lambda i=i: self._edit_action(i), "ghost", height=26,
                   font=K.FONTS["small_b"], padx=10).pack(side="right")
            label(card.body, a["prompt"], "small", TEXT_2, wrap=520).pack(fill="x", pady=(px(4), 0))
        full = len(acts) >= ACT.MAX_CUSTOM_ACTIONS and self._act_edit is None
        self.act_save.set_state("disabled" if full else "normal")

    def _save_action(self):
        import actions as ACT
        name = " ".join(self.act_name.get().split())[:ACT.MAX_NAME]
        prompt = " ".join(self.act_prompt.get().split())[:ACT.MAX_PROMPT]
        if not name or not prompt:
            self.act_status.configure(text="Give the action a name and say what it should do.", fg=RED)
            return
        acts = ACT.custom_actions(C.load_config())
        if self._act_edit is not None and self._act_edit < len(acts):
            acts[self._act_edit] = {"name": name, "prompt": prompt}
        elif len(acts) >= ACT.MAX_CUSTOM_ACTIONS:
            self.act_status.configure(text=f"Up to {ACT.MAX_CUSTOM_ACTIONS} actions.", fg=RED)
            return
        else:
            acts.append({"name": name, "prompt": prompt})
        C.update_config(custom_actions=acts)
        self._cancel_action_edit()
        self._render_actions()
        self.act_status.configure(text="Saved.", fg=GREEN)
        self.after(1500, lambda: self.act_status.configure(text=""))

    def _edit_action(self, i):
        import actions as ACT
        acts = ACT.custom_actions(C.load_config())
        if not 0 <= i < len(acts):
            return
        for entry, value in ((self.act_name, acts[i]["name"]), (self.act_prompt, acts[i]["prompt"])):
            entry.delete(0, "end")
            entry.insert(0, value)
        self._act_edit = i
        self.act_title.configure(text=f"Edit “{acts[i]['name']}”")
        self.act_save.set_text("Save")
        self.act_save.set_state("normal")
        self.act_cancel.pack(side="right", padx=(0, px(8)))
        self.act_name.focus_set()

    def _cancel_action_edit(self):
        self._act_edit = None
        for entry in (self.act_name, self.act_prompt):
            entry.delete(0, "end")
        self.act_title.configure(text="Add an action")
        self.act_save.set_text("Add action")
        self.act_cancel.pack_forget()

    def _delete_action(self, i):
        import actions as ACT
        acts = ACT.custom_actions(C.load_config())
        if 0 <= i < len(acts):
            del acts[i]
            C.update_config(custom_actions=acts)
            if self._act_edit is not None:
                self._cancel_action_edit()
            self._render_actions()

    def _restore_actions(self):
        import actions as ACT
        C.update_config(custom_actions=[dict(a) for a in ACT.DEFAULT_ACTIONS])
        self._cancel_action_edit()
        self._render_actions()

    # -- History ----------------------------------------------------------------------

    def _build_history(self, page):
        import history
        cfg = C.load_config()
        head = tk.Frame(page, bg=BG)
        head.pack(fill="x")
        label(head, "History", "title").pack(side="left")
        self.history_clear = Button(head, "Clear history", self._clear_history, "ghost", height=30,
                                    font=K.FONTS["small_b"], padx=10)
        self.history_clear.pack(side="right")
        self.history_note = label(head, "", "small", GREEN)
        self.history_note.pack(side="right", padx=px(10))
        label(page, f"Your last {history.MAX_ENTRIES} changes, so you can get the original back later. "
                    "Kept only on this computer.", "small", TEXT_2, wrap=600).pack(fill="x", pady=(px(3), px(10)))
        prefs = Card(page, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=2)
        prefs.pack(fill="x", pady=(0, px(12)))
        self._hist_var = tk.BooleanVar(master=self.win, value=bool(cfg.get("keep_history", True)))
        _pref_row(prefs.body, self._hist_var, "Keep history", "Turn off to stop saving your changes.",
                  self._toggle_history, first=True)
        self.history_list = ScrollArea(page, 390)
        self.history_list.pack(fill="both", expand=True)
        self._render_history()

    def _render_history(self):
        import history
        inner = self.history_list.inner
        for child in inner.winfo_children():
            child.destroy()
        items = history.load(C.get_config_dir())
        self.history_clear.set_state("normal" if items else "disabled")
        if not items:
            empty = "Nothing yet. Every fix, polish and quick action shows up here." \
                if self._hist_var.get() else "History is off."
            label(inner, empty, "body", TEXT_3).pack(fill="x", pady=px(24))
            return
        now = time.time()
        for e in items:
            card = Card(inner, fill=SURFACE, border=BORDER, radius=10, padx=14, pady=10)
            card.pack(fill="x", pady=(0, px(8)))
            top = tk.Frame(card.body, bg=SURFACE)
            top.pack(fill="x")
            meta = "  ·  ".join(p for p in (history.MODE_LABELS.get(e.get("mode"), "Changed"), e.get("app", ""),
                                            history.when(e.get("time", now), now)) if p)
            label(top, meta, "small_b", TEXT_2).pack(side="left")
            for text, value in (("Copy result", e["after"]), ("Copy original", e["before"])):
                Button(top, text, lambda v=value, t=text: self._copy_history(v, t), "ghost", height=26,
                       font=K.FONTS["small_b"], padx=8).pack(side="right", padx=(px(4), 0))
            for text, color in ((e["before"], TEXT_3), (e["after"], TEXT)):
                shown = " ".join(text.split())
                if len(shown) > 240:
                    shown = shown[:239] + "…"
                label(card.body, shown, "small", color, wrap=560).pack(fill="x", pady=(px(4), 0))

    def _copy_history(self, value, what):
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(value)
            self.history_note.configure(text="Original copied." if what == "Copy original" else "Result copied.")
            self.after(1600, lambda: self.history_note.configure(text=""))
        except tk.TclError:
            pass

    def _toggle_history(self):
        C.update_config(keep_history=bool(self._hist_var.get()))
        self._render_history()

    def _clear_history(self):
        import history
        history.clear(C.get_config_dir())
        self._render_history()

    # -- Model ------------------------------------------------------------------------

    def _build_model(self, page):
        hw = H.detect_hardware()
        label(page, "AI model", "title").pack(fill="x")
        label(page, _hw_line(hw), "small", TEXT_2).pack(fill="x", pady=(px(3), px(14)))
        ModelPicker(page, self, self.services, list_height=390).pack(fill="x")

    # -- General ----------------------------------------------------------------------

    def _build_general(self, page):
        foot = tk.Frame(page, bg=BG)
        foot.pack(side="bottom", fill="x", pady=(px(10), 0))
        Button(foot, "Privacy & licenses", lambda: PrivacyWindow(self.win), "secondary", height=34).pack(side="left")
        label(foot, f"  Fixelect {APP_VERSION}", "caption", TEXT_3).pack(side="left", padx=px(8))
        Button(foot, "Quit Fixelect", self._quit, "danger", height=34).pack(side="right")
        body = self._scroll_page(page, 470)
        cfg = C.load_config()

        prefs = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=6)
        prefs.pack(fill="x")
        rows = [
            ("sound", "Sound feedback", "A soft chime when your text is replaced.", cfg.get("sound_enabled", True)),
            ("autostart", "Open at login" if IS_MAC else "Start with Windows",
             "Fixelect waits quietly in the " + ("menu bar." if IS_MAC else "system tray."), C.is_auto_start_enabled()),
        ]
        if not IS_MAC:
            rows.append(("prefetch", "Prepare fixes in advance",
                         "Starts fixing text as soon as you select it. Faster, uses more power.",
                         cfg.get("prefetch_enabled", False)))
        self._vars = {}
        for i, (key, title, desc, value) in enumerate(rows):
            var = tk.BooleanVar(master=self.win, value=bool(value))
            self._vars[key] = var
            _pref_row(prefs.body, var, title, desc, lambda k=key: self._save_pref(k), first=i == 0)

        mem = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=14)
        mem.pack(fill="x", pady=(px(12), 0))
        label(mem.body, "Free memory when idle", "body_b").pack(fill="x")
        label(mem.body, "The AI model uses 1–4 GB. Fixelect unloads it after a break and reloads it in "
                        "a few seconds on your next fix.", "small", TEXT_2, wrap=540).pack(fill="x", pady=(px(2), px(10)))
        current = int(cfg.get("unload_minutes", 10) or 0)
        Segmented(mem.body, IDLE_OPTIONS, current if current in dict(IDLE_OPTIONS) else 10,
                  lambda v: (C.update_config(unload_minutes=v), self.services.prefs_changed())).pack(anchor="w")

        off = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=14)
        off.pack(fill="x", pady=(px(12), 0))
        head = tk.Frame(off.body, bg=SURFACE)
        head.pack(fill="x")
        label(head, "Turned off in", "body_b").pack(side="left")
        self.add_app_btn = Button(head, "Add app…", self._pick_app, "secondary", height=28,
                                  font=K.FONTS["small_b"], padx=12)
        self.add_app_btn.pack(side="right")
        label(off.body, "Fixelect ignores the shortcuts in these apps (terminals and password managers by default).",
              "small", TEXT_2, wrap=540).pack(fill="x", pady=(px(2), px(8)))
        self.app_chips = Chips(off.body, self._remove_app)
        self.app_chips.pack(fill="x")
        self._render_apps()

        upd = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=6)
        upd.pack(fill="x", pady=(px(12), 0))
        if _store_install():
            label(upd.body, f"Fixelect {APP_VERSION}  ·  updates come from the Microsoft Store automatically.",
                  "small", TEXT_2, wrap=540).pack(fill="x", pady=px(10))
            self.upd_btn = None
        else:
            self._build_updater(upd.body)
        self._build_general_rest(body)

    def _build_updater(self, parent):
        cfg = C.load_config()
        self._upd_var = tk.BooleanVar(master=self.win, value=bool(cfg.get("check_updates", True)))
        _pref_row(parent, self._upd_var, "Check for updates",
                  "Once a day, asks GitHub whether a newer Fixelect exists. Nothing about you is sent.",
                  lambda: self._save_bool("check_updates", self._upd_var), first=True)
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x")
        urow = tk.Frame(parent, bg=SURFACE)
        urow.pack(fill="x", pady=px(10))
        self.upd_btn = Button(urow, "Check now", self._update_action, "secondary", height=30,
                              font=K.FONTS["small_b"], padx=12)
        self.upd_btn.pack(side="right")
        ubox = tk.Frame(urow, bg=SURFACE)
        ubox.pack(side="left", fill="x", expand=True, padx=(0, px(12)))
        self.upd_label = label(ubox, f"You have Fixelect {APP_VERSION}.", "small", TEXT_2, wrap=420)
        self.upd_label.pack(fill="x")
        self.upd_progress = ProgressBar(ubox)
        self._upd_cancel = None
        info = self.services.update_info()
        if info:
            self._show_update(info)

    def _build_general_rest(self, body):
        words = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=14)
        words.pack(fill="x", pady=(px(12), 0))
        label(words.body, "Protected words", "body_b").pack(fill="x")
        label(words.body, "Names and jargon Fixelect will never change.", "small", TEXT_2).pack(fill="x", pady=(px(2), px(10)))
        add = tk.Frame(words.body, bg=SURFACE)
        add.pack(fill="x")
        field = Card(add, fill=FIELD, border=BORDER, radius=8, padx=10, pady=6)
        field.pack(side="left", fill="x", expand=True, padx=(0, px(8)))
        self.word_entry = tk.Entry(field.body, bg=FIELD, fg=TEXT, insertbackground=TEXT, relief="flat",
                                   bd=0, highlightthickness=0, font=K.FONTS["body"])
        self.word_entry.pack(fill="x")
        K.layout_independent_shortcuts(self.word_entry)
        self.word_entry.bind("<Return>", lambda e: self._add_word())
        self.word_entry.bind("<FocusIn>", lambda e: field.set_style(border=ACCENT))
        self.word_entry.bind("<FocusOut>", lambda e: field.set_style(border=BORDER))
        Button(add, "Add", self._add_word, "secondary", width=70, height=32).pack(side="right")
        self.chips = Chips(words.body, self._remove_word)
        self.chips.pack(fill="x", pady=(px(10), 0))
        self._render_words()

    def _save_pref(self, key):
        v = self._vars[key].get()
        if key == "sound":
            C.update_config(sound_enabled=v)
        elif key == "autostart":
            C.set_auto_start(v)
            C.update_config(auto_start=v)
        elif key == "prefetch":
            C.update_config(prefetch_enabled=v)
        self.services.prefs_changed()

    # per-app off switch

    def _render_apps(self):
        apps = C.load_config().get("disabled_apps", [])
        self.app_chips.render([(a, A.display_name(a)) for a in apps],
                              trailing="" if apps else "Fixelect works in every app.")

    def _remove_app(self, app_id):
        cfg = C.load_config()
        C.update_config(disabled_apps=[a for a in cfg.get("disabled_apps", []) if a != app_id])
        self._render_apps()

    def _add_app(self, app_id):
        cfg = C.load_config()
        apps = cfg.get("disabled_apps", [])
        if app_id not in apps:
            C.update_config(disabled_apps=apps + [app_id])
        self._render_apps()

    def _pick_app(self):
        current = set(C.load_config().get("disabled_apps", []))
        menu = tk.Menu(self.win, tearoff=0, bg=SURFACE_2, fg=TEXT, activebackground=ACCENT,
                       activeforeground="#FFFFFF", bd=0, font=K.FONTS["body"])
        running = [(k, n) for k, n in A.list_open_apps() if k not in current]
        if running:
            menu.add_command(label="Open apps", state="disabled")
            for key, name in running[:20]:
                menu.add_command(label="   " + name, command=lambda k=key: self._add_app(k))
            menu.add_separator()
        suggestions = [k for k in A.SUGGESTED if k not in current and k not in dict(running)]
        if suggestions:
            menu.add_command(label="Suggestions", state="disabled")
            for key in suggestions[:14]:
                menu.add_command(label="   " + A.display_name(key), command=lambda k=key: self._add_app(k))
        b = self.add_app_btn
        try:
            menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height() + px(4))
        finally:
            menu.grab_release()

    # updates

    def _show_update(self, info):
        self._update = info
        self.upd_label.configure(text=f"Fixelect {info['version']} is available.", fg=ACCENT)
        self.upd_btn.set_text("Install update" if not IS_MAC else "Get update")
        self.upd_btn.set_variant("primary")

    def _update_action(self):
        info = getattr(self, "_update", None)
        if self._upd_cancel is not None:
            self._upd_cancel.set()
            return
        if info:
            self._install_update(info)
            return
        self.upd_btn.set_state("disabled")
        self.upd_label.configure(text="Checking…", fg=TEXT_2)

        def work():
            found, err = self.services.check_updates()
            self.post(lambda: self._update_checked(found, err))
        threading.Thread(target=work, daemon=True).start()

    def _update_checked(self, info, err):
        if not self.alive:
            return
        self.upd_btn.set_state("normal")
        if err:
            self.upd_label.configure(text=err, fg=RED)
        elif info:
            self._show_update(info)
        else:
            self.upd_label.configure(text=f"You're up to date (Fixelect {APP_VERSION}).", fg=GREEN)

    def _install_update(self, info):
        if IS_MAC:
            self.services.install_update(info, None, None)
            return
        self._upd_cancel = threading.Event()
        cancel = self._upd_cancel
        self.upd_btn.set_text("Cancel")
        self.upd_btn.set_variant("secondary")
        self.upd_label.configure(text="Downloading the update…", fg=TEXT_2)
        self.upd_progress.pack(fill="x", pady=(px(6), 0))

        def progress(done, total):
            self.post(lambda: self.upd_progress.set(done / total if total else 0))

        def work():
            try:
                self.services.install_update(info, progress, cancel)
                self.post(lambda: self.upd_label.configure(text="Installing… Fixelect restarts by itself.", fg=GREEN))
            except Exception as e:
                msg = str(e) or type(e).__name__
                self.post(lambda: self._update_failed(msg))
        threading.Thread(target=work, daemon=True).start()

    def _update_failed(self, msg):
        if not self.alive:
            return
        self._upd_cancel = None
        self.upd_progress.pack_forget()
        self.upd_label.configure(text=msg, fg=RED)
        self.upd_btn.set_text("Install update")
        self.upd_btn.set_variant("primary")

    # protected words

    def _render_words(self):
        from check_guard import get_user_words, BUILTIN_WORDS
        self.chips.render([(w, w) for w in get_user_words()], trailing=f"+{len(BUILTIN_WORDS)} built-in")

    def _add_word(self):
        from check_guard import add_protected_word
        value = self.word_entry.get().strip()
        if value and add_protected_word(value):
            self.word_entry.delete(0, "end")
            self._render_words()

    def _remove_word(self, word):
        from check_guard import remove_protected_word
        remove_protected_word(word)
        self._render_words()

    def _quit(self):
        self.close()
        self.services.quit()

    # -- Help ---------------------------------------------------------------------------

    def _build_help(self, page):
        foot = tk.Frame(page, bg=BG)
        foot.pack(side="bottom", fill="x", pady=(px(10), 0))
        self.diag_btn = Button(foot, "Copy diagnostics", self._copy_diagnostics, "secondary", height=34)
        self.diag_btn.pack(side="left")
        Button(foot, "Open log folder", lambda: _open_path(C.get_logs_dir()), "ghost", height=34).pack(side="left", padx=px(6))
        Button(foot, "Replay tutorial", lambda: self.show("Welcome"), "ghost", height=34).pack(side="right")
        body = self._scroll_page(page, 470)

        label(body, "How it works", "title").pack(fill="x")
        steps = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=10)
        steps.pack(fill="x", pady=(px(10), px(16)))
        for n, s in enumerate((
            "Select text in any app.",
            f"Press {C.get_hotkey_label('fix')} to fix it, or {C.get_hotkey_label('polish')} to polish it. "
            f"{C.get_menu_label()} opens a menu with Translate, other styles and your own actions.",
            "The text is replaced where it is. Undo from the card that appears, or with "
            + ("⌘Z." if IS_MAC else "Ctrl+Z."),
        ), 1):
            r = tk.Frame(steps.body, bg=SURFACE)
            r.pack(fill="x", pady=px(4))
            Pill(r, str(n), fg=ACCENT, fill=K.ACCENT_SOFT, height=22).pack(side="left", padx=(0, px(10)))
            label(r, s, "body", wrap=500).pack(side="left", fill="x")

        label(body, "Why wasn't my text fixed?", "title").pack(fill="x")
        faq = Card(body, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=6)
        faq.pack(fill="x", pady=(px(10), 0))
        for i, (q, a) in enumerate(HELP_ITEMS):
            if i:
                tk.Frame(faq.body, bg=BORDER, height=1).pack(fill="x")
            box = tk.Frame(faq.body, bg=SURFACE)
            box.pack(fill="x", pady=px(9))
            label(box, q, "body_b").pack(fill="x")
            label(box, a, "small", TEXT_2, wrap=540).pack(fill="x", pady=(px(2), 0))
        label(body, "Diagnostics contain your settings and recent errors — never your text.", "caption",
              TEXT_3).pack(fill="x", pady=(px(10), 0))

    def _copy_diagnostics(self):
        self.diag_btn.set_state("disabled")

        def work():
            try:
                text = self.services.diagnostics()
            except Exception as e:
                text = f"Could not collect diagnostics: {e}"
            self.post(lambda: self._diagnostics_ready(text))
        threading.Thread(target=work, daemon=True).start()

    def _diagnostics_ready(self, text):
        if not self.alive:
            return
        self.win.clipboard_clear()
        self.win.clipboard_append(text)
        self.diag_btn.set_state("normal")
        self.diag_btn.set_text("Copied")
        self.after(1600, lambda: self.diag_btn.set_text("Copy diagnostics"))


# ---------------------------------------------------------------------------
# First-run setup
# ---------------------------------------------------------------------------

class SetupWindow(_Window):
    def __init__(self, master, services, post, on_done):
        super().__init__(master, "Welcome to Fixelect", 600, 690, on_close=self._closed)
        self.post, self.on_done, self._finished = post, on_done, False
        outer = tk.Frame(self.win, bg=BG, padx=px(30), pady=px(28))
        outer.pack(fill="both", expand=True)
        self._logo = _logo(px(34), self.win)
        if self._logo:
            tk.Label(outer, image=self._logo, bg=BG).pack(anchor="w")
        spacer(outer, 18)
        label(outer, "Grammar fixes in every app", "display").pack(fill="x")
        trigger = "Option (⌥)" if IS_MAC else "Alt"
        label(outer, f"Select text anywhere and double-tap {trigger}. Fixelect runs entirely on this "
                     "computer — pick a model to get started.", "body", TEXT_2, wrap=520).pack(fill="x", pady=(px(6), px(16)))
        hw = H.detect_hardware()
        Pill(outer, "Detected  " + _hw_line(hw), fg=TEXT_2, fill=SURFACE_2, height=26, dot=GREEN).pack(anchor="w")
        spacer(outer, 16)
        ModelPicker(outer, self, services, list_height=372, setup_mode=True, on_ready=self._ready).pack(fill="x")
        self.present()

    def _ready(self, _key):
        self._finished = True
        self.close()

    def _closed(self):
        profile = C.load_config().get("model_profile", "3b")
        self.on_done(self._finished or D.resolve_model(profile) is not None)


# ---------------------------------------------------------------------------
# macOS accessibility onboarding
# ---------------------------------------------------------------------------

class PermissionsWindow(_Window):
    def __init__(self, master, on_done):
        super().__init__(master, "Fixelect needs Accessibility access", 540, 480, on_close=lambda: on_done(self._granted))
        self._granted = False
        outer = tk.Frame(self.win, bg=BG, padx=px(30), pady=px(28))
        outer.pack(fill="both", expand=True)
        label(outer, "Allow Accessibility access", "display").pack(fill="x")
        label(outer, "macOS asks for this so Fixelect can notice your double-tap and paste the corrected "
                     "text back into the app you are using. Nothing is recorded or sent anywhere.",
              "body", TEXT_2, wrap=470).pack(fill="x", pady=(px(6), px(16)))
        steps = Card(outer, fill=SURFACE, border=BORDER, radius=12, padx=16, pady=12)
        steps.pack(fill="x")
        for n, s in enumerate(("Click “Open System Settings”.",
                               "Turn on Fixelect in the Accessibility list.",
                               "That's it. This window closes by itself."), 1):
            r = tk.Frame(steps.body, bg=SURFACE)
            r.pack(fill="x", pady=px(4))
            Pill(r, str(n), fg=ACCENT, fill=K.ACCENT_SOFT, height=22).pack(side="left", padx=(0, px(10)))
            label(r, s, "body").pack(side="left")
        label(outer, "Fixelect is already on but this window keeps waiting? Select Fixelect in the list, "
                     "remove it with −, then click “Open System Settings” again. macOS needs this after "
                     "each update.", "small", TEXT_2, wrap=470).pack(fill="x", pady=(px(12), 0))
        self.state = Pill(outer, "Waiting for permission…", fg=AMBER, fill=AMBER_SOFT, dot=AMBER, height=26)
        self.state.pack(anchor="w", pady=(px(16), 0))
        row = tk.Frame(outer, bg=BG)
        row.pack(side="bottom", fill="x")
        Button(row, "Open System Settings", self._open_settings, "primary", height=38).pack(side="left")
        Button(row, "Later", self.close, "ghost", height=38).pack(side="right")
        self.present()
        self._poll()

    def _open_settings(self):
        try:
            # Asking once puts Fixelect in the Accessibility list, so the user only flips its switch.
            from hotkey_mac import check_accessibility_permissions
            check_accessibility_permissions(prompt=True)
        except Exception:
            pass
        try:
            subprocess.Popen(["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"])
        except Exception:
            pass

    def _poll(self):
        try:
            from hotkey_mac import check_accessibility_permissions
            ok = check_accessibility_permissions(prompt=False)
        except Exception:
            ok = False
        if ok:
            self._granted = True
            self.state.set("Access granted", GREEN, GREEN_SOFT, dot=GREEN)
            self.after(700, self.close)
            return
        self.after(800, self._poll)


class PrivacyWindow(_Window):
    def __init__(self, master):
        super().__init__(master, "Privacy & licenses", 620, 580)
        outer = tk.Frame(self.win, bg=BG, padx=px(26), pady=px(22))
        outer.pack(fill="both", expand=True)
        label(outer, "Privacy & licenses", "title").pack(fill="x")
        label(outer, "Fixelect processes text in memory on this device. No accounts, no telemetry, no cloud.",
              "small", TEXT_2, wrap=560).pack(fill="x", pady=(px(3), px(14)))
        Button(outer, "Close", self.close, "secondary", width=90, height=34).pack(side="bottom", anchor="e", pady=(px(12), 0))
        box = TextBox(outer, height=18, readonly=True)
        box.pack(fill="both", expand=True)
        parts = []
        for names in (("PRIVACY_POLICY.md", "resources/PRIVACY_POLICY.md"), ("LICENSE.txt", "resources/LICENSE.txt")):
            p = _resource(*names)
            if p:
                parts.append(p.read_text(encoding="utf-8", errors="replace").strip())
        box.set(("\n\n" + "─" * 40 + "\n\n").join(parts) or "Fixelect is 100% offline and collects no data.")
        box.text.configure(font=K.FONTS["small"])
        self.present()


# ---------------------------------------------------------------------------
# Hosting
# ---------------------------------------------------------------------------

class UIManager:
    """Runs every Fixelect window, the status card and the Polish preview on
    one dedicated Tk thread (Windows)."""

    def __init__(self, services):
        self.services = services
        self._q = queue.Queue()
        self._ready = threading.Event()
        self._thread = None
        self.root = None
        self.dashboard = None
        self._hud = None
        self.preview = None

    def _ensure(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._main, daemon=True, name="fixelect-ui")
            self._thread.start()
        self._ready.wait(15)

    def _main(self):
        self.root = tk.Tk()
        self.root.withdraw()
        K.init(self.root)
        _set_default_icon(self.root)
        self._ready.set()
        self.root.after(30, self._pump)
        self.root.mainloop()

    def _pump(self):
        while True:
            try:
                fn = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except Exception as e:
                print(f"  (ui error: {e})")
        self.root.after(30, self._pump)

    def post(self, fn):
        self._q.put(fn)

    # dashboard

    def open_dashboard(self, page=None):
        self._ensure()
        self.post(lambda: self._open_dashboard(page))

    def _open_dashboard(self, page=None):
        if self.dashboard is not None and self.dashboard.alive:
            self.dashboard.request_focus(page)
            return

        def closed():
            self.dashboard = None
        self.dashboard = Dashboard(self.root, self.services, self.post, on_close=closed, page=page)

    def run_setup_blocking(self):
        self._ensure()
        done, result = threading.Event(), [False]

        def finish(ok):
            result[0] = ok
            done.set()
        self.post(lambda: SetupWindow(self.root, self.services, self.post, finish))
        done.wait()
        return result[0]

    # status card & polish preview (Windows)

    def warm_up(self):
        """Start the UI thread and build the (hidden) status card now. Creating
        Tk windows can briefly take focus, which must never happen mid-fix."""
        self._ensure()
        self.post(self._card)

    def _card(self):
        if self._hud is None:
            from hud_win import Hud
            self._hud = Hud(self.root)
        return self._hud

    def hud(self, **kw):
        self._ensure()
        self.post(lambda: self._card().show(**kw))

    def hide_hud(self):
        if self._hud is not None:
            self.post(self._hud.hide)

    def open_preview(self, styles, style, on_decision, anchor=None):
        self._ensure()

        def make():
            try:
                from hud_win import PolishPreview
                if self._hud is not None:
                    self._hud.hide()
                self.preview = PolishPreview(self.root, styles, style, on_decision)
                self.preview.present(anchor)
            except Exception as e:
                # The worker waits for a decision: without one every later shortcut hung.
                print(f"  (preview failed: {e})")
                if self.preview is not None and self.preview.alive:
                    self.preview.cancel()
                else:
                    on_decision("cancel", None)
        self.post(make)

    def open_menu(self, items, submenu, on_choice, anchor=None):
        """The quick-action menu. `on_choice(item | None)` is called exactly once."""
        self._ensure()

        def make():
            try:
                from hud_win import ActionMenu
                if self._hud is not None:
                    self._hud.hide()
                ActionMenu(self.root, items, submenu, on_choice).present(anchor)
            except Exception as e:
                print(f"  (menu failed: {e})")
                on_choice(None)
        self.post(make)

    def preview_result(self, before, after, note=""):
        self.post(lambda: self.preview and self.preview.alive and self.preview.show_result(before, after, note))

    def preview_error(self, message):
        self.post(lambda: self.preview and self.preview.alive and self.preview.show_error(message))

    def stop(self):
        if self.root is not None:
            self.post(self.root.quit)


def run_standalone(kind="dashboard", services=None, page=None):
    """Run one window on the calling (main) thread until it closes. Returns its result."""
    root = tk.Tk()
    root.withdraw()
    K.init(root)
    _set_default_icon(root)
    services = services or LocalServices()
    q = queue.Queue()
    result = [None]

    def post(fn):
        q.put(fn)

    def pump():
        while True:
            try:
                q.get_nowait()()
            except queue.Empty:
                break
            except Exception as e:
                print(f"  (ui error: {e})")
        root.after(30, pump)

    def done(value=None):
        result[0] = value
        root.after(10, root.quit)

    def focus_request():
        target = None
        try:
            target = (C.get_config_dir() / "dashboard_page").read_text().strip() or None
            (C.get_config_dir() / "dashboard_page").unlink()
        except Exception:
            pass
        if win is not None and hasattr(win, "request_focus"):
            win.request_focus(target) if isinstance(win, Dashboard) else win.request_focus()

    if IS_MAC:
        try:
            import signal
            # The menu-bar daemon sends SIGUSR1 to ask an open dashboard to come forward.
            signal.signal(signal.SIGUSR1, lambda *_: post(focus_request))
        except Exception:
            pass

    win = None
    if kind == "setup":
        win = SetupWindow(root, services, post, done)
    elif kind == "permissions":
        win = PermissionsWindow(root, done)
    else:
        win = Dashboard(root, services, post, on_close=done, page=page)
    root.after(30, pump)
    root.mainloop()
    try:
        root.destroy()
    except tk.TclError:
        pass
    return result[0]
