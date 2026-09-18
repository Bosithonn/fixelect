"""
Double-tap modifier detection for Fixelect on Windows.

    Alt  x2  -> Fix
    Ctrl x2  -> Polish

Only the double-tap trigger needs a low-level keyboard hook. Every key
*combination* (Alt+Space, Ctrl+Alt+F, custom shortcuts, Ctrl+Alt+Q) is
registered with Win32 RegisterHotKey by the main thread instead, which
swallows the keystroke and cannot fire twice. Running pynput for those too
made every combo trigger two jobs, and in editors that copy the whole line on
an empty Ctrl+C the second job duplicated the line into the document.
"""

import collections
import threading
import time
from typing import Callable, Optional

try:
    from pynput import keyboard
    _has_pynput = True
except ImportError:
    keyboard = None
    _has_pynput = False

try:
    from config import load_config
except ImportError:  # pragma: no cover
    def load_config():
        return {"trigger_mode": "double_tap"}

_ALT_VKS = {18, 164, 165}
_CTRL_VKS = {17, 162, 163}


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
                 on_quit: Optional[Callable] = None, config: Optional[dict] = None):
        self.on_fix = on_fix
        self.on_polish = on_polish
        self.on_quit = on_quit  # Ctrl+Alt+Q is handled by RegisterHotKey; kept for API compatibility
        self.config = config or load_config()
        self.listener = None
        self._lock = threading.RLock()
        self._suspended = False
        self._alt = _Tap()
        self._ctrl = _Tap()
        # Windows' own time for each key, recorded as it arrives (see _stamp)
        self._stamps = collections.deque(maxlen=64)

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
        self._alt.reset()
        self._ctrl.reset()

    @property
    def active(self) -> bool:
        return self.listener is not None

    def _start_unlocked(self) -> bool:
        if self.config.get("trigger_mode", "double_tap") != "double_tap":
            return True  # combos are RegisterHotKey's job
        if not _has_pynput:
            print("  ! pynput not installed - double-tap triggers unavailable")
            return False
        try:
            self._alt.reset()
            self._ctrl.reset()
            self._stamps.clear()
            self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release,
                                              win32_event_filter=self._stamp)
            self.listener.daemon = True
            self.listener.start()
            return True
        except Exception as e:
            print(f"  ! could not start double-tap listener: {e}")
            self.listener = None
            return False

    def _stop_unlocked(self):
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None

    # -- key classification --------------------------------------------------

    @staticmethod
    def _kind(key):
        if _has_pynput:
            if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
                return "alt"
            if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
                return "ctrl"
        vk = getattr(key, "vk", None)
        if vk in _ALT_VKS:
            return "alt"
        if vk in _CTRL_VKS:
            return "ctrl"
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
        for name, tap in (("alt", self._alt), ("ctrl", self._ctrl)):
            if kind == name:
                if tap.down_at == 0.0 or now - tap.down_at > self.STALE_PRESS:
                    tap.down_at = now
                    tap.spoiled = False
                # auto-repeat of a held modifier: keep the original down time
            elif tap.down_at:
                # Any other key while this modifier is held makes it a chord
                # (Alt+Tab, Ctrl+C, Ctrl+Alt, AltGr...), never a tap.
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
            if self._register_tap(self._alt, now):
                self._fire(self.on_fix)
        elif kind == "ctrl":
            if self._register_tap(self._ctrl, now):
                self._fire(self.on_polish)

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
