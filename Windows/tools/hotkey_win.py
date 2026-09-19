"""
Double-tap modifier detection for Fixelect on Windows.

    Alt   x2  -> Fix
    Ctrl  x2  -> Polish
    Shift x2  -> quick-action menu (the default menu shortcut, in every trigger mode)

Only double-taps need a low-level keyboard hook. Every key *combination*
(Alt+Space, Ctrl+Alt+F, custom shortcuts, Ctrl+Alt+Q, a custom menu shortcut)
is registered with Win32 RegisterHotKey by the main thread instead, which
swallows the keystroke and cannot fire twice. Running pynput for those too
made every combo trigger two jobs, and in editors that copy the whole line on
an empty Ctrl+C the second job duplicated the line into the document.

A double-tap can't be taken by another app the way a combination can (the
1.2.0 menu shortcut, Ctrl+Alt+Space, belongs to the Claude app). Typing
capitals or Shift-clicking a selection never counts: a key or a click between
the taps cancels them.
"""

import collections
import threading
import time
from typing import Callable, Optional

try:
    from pynput import keyboard, mouse
    _has_pynput = True
except ImportError:
    keyboard = mouse = None
    _has_pynput = False

try:
    from config import load_config, get_menu_hotkey, MENU_DOUBLE_SHIFT
except ImportError:  # pragma: no cover
    MENU_DOUBLE_SHIFT = "double_shift"

    def load_config():
        return {"trigger_mode": "double_tap"}

    def get_menu_hotkey(config=None):
        return MENU_DOUBLE_SHIFT

_ALT_VKS = {18, 164, 165}
_CTRL_VKS = {17, 162, 163}
_SHIFT_VKS = {16, 160, 161}


class _Tap:
    """State for one modifier: pressed alone, released quickly, twice in a row."""

    __slots__ = ("down_at", "spoiled", "last_tap_at")

    def __init__(self):
        self.down_at = 0.0
        self.spoiled = False
        self.last_tap_at = 0.0

    def reset(self):
        self.down_at = 0.0
        self.spoiled = False
        self.last_tap_at = 0.0


class WinHotkeyListener:
    DOUBLE_TAP_MAX_INTERVAL = 0.45  # seconds between the two releases
    TAP_MAX_HOLD = 0.35             # longer than this is a hold, not a tap
    STALE_PRESS = 2.0               # a press this old means we missed its release

    def __init__(self, on_fix: Callable, on_polish: Callable,
                 on_quit: Optional[Callable] = None, config: Optional[dict] = None,
                 on_menu: Optional[Callable] = None):
        self.on_fix = on_fix
        self.on_polish = on_polish
        self.on_menu = on_menu
        self.on_quit = on_quit  # Ctrl+Alt+Q is handled by RegisterHotKey; kept for API compatibility
        self.config = config or load_config()
        self.listener = None
        self.mouse_listener = None
        self._lock = threading.RLock()
        self._suspended = False
        self._alt = _Tap()
        self._ctrl = _Tap()
        self._shift = _Tap()
        self._fix_taps = False      # Alt Alt / Ctrl Ctrl (the "double_tap" trigger mode)
        self._menu_tap = False      # Shift Shift (menu shortcut "double_shift")
        # Windows' own time for each key, recorded as it arrives (see _stamp)
        self._stamps = collections.deque(maxlen=64)
        self._configure()

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> bool:
        with self._lock:
            return self._start_unlocked()

    def stop(self):
        with self._lock:
            self._stop_unlocked()

    def reload(self, new_config: Optional[dict] = None) -> bool:
        with self._lock:
            self._stop_unlocked()
            self.config = new_config or load_config()
            return self._start_unlocked()

    def suspend(self, flag: bool):
        """Ignore taps while the user is recording a shortcut in the dashboard."""
        self._suspended = bool(flag)
        for tap in (self._alt, self._ctrl, self._shift):
            tap.reset()

    @property
    def active(self) -> bool:
        return self.listener is not None

    @property
    def needed(self) -> bool:
        """Whether any double-tap is in use (so the hook must be running)."""
        return self._fix_taps or self._menu_tap

    def _configure(self):
        self._fix_taps = self.config.get("trigger_mode", "double_tap") == "double_tap"
        self._menu_tap = self.on_menu is not None and get_menu_hotkey(self.config) == MENU_DOUBLE_SHIFT
        for tap in (self._alt, self._ctrl, self._shift):
            tap.reset()

    def _start_unlocked(self) -> bool:
        self._configure()
        if not self.needed:
            return True  # combos are RegisterHotKey's job
        if not _has_pynput:
            print("  ! pynput not installed - double-tap triggers unavailable")
            return False
        try:
            self._stamps.clear()
            self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release,
                                              win32_event_filter=self._stamp)
            self.listener.daemon = True
            self.listener.start()
        except Exception as e:
            print(f"  ! could not start double-tap listener: {e}")
            self.listener = None
            return False
        if self._menu_tap:
            try:   # a click between two Shift taps (Shift-click selecting) cancels them
                self.mouse_listener = mouse.Listener(on_click=self._on_click)
                self.mouse_listener.daemon = True
                self.mouse_listener.start()
            except Exception:
                self.mouse_listener = None
        return True

    def _stop_unlocked(self):
        for name in ("listener", "mouse_listener"):
            lst = getattr(self, name)
            if lst is not None:
                try:
                    lst.stop()
                except Exception:
                    pass
                setattr(self, name, None)

    # -- key classification --------------------------------------------------

    @staticmethod
    def _kind(key):
        if _has_pynput:
            if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                return "alt"
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                return "ctrl"
            if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r):
                return "shift"
        vk = getattr(key, "vk", None)
        if vk in _ALT_VKS:
            return "alt"
        if vk in _CTRL_VKS:
            return "ctrl"
        if vk in _SHIFT_VKS:
            return "shift"
        return "other"  # includes AltGr, which Windows reports as Ctrl+AltGr

    # -- callbacks (run on pynput's hook thread: keep them tiny) --------------

    def _stamp(self, msg, data):
        """pynput's event filter: runs in the hook the moment each key arrives.
        Timing taps by Windows' own time (ms since boot, like time.monotonic)
        instead of when the callback runs keeps a quick double-tap reliable
        while the PC is busy, e.g. loading the model right after start-up."""
        self._stamps.append(data.time / 1000.0)
        return True

    def _event_time(self):
        """The time of the key being handled (one stamp per key, in order)."""
        try:
            return self._stamps.popleft()
        except IndexError:
            return time.monotonic()

    def _on_press(self, key, injected=False):
        now = self._event_time()     # consume the stamp even for ignored keys
        if injected or self._suspended:
            return
        kind = self._kind(key)
        for name, tap in (("alt", self._alt), ("ctrl", self._ctrl), ("shift", self._shift)):
            if kind == name:
                if tap.down_at == 0.0 or now - tap.down_at > self.STALE_PRESS:
                    tap.down_at = now
                    tap.spoiled = False
                # auto-repeat of a held modifier: keep the original down time
            elif tap.down_at:
                # Any other key while this modifier is held makes it a chord
                # (Alt+Tab, Ctrl+C, Shift+A, Ctrl+Alt, AltGr...), never a tap.
                tap.spoiled = True
            else:
                # Typing between two taps breaks the sequence.
                tap.last_tap_at = 0.0

    def _on_release(self, key, injected=False):
        now = self._event_time()
        if injected or self._suspended:
            return
        kind = self._kind(key)
        if kind == "alt":
            if self._register_tap(self._alt, now) and self._fix_taps:
                self._fire(self.on_fix)
        elif kind == "ctrl":
            if self._register_tap(self._ctrl, now) and self._fix_taps:
                self._fire(self.on_polish)
        elif kind == "shift":
            if self._register_tap(self._shift, now) and self._menu_tap:
                self._fire(self.on_menu)

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        for tap in (self._alt, self._ctrl, self._shift):
            if tap.down_at:
                tap.spoiled = True       # Shift-click, Ctrl-click: a chord
            else:
                tap.last_tap_at = 0.0    # a click between taps breaks the sequence

    def _register_tap(self, tap: _Tap, now: float) -> bool:
        clean = tap.down_at and not tap.spoiled and (now - tap.down_at) <= self.TAP_MAX_HOLD
        tap.down_at = 0.0
        tap.spoiled = False
        if not clean:
            tap.last_tap_at = 0.0
            return False
        if tap.last_tap_at and now - tap.last_tap_at <= self.DOUBLE_TAP_MAX_INTERVAL:
            tap.last_tap_at = 0.0
            return True
        tap.last_tap_at = now
        return False

    @staticmethod
    def _fire(cb):
        if cb:
            threading.Thread(target=cb, daemon=True).start()
