"""
macOS Global Hotkey Dispatcher and Accessibility Permissions Handler.
Supports:
- Default Double-Tap Modifiers:
    Option x2 (⌥ ⌥) -> Default Fix Mode
    Control x2 (⌃ ⌃) -> Professional Polish Mode
- Option + Space preset (⌥ Space / ⌥⇧ Space)
- Classic 3-Key preset (Cmd + Option + F / P)
- Fully customizable combinations
- System Settings Accessibility verification (AXIsProcessTrustedWithOptions)
- Non-blocking background event loop with live config reloading
"""

import subprocess
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
    from config_mac import load_config
except ImportError:
    def load_config():
        return {
            "trigger_mode": "double_tap",
            "hotkey_fix": "double_option",
            "hotkey_polish": "double_control",
            "custom_fix": "<cmd>+<alt>+f",
            "custom_polish": "<cmd>+<alt>+p",
        }


def check_accessibility_permissions(prompt: bool = True) -> bool:
    """
    Check if the process has macOS Accessibility permissions to monitor hotkeys.
    If prompt=True and permissions are missing, macOS displays the native permission dialog.
    """
    if sys.platform != "darwin":
        return True

    # 1. Try PyObjC ApplicationServices
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
        options = {kAXTrustedCheckOptionPrompt: prompt}
        return bool(AXIsProcessTrustedWithOptions(options))
    except Exception:
        pass

    # 2. Check via AppleScript
    try:
        cmd = 'osascript -e "tell application \\"System Events\\" to return UI elements enabled"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=2.0)
        if "true" in res.stdout.lower():
            return True
    except Exception:
        pass

    return True


class MacHotkeyListener:
    """
    Background global hotkey dispatcher for macOS.
    Supports double-tap modifiers (Option x2, Control x2) as well as
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
        self._lock = threading.RLock()

        # Double-tap tracking state
        self._active_keys = set()
        self._non_modifier_pressed = False
        self._option_press_time = 0.0
        self._last_option_release_time = 0.0
        self._ctrl_press_time = 0.0
        self._last_ctrl_release_time = 0.0

    def start(self) -> bool:
        if not _has_pynput:
            print("  ! warning: pynput module not installed. Global hotkeys unavailable.")
            return False

        check_accessibility_permissions(prompt=True)
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

    def reload(self, new_config: Optional[dict] = None) -> bool:
        """Dynamically reload hotkeys with updated configuration without stopping daemon."""
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
                # Use raw Key listener to detect double-tap Option & Control
                self.listener = keyboard.Listener(
                    on_press=self._on_dt_press,
                    on_release=self._on_dt_release
                )
                self.listener.start()
                self._running = True
                return True
            else:
                # Combination shortcuts
                hotkey_map = {}
                if trigger_mode == "option_space":
                    hotkey_map["<alt>+<space>"] = self._handle_fix
                    hotkey_map["<alt>+<shift>+<space>"] = self._handle_polish
                elif trigger_mode == "classic":
                    hotkey_map["<cmd>+<alt>+f"] = self._handle_fix
                    hotkey_map["<cmd>+<alt>+p"] = self._handle_polish
                elif trigger_mode == "custom":
                    fix_key = self._normalize_combo(self.config.get("custom_fix", "<cmd>+<alt>+f"))
                    pol_key = self._normalize_combo(self.config.get("custom_polish", "<cmd>+<alt>+p"))
                    if fix_key:
                        hotkey_map[fix_key] = self._handle_fix
                    if pol_key:
                        hotkey_map[pol_key] = self._handle_polish

                if self.on_quit:
                    hotkey_map["<cmd>+<alt>+q"] = self._handle_quit

                self.listener = keyboard.GlobalHotKeys(hotkey_map)
                self.listener.start()
                self._running = True
                return True

        except Exception as e:
            print(f"  ! Error starting hotkey listener ({trigger_mode}): {e}")
            return False

    @staticmethod
    def _normalize_combo(combo: str) -> str:
        """Convert friendly shortcut strings like 'Cmd+Option+F' into pynput '<cmd>+<alt>+f' format."""
        if not combo:
            return ""
        s = combo.strip().lower()
        replacements = [
            ("command", "<cmd>"),
            ("cmd", "<cmd>"),
            ("option", "<alt>"),
            ("alt", "<alt>"),
            ("control", "<ctrl>"),
            ("ctrl", "<ctrl>"),
            ("shift", "<shift>"),
            ("space", "<space>"),
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

    def _is_option_key(self, key) -> bool:
        if _has_pynput and (key in (keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r)):
            return True
        return getattr(key, "name", "") in ("alt", "alt_l", "alt_r", "alt_gr")

    def _is_ctrl_key(self, key) -> bool:
        if _has_pynput and (key in (keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)):
            return True
        return getattr(key, "name", "") in ("ctrl", "ctrl_l", "ctrl_r")

    def _is_modifier_key(self, key) -> bool:
        if self._is_option_key(key) or self._is_ctrl_key(key):
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

        # Check for clean exit combo Cmd+Option+Q even in double-tap mode
        if self.on_quit:
            cmd_down = any(getattr(k, "name", "") in ("cmd", "cmd_l", "cmd_r") for k in self._active_keys)
            alt_down = any(getattr(k, "name", "") in ("alt", "alt_l", "alt_r") for k in self._active_keys)
            q_down = False
            if hasattr(key, "char") and key.char and key.char.lower() == "q":
                q_down = True
            if cmd_down and alt_down and q_down:
                self._handle_quit()
                return

        if self._is_option_key(key):
            if len(self._active_keys) == 1:
                self._option_press_time = now
                self._non_modifier_pressed = False
            else:
                self._non_modifier_pressed = True
        elif self._is_ctrl_key(key):
            if len(self._active_keys) == 1:
                self._ctrl_press_time = now
                self._non_modifier_pressed = False
            else:
                self._non_modifier_pressed = True
        else:
            self._non_modifier_pressed = True

    def _on_dt_release(self, key):
        now = time.time()

        if self._is_option_key(key):
            duration = now - self._option_press_time
            # Valid pure tap: held briefly and no character keys were typed simultaneously
            if not self._non_modifier_pressed and duration <= self.TAP_MAX_HOLD:
                since_last = now - self._last_option_release_time
                if since_last <= self.DOUBLE_TAP_MAX_INTERVAL:
                    # Double-tap Option detected!
                    self._last_option_release_time = 0.0
                    self._handle_fix()
                else:
                    self._last_option_release_time = now

        elif self._is_ctrl_key(key):
            duration = now - self._ctrl_press_time
            if not self._non_modifier_pressed and duration <= self.TAP_MAX_HOLD:
                since_last = now - self._last_ctrl_release_time
                if since_last <= self.DOUBLE_TAP_MAX_INTERVAL:
                    # Double-tap Control detected!
                    self._last_ctrl_release_time = 0.0
                    self._handle_polish()
                else:
                    self._last_ctrl_release_time = now

        self._active_keys.discard(key)
        if not self._active_keys:
            self._non_modifier_pressed = False

    def _handle_fix(self):
        if self.on_fix:
            threading.Thread(target=self.on_fix, daemon=True).start()

    def _handle_polish(self):
        if self.on_polish:
            threading.Thread(target=self.on_polish, daemon=True).start()

    def _handle_quit(self):
        if self.on_quit:
            threading.Thread(target=self.on_quit, daemon=True).start()


