"""
Configuration and Windows Startup registry manager for Fixelect.
Stores persistent user preferences in %LOCALAPPDATA%\\Fixelect\\config.json.
"""

import json
import os
import pathlib
import sys

DEFAULT_CONFIG = {
    "model_profile": "3b",
    "sound_enabled": True,
    "auto_start": False,
    "engine": "embedded",
    "theme": "dark",
    "trigger_mode": "double_tap",       # "double_tap" | "alt_space" | "classic" | "custom"
    "hotkey_fix": "double_alt",
    "hotkey_polish": "double_control",
    "custom_fix": "<ctrl>+<alt>+f",
    "custom_polish": "<ctrl>+<alt>+p",
}


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
            "<alt>": "Alt", "alt": "Alt",
            "<ctrl>": "Ctrl", "control": "Ctrl", "ctrl": "Ctrl",
            "<shift>": "Shift", "shift": "Shift",
            "<space>": "Space", "space": "Space",
            "<win>": "Win", "win": "Win",
        }
        parts = [p.strip().lower() for p in raw.replace("+", " + ").split(" + ") if p.strip()]
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
    cfg = DEFAULT_CONFIG.copy()
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
    """Save configuration dictionary to disk."""
    p = get_config_path()
    try:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        return True
    except Exception:
        return False


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
