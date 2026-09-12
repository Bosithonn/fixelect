"""
macOS global triggers for Fixelect and the Accessibility permission check.

    Option x2 (⌥ ⌥)  -> Fix
    Shift  x2 (⇧ ⇧)  -> Polish   (not ⌃ ⌃: that is macOS's Dictation shortcut)
    Presets: ⌥ Space / ⌥⇧ Space, ⌘⌥F / ⌘⌥P, or custom combinations.

All triggers run on Fixelect's own Quartz event tap instead of pynput's:
- it is an active tap, which needs only Accessibility. pynput's listen-only tap
  also needs Input Monitoring, which Fixelect never asked for, so the
  double-tap silently never fired;
- macOS disables a tap after a slow callback or during secure input; the tap
  re-enables itself, and a watchdog recreates it (e.g. once Accessibility is
  granted);
- only Fixelect's own synthetic keys (Cmd+C / Cmd+V) are ignored, so key
  events from other processes - including the end-to-end test - count;
- shortcut keys are swallowed, so ⌥Space no longer types a space in the app;
- a key press or mouse click between two taps cancels the double-tap, so
  typing capitals or Shift-clicking a selection never triggers Polish.

There is deliberately NO global quit shortcut; Quit lives in the menu bar.
"""

import os
import subprocess
import sys
import threading
import time
from typing import Callable, Optional

try:
    import Quartz
    _has_quartz = True
except ImportError:  # pragma: no cover - not macOS
    Quartz = None
    _has_quartz = False

try:
    from config_mac import load_config
except ImportError:  # pragma: no cover
    def load_config():
        return {"trigger_mode": "double_tap"}

_SHIFT, _CTRL, _OPT, _CMD = 0x20000, 0x40000, 0x80000, 0x100000   # kCGEventFlagMask*
_MODS = _SHIFT | _CTRL | _OPT | _CMD
_ESC = 53
_MOUSE_DOWN = (1, 3, 25)   # kCGEventLeftMouseDown, RightMouseDown, OtherMouseDown

# ANSI virtual key codes for custom shortcuts
_KEYCODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11,
    "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21,
    "6": 22, "5": 23, "=": 24, "9": 25, "7": 26, "-": 27, "8": 28, "0": 29, "]": 30, "o": 31,
    "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38, "'": 39, "k": 40, ";": 41, "\\": 42,
    ",": 43, "/": 44, "n": 45, "m": 46, ".": 47, "`": 50, "space": 49, "return": 36, "tab": 48,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100,
    "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}
_MOD_NAMES = {"cmd": _CMD, "alt": _OPT, "ctrl": _CTRL, "shift": _SHIFT}


def check_accessibility_permissions(prompt: bool = False) -> bool:
    """True if this app may watch and send keys. prompt=True shows Apple's dialog and
    adds Fixelect to the Accessibility list, so the user only has to flip the switch."""
    if sys.platform != "darwin":
        return True
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: bool(prompt)}))
    except Exception:
        pass
    try:
        from ApplicationServices import AXIsProcessTrusted
        return bool(AXIsProcessTrusted())
    except Exception:
        pass
    try:
        res = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to return UI elements enabled'],
            capture_output=True, text=True, timeout=2.0,
        )
        return "true" in res.stdout.lower()
    except Exception:
        return True  # cannot tell; don't nag


def parse_combo(combo: str):
    """'<cmd>+<alt>+f' / 'Cmd+Option+F' -> (modifier flags, key code), or None."""
    names = {"command": "cmd", "option": "alt", "opt": "alt", "control": "ctrl"}
    mods, code = 0, None
    for t in (combo or "").lower().replace(" ", "").split("+"):
        t = names.get(t.strip("<>"), t.strip("<>"))
        if not t:
            continue
        if t in _MOD_NAMES:
            mods |= _MOD_NAMES[t]
        elif t in _KEYCODES:
            code = _KEYCODES[t]
        else:
            return None
    return (mods, code) if mods and code is not None else None


class _Tap:
    __slots__ = ("down_at", "spoiled", "last_tap_at")

    def __init__(self):
        self.down_at = 0.0
        self.spoiled = False
        self.last_tap_at = 0.0

    def reset(self):
        self.down_at, self.spoiled, self.last_tap_at = 0.0, False, 0.0


class _KeyTap:
    """An active keyboard event tap on its own run-loop thread."""

    def __init__(self, on_flags, on_key):
        self.on_flags, self.on_key = on_flags, on_key
        self.tap = None
        self._loop = None
        self._thread = None
        self._ready = threading.Event()
        self._pid = os.getpid()
        self._callback_ref = self._callback   # PyObjC must keep the callback alive

    def start(self) -> bool:
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="fixelect-keytap", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)
        return self.tap is not None

    def healthy(self) -> bool:
        return (self.tap is not None and self._thread is not None and self._thread.is_alive()
                and bool(Quartz.CGEventTapIsEnabled(self.tap)))

    def stop(self):
        tap, loop = self.tap, self._loop
        self.tap, self._loop = None, None
        try:
            if tap is not None:
                Quartz.CGEventTapEnable(tap, False)
                Quartz.CFMachPortInvalidate(tap)
            if loop is not None:
                Quartz.CFRunLoopStop(loop)
        except Exception:
            pass

    def _callback(self, proxy, etype, event, refcon):
        try:
            if etype in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
                if self.tap is not None:
                    Quartz.CGEventTapEnable(self.tap, True)
                return event
            if Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID) == self._pid:
                return event   # our own Cmd+C / Cmd+V
            if etype == Quartz.kCGEventFlagsChanged:
                self.on_flags(int(Quartz.CGEventGetFlags(event)))
            elif etype in _MOUSE_DOWN:
                self.on_key(-1, int(Quartz.CGEventGetFlags(event)), False)   # a click, e.g. ⇧-click
            elif etype == Quartz.kCGEventKeyDown:
                code = int(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode))
                repeat = bool(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat))
                if self.on_key(code, int(Quartz.CGEventGetFlags(event)), repeat):
                    return None   # a Fixelect shortcut: don't also type it into the app
        except Exception:
            pass
        return event

    def _run(self):
        try:
            mask = (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
                    | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged))
            for etype in _MOUSE_DOWN:
                mask |= Quartz.CGEventMaskBit(etype)
            self.tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                               Quartz.kCGEventTapOptionDefault, mask, self._callback_ref, None)
            if self.tap is None:   # no Accessibility permission (yet)
                return
            source = Quartz.CFMachPortCreateRunLoopSource(None, self.tap, 0)
            self._loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(self._loop, source, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(self.tap, True)
            self._ready.set()
            Quartz.CFRunLoopRun()
        except Exception as e:
            print(f"  ! keyboard tap failed: {e}")
            self.tap = None
        finally:
            self._ready.set()


class MacHotkeyListener:
    DOUBLE_TAP_MAX_INTERVAL = 0.40
    TAP_MAX_HOLD = 0.32
    STALE_PRESS = 2.0
    WATCHDOG_SECONDS = 3.0

    def __init__(self, on_fix: Callable, on_polish: Callable,
                 on_quit: Optional[Callable] = None, config: Optional[dict] = None):
        self.on_fix = on_fix
        self.on_polish = on_polish
        self.on_quit = on_quit  # kept for API compatibility; no global quit key
        self.config = config or load_config()
        self._lock = threading.RLock()
        self._suspended = False
        self._running = False
        self._keytap = None
        self._flags = 0
        self._opt = _Tap()
        self._shift = _Tap()
        self._combos = {}
        self._escape = None
        self._capture = None
        self._watchdog = None

    # -- public API -------------------------------------------------------------

    @property
    def active(self):
        """True while the keyboard tap is actually receiving keys."""
        return self._keytap is not None and self._keytap.healthy()

    def start(self) -> bool:
        with self._lock:
            self._running = True
            self._configure()
            ok = self._open_tap()
            if self._watchdog is None or not self._watchdog.is_alive():
                self._watchdog = threading.Thread(target=self._watch, name="fixelect-keytap-watchdog", daemon=True)
                self._watchdog.start()
            if not ok:
                print("  [Fixelect] Waiting for Accessibility access before listening for shortcuts.")
            return ok

    def stop(self):
        with self._lock:
            self._running = False
            self._close_tap()

    def reload(self, new_config: Optional[dict] = None) -> bool:
        with self._lock:
            self.config = new_config or load_config()
            self._configure()
            if not self.active:
                self._close_tap()
                return self._open_tap()
            return True

    def suspend(self, flag: bool):
        self._suspended = bool(flag)
        self._opt.reset()
        self._shift.reset()

    def watch_escape(self, callback: Optional[Callable]):
        """Call `callback` when Esc is pressed (None stops watching)."""
        self._escape = callback

    def capture_keys(self, handler: Optional[Callable]):
        """Offer every key press to handler(code, flags) first; True swallows it (None stops).

        The Polish preview uses this: macOS 14+ won't let a background app take the
        keyboard, so Return would otherwise land in the user's document."""
        self._capture = handler

    # -- tap lifecycle ----------------------------------------------------------

    def _configure(self):
        mode = self.config.get("trigger_mode", "double_tap")
        combos = {}
        if mode == "option_space":
            combos = {"<alt>+<space>": self.on_fix, "<alt>+<shift>+<space>": self.on_polish}
        elif mode == "classic":
            combos = {"<cmd>+<alt>+f": self.on_fix, "<cmd>+<alt>+p": self.on_polish}
        elif mode == "custom":
            combos = {self.config.get("custom_fix", ""): self.on_fix,
                      self.config.get("custom_polish", ""): self.on_polish}
        self._combos = {}
        for text, cb in combos.items():
            parsed = parse_combo(text)
            if parsed:
                self._combos[parsed] = cb
        self._double_tap = mode == "double_tap"
        self._opt.reset()
        self._shift.reset()

    def _open_tap(self) -> bool:
        if not _has_quartz:
            print("  ! Quartz is not available - global triggers unavailable")
            return False
        self._keytap = _KeyTap(self._on_flags, self._on_key)
        if self._keytap.start():
            self._flags = 0
            return True
        self._keytap = None
        return False

    def _close_tap(self):
        if self._keytap is not None:
            self._keytap.stop()
            self._keytap = None

    def _watch(self):
        """Recreate the tap if macOS dropped it or permission arrived later."""
        while True:
            time.sleep(self.WATCHDOG_SECONDS)
            with self._lock:
                if not self._running:
                    return
                if self._keytap is not None and self._keytap.healthy():
                    continue
                self._close_tap()
                if self._open_tap():
                    print("  [Fixelect] Keyboard shortcuts are active.")

    # -- key handling (called on the tap thread: keep it quick) -----------------

    def _on_flags(self, flags):
        pressed = flags & ~self._flags
        released = self._flags & ~flags
        self._flags = flags
        if self._suspended or not self._double_tap:
            return
        now = time.monotonic()
        for bit, tap, cb in ((_OPT, self._opt, self.on_fix), (_SHIFT, self._shift, self.on_polish)):
            if pressed & bit:
                if tap.down_at == 0.0 or now - tap.down_at > self.STALE_PRESS:
                    tap.down_at = now
                tap.spoiled = bool(flags & _MODS & ~bit)   # held together with another modifier
            elif released & bit:
                if self._register(tap):
                    self._fire(cb)
            elif pressed & _MODS:
                if tap.down_at:
                    tap.spoiled = True       # chord such as ⌃⌥
                else:
                    tap.last_tap_at = 0.0    # another modifier between taps breaks the sequence

    def _on_key(self, code, flags, repeat) -> bool:
        capture = self._capture
        if capture is not None and not repeat:
            try:
                if capture(code, flags):
                    return True
            except Exception:
                pass
        if code == _ESC and self._escape is not None:
            self._fire(self._escape)
        if self._suspended:
            return False
        for tap in (self._opt, self._shift):
            if tap.down_at:
                tap.spoiled = True           # a chord such as ⌥E
            else:
                tap.last_tap_at = 0.0        # typing between taps breaks the sequence
        cb = self._combos.get((flags & _MODS, code))
        if cb is None:
            return False
        if not repeat:
            self._fire(cb)
        return True

    def _register(self, tap) -> bool:
        now = time.monotonic()
        clean = tap.down_at and not tap.spoiled and (now - tap.down_at) <= self.TAP_MAX_HOLD
        tap.down_at, tap.spoiled = 0.0, False
        if not clean:
            tap.last_tap_at = 0.0
            return False
        if tap.last_tap_at and now - tap.last_tap_at <= self.DOUBLE_TAP_MAX_INTERVAL:
            tap.last_tap_at = 0.0
            return True
        tap.last_tap_at = now
        return False

    def _fire(self, cb):
        if cb and not self._suspended:
            threading.Thread(target=cb, daemon=True).start()
