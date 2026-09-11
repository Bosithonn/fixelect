"""
macOS global triggers for Fixelect and the Accessibility permission check.

    Option  x2 (⌥ ⌥)  -> Fix
    Control x2 (⌃ ⌃)  -> Polish
    Presets: ⌥ Space / ⌥⇧ Space, ⌘⌥F / ⌘⌥P, or custom combinations.

There is deliberately NO global quit shortcut: pynput cannot swallow keys on
macOS, so the old ⌘⌥Q also reached the frontmost app - where ⌘Q quits it.
Quit lives in the menu bar instead.
"""

import subprocess
import sys
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
    from config_mac import load_config
except ImportError:  # pragma: no cover
    def load_config():
        return {"trigger_mode": "double_tap"}


def check_accessibility_permissions(prompt: bool = False) -> bool:
    """True if this app may observe the keyboard. prompt=True shows Apple's dialog once."""
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


class _Tap:
    __slots__ = ("down_at", "spoiled", "last_tap_at")

    def __init__(self):
        self.down_at = 0.0
        self.spoiled = False
        self.last_tap_at = 0.0

    def reset(self):
        self.down_at, self.spoiled, self.last_tap_at = 0.0, False, 0.0


class MacHotkeyListener:
    DOUBLE_TAP_MAX_INTERVAL = 0.40
    TAP_MAX_HOLD = 0.32
    STALE_PRESS = 2.0

    def __init__(self, on_fix: Callable, on_polish: Callable,
                 on_quit: Optional[Callable] = None, config: Optional[dict] = None):
        self.on_fix = on_fix
        self.on_polish = on_polish
        self.on_quit = on_quit  # kept for API compatibility; no global quit key
        self.config = config or load_config()
        self.listener = None
        self._lock = threading.RLock()
        self._suspended = False
        self._opt = _Tap()
        self._ctrl = _Tap()

    @property
    def active(self):
        return self.listener is not None

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
        self._suspended = bool(flag)
        self._opt.reset()
        self._ctrl.reset()

    def _start_unlocked(self) -> bool:
        if not _has_pynput:
            print("  ! pynput not installed - global triggers unavailable")
            return False
        mode = self.config.get("trigger_mode", "double_tap")
        try:
            if mode == "double_tap":
                self._opt.reset()
                self._ctrl.reset()
                self.listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
            else:
                combos = {}
                if mode == "option_space":
                    combos["<alt>+<space>"] = lambda: self._fire(self.on_fix)
                    combos["<alt>+<shift>+<space>"] = lambda: self._fire(self.on_polish)
                elif mode == "classic":
                    combos["<cmd>+<alt>+f"] = lambda: self._fire(self.on_fix)
                    combos["<cmd>+<alt>+p"] = lambda: self._fire(self.on_polish)
                elif mode == "custom":
                    for key, cb in (("custom_fix", self.on_fix), ("custom_polish", self.on_polish)):
                        combo = self._normalize_combo(self.config.get(key, ""))
                        if combo:
                            combos[combo] = (lambda c=cb: self._fire(c))
                if not combos:
                    return True
                self.listener = keyboard.GlobalHotKeys(combos)
            self.listener.daemon = True
            self.listener.start()
            return True
        except Exception as e:
            print(f"  ! could not start hotkey listener ({mode}): {e}")
            self.listener = None
            return False

    def _stop_unlocked(self):
        if self.listener is not None:
            try:
                self.listener.stop()
            except Exception:
                pass
            self.listener = None

    @staticmethod
    def _normalize_combo(combo: str) -> str:
        """'Cmd+Option+F' / '<cmd>+<alt>+f' -> pynput's '<cmd>+<alt>+f'."""
        names = {
            "command": "<cmd>", "cmd": "<cmd>", "option": "<alt>", "opt": "<alt>", "alt": "<alt>",
            "control": "<ctrl>", "ctrl": "<ctrl>", "shift": "<shift>", "space": "<space>",
        }
        out = []
        for t in (combo or "").lower().replace(" ", "").split("+"):
            t = t.strip("<>")
            if not t:
                continue
            if t in names:
                out.append(names[t])
            elif len(t) > 1 and t[0] == "f" and t[1:].isdigit():
                out.append(f"<{t}>")
            else:
                out.append(t)
        return "+".join(out)

    # -- double-tap -----------------------------------------------------------

    @staticmethod
    def _kind(key):
        if key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r):
            return "opt"
        if key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            return "ctrl"
        return "other"

    def _on_press(self, key, injected=False):
        if injected or self._suspended:
            return
        now = time.monotonic()
        kind = self._kind(key)
        for name, tap in (("opt", self._opt), ("ctrl", self._ctrl)):
            if kind == name:
                if tap.down_at == 0.0 or now - tap.down_at > self.STALE_PRESS:
                    tap.down_at, tap.spoiled = now, False
            elif tap.down_at:
                tap.spoiled = True       # chord such as ⌥E or ⌃⌥
            else:
                tap.last_tap_at = 0.0    # typing between taps breaks the sequence

    def _on_release(self, key, injected=False):
        if injected or self._suspended:
            return
        kind = self._kind(key)
        if kind == "opt" and self._register(self._opt):
            self._fire(self.on_fix)
        elif kind == "ctrl" and self._register(self._ctrl):
            self._fire(self.on_polish)

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
