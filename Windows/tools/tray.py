"""
Windows system tray for Fixelect (pystray).

Every label is computed when the menu is rebuilt, so the tray always shows the
hotkeys, model and engine state that are actually in effect, and every toggle
re-reads the config from disk before writing it (the dashboard may have changed
other settings in the meantime).
"""

import pathlib
import sys
import threading

from PIL import Image, ImageDraw

_tools_dir = pathlib.Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

try:
    import pystray
    if sys.platform == "win32":
        import ctypes
        try:
            uxtheme = ctypes.windll.uxtheme
            SetPreferredAppMode = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)((135, uxtheme))
            SetPreferredAppMode(2)  # ForceDark context menus
            FlushMenuThemes = ctypes.WINFUNCTYPE(None)((136, uxtheme))
            FlushMenuThemes()
        except Exception:
            pass
except ImportError:
    pystray = None

from config import (  # noqa: E402
    load_config, update_config, is_auto_start_enabled, set_auto_start,
    get_resource_path, get_hotkey_label,
)
from downloader import MODELS, resolve_model  # noqa: E402


def create_tray_icon(size=64, active=True):
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
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([4, 4, size - 4, size - 4], radius=14, fill=(18, 21, 28, 255),
                           outline=(61, 123, 255, 255), width=3)
    return image


_STATE_TEXT = {"loading": "Starting…", "ready": "Ready", "error": "Needs attention", "busy": "Working…",
               "sleeping": "Ready (model asleep to save memory)"}


class TrayManager:
    def __init__(self, on_open_settings=None, on_quit=None, on_switch_model=None, get_status=None,
                 get_update=None):
        self.on_open_settings = on_open_settings
        self.get_update = get_update or (lambda: None)
        self.on_quit = on_quit
        self.on_switch_model = on_switch_model
        self.get_status = get_status or (lambda: {"state": "ready"})
        self.icon = None
        self._thread = None

    # -- actions -------------------------------------------------------------

    def _open(self, icon=None, item=None):
        self._open_page(None)

    def _open_page(self, page):
        if self.on_open_settings:
            threading.Thread(target=lambda: self.on_open_settings(page), daemon=True).start()

    def _toggle_sound(self, icon, item):
        update_config(sound_enabled=not load_config().get("sound_enabled", True))
        self.refresh()

    def _toggle_autostart(self, icon, item):
        new_val = not is_auto_start_enabled()
        set_auto_start(new_val)
        update_config(auto_start=new_val)
        self.refresh()

    def _quit(self, icon, item):
        self.stop()
        if self.on_quit:
            self.on_quit()

    def _switch_model(self, profile):
        if resolve_model(profile) is None:
            self._open()  # not downloaded yet: the dashboard's Model tab handles that
            return
        if self.on_switch_model:
            self.on_switch_model(profile)
        self.refresh()

    # -- menu ----------------------------------------------------------------

    def _status_text(self, _item=None):
        st = self.get_status() or {}
        text = _STATE_TEXT.get(st.get("state"), "Ready")
        backend = st.get("backend")
        return f"Fixelect — {text}" + (f" ({backend})" if backend and st.get("state") == "ready" else "")

    def _model_items(self):
        for key, spec in MODELS.items():
            ready = resolve_model(key) is not None
            label = spec["short_name"] + ("" if ready else "  (download…)")
            yield pystray.MenuItem(
                label,
                (lambda k: (lambda icon, item: self._switch_model(k)))(key),
                checked=(lambda k: (lambda item: load_config().get("model_profile", "3b") == k))(key),
                radio=True,
            )

    def build_menu(self):
        if not pystray:
            return None
        M = pystray.MenuItem
        return pystray.Menu(
            M(self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            M(lambda item: f"Fix selected text\t{get_hotkey_label('fix')}", None, enabled=False),
            M(lambda item: f"Polish selected text\t{get_hotkey_label('polish')}", None, enabled=False),
            pystray.Menu.SEPARATOR,
            M("Open Fixelect", self._open, default=True),
            M(lambda item: f"Update to Fixelect {(self.get_update() or {}).get('version', '')}…",
              lambda icon, item: self._open_page("General"), visible=lambda item: bool(self.get_update())),
            M("Model", pystray.Menu(self._model_items)),
            M("Help & diagnostics", lambda icon, item: self._open_page("Help")),
            pystray.Menu.SEPARATOR,
            M("Sound feedback", self._toggle_sound,
              checked=lambda item: load_config().get("sound_enabled", True)),
            M("Start with Windows", self._toggle_autostart,
              checked=lambda item: is_auto_start_enabled()),
            pystray.Menu.SEPARATOR,
            M("Quit Fixelect", self._quit),
        )

    def refresh(self):
        """Rebuild the native menu and tooltip so they reflect current state."""
        if not self.icon:
            return
        try:
            self.icon.title = self._status_text()
            self.icon.update_menu()
        except Exception:
            pass

    def start(self):
        if not pystray:
            print("  (pystray not installed; system tray unavailable)")
            return
        self.icon = pystray.Icon("Fixelect", create_tray_icon(64), self._status_text(), menu=self.build_menu())

        def run_tray():
            try:
                self.icon.run()
            except Exception as e:
                print(f"Tray run exception: {e}")

        self._thread = threading.Thread(target=run_tray, daemon=True)
        self._thread.start()

    def notify(self, title, message):
        if self.icon:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
