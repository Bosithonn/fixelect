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
}

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
