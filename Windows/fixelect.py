"""
Fixelect for Windows — 100% Offline AI Grammar Correction & Executive Polish
Hardware-Accelerated Local Inference (CUDA / Vulkan / AVX2) • Global Hotkeys • Fluent Dark UI

Triggers (default):
  Alt x2 (Alt Alt)     ->  Proofread & fix grammar (voice preserved)
  Ctrl x2 (Ctrl Ctrl)  ->  Professional polish
  Ctrl + Alt + Q       ->  Quit Fixelect
Presets and custom shortcuts can be chosen in the dashboard.

Author: Bositxon Erkinxonov
License: MIT (100% Offline, Zero Telemetry)
"""

import atexit
import ctypes
import ctypes.wintypes as wintypes
import pathlib
import queue
import re
import sys
import threading
import time


class _NullWriter:
    def write(self, *args, **kwargs):
        pass

    def flush(self, *args, **kwargs):
        pass


if sys.stdout is None:
    sys.stdout = _NullWriter()
if sys.stderr is None:
    sys.stderr = _NullWriter()
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fixelect.App.1.0")
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor High DPI
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        uxtheme = ctypes.windll.uxtheme
        ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)((135, uxtheme))(2)  # SetPreferredAppMode(ForceDark)
        ctypes.WINFUNCTYPE(None)((136, uxtheme))()                         # FlushMenuThemes
    except Exception:
        pass

if getattr(sys, "frozen", False):
    _base_dir = pathlib.Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    if (_base_dir / "tools").is_dir():
        sys.path.insert(0, str(_base_dir / "tools"))
    sys.path.insert(0, str(_base_dir))
    _exe_dir = pathlib.Path(sys.executable).resolve().parent
    if (_exe_dir / "tools").is_dir():
        sys.path.insert(0, str(_exe_dir / "tools"))
else:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tools"))

from check_guard import BEAMS, MODELS, load_pipeline  # noqa: E402
from config import (  # noqa: E402
    load_config,
    get_config_dir,
    get_hotkey_label,
    parse_hotkey_string,
    validate_hotkey,
    log_error,
)
from downloader import resolve_model  # noqa: E402
from hotkey_win import WinHotkeyListener  # noqa: E402
import clipboard_win as clip  # noqa: E402

MODEL = "qwen2.5"
ENGINE = "embedded"
FAST = False
CANDIDATES = 1

# Prefetch (opt-in): fix a selection speculatively while the user is still looking at it.
POLL_SECONDS = 0.35
SETTLE_SECONDS = 0.4
MIN_PREFETCH_CHARS = 8
MAX_PREFETCH_CHARS = 600

MAX_SELECTION_CHARS = 12000     # beyond this a local model would take minutes
CLIPBOARD_RESTORE_DELAY = 0.8   # give slow apps (Word, Slack, IDEs) time to read the paste

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000
VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN = 0x11, 0x12, 0x10, 0x5B, 0x5C
VK_C, VK_V, VK_F, VK_P, VK_Q, VK_SPACE = 0x43, 0x56, 0x46, 0x50, 0x51, 0x20
VK_MASK = 0xE8  # unassigned key: breaks "lone Win/Alt release" menu activation
KEYEVENTF_KEYUP = 0x0002
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
WM_APP_RELOAD_HOTKEYS = 0x8000 + 10
WM_APP_SUSPEND_HOTKEYS = 0x8000 + 11
ID_FIX, ID_POLISH, ID_QUIT = 1001, 1002, 1003
ID_FALLBACK_FIX, ID_FALLBACK_POLISH = 1004, 1005
ALL_HOTKEY_IDS = (ID_FIX, ID_POLISH, ID_QUIT, ID_FALLBACK_FIX, ID_FALLBACK_POLISH)

IDC_WAIT = 32514
IDC_APPSTARTING = 32650
OCR_NORMAL, OCR_IBEAM, OCR_HAND = 32512, 32513, 32649
SPI_SETCURSORS = 0x0057
IMAGE_CURSOR = 2
LR_SHARED = 0x8000

user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.CopyImage.restype = wintypes.HANDLE
user32.CopyImage.argtypes = [wintypes.HANDLE, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.SetSystemCursor.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.CreateEventW.restype = wintypes.HANDLE
kernel32.OpenEventW.restype = wintypes.HANDLE
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.SetEvent.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

MUTEX_NAME = "Local\\Fixelect_SingleInstance_Mutex"
SHOW_EVENT_NAME = "Local\\Fixelect_ShowDashboard_Event"
_single_instance_mutex = None


# --------------------------------------------------------------------------
# Sound
# --------------------------------------------------------------------------

def _sound_file(mode):
    """Soft two-note chime, generated once. MessageBeep's default "ding" is jarring."""
    path = get_config_dir() / f"chime_{mode}.wav"
    if path.is_file():
        return path
    import math
    import struct
    import wave
    rate = 44100
    notes = (1318.5, 1760.0) if mode == "fix" else (987.8, 1318.5)
    frames = bytearray()
    for i, freq in enumerate(notes):
        n = int(rate * 0.07)
        for s in range(n):
            t = s / rate
            env = min(1.0, s / (rate * 0.004)) * math.exp(-t * 38)
            val = 0.16 * env * math.sin(2 * math.pi * freq * t)
            frames += struct.pack("<h", int(val * 32767))
        if i == 0:
            frames += b"\0\0" * int(rate * 0.012)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))
    return path


def play_fix_sound(mode="fix"):
    if not load_config().get("sound_enabled", True):
        return
    try:
        import winsound
        winsound.PlaySound(str(_sound_file(mode)), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Text layout
# --------------------------------------------------------------------------

from check_guard import fix_preserving_layout, is_probably_english, split_edges as _split_edges  # noqa: E402


# --------------------------------------------------------------------------
# Single instance
# --------------------------------------------------------------------------

def ensure_single_instance(on_show_callback):
    """One Fixelect per user session. A second launch asks the first to show its window."""
    global _single_instance_mutex
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    h_mutex = k32.CreateMutexW(None, False, MUTEX_NAME)
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        h_event = kernel32.OpenEventW(0x0002, False, SHOW_EVENT_NAME)
        if h_event:
            kernel32.SetEvent(h_event)
            kernel32.CloseHandle(h_event)
        if h_mutex:
            kernel32.CloseHandle(h_mutex)
        sys.exit(0)

    _single_instance_mutex = h_mutex
    h_event = kernel32.CreateEventW(None, False, False, SHOW_EVENT_NAME)

    def event_listener():
        while True:
            if kernel32.WaitForSingleObject(h_event, 0xFFFFFFFF) == 0:
                # Never block this loop: a second launch must always be answered.
                threading.Thread(target=on_show_callback, daemon=True).start()

    threading.Thread(target=event_listener, daemon=True).start()


# --------------------------------------------------------------------------
# Cursor
# --------------------------------------------------------------------------

_cursor_busy = False


def show_busy_cursor():
    global _cursor_busy
    try:
        h_wait = user32.LoadImageW(None, IDC_WAIT, IMAGE_CURSOR, 0, 0, LR_SHARED) or \
            user32.LoadImageW(None, IDC_APPSTARTING, IMAGE_CURSOR, 0, 0, LR_SHARED)
        if h_wait:
            for ocr in (OCR_NORMAL, OCR_IBEAM, OCR_HAND):
                user32.SetSystemCursor(user32.CopyImage(h_wait, IMAGE_CURSOR, 0, 0, 0), ocr)
            _cursor_busy = True
    except Exception:
        pass


def restore_cursor():
    global _cursor_busy
    try:
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
    except Exception:
        pass
    _cursor_busy = False


atexit.register(lambda: _cursor_busy and restore_cursor())


# --------------------------------------------------------------------------
# Keyboard
# --------------------------------------------------------------------------

def _scan(vk):
    # Real scan codes: apps that read them (Tk, Java, games, RDP clients) ignore scan code 0.
    return user32.MapVirtualKeyW(vk, 0) & 0xFF


def key_down(vk):
    user32.keybd_event(vk, _scan(vk), 0, 0)


def key_up(vk):
    user32.keybd_event(vk, _scan(vk), KEYEVENTF_KEYUP, 0)


def _is_down(vk):
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def settle_modifiers():
    """Wait for the trigger's modifiers to be released before sending Ctrl+C.

    Ctrl+C sent while Alt is still held arrives as Ctrl+Alt+C, which copies
    nothing. Only keys that are genuinely still down are released - blindly
    sending a lone Alt/Win key-up activates the app's menu bar or Start menu.
    """
    mods = (VK_CONTROL, VK_MENU, VK_SHIFT, VK_LWIN, VK_RWIN)
    deadline = time.time() + 0.5
    while time.time() < deadline and any(_is_down(vk) for vk in mods):
        time.sleep(0.01)
    stuck = [vk for vk in mods if _is_down(vk)]
    if stuck:
        if any(vk in (VK_MENU, VK_LWIN, VK_RWIN) for vk in stuck):
            key_down(VK_MASK)
            key_up(VK_MASK)
        for vk in stuck:
            key_up(vk)
        time.sleep(0.03)


def send_ctrl(vk):
    key_down(VK_CONTROL)
    key_down(vk)
    key_up(vk)
    key_up(VK_CONTROL)


def copy_selection():
    """Ctrl+C, then wait until the clipboard actually changes. False = nothing selected."""
    before = clip.sequence()
    send_ctrl(VK_C)
    deadline = time.time() + 0.8
    while time.time() < deadline:
        time.sleep(0.012)
        if clip.sequence() != before:
            time.sleep(0.025)  # let the source app finish writing every format
            return not clip.copied_from_empty_selection()
    return False


def bring_window_to_front(hwnd):
    if not hwnd:
        return
    try:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.SwitchToThisWindow(hwnd, True)
    except Exception:
        pass


# --------------------------------------------------------------------------
# Reading the selection without touching the clipboard (prefetch)
# --------------------------------------------------------------------------

class SelectionReader:
    """Reads the focused control's selected text through UI Automation. Every
    failure is silent: text() returns None and the hotkey path is unaffected."""

    def __init__(self):
        self.ok = False
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            self.uia = comtypes.client.CreateObject(module.CUIAutomation, interface=module.IUIAutomation)
            self.text_pattern_id = module.UIA_TextPatternId
            self.IUIAutomationTextPattern = module.IUIAutomationTextPattern
            self.ok = True
        except Exception as e:
            print(f"  (prefetch off: UI Automation unavailable - {e})")

    def text(self):
        if not self.ok:
            return None
        try:
            element = self.uia.GetFocusedElement()
            if not element:
                return None
            pattern = element.GetCurrentPattern(self.text_pattern_id)
            if not pattern:
                return None
            ranges = pattern.QueryInterface(self.IUIAutomationTextPattern).GetSelection()
            if not ranges or ranges.Length == 0:
                return None
            selected = ranges.GetElement(0).GetText(MAX_PREFETCH_CHARS + 1)
            return selected.strip() or None
        except Exception:
            return None


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

class FixelectApp:
    """Owns the model, the hotkeys and the clipboard dance. One worker thread
    runs every job in order, so nothing races the engine or the clipboard."""

    def __init__(self):
        self.jobs = queue.Queue()
        self.cache = {}
        self.fix = None
        self.status_info = {"state": "loading", "detail": "Starting the AI engine…", "backend": "", "model": ""}
        self.hotkey_errors = []
        self.main_thread_id = kernel32.GetCurrentThreadId()
        self.prefetch_on = threading.Event()
        self._restore_lock = threading.Lock()
        self._restore_timer = None
        self._pending_restore = None
        self._last_hotkey_done = 0.0
        self.tray = None
        self.ui = None
        self.listener = None

    # -- status & notifications ----------------------------------------------

    def set_status(self, state, detail=""):
        self.status_info.update(state=state, detail=detail)
        try:
            from engine import get_default_engine
            eng = get_default_engine()
            self.status_info["backend"] = eng.backend_label or ""
            self.status_info["model"] = eng.model_profile
        except Exception:
            pass
        if self.tray:
            self.tray.refresh()

    def status(self):
        return dict(self.status_info)

    def notify(self, title, message):
        if self.tray:
            self.tray.notify(title, message)

    # -- engine -----------------------------------------------------------------

    def _load_engine(self):
        self.set_status("loading", "Loading the AI model…")
        try:
            self.fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
            self.set_status("ready", "Ready")
            return True
        except Exception as e:
            self.fix = None
            log_error(f"engine load failed: {e}")
            self.set_status("error", str(e))
            return False

    def _switch_model(self, profile):
        from engine import get_default_engine
        self.set_status("loading", "Switching model…")
        self.cache.clear()
        try:
            get_default_engine(model_profile=profile)
        except Exception:
            pass
        self._load_engine()
        if self.status_info["state"] == "ready":
            from downloader import MODELS as DL_MODELS
            self.notify("Model ready", f"Fixelect now uses {DL_MODELS.get(profile, {}).get('short_name', profile)}.")

    # -- clipboard restore ---------------------------------------------------------

    def _take_pending_restore(self):
        """If the previous job's restore hasn't happened yet, cancel it and hand
        back the user's original clipboard, so we never capture our own output."""
        with self._restore_lock:
            if self._restore_timer is not None:
                self._restore_timer.cancel()
                self._restore_timer = None
                snap, self._pending_restore = self._pending_restore, None
                return snap, True
            return None, False

    def _schedule_restore(self, snapshot, delay, only_if_seq=None):
        if snapshot is None:
            return

        def do_restore():
            with self._restore_lock:
                if self._restore_timer is None:
                    return
                self._restore_timer = None
                self._pending_restore = None
                # If the user copied something new meanwhile, leave it alone.
                if only_if_seq is not None and clip.sequence() != only_if_seq:
                    return
                clip.restore(snapshot)

        with self._restore_lock:
            if self._restore_timer is not None:
                self._restore_timer.cancel()
            self._pending_restore = snapshot
            self._restore_timer = threading.Timer(delay, do_restore)
            self._restore_timer.daemon = True
            self._restore_timer.start()

    # -- jobs ----------------------------------------------------------------------

    def trigger(self, mode):
        show_busy_cursor()
        self.jobs.put((mode, None, time.time()))

    def run_fix_sync(self, text, mode="fix", timeout=240):
        """Used by the dashboard playground: runs on the worker, returns fixed text."""
        reply = queue.Queue()
        self.jobs.put(("playground", (text, mode, reply), time.time()))
        ok, value = reply.get(timeout=timeout)
        if not ok:
            raise RuntimeError(value)
        return value

    def request_model_switch(self, profile):
        self.jobs.put(("switch_model", profile, time.time()))

    def worker(self):
        self._load_engine()
        while True:
            kind, payload, queued_at = self.jobs.get()
            try:
                if kind == "prefetch":
                    self._do_prefetch(payload)
                elif kind == "switch_model":
                    self._switch_model(payload)
                elif kind == "playground":
                    self._do_playground(*payload)
                elif kind in ("fix", "polish"):
                    if queued_at < self._last_hotkey_done:
                        continue  # pressed again while the previous one was running
                    try:
                        self._do_hotkey(kind)
                    finally:
                        restore_cursor()
                        self._last_hotkey_done = time.time()
            except Exception as e:
                log_error(f"job {kind} failed: {type(e).__name__}: {e}")
                if kind in ("fix", "polish"):
                    self.notify("Fixelect couldn't finish", str(e) or type(e).__name__)

    def _ensure_fix(self):
        if self.fix is None and not self._load_engine():
            raise RuntimeError(self.status_info.get("detail") or "The AI engine is not available.")
        return self.fix

    def _run(self, text, mode):
        fix = self._ensure_fix()
        self.set_status("busy", "Working…")
        try:
            return fix_preserving_layout(text, lambda t: fix(t, mode=mode), mode=mode)
        finally:
            self.set_status("ready", "Ready")

    def _do_playground(self, text, mode, reply):
        try:
            reply.put((True, self._run(text, mode)[0]))
        except Exception as e:
            reply.put((False, str(e)))

    def _do_prefetch(self, text):
        if self.fix is None or text in self.cache or not self.prefetch_on.is_set():
            return
        try:
            self.cache[text] = fix_preserving_layout(text, lambda t: self.fix(t, mode="fix"))[0]
            while len(self.cache) > 20:
                self.cache.pop(next(iter(self.cache)))
        except Exception:
            pass

    def _drop_queued_prefetch(self):
        kept = []
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                break
            if job[0] != "prefetch":
                kept.append(job)
        for job in kept:
            self.jobs.put(job)

    def _do_hotkey(self, mode):
        show_busy_cursor()
        self._drop_queued_prefetch()

        original, _ = self._take_pending_restore()
        if original is None:
            original = clip.snapshot()

        settle_modifiers()
        if not copy_selection():
            print("  ! nothing selected")
            self._schedule_restore(original, 0.05)
            return

        text = clip.get_text()
        if not text or not text.strip():
            self._schedule_restore(original, 0.05)
            return
        if len(text) > MAX_SELECTION_CHARS:
            self._schedule_restore(original, 0.05)
            self.notify("Selection too long", f"Select fewer than {MAX_SELECTION_CHARS:,} characters at a time.")
            return
        if not is_probably_english(text):
            self._schedule_restore(original, 0.05)
            self.notify("Only English for now", "Fixelect leaves text in other languages unchanged.")
            return

        started = time.time()
        lead, core, trail = _split_edges(text)
        cached = self.cache.get(core) if (mode == "fix" and "\n" not in core) else None
        if cached is not None:
            fixed, note = lead + cached + trail, " (prepared)"
        else:
            fixed, note = self._run(text, mode)[0], ""
        took = (time.time() - started) * 1000

        if fixed == text:
            print(f"  = left alone ({took:.0f}ms){note}")
            self._schedule_restore(original, 0.05)
            return

        clip.set_text(fixed, private=True)
        seq_after_set = clip.sequence()
        time.sleep(0.03)
        send_ctrl(VK_V)
        play_fix_sound(mode)
        print(f"  ~ [{'POLISHED' if mode == 'polish' else 'FIXED'}] in {took:.0f}ms{note}")
        self._schedule_restore(original, CLIPBOARD_RESTORE_DELAY, only_if_seq=seq_after_set)

    # -- prefetch watcher ---------------------------------------------------------

    def watcher(self):
        reader = None
        last_seen, seen_at, submitted = None, 0.0, None
        while True:
            if not self.prefetch_on.is_set():
                self.prefetch_on.wait()
                last_seen, submitted = None, None
            if reader is None:
                reader = SelectionReader()
                if not reader.ok:
                    return
            time.sleep(POLL_SECONDS)
            current = reader.text()
            if current != last_seen:
                last_seen, seen_at = current, time.time()
                continue
            if (current and MIN_PREFETCH_CHARS <= len(current) <= MAX_PREFETCH_CHARS
                    and "\n" not in current and "\r" not in current
                    and current != submitted and current not in self.cache
                    and time.time() - seen_at >= SETTLE_SECONDS):
                submitted = current
                self.jobs.put(("prefetch", current, time.time()))

    # -- hotkeys (main thread only: RegisterHotKey binds to the calling thread) -----

    def apply_system_hotkeys(self, suspended=False):
        for hid in ALL_HOTKEY_IDS:
            user32.UnregisterHotKey(None, hid)
        errors = []
        if suspended:
            self.hotkey_errors = errors
            return

        def reg(hid, mods, vk, label, report=True):
            if not vk:
                return
            if not user32.RegisterHotKey(None, hid, mods | MOD_NOREPEAT, vk) and report:
                errors.append(f"{label} is already used by another app.")

        cfg = load_config()
        reg(ID_QUIT, MOD_CONTROL | MOD_ALT, VK_Q, "Ctrl+Alt+Q", report=False)
        mode = cfg.get("trigger_mode", "double_tap")
        fallbacks = True
        if mode == "alt_space":
            reg(ID_FIX, MOD_ALT, VK_SPACE, "Alt+Space")
            reg(ID_POLISH, MOD_ALT | MOD_SHIFT, VK_SPACE, "Alt+Shift+Space")
        elif mode == "classic":
            reg(ID_FIX, MOD_CONTROL | MOD_ALT, VK_F, "Ctrl+Alt+F")
            reg(ID_POLISH, MOD_CONTROL | MOD_ALT, VK_P, "Ctrl+Alt+P")
            fallbacks = False
        elif mode == "custom":
            for hid, key in ((ID_FIX, "custom_fix"), (ID_POLISH, "custom_polish")):
                combo = cfg.get(key, "")
                ok, msg = validate_hotkey(combo)
                if not ok:
                    errors.append(f"{combo or 'Shortcut'}: {msg}")
                    continue
                m, v = parse_hotkey_string(combo)
                reg(hid, m & ~MOD_NOREPEAT, v, combo)
        # Ctrl+Alt+F / Ctrl+Alt+P always work as a backup (silently skipped if taken).
        if fallbacks:
            reg(ID_FALLBACK_FIX, MOD_CONTROL | MOD_ALT, VK_F, "Ctrl+Alt+F", report=False)
            reg(ID_FALLBACK_POLISH, MOD_CONTROL | MOD_ALT, VK_P, "Ctrl+Alt+P", report=False)
        if mode == "double_tap" and self.listener is not None and not self.listener.active:
            errors.append("Double-tap detection is unavailable (keyboard hook failed).")
        self.hotkey_errors = errors

    def post_reload(self):
        user32.PostThreadMessageW(self.main_thread_id, WM_APP_RELOAD_HOTKEYS, 0, 0)

    def post_suspend(self, flag):
        user32.PostThreadMessageW(self.main_thread_id, WM_APP_SUSPEND_HOTKEYS, 1 if flag else 0, 0)

    def quit(self):
        user32.PostThreadMessageW(self.main_thread_id, WM_QUIT, 0, 0)

    def _reload_everything(self):
        cfg = load_config()
        if self.listener is not None:
            self.listener.reload(cfg)
        self.apply_system_hotkeys()
        if cfg.get("prefetch_enabled"):
            self.prefetch_on.set()
        else:
            self.prefetch_on.clear()
            self.cache.clear()
        if self.tray:
            self.tray.refresh()

    # -- UI glue ---------------------------------------------------------------------

    def services(self):
        app = self

        class Services:
            platform = "win"

            def fix(self, text, mode="fix"):
                return app.run_fix_sync(text, mode)

            def status(self):
                return app.status()

            def quit(self):
                app.quit()

            def hotkeys_changed(self):
                app.post_reload()

            def hotkey_errors(self):
                return list(app.hotkey_errors)

            def suspend_hotkeys(self, flag):
                if app.listener is not None:
                    app.listener.suspend(flag)
                app.post_suspend(flag)

            def model_changed(self, profile):
                app.request_model_switch(profile)

            def prefs_changed(self):
                app.post_reload()

        return Services()

    def open_dashboard(self):
        if self.ui is None:
            from ui import UIManager
            self.ui = UIManager(self.services())
        self.ui.open_dashboard()

    # -- main ---------------------------------------------------------------------------

    def run(self, show_dashboard, show_startup_toast):
        ensure_single_instance(self.open_dashboard)

        if ENGINE == "embedded":
            profile = load_config().get("model_profile", "3b")
            if not resolve_model(profile):
                from ui import UIManager
                self.ui = UIManager(self.services())
                if not self.ui.run_setup_blocking():
                    print("  [Fixelect] Setup cancelled - exiting.")
                    return
                show_dashboard = False  # setup just finished; don't stack another window

        cfg = load_config()
        if cfg.get("prefetch_enabled"):
            self.prefetch_on.set()

        threading.Thread(target=self.worker, daemon=True, name="fixelect-worker").start()
        threading.Thread(target=self.watcher, daemon=True, name="fixelect-prefetch").start()

        self.listener = WinHotkeyListener(
            on_fix=lambda: self.trigger("fix"),
            on_polish=lambda: self.trigger("polish"),
            config=cfg,
        )
        self.listener.start()
        self.apply_system_hotkeys()

        try:
            from tray import TrayManager
            self.tray = TrayManager(
                on_open_settings=self.open_dashboard,
                on_quit=self.quit,
                on_switch_model=self.request_model_switch,
                get_status=self.status,
            )
            self.tray.start()
            if show_startup_toast:
                def toast():
                    time.sleep(1.5)
                    self.notify("Fixelect is running",
                                f"Fix: {get_hotkey_label('fix')}   •   Polish: {get_hotkey_label('polish')}")
                threading.Thread(target=toast, daemon=True).start()
        except Exception as e:
            print(f"  (Tray disabled: {e})")

        if show_dashboard:
            self.open_dashboard()

        print(f"\n  Engine: {ENGINE.upper()}")
        print(f"  {get_hotkey_label('fix'):<14} fix selected text")
        print(f"  {get_hotkey_label('polish'):<14} polish selected text")
        print("  Ctrl+Alt+Q     quit\n")

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    if msg.wParam == ID_QUIT:
                        break
                    self.trigger("polish" if msg.wParam in (ID_POLISH, ID_FALLBACK_POLISH) else "fix")
                elif msg.message == WM_APP_RELOAD_HOTKEYS:
                    self._reload_everything()
                elif msg.message == WM_APP_SUSPEND_HOTKEYS:
                    self.apply_system_hotkeys(suspended=bool(msg.wParam))
        finally:
            self.shutdown()

    def shutdown(self):
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
        if self.tray:
            self.tray.stop()
        for hid in ALL_HOTKEY_IDS:
            user32.UnregisterHotKey(None, hid)
        snap, _ = self._take_pending_restore()
        if snap is not None:
            clip.restore(snap)
        restore_cursor()
        if self.ui is not None:
            try:
                self.ui.stop()
            except Exception:
                pass
        if ENGINE == "embedded":
            try:
                from engine import get_default_engine
                get_default_engine().stop()
            except Exception:
                pass
        print("bye")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

HELP = """Fixelect - AI Offline Grammar & Executive Polish for Windows

Usage:
  fixelect.py                    Start in the system tray and open the dashboard
  fixelect.py --silent           Start in the tray only (also: --autostart)
  fixelect.py --dashboard        Open the dashboard standalone
  fixelect.py --setup            Open model setup
  fixelect.py "some text"        Fix text in the console
  fixelect.py -p "some text"     Polish text in the console
  fixelect.py --test             Run the self-test suite
  fixelect.py --benchmark        Time a few sentences
"""


def _pop_flag(*names):
    found = False
    for n in names:
        while n in sys.argv:
            sys.argv.remove(n)
            found = True
    return found


def main():
    global MODEL, CANDIDATES, ENGINE

    for i, a in enumerate(sys.argv):
        if a == "--model" and i + 1 < len(sys.argv):
            MODEL = sys.argv[i + 1]
            CANDIDATES = 2 if MODELS.get(MODEL, {}).get("kind") == "ollama" else BEAMS
            del sys.argv[i:i + 2]
            break
    for a in list(sys.argv):
        if a.startswith("--engine="):
            ENGINE = a.split("=", 1)[1]
            sys.argv.remove(a)
    if _pop_flag("--ollama"):
        ENGINE = "ollama"
    if _pop_flag("--embedded"):
        ENGINE = "embedded"
    _pop_flag("--no-sound", "--background", "--hide")

    if _pop_flag("--help", "-h"):
        print(HELP)
        return

    if _pop_flag("--download"):
        from downloader import download_model
        download_model(profile=load_config().get("model_profile", "3b"))
        return

    if _pop_flag("--setup"):
        from ui import run_standalone
        run_standalone("setup")
        return

    if _pop_flag("--dashboard", "--settings"):
        from ui import run_standalone
        run_standalone("dashboard")
        return

    polish_mode = _pop_flag("--polish", "-p")

    if _pop_flag("--benchmark"):
        fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
        for s in [
            "helo how are you im fne wht abt you",
            "to behonst its kinda really strannge an i don know what s hapenning",
            "tobehonest its kinda really difficult to change someint in that isutation and you can do that too",
            "The MT300 SWIFT message failed validation in the PLSQL package.",
        ]:
            t0 = time.time()
            out, _, _ = fix_preserving_layout(s, lambda t: fix(t, mode="fix"))
            print(f"\nIn:    {s}\nOut:   {out}\nSpeed: {(time.time() - t0) * 1000:.1f}ms")
        return

    if _pop_flag("--test"):
        sys.exit(0 if run_self_tests() else 1)

    is_silent = _pop_flag("--silent")
    is_autostart = _pop_flag("--autostart")
    _pop_flag("--no-tray")
    no_dashboard = _pop_flag("--no-dashboard")

    args = sys.argv[1:]
    if args and args[0] == "--raw":
        args = args[1:]
    if args:
        text = " ".join(args)
        fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
        mode = "polish" if polish_mode else "fix"
        started = time.time()
        fixed, _, _ = fix_preserving_layout(text, lambda t: fix(t, mode=mode), mode=mode)
        print(f"\n  mode: {mode.upper()}\n  in  : {text}\n  out : {fixed}\n  {(time.time() - started) * 1000:.0f}ms")
        return

    FixelectApp().run(
        show_dashboard=not (is_silent or is_autostart or no_dashboard),
        show_startup_toast=is_autostart or is_silent,
    )


def run_self_tests():
    print(f"Running Fixelect self-tests with engine [{ENGINE.upper()}]...")
    fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
    from check_guard import normalise, expand
    all_passed = True

    def report(ok, line):
        nonlocal all_passed
        all_passed &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {line}")

    print("\n--- [1/3] Guard rules (no model) ---")
    for inp, exp in [("enter your user id", "enter your user id"), ("i feel ill", "I feel ill"),
                     ("she lets me go", "she lets me go"), ("im fne", "I'm fine")]:
        out = expand(inp)
        report(out == exp, f"expand({inp!r}) -> {out!r}")
    for inp, exp in [("  hello  ", ("  ", "hello", "  ")), ("x", ("", "x", ""))]:
        report(_split_edges(inp) == exp, f"edges({inp!r})")

    print("\n--- [2/3] Default Fix Mode ---")
    for inp, exp in [
        ("your welcome", "you're welcome"),
        ("i cant seem too focus on the the task", "I can't seem to focus on the task"),
        ("better then that", "better than that"),
        ("helo how are you", "hello how are you"),
        ("tobehonest its kinda really difficult to change someint in that isutation and you can do that too",
         "to be honest it's kind of really difficult to change something in that situation and you can do that too"),
        ("This sentence is perfectly fine already.", "This sentence is perfectly fine already."),
        ("- helo world\n- im fne", "- hello world\n- I'm fine"),
    ]:
        out, _, _ = fix_preserving_layout(inp, lambda t: fix(t, mode="fix"))
        report(normalise(out) == normalise(exp), f"{inp.replace(chr(10), ' | ')!r} -> {out.replace(chr(10), ' | ')!r}")
    out, _, _ = fix_preserving_layout("helo world ", lambda t: fix(t, mode="fix"))
    report(out.endswith(" "), f"trailing space kept -> {out!r}")

    print("\n--- [3/3] Professional Polish Mode ---")
    for inp, required in [
        ("tobehonest i think we need to change someint in that isutation cause it looks bad", ["situation", "honest"]),
        ("The MT300 SWIFT message failed validation in the PLSQL package.", ["MT300", "SWIFT", "PLSQL"]),
        ("im rly sorry for the delay i was stuck in traffic and my phone died so i couldnt email you earlier",
         ["delay", "traffic"]),
    ]:
        out, _, _ = fix_preserving_layout(inp, lambda t: fix(t, mode="polish"), mode="polish")
        report(all(tok.lower() in out.lower() for tok in required), f"{inp!r}\n       -> {out!r}")

    print(f"\nSelf-tests {'PASSED ALL CHECKS' if all_passed else 'HAD FAILURES'}.")
    return all_passed


if __name__ == "__main__":
    main()
