"""
Configuration manager and native platform bridge for Fixelect on macOS.
Handles:
- ~/Library/Application Support/Fixelect/ persistence
- macOS LaunchAgent autostart management (~/Library/LaunchAgents/com.fixelect.app.plist)
- Resource path resolution (standalone bundle vs development)
- Native macOS audio chimes via afplay
"""

import json
import os
import pathlib
import plistlib
import subprocess
import sys

APP_NAME = "Fixelect"
BUNDLE_ID = "com.fixelect.app"

DEFAULT_CONFIG = {
    "model_profile": "3b",
    "sound_enabled": True,
    "engine": "embedded",
    "trigger_mode": "double_tap",       # "double_tap" | "option_space" | "classic" | "custom"
    "hotkey_fix": "double_option",
    "hotkey_polish": "double_control",
    "custom_fix": "<cmd>+<alt>+f",
    "custom_polish": "<cmd>+<alt>+p",
}


def get_hotkey_keycaps(mode: str = "fix", config: dict = None) -> list:
    """Return a list of key symbol strings to display in UI badges/KeyCaps."""
    if config is None:
        config = load_config()
    t_mode = config.get("trigger_mode", "double_tap")
    if t_mode == "double_tap":
        return ["⌥", "⌥"] if mode == "fix" else ["⌃", "⌃"]
    elif t_mode == "option_space":
        return ["⌥", "Space"] if mode == "fix" else ["⌥", "⇧", "Space"]
    elif t_mode == "classic":
        return ["⌘", "⌥", "F"] if mode == "fix" else ["⌘", "⌥", "P"]
    elif t_mode == "custom":
        raw = config.get("custom_fix" if mode == "fix" else "custom_polish", "")
        mapping = {
            "<cmd>": "⌘", "cmd": "⌘",
            "<alt>": "⌥", "option": "⌥", "alt": "⌥",
            "<ctrl>": "⌃", "control": "⌃", "ctrl": "⌃",
            "<shift>": "⇧", "shift": "⇧",
            "<space>": "Space", "space": "Space",
        }
        parts = [p.strip().lower() for p in raw.replace("+", " + ").split(" + ") if p.strip()]
        result = []
        for p in parts:
            result.append(mapping.get(p, p.upper()))
        return result or (["⌥", "⌥"] if mode == "fix" else ["⌃", "⌃"])
    return ["⌥", "⌥"] if mode == "fix" else ["⌃", "⌃"]


def get_hotkey_label(mode: str = "fix", config: dict = None) -> str:
    """Return a clean human-readable label for menus, CLI and buttons (e.g. '⌥ ⌥' or '⌥⌘F')."""
    caps = get_hotkey_keycaps(mode, config)
    if len(caps) == 2 and caps[0] == caps[1]:
        return f"{caps[0]} {caps[1]}"
    return "".join(caps)


def get_config_dir() -> pathlib.Path:
    """Return the macOS Application Support directory for Fixelect."""
    if sys.platform == "darwin":
        base = pathlib.Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        base = pathlib.Path.home() / ".config" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_models_dir() -> pathlib.Path:
    """Return the models cache directory."""
    models_dir = get_config_dir() / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def get_config_path() -> pathlib.Path:
    return get_config_dir() / "config.json"


def load_config() -> dict:
    cfg_path = get_config_path()
    if cfg_path.is_file():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                res = DEFAULT_CONFIG.copy()
                res.update(data)
                return res
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    cfg_path = get_config_path()
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")


def get_launch_agent_path() -> pathlib.Path:
    """Return the path to the user's LaunchAgent plist."""
    agents_dir = pathlib.Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    return agents_dir / f"{BUNDLE_ID}.plist"


def is_auto_start_enabled() -> bool:
    """Check if the LaunchAgent plist exists."""
    return get_launch_agent_path().is_file()


def set_auto_start(enabled: bool) -> bool:
    """Register or unregister Fixelect as a macOS LaunchAgent for automatic startup."""
    plist_path = get_launch_agent_path()

    if not enabled:
        if plist_path.is_file():
            try:
                subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
            except Exception:
                pass
            try:
                plist_path.unlink()
            except Exception:
                pass
        return True

    # Determine executable path
    if getattr(sys, "frozen", False):
        app_bin = sys.executable
    else:
        app_bin = sys.executable
        script = str(pathlib.Path(__file__).resolve().parent.parent / "fixelect_mac.py")

    args = [app_bin]
    if not getattr(sys, "frozen", False):
        args.append(script)
    args.append("--silent")

    plist_data = {
        "Label": BUNDLE_ID,
        "ProgramArguments": args,
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
    }

    try:
        with open(plist_path, "wb") as f:
            plistlib.dump(plist_data, f)
        subprocess.run(["launchctl", "load", str(plist_path)], capture_output=True)
        return True
    except Exception as e:
        print(f"Failed to register LaunchAgent: {e}")
        return False


def get_resource_path(relative_path: str) -> pathlib.Path:
    """
    Resolve resource path whether running in development,
    inside a py2app bundle, or inside a PyInstaller macOS app bundle.
    """
    # 1. PyInstaller frozen path
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = pathlib.Path(sys._MEIPASS) / relative_path
        if p.exists():
            return p

    # 2. py2app bundle path (Contents/Resources)
    app_dir = pathlib.Path(sys.executable).resolve()
    if ".app" in str(app_dir):
        while app_dir.name and not app_dir.name.endswith(".app"):
            app_dir = app_dir.parent
        res_dir = app_dir / "Contents" / "Resources" / relative_path
        if res_dir.exists():
            return res_dir

    # 3. Development root relative path
    base_dir = pathlib.Path(__file__).resolve().parent.parent
    p = base_dir / relative_path
    if p.exists():
        return p

    # 4. Check resources subdir
    p = base_dir / "resources" / relative_path
    if p.exists():
        return p

    return base_dir / relative_path


def play_sound(mode: str = "fix") -> None:
    """Play a subtle native macOS completion chime via afplay."""
    cfg = load_config()
    if not cfg.get("sound_enabled", True):
        return

    # Native macOS system sound library
    sound_name = "Tink.aiff" if mode == "fix" else "Pop.aiff"
    sound_path = pathlib.Path(f"/System/Library/Sounds/{sound_name}")

    if sound_path.is_file():
        try:
            # Run non-blocking
            subprocess.Popen(["afplay", "-v", "0.45", str(sound_path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
