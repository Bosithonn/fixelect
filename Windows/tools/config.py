"""
Configuration and Windows Startup registry manager for Fixelect.
Stores persistent user preferences in %LOCALAPPDATA%\\Fixelect\\config.json.
"""

import json
import os
import pathlib
import sys

try:
    from apps_win import DEFAULT_DISABLED
except Exception:  # pragma: no cover
    DEFAULT_DISABLED = []

DEFAULT_CONFIG = {
    "model_profile": "3b",
    "sound_enabled": True,
    "auto_start": False,
    "engine": "embedded",
    "theme": "dark",
    "trigger_mode": "double_tap",       # "double_tap" | "alt_space" | "classic" | "custom"
    "hotkey_fix": "double_alt",
    "hotkey_polish": "double_control",
    "custom_fix": "Ctrl+Alt+F",
    "custom_polish": "Ctrl+Alt+P",
    "prefetch_enabled": False,          # speculative fixes of selected text (uses more power)
    "polish_style": "professional",     # see check_guard.POLISH_STYLES
    "custom_instruction": "",           # the writer's own style note for Polish
    "polish_preview": True,             # show Polish results before replacing
    "multilingual": True,               # fix Spanish, French, German, ... too
    "hud_enabled": True,                # small on-screen status card
    "keep_formatting": True,            # paste rich text when the app copied rich text
    "unload_minutes": 10,               # free the model's memory after this idle time (0 = never)
    "check_updates": True,
    "last_update_check": 0,
    "skipped_version": "",
    "onboarding_done": False,
    "disabled_apps": list(DEFAULT_DISABLED),
}

_MODIFIER_TOKENS = {"ctrl", "control", "alt", "menu", "opt", "option", "shift", "win", "windows", "cmd", "super"}
_FUNCTION_KEYS = {f"f{i}" for i in range(1, 13)}


def validate_hotkey(combo: str):
    """Return (ok, message). A usable global shortcut needs at least one modifier
    (Ctrl / Alt / Win) plus a key, otherwise registering it would hijack normal typing."""
    if not combo or not combo.strip():
        return False, "Shortcut is empty."
    tokens = [t.strip().lower().strip("<>") for t in combo.replace("+", " ").split() if t.strip()]
    mods = [t for t in tokens if t in _MODIFIER_TOKENS]
    keys = [t for t in tokens if t not in _MODIFIER_TOKENS]
    if len(keys) != 1:
        return False, "Use modifiers plus exactly one key, e.g. Ctrl+Alt+F."
    if keys[0] in _FUNCTION_KEYS:
        return True, ""
    if not any(m not in ("shift",) for m in mods):
        return False, "Add Ctrl, Alt or Win — a plain key would block normal typing."
    return True, ""


def get_hotkey_keycaps(mode: str = "fix", config: dict = None) -> list:
    """Return a list of key symbol strings to display in UI badges/KeyCaps on Windows."""
    if config is None:
        config = load_config()
    t_mode = config.get("trigger_mode", "double_tap")
    if t_mode == "double_tap":
        return ["Alt", "Alt"] if mode == "fix" else ["Ctrl", "Ctrl"]
    elif t_mode == "alt_space":
        return ["Alt", "Space"] if mode == "fix" else ["Alt", "Shift", "Space"]
    elif t_mode == "classic":
        return ["Ctrl", "Alt", "F"] if mode == "fix" else ["Ctrl", "Alt", "P"]
    elif t_mode == "custom":
        raw = config.get("custom_fix" if mode == "fix" else "custom_polish", "")
        mapping = {
            "alt": "Alt",
            "ctrl": "Ctrl", "control": "Ctrl",
            "shift": "Shift",
            "space": "Space",
            "win": "Win", "cmd": "Win",
        }
        parts = [p.strip().lower().strip("<>") for p in raw.replace("+", " + ").split(" + ") if p.strip()]
        result = []
        for p in parts:
            result.append(mapping.get(p, p.upper()))
        return result or (["Alt", "Alt"] if mode == "fix" else ["Ctrl", "Ctrl"])
    return ["Alt", "Alt"] if mode == "fix" else ["Ctrl", "Ctrl"]


def get_hotkey_label(mode: str = "fix", config: dict = None) -> str:
    """Return a clean human-readable label (e.g. 'Alt Alt' or 'Ctrl+Alt+F')."""
    caps = get_hotkey_keycaps(mode, config)
    if len(caps) == 2 and caps[0] == caps[1]:
        return f"{caps[0]} {caps[1]}"
    return " + ".join(caps)


def parse_hotkey_string(combo: str) -> tuple:
    """Parse a shortcut string like 'Alt + Space' or 'Ctrl+Alt+F' into Win32 (fsModifiers, vkCode)."""
    if not combo:
        return 0, 0
    tokens = [t.strip().lower().strip("<>") for t in combo.replace("+", " ").split() if t.strip()]
    mods = 0x4000  # MOD_NOREPEAT
    vk = 0
    vk_map = {
        "space": 0x20, "return": 0x0D, "enter": 0x0D, "tab": 0x09,
        "backspace": 0x08, "escape": 0x1B, "esc": 0x1B,
        "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "ins": 0x2D,
        "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
        "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74, "f6": 0x75,
        "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    }
    for i in range(10):
        vk_map[str(i)] = 0x30 + i
    for c in "abcdefghijklmnopqrstuvwxyz":
        vk_map[c] = ord(c.upper())

    for t in tokens:
        if t in ("ctrl", "control"):
            mods |= 0x0002  # MOD_CONTROL
        elif t in ("alt", "menu", "opt", "option"):
            mods |= 0x0001  # MOD_ALT
        elif t in ("shift",):
            mods |= 0x0004  # MOD_SHIFT
        elif t in ("win", "windows", "cmd", "super"):
            mods |= 0x0008  # MOD_WIN
        elif t in vk_map:
            vk = vk_map[t]
        elif len(t) == 1:
            vk = ord(t.upper())
    return mods, vk


RUN_REG_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_REG_NAME = "Fixelect"


def get_config_dir():
    """Return the configuration directory path."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        p = pathlib.Path(local_appdata) / "Fixelect"
    else:
        p = pathlib.Path.home() / ".fixelect"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_config_path():
    return get_config_dir() / "config.json"


def get_resource_path(relative_path):
    """Resolve absolute path to a resource file, supporting PyInstaller bundles."""
    # 1. PyInstaller extraction directory / _internal
    if hasattr(sys, "_MEIPASS"):
        p = pathlib.Path(sys._MEIPASS) / relative_path
        if p.exists():
            return p

    # 2. Beside executable or inside _internal (one-dir bundle)
    if getattr(sys, "frozen", False):
        exe_dir = pathlib.Path(sys.executable).resolve().parent
        p_internal = exe_dir / "_internal" / relative_path
        if p_internal.exists():
            return p_internal
        p = exe_dir / relative_path
        if p.exists():
            return p

    # 3. Development source tree (parent of tools/ directory)
    src_root = pathlib.Path(__file__).resolve().parent.parent
    p = src_root / relative_path
    if p.exists():
        return p

    return p



def load_config():
    """Load configuration dictionary from disk, merging with defaults."""
    cfg = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULT_CONFIG.items()}
    p = get_config_path()
    if p.is_file():
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    cfg.update(data)
        except Exception:
            pass
    return cfg


def save_config(cfg):
    """Save configuration dictionary to disk atomically (never leaves a half-written file)."""
    p = get_config_path()
    tmp = p.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def update_config(**changes):
    """Read the latest config from disk, apply `changes`, save, and return it.

    Always use this instead of saving a long-lived dict: the tray, dashboard and
    daemon each hold their own copy, and saving a stale copy silently reverts
    settings another component just changed."""
    cfg = load_config()
    cfg.update(changes)
    save_config(cfg)
    return cfg


def get_user_words_path():
    """User-editable protected words live beside the config (the install dir may be read-only)."""
    return get_config_dir() / "words.txt"


def get_logs_dir():
    p = get_config_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_error(message):
    """Append a short diagnostic line (never user text) to the local log file."""
    try:
        import time as _t
        path = get_logs_dir() / "fixelect.log"
        if path.is_file() and path.stat().st_size > 512 * 1024:
            path.write_text("", encoding="utf-8")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{_t.strftime('%Y-%m-%d %H:%M:%S')}  {message}\n")
    except Exception:
        pass


def is_auto_start_enabled():
    """Check if Fixelect is registered in Windows Startup registry."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_KEY, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, APP_REG_NAME)
                return True
            except FileNotFoundError:
                return False
    except Exception:
        return False


def set_auto_start(enabled=True):
    """Enable or disable Fixelect launch on Windows startup."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_REG_KEY, 0, winreg.KEY_ALL_ACCESS) as key:
            if enabled:
                # Find executable or pythonw script path
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}" --autostart'
                else:
                    app_py = pathlib.Path(__file__).resolve().parent.parent / "fixelect.py"
                    pythonw = pathlib.Path(sys.executable).parent / "pythonw.exe"
                    py_exec = pythonw if pythonw.exists() else sys.executable
                    cmd = f'"{py_exec}" "{app_py}" --autostart'

                winreg.SetValueEx(key, APP_REG_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, APP_REG_NAME)
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        print(f"Error setting auto-start: {e}")
        return False
