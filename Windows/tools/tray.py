"""
Windows System Tray integration for Fixelect using pystray and Pillow.
Provides a persistent background controller, status indicators, and quick-access menu.
"""

import pathlib
import sys
import threading
from PIL import Image, ImageDraw

# Ensure tools directory is in sys.path
_tools_dir = pathlib.Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

try:
    import pystray
    if sys.platform == "win32":
        import ctypes
        try:
            uxtheme = ctypes.windll.uxtheme
            # SetPreferredAppMode(2) = ForceDark
            SetPreferredAppMode = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)((135, uxtheme))
            SetPreferredAppMode(2)
            FlushMenuThemes = ctypes.WINFUNCTYPE(None)((136, uxtheme))
            FlushMenuThemes()
            
            # Hook pystray window creation to set AllowDarkModeForWindow
            import pystray._win32
            AllowDarkModeForWindow = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_bool)((133, uxtheme))
            _orig_create_window = pystray._win32.Icon._create_window
            SetWindowTheme = uxtheme.SetWindowTheme
            SetWindowTheme.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
            def _dark_create_window(self, atom):
                hwnd = _orig_create_window(self, atom)
                try:
                    AllowDarkModeForWindow(hwnd, True)
                    SetWindowTheme(hwnd, "DarkMode_Explorer", None)
                    val = ctypes.c_int(1)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
                except Exception:
                    pass
                return hwnd
            pystray._win32.Icon._create_window = _dark_create_window
        except Exception:
            pass
except ImportError:
    pystray = None

from config import load_config, save_config, is_auto_start_enabled, set_auto_start, get_resource_path
from hardware import detect_hardware
from downloader import MODELS, resolve_model


def create_tray_icon(size=64, active=True):
    """
    Generate the system tray icon using the official Fixelect brand logo symbol.
    Provides pristine 32-bit alpha transparency with razor-sharp anti-aliased edges.
    """
    icon_path = get_resource_path("resources/tray_icon.png")
    if not icon_path.is_file():
        icon_path = get_resource_path("resources/app_icon.png")

    if icon_path.is_file():
        try:
            image = Image.open(icon_path).convert("RGBA")
            if image.size != (size, size):
                image = image.resize((size, size), Image.Resampling.LANCZOS)
            return image
        except Exception:
            pass

    # Fallback if image file is not found
    image = Image.new("RGBA", (size, size), (7, 11, 25, 255))
    draw = ImageDraw.Draw(image)
    margin = 4
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=14,
        fill=(15, 22, 46, 255),
        outline=(29, 104, 254, 240),
        width=2,
    )
    if active:
        draw.ellipse([size - 9, size - 9, size - 1, size - 1], fill=(16, 185, 129, 255))
    return image


class TrayManager:
    """Manages the lifecycle of the system tray icon."""

    def __init__(self, on_open_settings=None, on_quit=None):
        self.on_open_settings = on_open_settings
        self.on_quit = on_quit
        self.icon = None
        self._thread = None
        self.config = load_config()
        self.hw = detect_hardware()

    def _toggle_sound(self, icon, item):
        new_val = not self.config.get("sound_enabled", True)
        self.config["sound_enabled"] = new_val
        save_config(self.config)

    def _toggle_autostart(self, icon, item):
        curr = is_auto_start_enabled()
        set_auto_start(not curr)
        self.config["auto_start"] = not curr
        save_config(self.config)

    def _handle_open_settings(self, icon=None, item=None):
        if self.on_open_settings:
            # Run on a separate thread so it doesn't block the tray message loop
            threading.Thread(target=self.on_open_settings, daemon=True).start()

    def _handle_quit(self, icon, item):
        self.stop()
        if self.on_quit:
            self.on_quit()

    def _switch_model(self, profile):
        self.config = load_config()
        self.config["model_profile"] = profile
        save_config(self.config)
        try:
            from engine import get_default_engine
            eng = get_default_engine(model_profile=profile)
            threading.Thread(target=eng.start, daemon=True).start()
        except Exception as e:
            print(f"Tray model switch notice: {e}")
        if self.icon:
            self.icon.menu = self.build_menu()

    def build_menu(self):
        if not pystray:
            return None

        self.config = load_config()
        curr_profile = self.config.get("model_profile", self.hw.get("recommended_model", "3b"))

        device_desc = self.hw["backend"].upper()
        if self.hw["backend"] == "cuda":
            device_desc = "CUDA GPU"
        elif self.hw["backend"] == "vulkan":
            device_desc = "Vulkan"
        else:
            device_desc = "CPU"

        # Construct dynamic model switching submenu
        model_items = []
        for p_key, p_spec in MODELS.items():
            is_active = (p_key == curr_profile)
            is_ready = resolve_model(p_key) is not None

            tag = ""
            if not is_ready:
                tag = " [Download Needed]"
            elif p_key == self.hw.get("recommended_model"):
                tag = " (Recommended)"

            display_name = f"{p_spec['short_name']}{tag}"

            def make_handler(pk=p_key, ready=is_ready):
                def handler(icon, item):
                    if ready:
                        self._switch_model(pk)
                    else:
                        self._handle_open_settings()
                return handler

            model_items.append(
                pystray.MenuItem(
                    display_name,
                    make_handler(),
                    checked=lambda item, active=is_active: active,
                    radio=True,
                )
            )

        model_submenu = pystray.Menu(*model_items)

        return pystray.Menu(
            pystray.MenuItem(f"Fixelect: Active ({device_desc})", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Default Fix: Ctrl + Alt + F", None, enabled=False),
            pystray.MenuItem("Professional Polish: Ctrl + Alt + P", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Switch AI Model", model_submenu),
            pystray.MenuItem("Dashboard & Settings...", self._handle_open_settings, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Sound Feedback",
                self._toggle_sound,
                checked=lambda item: self.config.get("sound_enabled", True),
            ),
            pystray.MenuItem(
                "Start with Windows",
                self._toggle_autostart,
                checked=lambda item: is_auto_start_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit Fixelect (Ctrl + Alt + Q)", self._handle_quit),
        )

    def start(self):
        """Start tray icon in background thread."""
        if not pystray:
            print("  (pystray not installed; system tray unavailable)")
            return

        icon_image = create_tray_icon(64, active=True)
        menu = self.build_menu()

        self.icon = pystray.Icon(
            "Fixelect",
            icon_image,
            "Fixelect - AI Offline Grammar & Polish",
            menu=menu,
        )

        def run_tray():
            try:
                self.icon.run()
            except Exception as e:
                print(f"Tray run exception: {e}")

        self._thread = threading.Thread(target=run_tray, daemon=True)
        self._thread.start()

    def notify(self, title, message):
        """Display a native Windows notification from the tray."""
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        """Stop and remove the tray icon."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
