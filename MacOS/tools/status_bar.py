"""
macOS menu bar item for Fixelect (rumps).

Runs on the MAIN thread (Cocoa requires it; the old version started rumps on a
background thread, where the icon either never appeared or crashed the app).
A one-second timer refreshes the labels and gives Python a chance to handle
signals (SIGTERM from the Dashboard's Quit, SIGUSR1 from a second launch).
"""

import time

from config_mac import get_resource_path, load_config, get_hotkey_label
from downloader_mac import MODELS

_STATE = {"loading": "Loading model…", "ready": "Ready", "busy": "Working…", "error": "Engine offline"}


class MacStatusBar:
    def __init__(self, on_open_dashboard=None, on_quit=None, get_status=None, want_dashboard=None, **_legacy):
        self.on_open_dashboard = on_open_dashboard
        self.on_quit = on_quit
        self.get_status = get_status or (lambda: {"state": "ready"})
        self.want_dashboard = want_dashboard
        self._app = None

    def _status_title(self):
        st = self.get_status() or {}
        model = MODELS.get(st.get("model") or load_config().get("model_profile", ""), {}).get("short_name", "")
        text = _STATE.get(st.get("state"), "Ready")
        return f"Fixelect — {text}" + (f"  ·  {model}" if model and st.get("state") == "ready" else "")

    def run(self):
        try:
            import rumps
        except ImportError:
            print("  [StatusBar] rumps not installed - running headless (Ctrl+C to quit).")
            try:
                while True:
                    time.sleep(0.5)
                    if self.want_dashboard is not None and self.want_dashboard.is_set():
                        self.want_dashboard.clear()
                        self.on_open_dashboard and self.on_open_dashboard()
            except KeyboardInterrupt:
                pass
            return

        bar = self
        self._install_reopen_handler(rumps)

        icon = get_resource_path("resources/status_bar_template.png")

        class App(rumps.App):
            def __init__(self):
                super().__init__("Fixelect", icon=str(icon) if icon.is_file() else None,
                                 template=True, quit_button=None)
                if not icon.is_file():
                    self.title = "Fx"
                self.i_status = rumps.MenuItem(bar._status_title())
                self.i_fix = rumps.MenuItem("")
                self.i_pol = rumps.MenuItem("")
                self.menu = [
                    self.i_status, None,
                    self.i_fix, self.i_pol, None,
                    rumps.MenuItem("Open Fixelect…", callback=lambda _: bar.on_open_dashboard and bar.on_open_dashboard(),
                                   key=","),
                    None,
                    rumps.MenuItem("Quit Fixelect", callback=lambda _: bar.on_quit and bar.on_quit(), key="q"),
                ]
                self.refresh()
                rumps.Timer(self._tick, 1).start()

            def refresh(self):
                cfg = load_config()
                self.i_status.title = bar._status_title()
                self.i_fix.title = f"Fix selected text      {get_hotkey_label('fix', cfg)}"
                self.i_pol.title = f"Polish selected text   {get_hotkey_label('polish', cfg)}"

            def _tick(self, _timer):
                self.refresh()
                if bar.want_dashboard is not None and bar.want_dashboard.is_set():
                    bar.want_dashboard.clear()
                    bar.on_open_dashboard and bar.on_open_dashboard()

        self._app = App()
        self._app.run()

    def _install_reopen_handler(self, rumps):
        """Clicking Fixelect in Finder/Launchpad while it runs opens the dashboard."""
        try:
            from rumps import rumps as core
            base = core.NSApp
            bar = self

            class FixelectNSApp(base):
                def applicationShouldHandleReopen_hasVisibleWindows_(self, app, flag):
                    if bar.on_open_dashboard:
                        bar.on_open_dashboard()
                    return True

            core.NSApp = FixelectNSApp
        except Exception:
            pass

    def stop(self):
        try:
            import rumps
            rumps.quit_application()
        except Exception:
            pass
