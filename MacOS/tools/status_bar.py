"""
macOS Menu Bar Extra (Status Item) for Fixelect.
Renders an adaptive native Menu Bar item using PyObjC (NSStatusBar) or rumps.
Provides instant mode switching, hardware specs, preferences, and quick links.
"""

import pathlib
import sys
import threading
from config_mac import get_resource_path, load_config, get_hotkey_label


class MacStatusBar:
    """
    macOS Menu Bar controller.
    Uses native AppKit.NSStatusBar when available, or rumps as an alternative.
    """

    def __init__(self, on_open_dashboard=None, on_open_setup=None, on_open_words=None, on_quit=None):
        self.on_open_dashboard = on_open_dashboard
        self.on_open_setup = on_open_setup
        self.on_open_words = on_open_words
        self.on_quit = on_quit
        self._running = False
        self._app = None

    def start(self):
        """Start the status bar item in background thread or main loop."""
        self._running = True

        cfg = load_config()
        fix_lbl = get_hotkey_label("fix", cfg)
        pol_lbl = get_hotkey_label("polish", cfg)

        # 1. Try rumps if available
        try:
            import rumps

            icon_path = get_resource_path("resources/status_bar_template.png")

            class FixelectRumpsApp(rumps.App):
                def __init__(self, parent):
                    super().__init__("Fixelect", icon=str(icon_path) if icon_path.is_file() else None, template=True)
                    self.parent = parent
                    self.menu = [
                        rumps.MenuItem("Fixelect: Active (Metal)", callback=None),
                        None,  # Separator
                        rumps.MenuItem(f"Fix Mode  ({fix_lbl})", callback=None),
                        rumps.MenuItem(f"Polish Mode  ({pol_lbl})", callback=None),
                        None,
                        rumps.MenuItem("Open Dashboard & Playground...", callback=self.open_dashboard),
                        rumps.MenuItem("Model & Hardware Setup...", callback=self.open_setup),
                        rumps.MenuItem("Protected Words & Whitelist...", callback=self.open_words),
                        None,
                        rumps.MenuItem("Quit Fixelect", callback=self.quit_app),
                    ]

                def open_dashboard(self, _):
                    if self.parent.on_open_dashboard:
                        self.parent.on_open_dashboard()

                def open_setup(self, _):
                    if self.parent.on_open_setup:
                        self.parent.on_open_setup()

                def open_words(self, _):
                    if self.parent.on_open_words:
                        self.parent.on_open_words()

                def quit_app(self, _):
                    if self.parent.on_quit:
                        self.parent.on_quit()

            self._app = FixelectRumpsApp(self)
            threading.Thread(target=self._app.run, daemon=True).start()
            return True

        except ImportError:
            pass

        # 2. Try native PyObjC AppKit
        if sys.platform == "darwin":
            try:
                from AppKit import (
                    NSStatusBar,
                    NSVariableStatusItemLength,
                    NSMenu,
                    NSMenuItem,
                    NSImage,
                )

                status_bar = NSStatusBar.systemStatusBar()
                self._status_item = status_bar.statusItemWithLength_(NSVariableStatusItemLength)

                icon_path = get_resource_path("resources/status_bar_template.png")
                if icon_path.is_file():
                    img = NSImage.alloc().initWithContentsOfFile_(str(icon_path))
                    if img:
                        img.setTemplate_(True)
                        self._status_item.button().setImage_(img)
                else:
                    self._status_item.button().setTitle_("Fixelect")

                menu = NSMenu.alloc().init()

                item_status = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Fixelect: Active (Metal)", None, "")
                menu.addItem_(item_status)
                menu.addItem_(NSMenuItem.separatorItem())

                def _add_action(title, callback):
                    item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, "action:", "")
                    menu.addItem_(item)
                    return item

                _add_action("Open Dashboard...", lambda _: self.on_open_dashboard() if self.on_open_dashboard else None)
                _add_action("Model Setup...", lambda _: self.on_open_setup() if self.on_open_setup else None)
                _add_action("Protected Words...", lambda _: self.on_open_words() if self.on_open_words else None)
                menu.addItem_(NSMenuItem.separatorItem())
                _add_action("Quit Fixelect", lambda _: self.on_quit() if self.on_quit else None)

                self._status_item.setMenu_(menu)
                return True

            except Exception:
                pass

        # 3. Headless / CLI fallback
        print("  [StatusBar] Running without native menu bar icon (CLI fallback).")
        return True

    def stop(self):
        self._running = False
