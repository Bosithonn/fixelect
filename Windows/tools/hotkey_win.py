"""
Windows Global Hotkey Dispatcher and Trigger Manager for Fixelect.
Supports:
- Default Double-Tap Modifiers:
    Alt x2 (Alt Alt)   -> Default Fix Mode (Effortless 1-hand thumb trigger)
    Ctrl x2 (Ctrl Ctrl) -> Professional Polish Mode
- Alt + Space preset (Alt+Space Fix / Alt+Shift+Space Polish)
- Classic 3-Key preset (Ctrl+Alt+F Fix / Ctrl+Alt+P Polish / Ctrl+Alt+Q Quit)
- Fully customizable user shortcuts
- Non-blocking background listener with live config reloading
"""

import sys
import threading
import time
from typing import Optional, Callable

try:
    from pynput import keyboard
    _has_pynput = True
except ImportError:
    _has_pynput = False

# Import config helpers
try:
    from config import load_config
except ImportError:
    def load_config():
        return {
            "trigger_mode": "double_tap",
            "hotkey_fix": "double_alt",
            "hotkey_polish": "double_control",
            "custom_fix": "<ctrl>+<alt>+f",
            "custom_polish": "<ctrl>+<alt>+p",
        }


class WinHotkeyListener:
    """
    Background global hotkey dispatcher for Windows.
    Supports double-tap modifiers (Alt x2, Ctrl x2) as well as
    standard hotkey combinations and custom user-defined shortcuts.
    """

    DOUBLE_TAP_MAX_INTERVAL = 0.38  # max seconds between consecutive taps
    TAP_MAX_HOLD = 0.32             # max duration a modifier can be held to count as a tap

    def __init__(self, on_fix: Callable, on_polish: Callable, on_quit: Optional[Callable] = None, config: Optional[dict] = None):
        self.on_fix = on_fix
        self.on_polish = on_polish
        self.on_quit = on_quit
        self.config = config or load_config()
        self.listener = None
        self._running = False
        self._lock = threading.Lock()

        # Double-tap tracking state
        self._active_keys = set()
        self._non_modifier_pressed = False
        self._alt_press_time = 0.0
        self._last_alt_release_time = 0.0
        self._ctrl_press_time = 0.0
        self._last_ctrl_release_time = 0.0

    def start(self) -> bool:
        if not _has_pynput:
            print("  ! warning: pynput module not installed. Global hotkeys unavailable.")
            return False
        return self._start_listener()

    def stop(self):
        with self._lock:
            if self.listener:
                try:
                    self.listener.stop()
                except Exception:
                    pass
                self.listener = None
            self._running = False
            self._active_keys.clear()

    def reload(self, new_config: Optional[dict] = None) -> bool:
        """Dynamically reload hotkeys with updated configuration without restarting daemon."""
        with self._lock:
            self.stop()
            if new_config:
                self.config = new_config
            else:
                self.config = load_config()
            return self._start_listener()

    def _start_listener(self) -> bool:
        trigger_mode = self.config.get("trigger_mode", "double_tap")

        try:
            if trigger_mode == "double_tap":
                self.listener = keyboard.Listener(
                    on_press=self._on_dt_press,
                    on_release=self._on_dt_release
                )
                self.listener.start()
                self._running = True
                return True
            else:
                hotkey_map = {}
                if trigger_mode == "alt_space":
                    hotkey_map["<alt>+<space>"] = self._handle_fix
                    hotkey_map["<alt>+<shift>+<space>"] = self._handle_polish
                elif trigger_mode == "classic":
                    hotkey_map["<ctrl>+<alt>+f"] = self._handle_fix
                    hotkey_map["<ctrl>+<alt>+p"] = self._handle_polish
                elif trigger_mode == "custom":
                    fix_key = self._normalize_combo(self.config.get("custom_fix", "<ctrl>+<alt>+f"))
                    pol_key = self._normalize_combo(self.config.get("custom_polish", "<ctrl>+<alt>+p"))
                    if fix_key:
                        hotkey_map[fix_key] = self._handle_fix
                    if pol_key:
                        hotkey_map[pol_key] = self._handle_polish

                if self.on_quit:
                    hotkey_map["<ctrl>+<alt>+q"] = self._handle_quit

                self.listener = keyboard.GlobalHotKeys(hotkey_map)
                self.listener.start()
                self._running = True
                return True

        except Exception as e:
            print(f"  ! Error starting Windows hotkey listener ({trigger_mode}): {e}")
            return False

    @staticmethod
    def _normalize_combo(combo: str) -> str:
        """Convert friendly shortcut strings like 'Ctrl+Alt+F' into pynput format."""
        if not combo:
            return ""
        s = combo.strip().lower()
        replacements = [
            ("control", "<ctrl>"),
            ("ctrl", "<ctrl>"),
            ("alt", "<alt>"),
            ("shift", "<shift>"),
            ("space", "<space>"),
            ("win", "<cmd>"),
            ("windows", "<cmd>"),
        ]
        tokens = [t.strip() for t in s.split("+") if t.strip()]
        out = []
        for t in tokens:
            matched = False
            for src, dst in replacements:
                if t == src or t == dst:
                    out.append(dst)
                    matched = True
                    break
            if not matched:
                out.append(t)
        return "+".join(out)

    def _is_alt_key(self, key) -> bool:
        if _has_pynput and (key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr)):
            return True
        return getattr(key, "name", "") in ("alt", "alt_l", "alt_r", "alt_gr")

    def _is_ctrl_key(self, key) -> bool:
        if _has_pynput and (key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)):
            return True
        return getattr(key, "name", "") in ("ctrl", "ctrl_l", "ctrl_r")

    def _is_modifier_key(self, key) -> bool:
        if self._is_alt_key(key) or self._is_ctrl_key(key):
            return True
        if _has_pynput and key in (
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
            keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r
        ):
            return True
        return getattr(key, "name", "") in ("cmd", "cmd_l", "cmd_r", "shift", "shift_l", "shift_r")

    def _on_dt_press(self, key):
        self._active_keys.add(key)
        now = time.time()

        # Check for clean exit combo Ctrl+Alt+Q even in double-tap mode
        if self.on_quit:
            ctrl_down = any(self._is_ctrl_key(k) for k in self._active_keys)
            alt_down = any(self._is_alt_key(k) for k in self._active_keys)
            q_down = False
            if hasattr(key, "char") and key.char and key.char.lower() == "q":
                q_down = True
            if ctrl_down and alt_down and q_down:
                self._handle_quit()
                return

        if self._is_alt_key(key):
            if len(self._active_keys) == 1:
                self._alt_press_time = now
                self._non_modifier_pressed = False
        elif self._is_ctrl_key(key):
            if len(self._active_keys) == 1:
                self._ctrl_press_time = now
                self._non_modifier_pressed = False
        else:
            self._non_modifier_pressed = True

    def _on_dt_release(self, key):
        now = time.time()
        self._active_keys.discard(key)

        # 1. Alt Double-Tap (Fix)
        if self._is_alt_key(key):
            hold_time = now - self._alt_press_time
            if hold_time <= self.TAP_MAX_HOLD and not self._non_modifier_pressed:
                interval = now - self._last_alt_release_time
                if interval <= self.DOUBLE_TAP_MAX_INTERVAL and self._last_alt_release_time > 0:
                    self._last_alt_release_time = 0.0
                    self._handle_fix()
                    return
                else:
                    self._last_alt_release_time = now
            else:
                self._last_alt_release_time = 0.0

        # 2. Ctrl Double-Tap (Polish)
        elif self._is_ctrl_key(key):
            hold_time = now - self._ctrl_press_time
            if hold_time <= self.TAP_MAX_HOLD and not self._non_modifier_pressed:
                interval = now - self._last_ctrl_release_time
                if interval <= self.DOUBLE_TAP_MAX_INTERVAL and self._last_ctrl_release_time > 0:
                    self._last_ctrl_release_time = 0.0
                    self._handle_polish()
                    return
                else:
                    self._last_ctrl_release_time = now
            else:
                self._last_ctrl_release_time = 0.0

    def _handle_fix(self):
        threading.Thread(target=self.on_fix, daemon=True).start()

    def _handle_polish(self):
        threading.Thread(target=self.on_polish, daemon=True).start()

    def _handle_quit(self):
        if self.on_quit:
            threading.Thread(target=self.on_quit, daemon=True).start()
