"""Model-free tests for the engine plumbing and the fixes around it: when the
AI engine is probed over HTTP (and when it must not be), the llama-server
flags each platform starts with, reply cleaning that keeps the writer's own
quotes, the macOS model lookup, the macOS quick-action menu closing on a click
elsewhere, the bounded macOS clipboard snapshot and, on Windows, the Polish
preview wait and the tray's model switch.

No model, no server: processes, HTTP and AppKit are faked.
Run: python tests/test_engine.py
"""

import json
import os
import pathlib
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Never touch the real config folders: every platform's config lives under a temp home.
_HOME = tempfile.mkdtemp(prefix="fixelect-test-home-")
os.environ["HOME"] = os.environ["USERPROFILE"] = _HOME
os.environ["LOCALAPPDATA"] = os.path.join(_HOME, "AppData", "Local")
os.environ["FIXELECT_MODELS_DIR"] = os.path.join(_HOME, "models")
sys.path.insert(0, str(ROOT / "shared"))

results = []


def check(name, fn):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, f"{type(e).__name__}: {e}"
    if ok is None:
        print(f"[SKIP] {name}: {detail}")
        return
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f": {detail}"))


class FakeProc:
    def __init__(self, alive=True, pid=4242):
        self.alive, self.pid, self.returncode = alive, pid, None

    def poll(self):
        return None if self.alive else 1

    def terminate(self):
        self.alive = False

    def kill(self):
        self.alive = False

    def wait(self, timeout=None):
        return 0


# ---------------------------------------------------------------------------
# Reply cleaning keeps what the writer wrote
# ---------------------------------------------------------------------------

def t_clean():
    from check_guard import clean
    cases = [
        (clean('"Hola," dijo.', source='"Hello," he said.'), '"Hola," dijo.'),
        (clean('Dijo "hola"', source='He said "hi"'), 'Dijo "hola"'),
        (clean('"I can\'t go"', source="i cant go"), "I can't go"),                 # a wrapper goes
        (clean("'fixed'", source="fixd"), "fixed"),
        (clean("The students'", source="the students'"), "The students'"),
        (clean("Output: the value is 5", source="Output: the value is 5"), "Output: the value is 5"),
        (clean("Output: fixed", source="fixd"), "fixed"),
        (clean("Here is my version:\nIt works.", preserve_newlines=True, source="here is my version:\nit works"),
         "Here is my version:\nIt works."),
        (clean("Here is the corrected text:\nHello", source="helo"), "Hello"),
        (clean('Sure!\n"x"'), 'Sure! "x'),   # no source: unchanged behaviour
    ]
    bad = [(got, want) for got, want in cases if got != want]
    return not bad, bad


def t_translate_keeps_quotes():
    import actions

    class Eng:
        def ensure_running(self):
            return True

        def chat_completion(self, messages, **k):
            return '"Hola," dijo.'
    out = actions.run(Eng(), '"Hello," he said.', {"kind": "translate", "target": "es"})
    return out == '"Hola," dijo.', out


# ---------------------------------------------------------------------------
# Windows engine: probing, flags
# ---------------------------------------------------------------------------

def _win_engine():
    sys.path.insert(0, str(ROOT / "Windows" / "tools"))
    try:
        import engine
    except Exception as e:  # ctypes.wintypes is unavailable on some platforms
        return None, f"Windows engine not importable here ({type(e).__name__})"
    return engine, ""


def _probe_counter(eng):
    calls = []

    def fake(path, timeout=0.8):
        calls.append(path)
        return {"status": "ok"}
    eng._get_json = fake
    return calls


def t_win_trusts_recent_answer():
    engine, why = _win_engine()
    if engine is None:
        return None, why
    eng = engine.EmbeddedEngine(port=1, model_profile="1.5b", model_path="x.gguf")
    calls = _probe_counter(eng)
    eng.process, eng._owns_process = FakeProc(), True
    eng._ok_at = time.monotonic()
    fast = eng.is_running() and eng.is_running() and not calls
    eng._ok_at = time.monotonic() - engine.TRUST_SECONDS - 1
    probed = eng.is_running() and calls == ["/health"]
    eng.process.alive = False
    dead = not eng.is_running() and calls == ["/health"]
    return fast and probed and dead, (fast, probed, dead, calls)


def t_win_no_probe_after_unload():
    engine, why = _win_engine()
    if engine is None:
        return None, why
    eng = engine.EmbeddedEngine(port=1, model_profile="1.5b", model_path="x.gguf")
    calls = _probe_counter(eng)
    eng.process, eng._owns_process = FakeProc(), True
    ok_unload = eng.unload()
    running = eng.is_running()
    # a server Fixelect did not start (reused from a previous run) is still probed
    eng2 = engine.EmbeddedEngine(port=1, model_profile="1.5b", model_path="x.gguf")
    calls2 = _probe_counter(eng2)
    eng2.is_running()
    return ok_unload and not running and not calls and calls2 == ["/health"], (running, calls, calls2)


def t_win_free_port_skips_probe():
    engine, why = _win_engine()
    if engine is None:
        return None, why
    with tempfile.TemporaryDirectory() as d:
        model = pathlib.Path(d) / "m.gguf"
        model.write_bytes(b"x")
        eng = engine.EmbeddedEngine(port=1, model_profile="1.5b", model_path=str(model))
        calls = _probe_counter(eng)
        eng._port_free = lambda p: True
        launched = []
        eng.server_candidates = lambda: [(pathlib.Path("llama-server.exe"), pathlib.Path(d), True)]
        eng._launch = lambda *a: launched.append(a)
        ok = eng.start()
    return ok and launched and not calls, (launched, calls)


def t_win_launch_flags_and_atexit_once():
    engine, why = _win_engine()
    if engine is None:
        return None, why
    cmds, registered = [], []

    class Popen(FakeProc):
        def __init__(self, cmd, **kw):
            super().__init__()
            cmds.append(cmd)

    old = (engine.subprocess.Popen, engine.atexit.register, engine.get_llama_args, engine._get_job)
    engine.subprocess.Popen = Popen
    engine.atexit.register = lambda fn: registered.append(fn)
    engine.get_llama_args = lambda context_size=2048: (["-c", str(context_size)],
                                                       {"backend": "cpu", "gpu_name": "CPU"})

    class Job:
        def adopt(self, p):
            pass
    engine._get_job = lambda: Job()
    try:
        with tempfile.TemporaryDirectory() as d:
            eng = engine.EmbeddedEngine(port=1, model_profile="1.5b", model_path="m.gguf")
            eng.is_healthy = lambda timeout=0.8: True
            eng._launch(pathlib.Path(d) / "llama-server.exe", pathlib.Path(d), True, 5)
            eng.stop()
            eng._launch(pathlib.Path(d) / "llama-server.exe", pathlib.Path(d), False, 5)
    finally:
        engine.subprocess.Popen, engine.atexit.register, engine.get_llama_args, engine._get_job = old
    bundled, other = cmds
    ok = ("--swa-full" in bundled and "--no-webui" in bundled and "--swa-full" not in other
          and len(registered) == 1)
    return ok, (bundled, other, len(registered))


def t_win_cpu_threads_for_prompt():
    sys.path.insert(0, str(ROOT / "Windows" / "tools"))
    try:
        import hardware
    except Exception as e:
        return None, f"not importable here ({type(e).__name__})"
    old = hardware.detect_hardware
    hardware.detect_hardware = lambda: {"is_gpu": False, "threads": 6, "total_cores": 12}
    try:
        cpu, _ = hardware.get_llama_args()
        hardware.detect_hardware = lambda: {"is_gpu": True, "threads": 6, "total_cores": 12}
        gpu, _ = hardware.get_llama_args()
    finally:
        hardware.detect_hardware = old
    ok = cpu[cpu.index("-t") + 1] == "6" and cpu[cpu.index("-tb") + 1] == "12" and "-tb" not in gpu
    return ok, (cpu, gpu)


def _prime_cases(eng, set_model):
    """Drive eng._prime() with a fake server. Returns a list of failed expectations."""
    problems = []
    with tempfile.TemporaryDirectory() as d:
        eng._slot_dir = pathlib.Path(d)
        set_model("gemma-4-E2B-it-Q4_K_M.gguf")
        name = eng._slot_file()
        server = {"restore_ok": True, "n_saved": None, "calls": []}

        def slot(action):
            server["calls"].append(action)
            if action == "restore":
                return {"n_restored": 571} if server["restore_ok"] else None
            (eng._slot_dir / name).write_bytes(b"kv")
            return {"n_saved": server["n_saved"]}
        eng._slot = slot
        primed = []

        def primer():
            primed.append(1)
            eng._last_total = 572
        eng.primer = primer

        # 1. no file yet: warm up once, save, keep it; another model's old file goes
        (eng._slot_dir / "old-model-1.0.0.slot").write_bytes(b"old")
        server["n_saved"] = 571
        eng._prime()
        files = sorted(p.name for p in eng._slot_dir.iterdir())
        if files != [name] or primed != [1] or server["calls"] != ["save"]:
            problems.append(("first load", files, primed, server["calls"]))
        # 2. file present: restore it, no warm-up request
        primed.clear(), server["calls"].clear()
        eng._prime()
        if primed or server["calls"] != ["restore"]:
            problems.append(("restore", primed, server["calls"]))
        # 3. restore refused (other llama.cpp build): delete, warm up, save a new one
        primed.clear(), server["calls"].clear()
        server["restore_ok"] = False
        eng._prime()
        if primed != [1] or server["calls"] != ["restore", "save"] or not (eng._slot_dir / name).is_file():
            problems.append(("bad file replaced", primed, server["calls"]))
        # 4. something else ran between the warm-up and the save: never keep that
        (eng._slot_dir / name).unlink()
        server["n_saved"] = 600
        eng._prime()
        if (eng._slot_dir / name).exists():
            problems.append("an interleaved request was kept on disk")
        # 5. no primer (e.g. the Ollama path): nothing is saved
        server["n_saved"], eng.primer = 571, None
        eng._prime()
        if (eng._slot_dir / name).exists():
            problems.append("saved without a warm-up")
        eng._slot_dir = None
    return problems


def t_win_prompt_cache():
    engine, why = _win_engine()
    if engine is None:
        return None, why
    eng = engine.EmbeddedEngine(port=1, model_profile="1.5b", model_path="x.gguf")

    def set_model(name):
        eng.model_path = name
    problems = _prime_cases(eng, set_model)
    return not problems, problems


def t_win_bundled_gets_cache_dir():
    engine, why = _win_engine()
    if engine is None:
        return None, why
    return (bool(engine.EmbeddedEngine._prompt_cache_dir()),
            "prompt cache folder could not be created in the config folder")


# ---------------------------------------------------------------------------
# macOS: model lookup, engine flags, menu, clipboard
# ---------------------------------------------------------------------------

def t_mac_prompt_cache():
    _mac_tools()
    import engine_mac as E
    eng = E.MacEmbeddedEngine(model_profile="gemma4-e2b")

    def set_model(name):
        eng._slot_model = name
    problems = _prime_cases(eng, set_model)
    return not problems, problems

def _mac_tools():
    p = str(ROOT / "MacOS" / "tools")
    if p not in sys.path:
        sys.path.insert(1, p)


def t_mac_ollama_lookup_only_for_qwen():
    _mac_tools()
    import downloader_mac as DM
    home = pathlib.Path(_HOME)
    manifests = home / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    blobs = home / ".ollama" / "models" / "blobs"
    manifests.mkdir(parents=True, exist_ok=True)
    blobs.mkdir(parents=True, exist_ok=True)
    (blobs / "sha256-small").write_bytes(b"model")
    (manifests / "0.5b").write_text(json.dumps({"layers": [
        {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:small"}]}))
    gemma = DM.find_ollama_mac_model("gemma4-e2b")
    small = DM.find_ollama_mac_model("0.5b")
    return gemma is None and small is not None and small.name == "sha256-small", (gemma, small)


def t_mac_engine_flags():
    _mac_tools()
    import engine_mac as E
    cmds = []

    class Popen(FakeProc):
        def __init__(self, cmd, **kw):
            super().__init__()
            cmds.append(cmd)

    old_popen, old_resolve = E.subprocess.Popen, E.resolve_model
    E.subprocess.Popen = Popen
    E.resolve_model = lambda profile: pathlib.Path("model.gguf")
    try:
        for pinned in (True, False):
            eng = E.MacEmbeddedEngine(model_profile="gemma4-e2b")
            eng.publish = True          # the daemon: no attaching to another process
            eng.hw = {"is_apple_silicon": False}
            eng._find_llama_server = lambda pinned=pinned: (pathlib.Path("/x/llama-server"), pinned)
            eng._free_port = lambda: 18899
            state = {"n": 0}

            def healthy(port=None, timeout=0.8, state=state):
                state["n"] += 1
                return state["n"] > 1    # nothing there before the launch, then up
            eng.is_healthy = healthy
            eng._serves = lambda *a, **k: False
            eng.start(timeout=5)
            eng._owns_process = False   # don't let atexit try to stop the fake
    finally:
        E.subprocess.Popen, E.resolve_model = old_popen, old_resolve
    cmds = [c for c in cmds if "llama-server" in str(c[0])]   # not the hardware probe's sysctl
    pinned_cmd, brew_cmd = cmds
    ok = ("--swa-full" in pinned_cmd and "--swa-full" not in brew_cmd
          and "-tb" in pinned_cmd and "-tb" in brew_cmd)
    return ok, cmds


def t_mac_engine_no_probe_after_unload():
    _mac_tools()
    import engine_mac as E
    eng = E.MacEmbeddedEngine(model_profile="gemma4-e2b")
    calls = []
    eng._get_json = lambda path, port=None, timeout=0.8: calls.append(path) or {"status": "ok"}
    eng.process, eng._owns_process = FakeProc(), True
    eng._ok_at = time.monotonic()
    fast = eng.is_running() and not calls
    eng.unload()
    after = eng.is_running()
    return fast and not after and not calls, (fast, after, calls)


class _Rect:
    def __init__(self, x, y, w, h):
        self.origin = type("P", (), {"x": x, "y": y})()
        self.size = type("S", (), {"width": w, "height": h})()


def t_mac_menu_click_elsewhere_closes():
    _mac_tools()
    import hud_mac as HM

    class AppHelper:
        @staticmethod
        def callAfter(fn, *a):
            fn(*a)

    mouse = {"x": 0.0, "y": 0.0}

    class NSEvent:
        @staticmethod
        def mouseLocation():
            return type("M", (), dict(mouse))()

    class Panel:
        def frame(self):
            return _Rect(100, 100, 300, 200)

        def orderOut_(self, _):
            pass

    old = {k: getattr(HM, k, None) for k in ("AppHelper", "NSEvent")}
    HM.AppHelper, HM.NSEvent = AppHelper, NSEvent
    finished = []
    try:
        HM._menu.update(state={"stack": [("Fixelect", [{"label": "a"}])], "index": 0,
                               "submenu": lambda i: None, "finish": finished.append}, panel=Panel())
        mouse.update(x=200, y=150)
        inside_swallowed = HM.menu_key(-1)          # click on the menu itself
        inside_kept_open = not finished
        mouse.update(x=10, y=10)
        outside_swallowed = HM.menu_key(-1)         # click in another app
    finally:
        HM._menu.pop("state", None)
        HM._menu.pop("panel", None)
        for k, v in old.items():
            if v is None:
                delattr(HM, k)
            else:
                setattr(HM, k, v)
    ok = not inside_swallowed and inside_kept_open and not outside_swallowed and finished == [None]
    return ok, (inside_swallowed, inside_kept_open, outside_swallowed, finished)


def t_mac_snapshot_is_bounded():
    _mac_tools()
    import clipboard_mac as CM

    class Data(bytes):
        def length(self):
            return len(self)

    class Item:
        def __init__(self, sizes):
            self.sizes = sizes

        def types(self):
            return list(self.sizes)

        def dataForType_(self, t):
            return Data(b"x" * self.sizes[t])

    class Pb:
        def pasteboardItems(self):
            return [Item({"public.utf8-plain-text": 10, "public.tiff": 40, "public.png": 40})]

    old = (CM._has_appkit, CM._pb, CM._SNAPSHOT_MAX_BYTES)
    CM._has_appkit, CM._pb, CM._SNAPSHOT_MAX_BYTES = True, lambda: Pb(), 45
    try:
        snap = CM.snapshot()
    finally:
        CM._has_appkit, CM._pb, CM._SNAPSHOT_MAX_BYTES = old
    types = list(snap[0]) if snap else []
    return types == ["public.utf8-plain-text", "public.tiff"], types


# ---------------------------------------------------------------------------
# Windows app: Polish preview wait, tray model switch
# ---------------------------------------------------------------------------

def _win_app():
    if sys.platform != "win32":
        return None, "Windows only"
    sys.path.insert(0, str(ROOT / "Windows"))
    import fixelect
    return fixelect, ""


def t_win_preview_wait():
    fx, why = _win_app()
    if fx is None:
        return None, why
    import queue
    import threading
    app = fx.FixelectApp()
    app.DECISION_POLL, app.DECISION_GONE_POLLS = 0.05, 3

    class Preview:
        alive = True

    class UI:
        preview = Preview()
    app.ui = UI()
    q = queue.Queue()
    threading.Timer(0.3, lambda: q.put(("accept", "done"))).start()
    answered = app._await_decision(q)           # a live preview is waited for, however long
    UI.preview.alive = False
    started = time.time()
    gone = app._await_decision(queue.Queue())   # a vanished one counts as Cancel
    quick = time.time() - started < 2
    return answered == ("accept", "done") and gone == ("cancel", None) and quick, (answered, gone)


def t_win_tray_switch_saves_choice():
    fx, why = _win_app()
    if fx is None:
        return None, why
    import engine
    app = fx.FixelectApp()
    fx.update_config(model_profile="3b")
    old = engine.get_default_engine
    engine.get_default_engine = lambda **k: None
    app._load_engine = lambda: True
    app.notify = lambda *a: None
    try:
        app._switch_model("1.5b")
    finally:
        engine.get_default_engine = old
    now = fx.load_config().get("model_profile")
    return now == "1.5b", now


def t_win_menu_translate_needs_gemma():
    """The real shortcut handler, with the clipboard and the menu stubbed: Uzbek with a
    Qwen model shows the Gemma 4 card and never reaches the engine; Italian goes through."""
    fx, why = _win_app()
    if fx is None:
        return None, why
    app = fx.FixelectApp()
    cards, ran = [], []
    old = (fx.apps.foreground, fx.clip.snapshot, fx.settle_modifiers, fx.copy_selection, fx.clip.get_text,
           fx.clip.get_html)
    fx.apps.foreground = lambda: (1, "notepad.exe", 4242)
    fx.clip.snapshot = lambda: []
    fx.settle_modifiers = lambda: None
    fx.copy_selection = lambda: True
    fx.clip.get_text = lambda: "Good morning, I will send you the report tomorrow."
    fx.clip.get_html = lambda: None
    app.hud = lambda kind, title, detail="", **k: cards.append((kind, title))
    app._schedule_restore = lambda *a, **k: None
    app._refocus = lambda hwnd: None
    app._do_action = lambda text, item, *a: ran.append(item["target"])
    try:
        results_ = []
        for profile, target in (("3b", "uz"), ("3b", "it"), ("gemma4-e2b", "uz")):
            fx.update_config(model_profile=profile, disabled_apps=[])
            cards.clear(), ran.clear()
            app._choose_action = lambda cfg, anchor, t=target: {"kind": "translate", "target": t, "label": t}
            app._do_hotkey_inner("menu")
            results_.append((profile, target, list(cards), list(ran)))
    finally:
        (fx.apps.foreground, fx.clip.snapshot, fx.settle_modifiers, fx.copy_selection, fx.clip.get_text,
         fx.clip.get_html) = old
    want = [("3b", "uz", [("info", "Uzbek needs the Gemma 4 model")], []),
            ("3b", "it", [], ["it"]),
            ("gemma4-e2b", "uz", [], ["uz"])]
    return results_ == want, results_


def main():
    check("clean() keeps the writer's quotes, labels and first line", t_clean)
    check("translate keeps quotes around the text", t_translate_keeps_quotes)
    check("Windows engine: a recent answer is trusted, then probed again", t_win_trusts_recent_answer)
    check("Windows engine: no probe after an idle unload", t_win_no_probe_after_unload)
    check("Windows engine: a free port is not probed before launching", t_win_free_port_skips_probe)
    check("Windows engine: --swa-full for the bundled build; atexit once", t_win_launch_flags_and_atexit_once)
    check("Windows CPU: every core reads the prompt", t_win_cpu_threads_for_prompt)
    check("Windows engine: prompt cache saved once, restored after, never someone's text",
          t_win_prompt_cache)
    check("Windows engine: prompt cache folder", t_win_bundled_gets_cache_dir)
    check("macOS engine: prompt cache saved once, restored after, never someone's text", t_mac_prompt_cache)
    check("macOS: Ollama lookup only maps Qwen tags", t_mac_ollama_lookup_only_for_qwen)
    check("macOS engine: --swa-full only for the pinned build, -tb on CPU", t_mac_engine_flags)
    check("macOS engine: no probe after an idle unload", t_mac_engine_no_probe_after_unload)
    check("macOS menu: a click elsewhere closes it", t_mac_menu_click_elsewhere_closes)
    check("macOS clipboard snapshot is bounded", t_mac_snapshot_is_bounded)
    check("Windows: the Polish preview wait gives up on a vanished preview", t_win_preview_wait)
    check("Windows: switching models from the tray saves the choice", t_win_tray_switch_saves_choice)
    check("Windows: Translate to Uzbek with Qwen asks for Gemma 4", t_win_menu_translate_needs_gemma)
    print(f"\n{sum(results)}/{len(results)} engine tests passed")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
