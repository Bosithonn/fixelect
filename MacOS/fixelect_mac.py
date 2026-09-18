#!/usr/bin/env python3
"""
Fixelect for macOS — Offline AI Grammar Correction & Polish
Apple Silicon Metal acceleration • Menu bar app • Global triggers

Triggers (default):
  Option x2 (⌥ ⌥)   ->  Fix typos & grammar (voice preserved)
  Shift x2   (⇧ ⇧)  ->  Polish (preview first, choose a style)
Quit from the menu bar icon.

Process layout: this daemon owns the menu bar (rumps, main thread), the
keyboard listener, the AI engine and the native status panel / Polish
preview. Every settings window (Dashboard, Setup, Permissions) runs as a
separate short-lived process, because Cocoa and Tk both insist on the main
thread.

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
for _p in (_here.parent / "shared", _here / "tools", pathlib.Path(getattr(sys, "_MEIPASS", _here)) / "tools"):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from config_mac import (  # noqa: E402
    load_config, update_config, get_hotkey_label, get_lock_path, get_config_path, get_config_dir, play_sound,
    log_error,
)
from downloader_mac import resolve_model, MODELS  # noqa: E402
from check_guard import (  # noqa: E402
    POLISH_STYLES, load_pipeline, fix_preserving_layout, normalise, expand, detect_language,
)
import apps_mac as apps  # noqa: E402
import chunking  # noqa: E402
import clipboard_mac as clip  # noqa: E402
import languages  # noqa: E402
import richtext  # noqa: E402
from hotkey_mac import MacHotkeyListener, check_accessibility_permissions  # noqa: E402
from version import APP_VERSION, RELEASES_URL  # noqa: E402

MODEL = "qwen2.5"
ENGINE = load_config().get("engine", "embedded")
MAX_SELECTION_CHARS = 30000
RESTORE_DELAY = 1.5     # slow apps (Word, Electron) read the paste late; restoring sooner pasted the old clipboard
HUD_DELAY = 0.35
UNDO_WINDOW = 30.0

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


def release_single_instance():
    global _lock_handle
    if _lock_handle is not None:
        try:
            _lock_handle.close()
        except Exception:
            pass
        _lock_handle = None


def offer_move_to_applications():
    """Opened straight from the disk image (or a copy macOS "translocated" to a
    random read-only folder), start-at-login points at a path that disappears and
    the app stops working once the disk is ejected. Offer to move it. Returns
    True when the moved copy was launched and this one should quit."""
    if not getattr(sys, "frozen", False):
        return False
    exe = pathlib.Path(sys.executable).resolve()
    bundle = next((p for p in exe.parents if p.suffix == ".app"), None)
    where = str(exe)
    if bundle is None or not ("/AppTranslocation/" in where or where.startswith("/Volumes/")):
        return False
    script = ('display dialog "Fixelect is running from the disk image. Move it to your Applications folder '
              'so it keeps working after you eject the disk and can start when you log in." '
              'with title "Fixelect" buttons {"Not Now", "Move to Applications"} '
              'default button "Move to Applications" with icon note')
    try:
        answer = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=300).stdout
    except Exception:
        return False
    if "Move to Applications" not in answer:
        return False
    target = pathlib.Path("/Applications/Fixelect.app")
    try:
        if target.exists():
            import shutil
            shutil.rmtree(target)
        subprocess.run(["ditto", str(bundle), str(target)], check=True, capture_output=True, timeout=300)
    except Exception as e:
        log_error(f"move to Applications failed: {type(e).__name__}: {e}")
        notify("Couldn't move Fixelect", "Drag Fixelect into your Applications folder, then open it from there.")
        return False
    log_error("moved to /Applications")
    subprocess.Popen(["open", "-n", str(target)])
    return True


def running_daemon_pid():
    try:
        pid = int(get_lock_path().read_text().strip() or 0)
        if pid and pid != os.getpid():
            os.kill(pid, 0)
            return pid
    except Exception:
        pass
    return None


def ui_command(kind, page=None):
    extra = [f"--page={page}"] if page else []
    if getattr(sys, "frozen", False):
        return [sys.executable, f"--{kind}"] + extra
    return [sys.executable, str(pathlib.Path(__file__).resolve()), f"--{kind}"] + extra


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


def supported_languages_line():
    names = ["English"] + [languages.NAMES[c] for c in languages.SUPPORTED]
    return ", ".join(names[:-1]) + " and " + names[-1]


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


class MacApp:
    def __init__(self):
        self.jobs = queue.Queue()
        self.fix = None
        self.status_info = {"state": "loading", "detail": "Starting…", "model": load_config().get("model_profile", "3b")}
        self.listener = None
        self.bar = None
        self.ui_procs = {}
        self.cancel_event = threading.Event()
        self.update_info = None
        self._restore_lock = threading.Lock()
        self._restore_timer = None
        self._pending = None
        self._last_hotkey_done = 0.0
        self._undo = None
        self._want_dashboard = threading.Event()
        self._stopping = False
        try:
            from hud_mac import MacHud
            self.card = MacHud()
        except Exception:
            self.card = None

    # -- status & feedback -----------------------------------------------------

    def set_status(self, state, detail=""):
        self.status_info.update(state=state, detail=detail, model=load_config().get("model_profile", "3b"))

    def status(self):
        return dict(self.status_info)

    def hud(self, kind, title, detail="", actions=(), timeout=None, progress=None):
        if load_config().get("hud_enabled", True) and self.card is not None and self.card.available:
            self.card.show(kind, title, detail, actions, timeout, progress)
        elif kind in ("info", "error"):
            notify(title, detail or title)

    def hide_hud(self):
        if self.card is not None:
            self.card.hide()

    # -- engine ---------------------------------------------------------------

    def _engine(self):
        from engine_mac import get_default_engine
        return get_default_engine()

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
            log_error(f"engine load failed: {e}")
            return False

    def _unload_if_idle(self):
        minutes = float(load_config().get("unload_minutes", 10) or 0)
        if ENGINE != "embedded" or minutes <= 0 or self.fix is None:
            return
        eng = self._engine()
        if eng.owns_server() and eng.idle_seconds() >= minutes * 60 and eng.unload():
            self.set_status("sleeping", "Model unloaded to free memory")
            log_error(f"model unloaded after {minutes:g} idle minutes")

    def _wake_engine(self, show_card=True):
        if ENGINE != "embedded" or self.fix is None:
            return
        eng = self._engine()
        if eng.is_running():
            return
        if show_card:
            self.hud("working", "Waking up the AI model…", "This takes a few seconds after a break.")
        self.set_status("loading", "Loading the AI model…")
        eng.ensure_running()
        self.set_status("ready", "Ready")

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
                elif kind == "unload":
                    self._unload_if_idle()
                elif kind == "wake":
                    self._wake_engine(show_card=False)
                elif kind == "undo":
                    self._do_undo(payload)
                elif kind in ("fix", "polish"):
                    if queued_at < self._last_hotkey_done:
                        continue
                    try:
                        self._do_hotkey(kind)
                    finally:
                        self._last_hotkey_done = time.time()
            except Exception as e:
                log_error(f"job {kind} failed: {type(e).__name__}: {e}")
                if kind in ("fix", "polish"):
                    self.set_status("ready" if self.fix else "error", "")
                    self.hud("error", "Fixelect couldn't finish", str(e) or type(e).__name__,
                             actions=[("Help", lambda: self.open_window("dashboard", "Help"))], timeout=7000)

    def trigger(self, mode):
        log_error(f"shortcut received: {mode}")
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

    # -- the hotkey path ----------------------------------------------------------

    def _options(self, cfg, mode, style=None, variant=0, info=None):
        return dict(style=style or cfg.get("polish_style", "professional"),
                    custom=cfg.get("custom_instruction", "") if mode == "polish" else "",
                    multilingual=bool(cfg.get("multilingual", True)), variant=variant, info=info)

    def _run(self, text, mode, opts, progress=None, cancel=None):
        if self.fix is None and not self._load_engine():
            raise RuntimeError(self.status_info.get("detail") or "The AI engine is not available.")
        self.set_status("busy", "Working…")
        try:
            return chunking.process(text, lambda t: self.fix(t, mode=mode, **opts), mode=mode,
                                    progress=progress, cancel=cancel)
        finally:
            self.set_status("ready", "Ready")

    def _enable_app(self, bundle_id):
        cfg = load_config()
        update_config(disabled_apps=[a for a in cfg.get("disabled_apps", []) if a != bundle_id])
        self.hud("success", f"Fixelect is on in {apps.display_name(bundle_id)}", "Use the shortcut again.", timeout=2500)

    def _do_hotkey(self, mode):
        cfg = load_config()
        front, bundle_id, pid = apps.foreground()
        if apps.is_disabled(bundle_id, cfg, pid):
            self.hud("info", f"Fixelect is off in {apps.display_name(bundle_id)}",
                     "You turned it off for this app in Settings.",
                     actions=[("Turn on here", lambda: self._enable_app(bundle_id))], timeout=4500)
            return

        original = self._take_pending()
        if original is None:
            original = clip.snapshot()
        clip.wait_for_modifiers()
        if not clip.copy_selection():
            self._schedule_restore(original, 0.05)
            self.hud("info", "Select some text first",
                     "Highlight the words you want to " + ("fix" if mode == "fix" else "polish")
                     + ", then use the shortcut again.", timeout=3500)
            return
        text = clip.get_text()
        rich = clip.get_rich() if cfg.get("keep_formatting", True) else {}
        if not text or not text.strip():
            self._schedule_restore(original, 0.05)
            self.hud("info", "Nothing to fix here", "The selection has no text (an image or a file?).", timeout=3000)
            return
        if len(text) > MAX_SELECTION_CHARS:
            self._schedule_restore(original, 0.05)
            self.hud("info", "That selection is very long",
                     f"Select up to {MAX_SELECTION_CHARS:,} characters at a time.", timeout=4500)
            return
        lang = detect_language(text)
        supported = languages.supported_for(cfg.get("model_profile"))
        if lang != "en" and (lang not in supported or not cfg.get("multilingual", True)):
            self._schedule_restore(original, 0.05)
            name = languages.NAMES.get(lang, "This language")
            if lang in supported:
                self.hud("info", f"{name} is turned off", "Turn on other languages in Settings → Writing.",
                         timeout=5000)
            elif lang in languages.supported_for(languages.MORE_LANGUAGES_MODEL):
                self.hud("info", f"{name} needs the Gemma 4 model",
                         f"{name} is in beta. Choose Gemma 4 E2B in Settings → Model.",
                         actions=[("Model", lambda: self.open_window("dashboard", "Model"))], timeout=6000)
            else:
                self.hud("info", f"{name if lang != 'other' else 'This language'} isn't supported yet",
                         f"Fixelect works in {supported_languages_line()}.", timeout=5500)
            return

        if mode == "polish" and cfg.get("polish_preview", True):
            fixed = self._polish_with_preview(text, cfg, front)
            info = {}
            if fixed is None:
                self._schedule_restore(original, 0.05)
                return
        else:
            fixed, info = self._compute(text, mode, cfg)
            if fixed is None:
                self._schedule_restore(original, 0.05)
                self.hud("info", "Cancelled", "Your text was not changed.", timeout=2000)
                return

        if fixed == text:
            self._schedule_restore(original, 0.05)
            if info.get("polish_fallback"):
                self.hud("info", "Left as is", "A polish would have changed what you meant.", timeout=3500)
            else:
                self.hud("success", "Looks good", "No changes needed.", timeout=2200)
            return

        kept = clip.rewrite_rich(rich, text, fixed) if rich else {}
        clip.set_text(fixed, transient=True, html=kept.get("html"), rtf=kept.get("rtf"))
        count = clip.change_count()
        time.sleep(0.03)
        clip.wait_for_modifiers()
        clip.paste()
        play_sound(mode)
        self._schedule_restore(original, RESTORE_DELAY, only_if_count=count)

        self._undo = {"app": front, "time": time.time()}
        undo = [("Undo", lambda ctx=self._undo: self.jobs.put(("undo", ctx, time.time())))]
        detail = "Formatting kept." if kept else ""
        if mode == "polish" and not info.get("polish_fallback"):
            self.hud("polish", "Polished", detail, actions=undo, timeout=5000)
        else:
            n = richtext.count_changes(text, fixed)
            if info.get("polish_fallback"):
                detail = "Polishing would have changed your meaning, so only typos were fixed."
            self.hud("success", f"Fixed {plural(n, 'word')}" if n else "Fixed", detail, actions=undo, timeout=5000)

    def _compute(self, text, mode, cfg, style=None, variant=0):
        info = {}
        opts = self._options(cfg, mode, style, variant, info)
        self.cancel_event.clear()
        done = threading.Event()
        long_job = chunking.needs_chunking(text, mode)
        verb = "Fixing" if mode == "fix" else "Polishing"
        state = {"progress": None}

        def show_working():
            if done.is_set():
                return
            p = state["progress"]
            self.hud("working", f"{verb}…" if p is None else f"{verb}…  {p[0] + 1} of {p[1]}",
                     "Esc to cancel" if long_job else "",
                     actions=[("Cancel", self.cancel_event.set)] if long_job else (),
                     progress=(p[0] / p[1]) if p else None)

        def progress(i, total):
            state["progress"] = (min(i, total - 1), total)
            if i and not done.is_set():
                show_working()

        timer = threading.Timer(HUD_DELAY, show_working)
        timer.daemon = True
        timer.start()
        esc = self._esc_listener() if long_job else None
        try:
            self._wake_engine()
            return self._run(text, mode, opts, progress=progress, cancel=self.cancel_event), info
        except chunking.Cancelled:
            return None, info
        finally:
            done.set()
            timer.cancel()
            if esc is not None:
                try:
                    esc.stop()
                except Exception:
                    pass
            self.hide_hud()

    def _esc_listener(self):
        """Esc cancels a long job. The shortcut tap watches for it (Esc still reaches the app)."""
        listener = self.listener
        if listener is None:
            return None
        listener.watch_escape(self.cancel_event.set)

        class _Stop:
            @staticmethod
            def stop():
                listener.watch_escape(None)
        return _Stop()

    def _polish_with_preview(self, text, cfg, front_app):
        if self.listener is not None:
            from hud_mac import preview_key
            self.listener.capture_keys(preview_key)
        try:
            return self._polish_preview_loop(text, cfg, front_app)
        finally:
            if self.listener is not None:
                self.listener.capture_keys(None)

    def _polish_preview_loop(self, text, cfg, front_app):
        from hud_mac import ask_polish
        style = cfg.get("polish_style", "professional")
        if style not in POLISH_STYLES:
            style = "professional"
        variant, seen = 0, set()
        while True:
            result, info = self._compute(text, "polish", cfg, style, variant)
            for _ in range(3):
                if not variant or (style, result) not in seen:
                    break
                variant += 1
                result, _ = self._compute(text, "polish", cfg, style, variant)
            if result is None:
                return None
            seen.add((style, result))
            note = "Kept your meaning: only typos were fixed." if info.get("polish_fallback") else ""
            if result == text:
                note = "Nothing to improve — this already reads well."
            action, value = ask_polish(POLISH_STYLES, style, text, result, note)
            if action == "retry":
                variant = variant + 1 if value == style else 0
                style = value
                continue
            if action == "cancel":
                apps.activate(front_app)
                return None
            apps.activate(front_app)
            time.sleep(0.25)
            return value

    def _do_undo(self, ctx):
        if not ctx or ctx is not self._undo or time.time() - ctx["time"] > UNDO_WINDOW:
            self.hud("info", "Nothing to undo", "Use ⌘Z in your app instead.", timeout=2500)
            return
        apps.activate(ctx.get("app"))
        time.sleep(0.15)
        self._undo = None
        clip.wait_for_modifiers()
        clip.undo()
        self.hud("success", "Undone", "Your original text is back.", timeout=1800)

    # -- windows (separate processes) ---------------------------------------------

    def open_window(self, kind, page=None):
        proc = self.ui_procs.get(kind)
        if proc is not None and proc.poll() is None:
            try:
                if page:
                    (get_config_dir() / "dashboard_page").write_text(page)
                os.kill(proc.pid, signal.SIGUSR1)  # ask it to come forward
            except Exception:
                pass
            return proc
        try:
            proc = subprocess.Popen(ui_command(kind, page))
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

    def permission_watcher(self, then_welcome=False):
        while not self._stopping and not check_accessibility_permissions(prompt=False):
            time.sleep(2.0)
        if self._stopping:
            return
        if self.listener:
            self.listener.reload(load_config())
        print("  [Fixelect] Accessibility granted - triggers active.")
        log_error("accessibility granted")
        if then_welcome:
            # First launch: the permission step came first; now show the tutorial.
            time.sleep(1.0)
            self.open_window("dashboard", "Welcome")

    def idle_watcher(self):
        while not self._stopping:
            time.sleep(30)
            if self.jobs.empty():
                self.jobs.put(("unload", None, time.time()))

    def update_watcher(self):
        import updater
        time.sleep(25)
        while not self._stopping:
            try:
                if updater.due(load_config()):
                    info = updater.check()
                    update_config(last_update_check=time.time())
                    self.update_info = info
                    if info and info["version"] != load_config().get("skipped_version"):
                        notify(f"Fixelect {info['version']} is available", "Choose “Update Fixelect…” in the menu bar.")
            except Exception as e:
                log_error(f"update check failed: {type(e).__name__}")
            time.sleep(3600)

    def open_update(self):
        info = self.update_info or {}
        subprocess.Popen(["open", info.get("url") or RELEASES_URL])

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
        if offer_move_to_applications():
            release_single_instance()   # the moved copy takes over
            return

        signal.signal(signal.SIGTERM, lambda *_: self.quit())
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        signal.signal(signal.SIGUSR1, lambda *_: self._want_dashboard.set())
        # A settings window found the model unloaded: load it again.
        signal.signal(signal.SIGUSR2, lambda *_: self.jobs.put(("wake", None, time.time())))

        just_set_up = False
        if ENGINE == "embedded" and not resolve_model(load_config().get("model_profile", "3b")):
            subprocess.run(ui_command("setup"))
            if not resolve_model(load_config().get("model_profile", "3b")):
                print("  [Fixelect] Setup cancelled - exiting.")
                return
            just_set_up = True

        threading.Thread(target=self.worker, daemon=True).start()
        self.listener = MacHotkeyListener(on_fix=lambda: self.trigger("fix"),
                                          on_polish=lambda: self.trigger("polish"), config=load_config())
        self.listener.start()
        threading.Thread(target=self.config_watcher, daemon=True).start()
        threading.Thread(target=self.idle_watcher, daemon=True).start()
        threading.Thread(target=self.update_watcher, daemon=True).start()

        needs_welcome = just_set_up or not load_config().get("onboarding_done", False)
        if not check_accessibility_permissions(prompt=False):
            self.open_window("permissions")
            threading.Thread(target=self.permission_watcher, args=(needs_welcome,), daemon=True).start()
        elif needs_welcome:
            self.open_window("dashboard", "Welcome")
        elif not silent:
            self.open_window("dashboard")

        print(f"  Fixelect {APP_VERSION} is running. Fix: {get_hotkey_label('fix')}  Polish: {get_hotkey_label('polish')}")
        from status_bar import MacStatusBar
        self.bar = MacStatusBar(
            on_open_dashboard=lambda page=None: self.open_window("dashboard", page),
            on_quit=self.quit,
            get_status=self.status,
            want_dashboard=self._want_dashboard,
            get_update=lambda: self.update_info,
            on_update=self.open_update,
        )
        try:
            self.bar.run()  # blocks on the main thread until quit
        finally:
            self.shutdown()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def run_tests():
    print(f"Running Fixelect {APP_VERSION} macOS self-tests [{ENGINE.upper()}]...")
    ok_all = True

    def report(ok, text):
        nonlocal ok_all
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {text}")

    for inp, exp in [("enter your user id", "enter your user id"), ("i feel ill", "I feel ill"), ("im fne", "I'm fine")]:
        report(expand(inp) == exp, f"expand({inp!r}) -> {expand(inp)!r}")
    for inp, exp in [("Привет, как дела?", "ru"), ("Salom, qalaysan? Ertaga uchrashamiz.", "uz")]:
        report(detect_language(inp) == exp, f"language({inp!r}) -> {detect_language(inp)}")
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
    out = chunking.process("Mañana voy a la ofisina porque tengo que acer muchas cosas.", lambda t: pipeline(t, mode="fix"))
    report("oficina" in out, f"Spanish fix -> {out!r}")
    print(f"\nSelf-tests {'PASSED' if ok_all else 'HAD FAILURES'}.")
    return ok_all


def main():
    args = sys.argv[1:]
    if "--help" in args or "-h" in args:
        print(__doc__)
        return
    if "--version" in args:
        print(APP_VERSION)
        return
    if "--check-https" in args:  # CI: can the frozen app verify HTTPS (model download)?
        import net
        ok, detail = net.check(MODELS["3b"]["url"])
        print(detail)
        sys.exit(0 if ok else 1)
    page = next((a.split("=", 1)[1] for a in args if a.startswith("--page=")), None)
    for kind in ("dashboard", "setup", "permissions"):
        if f"--{kind}" in args:
            from ui import run_standalone
            run_standalone(kind, page=page)
            return
    if "--test" in args:
        sys.exit(0 if run_tests() else 1)

    silent = "--silent" in args or "--autostart" in args
    rest = [a for a in args if not a.startswith("-psn_") and a not in ("--silent", "--autostart", "--no-bar")]
    if rest and not rest[0].startswith("--"):
        mode = "polish" if rest[0] == "-p" else "fix"
        text = " ".join(rest[1:] if mode == "polish" else rest)
        pipeline = load_pipeline(MODEL, fast=False, beams=1, engine_type=ENGINE)
        print(chunking.process(text, lambda t: pipeline(t, mode=mode), mode=mode))
        return

    MacApp().run(silent=silent)


if __name__ == "__main__":
    main()
