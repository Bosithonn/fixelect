#!/usr/bin/env python3
"""
Fixelect for macOS — Offline AI Grammar Correction & Executive Polish
Apple Silicon Metal acceleration • Menu bar app • Global triggers

Triggers (default):
  Option x2 (⌥ ⌥)   ->  Fix typos & grammar (voice preserved)
  Control x2 (⌃ ⌃)  ->  Professional polish
Quit from the menu bar icon.

Process layout: this daemon owns the menu bar (rumps, main thread), the
keyboard listener and the AI engine. Every window (Dashboard, Setup,
Permissions) runs as a separate short-lived process, because Cocoa and Tk both
insist on the main thread and the old single-process design crashed or froze.

Author: Bositxon Erkinxonov
License: MIT (100% Offline, Zero Telemetry)
"""

import os
import pathlib
import queue
import signal
import subprocess
import sys
import threading
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - macOS always has it
    fcntl = None

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

_here = pathlib.Path(__file__).resolve().parent
for _p in (_here / "tools", pathlib.Path(getattr(sys, "_MEIPASS", _here)) / "tools"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from config_mac import load_config, get_hotkey_label, get_lock_path, get_config_path, play_sound  # noqa: E402
from downloader_mac import resolve_model, MODELS  # noqa: E402
from check_guard import load_pipeline, fix_preserving_layout, normalise, expand, is_probably_english  # noqa: E402
import clipboard_mac as clip  # noqa: E402
from hotkey_mac import MacHotkeyListener, check_accessibility_permissions  # noqa: E402

MODEL = "qwen2.5"
ENGINE = load_config().get("engine", "embedded")
MAX_SELECTION_CHARS = 12000
RESTORE_DELAY = 0.8

_lock_handle = None


def acquire_single_instance():
    """Per-user advisory lock; the file also publishes our PID for window processes."""
    global _lock_handle
    if fcntl is None:
        return True
    path = get_lock_path()
    try:
        _lock_handle = open(path, "a+")
        fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_handle.seek(0)
        _lock_handle.truncate()
        _lock_handle.write(str(os.getpid()))
        _lock_handle.flush()
        return True
    except OSError:
        return False


def running_daemon_pid():
    try:
        pid = int(get_lock_path().read_text().strip() or 0)
        if pid and pid != os.getpid():
            os.kill(pid, 0)
            return pid
    except Exception:
        pass
    return None


def ui_command(kind):
    if getattr(sys, "frozen", False):
        return [sys.executable, f"--{kind}"]
    return [sys.executable, str(pathlib.Path(__file__).resolve()), f"--{kind}"]


def notify(title, message):
    try:
        import rumps
        rumps.notification("Fixelect", title, message)
        return
    except Exception:
        pass
    try:
        safe = message.replace('"', "'")
        subprocess.Popen(["osascript", "-e", f'display notification "{safe}" with title "Fixelect" subtitle "{title}"'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


class MacApp:
    def __init__(self):
        self.jobs = queue.Queue()
        self.fix = None
        self.status_info = {"state": "loading", "detail": "Starting…", "model": load_config().get("model_profile", "3b")}
        self.listener = None
        self.bar = None
        self.ui_procs = {}
        self._restore_lock = threading.Lock()
        self._restore_timer = None
        self._pending = None
        self._last_hotkey_done = 0.0
        self._want_dashboard = threading.Event()
        self._stopping = False

    # -- status ---------------------------------------------------------------

    def set_status(self, state, detail=""):
        self.status_info.update(state=state, detail=detail, model=load_config().get("model_profile", "3b"))

    def status(self):
        return dict(self.status_info)

    # -- engine ---------------------------------------------------------------

    def _load_engine(self):
        self.set_status("loading", "Loading the AI model…")
        try:
            if ENGINE == "embedded":
                from engine_mac import get_default_engine
                get_default_engine(model_profile=load_config().get("model_profile", "3b")).publish = True
            self.fix = load_pipeline(MODEL, fast=False, beams=1, engine_type=ENGINE)
            self.set_status("ready", "Ready")
            return True
        except Exception as e:
            self.fix = None
            self.set_status("error", str(e))
            print(f"  ! engine failed: {e}")
            return False

    def worker(self):
        self._load_engine()
        while True:
            kind, payload, queued_at = self.jobs.get()
            try:
                if kind == "switch_model":
                    from engine_mac import get_default_engine
                    get_default_engine(model_profile=payload)
                    if self._load_engine():
                        notify("Model ready", f"Now using {MODELS.get(payload, {}).get('short_name', payload)}.")
                elif kind in ("fix", "polish"):
                    if queued_at < self._last_hotkey_done:
                        continue
                    try:
                        self._do_hotkey(kind)
                    finally:
                        self._last_hotkey_done = time.time()
            except Exception as e:
                print(f"  ! {kind} failed: {e}")
                if kind in ("fix", "polish"):
                    notify("Couldn't finish", str(e) or type(e).__name__)

    def trigger(self, mode):
        self.jobs.put((mode, None, time.time()))

    # -- clipboard restore ------------------------------------------------------

    def _take_pending(self):
        with self._restore_lock:
            if self._restore_timer is not None:
                self._restore_timer.cancel()
                self._restore_timer = None
                snap, self._pending = self._pending, None
                return snap
            return None

    def _schedule_restore(self, snapshot, delay, only_if_count=None):
        if snapshot is None:
            return

        def run():
            with self._restore_lock:
                if self._restore_timer is None:
                    return
                self._restore_timer, self._pending = None, None
                if only_if_count is not None and clip.change_count() != only_if_count:
                    return  # the user copied something new; keep it
                clip.restore(snapshot)

        with self._restore_lock:
            if self._restore_timer is not None:
                self._restore_timer.cancel()
            self._pending = snapshot
            self._restore_timer = threading.Timer(delay, run)
            self._restore_timer.daemon = True
            self._restore_timer.start()

    def _do_hotkey(self, mode):
        original = self._take_pending()
        if original is None:
            original = clip.snapshot()
        clip.wait_for_modifiers()
        if not clip.copy_selection():
            self._schedule_restore(original, 0.05)
            return
        text = clip.get_text()
        if not text or not text.strip():
            self._schedule_restore(original, 0.05)
            return
        if len(text) > MAX_SELECTION_CHARS:
            self._schedule_restore(original, 0.05)
            notify("Selection too long", f"Select fewer than {MAX_SELECTION_CHARS:,} characters at a time.")
            return
        if not is_probably_english(text):
            self._schedule_restore(original, 0.05)
            notify("Only English for now", "Fixelect leaves text in other languages unchanged.")
            return
        if self.fix is None and not self._load_engine():
            self._schedule_restore(original, 0.05)
            raise RuntimeError(self.status_info.get("detail") or "The AI engine is not available.")

        started = time.time()
        self.set_status("busy", "Working…")
        try:
            fixed = fix_preserving_layout(text, lambda t: self.fix(t, mode=mode), mode=mode)[0]
        finally:
            self.set_status("ready", "Ready")
        if fixed == text:
            self._schedule_restore(original, 0.05)
            return
        clip.set_text(fixed, transient=True)
        count = clip.change_count()
        time.sleep(0.03)
        clip.paste()
        play_sound(mode)
        print(f"  ~ [{mode.upper()}] {(time.time() - started) * 1000:.0f}ms")
        self._schedule_restore(original, RESTORE_DELAY, only_if_count=count)

    # -- windows (separate processes) ---------------------------------------------

    def open_window(self, kind):
        proc = self.ui_procs.get(kind)
        if proc is not None and proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGUSR1)  # ask it to come forward
            except Exception:
                pass
            return proc
        try:
            proc = subprocess.Popen(ui_command(kind))
            self.ui_procs[kind] = proc
            return proc
        except Exception as e:
            print(f"  ! could not open {kind}: {e}")
            return None

    # -- background watchers ----------------------------------------------------------

    def config_watcher(self):
        path = get_config_path()
        last_mtime = path.stat().st_mtime if path.exists() else 0
        cfg = load_config()
        while not self._stopping:
            time.sleep(1.0)
            try:
                mtime = path.stat().st_mtime if path.exists() else 0
            except OSError:
                continue
            if mtime == last_mtime:
                continue
            last_mtime = mtime
            new = load_config()
            if any(new.get(k) != cfg.get(k) for k in ("trigger_mode", "custom_fix", "custom_polish")):
                if self.listener:
                    self.listener.reload(new)
            if new.get("model_profile") != cfg.get("model_profile") and resolve_model(new.get("model_profile")):
                self.jobs.put(("switch_model", new.get("model_profile"), time.time()))
            cfg = new

    def permission_watcher(self):
        while not self._stopping and not check_accessibility_permissions(prompt=False):
            time.sleep(2.0)
        if not self._stopping and self.listener:
            self.listener.reload(load_config())
            print("  [Fixelect] Accessibility granted - triggers active.")

    # -- lifecycle --------------------------------------------------------------------

    def quit(self):
        self._stopping = True
        try:
            import rumps
            rumps.quit_application()
        except Exception:
            os._exit(0)

    def shutdown(self):
        self._stopping = True
        if self.listener:
            self.listener.stop()
        snap = self._take_pending()
        if snap is not None:
            clip.restore(snap)
        for proc in self.ui_procs.values():
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
        try:
            from engine_mac import get_default_engine
            get_default_engine().stop()
        except Exception:
            pass

    def run(self, silent):
        if not acquire_single_instance():
            pid = running_daemon_pid()
            if pid:
                os.kill(pid, signal.SIGUSR1)  # the running copy opens its dashboard
            return

        signal.signal(signal.SIGTERM, lambda *_: self.quit())
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        signal.signal(signal.SIGUSR1, lambda *_: self._want_dashboard.set())

        if ENGINE == "embedded" and not resolve_model(load_config().get("model_profile", "3b")):
            subprocess.run(ui_command("setup"))
            if not resolve_model(load_config().get("model_profile", "3b")):
                print("  [Fixelect] Setup cancelled - exiting.")
                return

        threading.Thread(target=self.worker, daemon=True).start()
        self.listener = MacHotkeyListener(on_fix=lambda: self.trigger("fix"),
                                          on_polish=lambda: self.trigger("polish"), config=load_config())
        self.listener.start()
        threading.Thread(target=self.config_watcher, daemon=True).start()

        if not check_accessibility_permissions(prompt=False):
            self.open_window("permissions")
            threading.Thread(target=self.permission_watcher, daemon=True).start()
        elif not silent:
            self.open_window("dashboard")

        print(f"  Fixelect is running. Fix: {get_hotkey_label('fix')}  Polish: {get_hotkey_label('polish')}")
        from status_bar import MacStatusBar
        self.bar = MacStatusBar(
            on_open_dashboard=lambda: self.open_window("dashboard"),
            on_quit=self.quit,
            get_status=self.status,
            want_dashboard=self._want_dashboard,
        )
        try:
            self.bar.run()  # blocks on the main thread until quit
        finally:
            self.shutdown()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_tests():
    print(f"Running Fixelect macOS self-tests [{ENGINE.upper()}]...")
    ok_all = True

    def report(ok, text):
        nonlocal ok_all
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {text}")

    for inp, exp in [("enter your user id", "enter your user id"), ("i feel ill", "I feel ill"), ("im fne", "I'm fine")]:
        report(expand(inp) == exp, f"expand({inp!r}) -> {expand(inp)!r}")
    try:
        pipeline = load_pipeline(MODEL, fast=False, beams=1, engine_type=ENGINE)
    except Exception as e:
        print(f"Failed to load pipeline: {e}")
        return False
    for inp, exp in [("your welcome", "you're welcome"), ("better then that", "better than that"),
                     ("helo how are you", "hello how are you"), ("- helo world\n- im fne", "- hello world\n- I'm fine")]:
        out = fix_preserving_layout(inp, lambda t: pipeline(t, mode="fix"))[0]
        report(normalise(out) == normalise(exp), f"{inp!r} -> {out!r}")
    out = fix_preserving_layout("The MT300 SWIFT message failed validation in the PLSQL package.",
                                lambda t: pipeline(t, mode="polish"), mode="polish")[0]
    report(all(t in out for t in ("MT300", "SWIFT", "PLSQL")), f"polish keeps identifiers -> {out!r}")
    print(f"\nSelf-tests {'PASSED' if ok_all else 'HAD FAILURES'}.")
    return ok_all


def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return
    for kind in ("dashboard", "setup", "permissions"):
        if f"--{kind}" in args:
            from ui_mac import run_standalone
            run_standalone(kind)
            return
    if "--test" in args:
        sys.exit(0 if run_tests() else 1)

    silent = "--silent" in args or "--autostart" in args
    rest = [a for a in args if not a.startswith("-psn_") and a not in ("--silent", "--autostart", "--no-bar")]
    if rest and not rest[0].startswith("--"):
        mode = "polish" if rest[0] == "-p" else "fix"
        text = " ".join(rest[1:] if mode == "polish" else rest)
        pipeline = load_pipeline(MODEL, fast=False, beams=1, engine_type=ENGINE)
        print(fix_preserving_layout(text, lambda t: pipeline(t, mode=mode), mode=mode)[0])
        return

    MacApp().run(silent=silent)


if __name__ == "__main__":
    main()
