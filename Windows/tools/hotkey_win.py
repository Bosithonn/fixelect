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

    DOUBLE_TAP_MAX_INTERVAL = 0.55  # max seconds between consecutive taps
    TAP_MAX_HOLD = 0.45             # max duration a modifier can be held to count as a tap

    def __init__(self, on_fix: Callable, on_polish: Callable, on_quit: Optional[Callable] = None, config: Optional[dict] = None):
        self.on_fix = on_fix
        self.on_polish = on_polish
        self.on_quit = on_quit
        self.config = config or load_config()
        self.listener = None
        self._running = False
        self._lock = threading.RLock()

        # Double-tap tracking state
        self._alt_press_time = 0.0
        self._last_alt_release_time = 0.0
        self._alt_invalidated = False

        self._ctrl_press_time = 0.0
        self._last_ctrl_release_time = 0.0
        self._ctrl_invalidated = False

    def start(self) -> bool:
        if not _has_pynput:
            print("  ! warning: pynput module not installed. Global hotkeys unavailable.")
            return False
        with self._lock:
            return self._start_listener_unlocked()

    def stop(self):
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self):
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
            self._stop_unlocked()
            if new_config:
                self.config = new_config
            else:
                self.config = load_config()
            return self._start_listener_unlocked()

    def _start_listener_unlocked(self) -> bool:
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
                    fix_key = self._normalize_combo(self.config.get("custom_fix", "Ctrl+Alt+F"))
                    pol_key = self._normalize_combo(self.config.get("custom_polish", "Ctrl+Alt+P"))
                    if fix_key:
                        hotkey_map[fix_key] = self._handle_fix
                    if pol_key:
                        hotkey_map[pol_key] = self._handle_polish

                if self.on_quit:
                    hotkey_map["<ctrl>+<alt>+q"] = self._handle_quit

                if hotkey_map:
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
            ("cmd", "<cmd>"),
        ]
        tokens = [t.strip() for t in s.split("+") if t.strip()]
        out = []
        for t in tokens:
            t_clean = t.strip("<>")
            matched = False
            for src, dst in replacements:
                if t_clean == src or t == dst:
                    out.append(dst)
                    matched = True
                    break
            if not matched:
                out.append(t_clean)
        return "+".join(out)


    def _is_alt_key(self, key) -> bool:
        if _has_pynput and (key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr)):
            return True
        name = getattr(key, "name", "")
        if name in ("alt", "alt_l", "alt_r", "alt_gr"):
            return True
        vk = getattr(key, "vk", None)
        return vk in (18, 164, 165)

    def _is_ctrl_key(self, key) -> bool:
        if _has_pynput and (key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)):
            return True
        name = getattr(key, "name", "")
        if name in ("ctrl", "ctrl_l", "ctrl_r"):
            return True
        vk = getattr(key, "vk", None)
        return vk in (17, 162, 163)

    def _on_dt_press(self, key):
        now = time.time()
        is_alt = self._is_alt_key(key)
        is_ctrl = self._is_ctrl_key(key)

        if is_alt:
            if self._alt_press_time == 0.0:
                self._alt_press_time = now
                self._alt_invalidated = False
        elif is_ctrl:
            if self._ctrl_press_time == 0.0:
                self._ctrl_press_time = now
                self._ctrl_invalidated = False
        else:
            # If any other key is pressed while Alt or Ctrl is held down,
            # this is a combination (e.g. Alt+Tab, Ctrl+C), NOT a standalone tap
            if self._alt_press_time > 0.0:
                self._alt_invalidated = True
            if self._ctrl_press_time > 0.0:
                self._ctrl_invalidated = True

    def _on_dt_release(self, key):
        now = time.time()
        is_alt = self._is_alt_key(key)
        is_ctrl = self._is_ctrl_key(key)

        # 1. Alt Double-Tap (Fix)
        if is_alt:
            if self._alt_press_time > 0.0 and not self._alt_invalidated:
                hold_time = now - self._alt_press_time
                if 0.02 <= hold_time <= self.TAP_MAX_HOLD:
                    interval = now - self._last_alt_release_time
                    if 0.04 <= interval <= self.DOUBLE_TAP_MAX_INTERVAL:
                        self._last_alt_release_time = 0.0
                        self._alt_press_time = 0.0
                        self._handle_fix()
                        return
                    else:
                        self._last_alt_release_time = now
                else:
                    self._last_alt_release_time = 0.0
            else:
                self._last_alt_release_time = 0.0
            self._alt_press_time = 0.0
            self._alt_invalidated = False

        # 2. Ctrl Double-Tap (Polish)
        elif is_ctrl:
            if self._ctrl_press_time > 0.0 and not self._ctrl_invalidated:
                hold_time = now - self._ctrl_press_time
                if 0.02 <= hold_time <= self.TAP_MAX_HOLD:
                    interval = now - self._last_ctrl_release_time
                    if 0.04 <= interval <= self.DOUBLE_TAP_MAX_INTERVAL:
                        self._last_ctrl_release_time = 0.0
                        self._ctrl_press_time = 0.0
                        self._handle_polish()
                        return
                    else:
                        self._last_ctrl_release_time = now
                else:
                    self._last_ctrl_release_time = 0.0
            else:
                self._last_ctrl_release_time = 0.0
            self._ctrl_press_time = 0.0
            self._ctrl_invalidated = False

    def _handle_fix(self):
        threading.Thread(target=self.on_fix, daemon=True).start()

    def _handle_polish(self):
        threading.Thread(target=self.on_polish, daemon=True).start()

    def _handle_quit(self):
        if self.on_quit:
            threading.Thread(target=self.on_quit, daemon=True).start()
