"""
Fixelect - fix the grammar of whatever you have selected, anywhere in Windows.

Select some text in any app, press Ctrl+Alt+F, and it is replaced with a
corrected version. Ctrl+Alt+Q quits. Nothing leaves your machine.

    pip install pyperclip comtypes
    ollama serve                       # must be running - see MODEL below
    python fixelect.py

    python fixelect.py "helo how are u"          # fix one sentence and exit
    python fixelect.py --raw "helo how are u"    # ... and show the model's own
                                                 # words plus every edit the
                                                 # guard refused, which is how
                                                 # you tell a weak model from
                                                 # an over-strict guard

MODEL picks the engine. On "lfm" the work happens in Ollama, so torch is not
needed at all; on "base" you also need `pip install torch transformers
sentencepiece` and the first run downloads ~1 GB.

All the thinking lives in tools/check_guard.py - the guard that decides which
of the model's rewrites are corrections and which are it going off on one.
This file is only the Windows plumbing around it.
"""

import ctypes
import ctypes.wintypes as wintypes
import pathlib
import queue
import re
import sys
import threading
import time

if sys.stdout is None:
    class _NullWriter:
        def write(self, *args, **kwargs): pass
        def flush(self, *args, **kwargs): pass
    sys.stdout = _NullWriter()
if sys.stderr is None:
    class _NullWriter:
        def write(self, *args, **kwargs): pass
        def flush(self, *args, **kwargs): pass
    sys.stderr = _NullWriter()

if sys.platform == "win32":
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Fixelect.App.1.0")
    except Exception:
        pass
    try:
        # Per-Monitor High DPI V2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        uxtheme = ctypes.windll.uxtheme
        SetPreferredAppMode = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)((135, uxtheme))
        SetPreferredAppMode(2)  # ForceDark
        FlushMenuThemes = ctypes.WINFUNCTYPE(None)((136, uxtheme))
        FlushMenuThemes()
    except Exception:
        pass

if getattr(sys, "frozen", False):
    _base_dir = pathlib.Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    _tools = _base_dir / "tools"
    if _tools.is_dir():
        sys.path.insert(0, str(_tools))
    sys.path.insert(0, str(_base_dir))
    # Also add exe parent if running one-dir
    _exe_dir = pathlib.Path(sys.executable).resolve().parent
    if (_exe_dir / "tools").is_dir():
        sys.path.insert(0, str(_exe_dir / "tools"))
else:
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "tools"))

from check_guard import BEAMS, MODELS, load_pipeline  # noqa: E402
from config import load_config, save_config, is_auto_start_enabled, set_auto_start, get_resource_path  # noqa: E402
from downloader import resolve_model, download_model  # noqa: E402

# "qwen2.5" - Qwen2.5 3B (sub-second GPU, highest accuracy, zero paraphrasing).
MODEL = "qwen2.5"

# Inference engine: "embedded" (self-contained, zero external dependencies) or "ollama" (fallback)
ENGINE = "embedded"

# Ignored for embedded/Ollama models (already quantized GGUF).
FAST = False

# Greedy deterministic decoding (temp 0.0) provides maximum speed,
# zero hallucinations, and eliminates candidate drift on large documents.
CANDIDATES = 1

# How often to look at what you have selected, for the prefetch below.
POLL_SECONDS = 0.35

# How long a selection must sit still before we start working on it.
SETTLE_SECONDS = 0.4

# Minimum selection length for speculative prefetch.
MIN_PREFETCH_CHARS = 8

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def play_fix_sound(mode="fix"):
    """Subtle, pleasant Windows audio confirmation when text is corrected or polished."""
    cfg = load_config()
    if not cfg.get("sound_enabled", True):
        return
    try:
        import winsound
        if mode == "polish":
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        else:
            winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass


def fix_preserving_layout(text, fix_fn, mode="fix"):
    """Fix grammar and spelling while rigorously preserving line breaks and indentation."""
    if "\n" not in text:
        return fix_fn(text)

    # In professional mode, if text has no bullet/numbered list items,
    # process the whole text in one unified pass to preserve paragraph coherence and maximize speed.
    if mode == "polish":
        has_list_items = any(
            re.match(r"^\s*(?:[-*+]\s+|\d+\.\s+)", line)
            for line in text.splitlines()
        )
        if not has_list_items:
            return fix_fn(text)

    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    fixed_lines = []
    all_applied = []
    all_expanded = []
    word_offset = 0

    for line in lines:
        if not line.strip():
            fixed_lines.append(line)
            continue

        m_lead = re.match(r"^(\s*(?:[-*+]\s+|\d+\.\s+)?)(.*?)(\s*)$", line)
        if m_lead:
            prefix, content, suffix = m_lead.group(1), m_lead.group(2), m_lead.group(3)
            if content.strip():
                fixed_content, applied, expanded = fix_fn(content)
                fixed_lines.append(prefix + fixed_content + suffix)
                for s, e, words, votes in applied:
                    all_applied.append((s + word_offset, e + word_offset, words, votes))
                word_offset += len(expanded.split())
                all_expanded.append(expanded)
            else:
                fixed_lines.append(line)
        else:
            fixed_content, applied, expanded = fix_fn(line)
            fixed_lines.append(fixed_content)
            for s, e, words, votes in applied:
                all_applied.append((s + word_offset, e + word_offset, words, votes))
            word_offset += len(expanded.split())
            all_expanded.append(expanded)

    return newline.join(fixed_lines), all_applied, " ".join(all_expanded)

MOD_ALT, MOD_CONTROL, MOD_NOREPEAT = 0x0001, 0x0002, 0x4000
VK_CONTROL, VK_MENU, VK_SHIFT = 0x11, 0x12, 0x10
VK_C, VK_V, VK_F, VK_P, VK_Q = 0x43, 0x56, 0x46, 0x50, 0x51
KEYEVENTF_KEYUP = 0x0002
WM_HOTKEY = 0x0312
ID_FIX, ID_POLISH, ID_QUIT = 1, 2, 3

IDC_WAIT = 32514
IDC_APPSTARTING = 32650
OCR_NORMAL = 32512
OCR_IBEAM = 32513
OCR_HAND = 32649
SPI_SETCURSORS = 0x0057
IMAGE_CURSOR = 2
LR_SHARED = 0x8000


MUTEX_NAME = "Local\\Fixelect_SingleInstance_Mutex"
SHOW_EVENT_NAME = "Local\\Fixelect_ShowDashboard_Event"
_single_instance_mutex = None


def ensure_single_instance(on_show_callback):
    """
    Ensure only one instance of Fixelect runs per Windows user session.
    If another instance is active, signal it to show its dashboard and exit cleanly.
    """
    global _single_instance_mutex
    if sys.platform != "win32":
        return None

    h_mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    last_err = kernel32.GetLastError()
    if last_err == 183:  # ERROR_ALREADY_EXISTS
        h_event = kernel32.OpenEventW(0x0002, False, SHOW_EVENT_NAME)  # EVENT_MODIFY_STATE
        if h_event:
            kernel32.SetEvent(h_event)
            kernel32.CloseHandle(h_event)
        if h_mutex:
            kernel32.CloseHandle(h_mutex)
        sys.exit(0)

    _single_instance_mutex = h_mutex
    h_event = kernel32.CreateEventW(None, False, False, SHOW_EVENT_NAME)

    def event_listener():
        while True:
            ret = kernel32.WaitForSingleObject(h_event, 0xFFFFFFFF)  # INFINITE
            if ret == 0:  # WAIT_OBJECT_0
                try:
                    on_show_callback()
                except Exception:
                    pass

    threading.Thread(target=event_listener, daemon=True).start()
    return h_mutex


# --------------------------------------------------------------------------
# The cursor
# --------------------------------------------------------------------------

def show_busy_cursor():
    """Swap system arrow, text selection I-beam, and hand for the spinning wait cursor."""
    try:
        h_wait = user32.LoadImageW(0, IDC_WAIT, IMAGE_CURSOR, 0, 0, LR_SHARED)
        if not h_wait:
            h_wait = user32.LoadImageW(0, IDC_APPSTARTING, IMAGE_CURSOR, 0, 0, LR_SHARED)
        if h_wait:
            for ocr in (OCR_NORMAL, OCR_IBEAM, OCR_HAND):
                h_copy = user32.CopyImage(h_wait, IMAGE_CURSOR, 0, 0, 0)
                user32.SetSystemCursor(h_copy, ocr)
    except Exception:
        pass


def restore_cursor():
    """Reload the standard system cursors from Windows settings."""
    try:
        user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
    except Exception:
        pass


class BusyCursor:
    """Show the busy loading cursor immediately and restore it on exit."""

    def __enter__(self):
        show_busy_cursor()
        return self

    def __exit__(self, *_):
        restore_cursor()
        return False


# --------------------------------------------------------------------------
# Keyboard and clipboard
# --------------------------------------------------------------------------

def key_down(vk):
    user32.keybd_event(vk, 0, 0, 0)


def key_up(vk):
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def settle_modifiers():
    """Wait for the hotkey's own modifiers to be released, then force them up.

    THE most important function here. When Ctrl+Alt+F fires you are still
    physically holding Ctrl and Alt. Send Ctrl+C at that moment and Windows
    sees Ctrl+Alt+C, which is not copy - so nothing is copied and the tool
    looks like it randomly does nothing.
    """
    deadline = time.time() + 0.4
    while time.time() < deadline:
        if not any(
            user32.GetAsyncKeyState(vk) & 0x8000
            for vk in (VK_CONTROL, VK_MENU, VK_SHIFT)
        ):
            break
        time.sleep(0.01)

    for vk in (VK_MENU, VK_SHIFT, VK_CONTROL):
        key_up(vk)
    time.sleep(0.03)


def send_ctrl(vk):
    key_down(VK_CONTROL)
    key_down(vk)
    key_up(vk)
    key_up(VK_CONTROL)


def safe_copy(text, retries=5, delay=0.03):
    """Copy text to clipboard with retry loop to handle transient Windows lock contention."""
    import pyperclip
    for _ in range(retries):
        try:
            pyperclip.copy(text)
            return True
        except Exception:
            time.sleep(delay)
    return False


def safe_paste(retries=5, delay=0.03):
    """Paste text from clipboard with retry loop to handle transient lock contention."""
    import pyperclip
    for _ in range(retries):
        try:
            return pyperclip.paste()
        except Exception:
            time.sleep(delay)
    return ""


def set_clipboard_no_history(text):
    """
    Put text on clipboard and flag CanIncludeInClipboardHistory=0.
    Prevents temporary intermediate Fixelect edits from polluting the user's Win+V history.
    """
    try:
        CF_UNICODETEXT = 13
        CF_CAN_INCLUDE = user32.RegisterClipboardFormatW("CanIncludeInClipboardHistory")
        CF_CAN_UPLOAD = user32.RegisterClipboardFormatW("CanUploadToCloudClipboard")

        if not user32.OpenClipboard(None):
            return safe_copy(text)
        try:
            user32.EmptyClipboard()
            # 0 flag prevents Windows 10/11 Clipboard History and Cloud sync capture
            if CF_CAN_INCLUDE:
                user32.SetClipboardData(CF_CAN_INCLUDE, 0)
            if CF_CAN_UPLOAD:
                user32.SetClipboardData(CF_CAN_UPLOAD, 0)

            encoded = (text + "\0").encode("utf-16le")
            h_mem = kernel32.GlobalAlloc(0x0042, len(encoded))  # GMEM_MOVEABLE | GMEM_ZEROINIT
            if h_mem:
                p_mem = kernel32.GlobalLock(h_mem)
                ctypes.memmove(p_mem, encoded, len(encoded))
                kernel32.GlobalUnlock(h_mem)
                user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return safe_copy(text)


def bring_window_to_front(hwnd):
    """Force a Win32 window to the foreground on Windows 10/11 bypassing foreground lock."""
    if sys.platform != "win32" or not hwnd:
        return
    try:
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.SwitchToThisWindow(hwnd, True)
    except Exception:
        pass


def copy_selection():
    """Ctrl+C, then wait until the clipboard actually changes."""
    before = user32.GetClipboardSequenceNumber()
    send_ctrl(VK_C)

    deadline = time.time() + 0.7
    while time.time() < deadline:
        time.sleep(0.015)
        if user32.GetClipboardSequenceNumber() != before:
            time.sleep(0.02)  # let the source app finish writing
            return True
    return False


# --------------------------------------------------------------------------
# Reading the selection without touching the clipboard
# --------------------------------------------------------------------------

class SelectionReader:
    """Reads the focused control's selected text through UI Automation.

    This is what makes the prefetch possible: it sees your selection *without*
    sending Ctrl+C, so it can start work before you ask for it.

    Coverage is not universal. Chrome, Edge, Word, Notepad and most native
    controls implement the text pattern properly. Many Electron and Qt apps do
    not. Every failure here is silent and harmless - `text()` returns None, no
    prefetch happens, and the hotkey still works exactly as it always did.
    """

    def __init__(self):
        self.ok = False
        try:
            import comtypes
            import comtypes.client

            comtypes.CoInitialize()
            module = comtypes.client.GetModule("UIAutomationCore.dll")
            self.uia = comtypes.client.CreateObject(
                module.CUIAutomation, interface=module.IUIAutomation
            )
            self.text_pattern_id = module.UIA_TextPatternId
            self.IUIAutomationTextPattern = module.IUIAutomationTextPattern
            self.ok = True
        except Exception as e:
            print(f"  (prefetch off: UI Automation unavailable - {e})")

    def text(self):
        if not self.ok:
            return None
        try:
            element = self.uia.GetFocusedElement()
            if not element:
                return None
            pattern = element.GetCurrentPattern(self.text_pattern_id)
            if not pattern:
                return None
            ranges = pattern.QueryInterface(self.IUIAutomationTextPattern).GetSelection()
            if not ranges or ranges.Length == 0:
                return None
            selected = ranges.GetElement(0).GetText(-1)
            return selected.strip() or None
        except Exception:
            # Focus moved mid-call, app doesn't support it, COM hiccup - all
            # of these are ordinary and none of them should be visible.
            return None


def watcher(jobs, cache, reader_ready):
    """Watch the selection and queue speculative work on whatever settles.

    Prefetching is only ever an optimisation. If it is wrong, or slow, or the
    app is unsupported, nothing breaks - the hotkey path computes from scratch.
    """
    reader = SelectionReader()
    reader_ready.set()
    if not reader.ok:
        return

    last_seen, seen_at, submitted = None, 0.0, None

    while True:
        time.sleep(POLL_SECONDS)
        current = reader.text()

        if current != last_seen:
            last_seen, seen_at = current, time.time()
            continue

        if (
            current
            and len(current) >= MIN_PREFETCH_CHARS
            and current != submitted
            and current not in cache
            and time.time() - seen_at >= SETTLE_SECONDS
        ):
            submitted = current
            jobs.put(("prefetch", current))


# --------------------------------------------------------------------------
# The worker
# --------------------------------------------------------------------------

def worker(jobs, cache, fix_holder=None):
    """Owns the model. One job at a time, so nothing races the tensors.

    The hotkey thread must keep draining its Windows message queue; if it
    stopped to run the model, further hotkeys would be dropped.
    """
    import pyperclip

    print(f"loading engine [{ENGINE}] for {MODEL} ...")
    fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
    if fix_holder is not None:
        fix_holder[0] = fix
    print("ready. select some text and press ctrl+alt+f\n")

    while True:
        kind, payload = jobs.get()

        if kind == "prefetch":
            # Speculative: the answer may never be asked for. Silent either way.
            if payload not in cache:
                try:
                    cache[payload] = fix(payload)
                    trim(cache)
                except Exception:
                    pass
            continue

        # kind in ("fix", "polish") - the user pressed a hotkey.
        show_busy_cursor()
        mode = kind
        try:
            # Throw away every prefetch still waiting in the queue.
            pending = []
            while not jobs.empty():
                job = jobs.get_nowait()
                if job[0] != "prefetch":
                    pending.append(job)
            for job in pending:
                jobs.put(job)

            saved = None
            try:
                saved = safe_paste()
            except Exception:
                pass

            settle_modifiers()

            if not copy_selection():
                print("  ! nothing selected")
                continue

            text = safe_paste()
            if not text or not text.strip():
                print("  ! selection was empty")
                continue

            started = time.time()
            ready = cache.get(text.strip()) if mode == "fix" else None
            if ready is not None:
                fixed, applied, expanded = ready
                note = " (prepared)"
            else:
                fixed, applied, expanded = fix_preserving_layout(text, lambda t: fix(t, mode=mode), mode=mode)
                note = ""
            took = (time.time() - started) * 1000

            if fixed.strip() == text.strip():
                print(f"  = left alone ({took:.0f}ms){note}")
                print(f"    why: python fixelect.py --raw {text[:50]!r}")
            else:
                set_clipboard_no_history(fixed)
                time.sleep(0.04)
                send_ctrl(VK_V)
                time.sleep(0.12)
                play_fix_sound(mode)
                label = "POLISHED" if mode == "polish" else "FIXED"
                print(f"  ~ [{label}] in {took:.0f}ms{note}")
                print(f"    before: {text[:70]}")
                print(f"    after:  {fixed[:70]}")
                if mode == "fix":
                    for start, end, words, votes in applied:
                        was = " ".join(expanded.split()[start:end])
                        print(f"      + {was!r} -> {' '.join(words)!r} ({votes}/{CANDIDATES})")
        finally:
            restore_cursor()

        if saved is not None:
            def restore_cb(s=saved):
                time.sleep(0.85)  # Extended timeout for heavy desktop apps (Word, Slack, IDEs)
                safe_copy(s)
            threading.Thread(target=restore_cb, daemon=True).start()


def trim(cache, keep=20):
    """Keep the cache small. Selections are transient; old ones never return."""
    while len(cache) > keep:
        cache.pop(next(iter(cache)))


# --------------------------------------------------------------------------

def main():
    global SOUND_ENABLED, MODEL, CANDIDATES

    # Parse --model <name>
    for i, a in enumerate(sys.argv):
        if a == "--model" and i + 1 < len(sys.argv):
            MODEL = sys.argv[i + 1]
            CANDIDATES = 2 if MODELS.get(MODEL, {}).get("kind") == "ollama" else BEAMS
            del sys.argv[i:i + 2]
            break

    global SOUND_ENABLED, ENGINE
    if "--no-sound" in sys.argv:
        SOUND_ENABLED = False
        sys.argv.remove("--no-sound")

    if "--ollama" in sys.argv:
        ENGINE = "ollama"
        sys.argv.remove("--ollama")
    elif "--embedded" in sys.argv:
        ENGINE = "embedded"
        sys.argv.remove("--embedded")

    if "--help" in sys.argv or "-h" in sys.argv:
        print("""Fixelect - AI Offline Grammar & Executive Polish for Windows

Usage:
  python fixelect.py                    Start Fixelect in Windows System Tray (default)
  python fixelect.py --dashboard        Open Settings, Mode Guide & Live Playground
  python fixelect.py --setup            Open Model Setup & Hardware Downloader
  python fixelect.py "some text"        Fix text directly in console (Default Mode)
  python fixelect.py -p "some text"     Polish text directly (Professional Mode)
  python fixelect.py --test             Run complete self-test validation suite
  python fixelect.py --benchmark        Run speed benchmarks across sentences

Global Hotkeys (any app in Windows):
  Ctrl + Alt + F   Default Fix Mode (proofreading, typos, keeps tone & slang)
  Ctrl + Alt + P   Professional Polish Mode (executive tone, active voice)
  Ctrl + Alt + Q   Quit Fixelect cleanly
""")
        return

    for a in list(sys.argv):
        if a.startswith("--engine="):
            ENGINE = a.split("=", 1)[1]
            sys.argv.remove(a)
            break

    if "--download" in sys.argv:
        from downloader import download_model
        download_model(profile="3b")
        return

    if "--setup" in sys.argv:
        from ui import SetupWindow
        SetupWindow().show()
        return

    if "--dashboard" in sys.argv or "--settings" in sys.argv:
        from ui import DashboardWindow
        fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
        DashboardWindow(
            fix_fn=lambda t, mode="fix": fix_preserving_layout(t, lambda x: fix(x, mode=mode), mode=mode)
        ).show()
        return

    polish_mode = False
    for p_flag in ("--polish", "-p"):
        if p_flag in sys.argv:
            polish_mode = True
            sys.argv.remove(p_flag)
            break

    if "--background" in sys.argv or "--hide" in sys.argv:
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, 0)
        sys.argv = [a for a in sys.argv if a not in ("--background", "--hide")]

    if "--benchmark" in sys.argv:
        print(f"Benchmarking Fixelect engine '{ENGINE}' with model '{MODEL}'...")
        fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
        test_sentences = [
            "helo how are you im fne wht abt you",
            "to behonst its kinda really strannge an i don know what s hapenning",
            "tobehonest its kinda really difficult to change someint in that isutation and you can do that too",
            "The MT300 SWIFT message failed validation in the PLSQL package.",
        ]
        for s in test_sentences:
            t0 = time.time()
            out, applied, _ = fix_preserving_layout(s, lambda t: fix(t, mode="fix"))
            ms = (time.time() - t0) * 1000
            print(f"\nIn:    {s}\nOut:   {out}\nSpeed: {ms:.1f}ms")
        return

    if "--test" in sys.argv:
        print(f"Running Fixelect self-tests with engine [{ENGINE.upper()}] (Default Mode + Professional Polish Mode)...")
        fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
        from check_guard import normalise
        fix_cases = [
            ("your welcome", "you're welcome"),
            ("i cant seem too focus on the the task", "I can't seem to focus on the task"),
            ("better then that", "better than that"),
            ("helo how are you", "hello how are you"),
            ("tobehonest its kinda really difficult to change someint in that isutation and you can do that too",
             "to be honest it's kind of really difficult to change something in that situation and you can do that too"),
            ("This sentence is perfectly fine already.", "This sentence is perfectly fine already."),
            ("- helo world\n- im fne", "- hello world\n- I'm fine"),
        ]
        all_passed = True
        print("\n--- [1/2] Default Fix Mode Tests (Ctrl+Alt+F) ---")
        for inp, exp in fix_cases:
            out, _, _ = fix_preserving_layout(inp, lambda t: fix(t, mode="fix"))
            ok = normalise(out) == normalise(exp)
            if not ok:
                all_passed = False
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] In: '{inp.replace(chr(10), ' | ')}' -> Out: '{out.replace(chr(10), ' | ')}'")

        print("\n--- [2/2] Professional Polish Mode Tests (Ctrl+Alt+P) ---")
        pro_cases = [
            ("tobehonest i think we need to change someint in that isutation cause it looks bad",
             ["situation", "honest"]),
            ("The MT300 SWIFT message failed validation in the PLSQL package.",
             ["MT300", "SWIFT", "PLSQL"]),
            ("im rly sorry for the delay i was stuck in traffic and my phone died so i couldnt email you earlier",
             ["delay", "traffic"]),
        ]
        for inp, required_tokens in pro_cases:
            out, _, _ = fix_preserving_layout(inp, lambda t: fix(t, mode="polish"), mode="polish")
            ok = all(tok.lower() in out.lower() for tok in required_tokens)
            if not ok:
                all_passed = False
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] In:  '{inp}'\n       Out: '{out}'")

        print(f"\nSelf-tests {'PASSED ALL CHECKS' if all_passed else 'HAD FAILURES'}.")
        return

    # One-shot mode for testing: python fixelect.py "some text to fix"
    args = sys.argv[1:]
    raw = args and args[0] == "--raw"
    if raw:
        args = args[1:]

    if args:
        text = " ".join(args)

        # --raw shows what the model actually said, before the guard touches
        # it. When a fix doesn't happen there are only two possible culprits -
        # the model never proposed it, or the guard threw it away - and they
        # need opposite repairs. This is the one command that tells them apart.
        if raw:
            from check_guard import (
                consensus, expand, ollama_rewrites, MODELS as SPECS,
            )

            expanded = expand(text)
            print(f"\n  you typed : {text}")
            if expanded != text:
                print(f"  expanded  : {expanded}")

            started = time.time()
            rewrites = ollama_rewrites(SPECS[MODEL]["repo"], expanded, CANDIDATES, mode="fix")
            took = (time.time() - started) * 1000

            print("\n  what the model said:")
            for i, r in enumerate(rewrites):
                print(f"    [{i}] {r}")

            final, applied, outvoted = consensus(expanded, rewrites)
            print("\n  what the guard kept:")
            for start, end, words, votes in applied:
                was = " ".join(expanded.split()[start:end])
                print(f"    + {was!r} -> {' '.join(words)!r} ({votes}/{CANDIDATES})")
            if not applied:
                print("    (nothing)")

            if outvoted:
                print("\n  what the guard threw away:")
                for (start, end, words), votes in sorted(outvoted):
                    was = " ".join(expanded.split()[start:end])
                    print(f"    - {was!r} -> {' '.join(words)!r} "
                          f"(only {votes}/{CANDIDATES} agreed)")

            print(f"\n  result: {final}")
            print(f"  {took:.0f}ms for {CANDIDATES} candidates")
            return

        print(f"loading engine [{ENGINE}] for {MODEL} ...")
        fix = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)

        mode = "polish" if polish_mode else "fix"
        started = time.time()
        fixed, applied, expanded = fix_preserving_layout(text, lambda t: fix(t, mode=mode), mode=mode)

        label = "POLISH (Ctrl+Alt+P)" if mode == "polish" else "FIX (Ctrl+Alt+F)"
        print(f"\n  mode: {label}")
        print(f"  in  : {text}")
        print(f"  out : {fixed}")
        if mode == "fix":
            for start, end, words, votes in applied:
                was = " ".join(expanded.split()[start:end])
                print(f"        + {was!r} -> {' '.join(words)!r} ({votes}/{CANDIDATES})")
        print(f"  {(time.time() - started) * 1000:.0f}ms")
        return

    main_thread_id = kernel32.GetCurrentThreadId()

    _dashboard_lock = threading.Lock()
    _active_dashboard = [None]

    def open_dashboard():
        with _dashboard_lock:
            active = _active_dashboard[0]
            if active is not None and getattr(active, "root", None):
                try:
                    active.root.deiconify()
                    bring_window_to_front(active.root.winfo_id())
                    active.root.lift()
                    active.root.focus_force()
                    return
                except Exception:
                    _active_dashboard[0] = None

            def run_fix(t, mode="fix"):
                # Wait for engine to finish loading if recently started
                deadline = time.time() + 20.0
                while fix_holder[0] is None and time.time() < deadline:
                    time.sleep(0.15)

                if fix_holder[0] is None:
                    # Initialize on demand if worker hasn't finished
                    fix_holder[0] = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)

                fn = fix_holder[0]
                return fix_preserving_layout(t, lambda x: fn(x, mode=mode), mode=mode)

            from ui import DashboardWindow
            dash = DashboardWindow(
                fix_fn=run_fix,
                on_quit=quit_app,
            )
            _active_dashboard[0] = dash

        try:
            dash.show()
        finally:
            with _dashboard_lock:
                if _active_dashboard[0] is dash:
                    _active_dashboard[0] = None

    def quit_app():
        user32.PostThreadMessageW(main_thread_id, 0x0012, 0, 0)

    # 0. Single-Instance Check (Win32 Named Mutex)
    ensure_single_instance(open_dashboard)

    # 1. Onboarding check: If model is not yet available, launch Setup & Downloader
    if ENGINE == "embedded":
        cfg = load_config()
        profile = cfg.get("model_profile", "3b")
        if not resolve_model(profile):
            print("  [Fixelect] Model not found. Launching initial setup window...")
            from ui import SetupWindow
            SetupWindow().show()
            cfg = load_config()
            profile = cfg.get("model_profile", "3b")
            if not resolve_model(profile):
                print("  [Fixelect] Setup cancelled or model not downloaded. Exiting.")
                return

    jobs = queue.Queue()
    cache = {}
    reader_ready = threading.Event()
    fix_holder = [None]

    threading.Thread(target=worker, args=(jobs, cache, fix_holder), daemon=True).start()
    threading.Thread(
        target=watcher, args=(jobs, cache, reader_ready), daemon=True
    ).start()
    reader_ready.wait(timeout=10)

    # RegisterHotKey with a null window posts WM_HOTKEY to *this thread's*
    # message queue, so no window is needed at all.
    mods = MOD_CONTROL | MOD_ALT | MOD_NOREPEAT
    if not user32.RegisterHotKey(None, ID_FIX, mods, VK_F):
        err_msg = (
            "Fixelect could not register the primary hotkey (Ctrl + Alt + F).\n\n"
            "Another running application (such as GPU software, a recording tool, "
            "or another utility) is currently using this hotkey.\n\n"
            "Please close the conflicting application or change its shortcuts, "
            "then launch Fixelect again."
        )
        try:
            user32.MessageBoxW(0, err_msg, "Fixelect — Hotkey Collision", 0x00000010)
        except Exception:
            pass
        sys.exit(1)
    if not user32.RegisterHotKey(None, ID_POLISH, mods, VK_P):
        print("  ! warning: could not register ctrl+alt+p (professional mode)")
    user32.RegisterHotKey(None, ID_QUIT, mods, VK_Q)

    tray = None
    if "--no-tray" not in sys.argv:
        try:
            from tray import TrayManager
            tray = TrayManager(on_open_settings=open_dashboard, on_quit=quit_app)
            tray.start()
            if "--autostart" in sys.argv or "--silent" in sys.argv:
                def notify_startup():
                    time.sleep(1.2)
                    tray.notify(
                        "Fixelect Active",
                        "Running in system tray. Press Ctrl+Alt+F to fix text, Ctrl+Alt+P to polish."
                    )
                threading.Thread(target=notify_startup, daemon=True).start()
        except Exception as e:
            print(f"  (Tray disabled: {e})")

    # If launched explicitly by user (not Windows boot and not silent),
    # open Dashboard so the user sees the active window, hardware specs & playground!
    if "--silent" not in sys.argv and "--autostart" not in sys.argv and "--no-dashboard" not in sys.argv:
        threading.Thread(target=open_dashboard, daemon=True).start()

    print(f"\n  Engine: {ENGINE.upper()}")
    print("  ctrl+alt+f   fix selected text (default mode: proofread & typos)")
    print("  ctrl+alt+p   polish selected text (professional mode: structure & tone)")
    print("  ctrl+alt+q   quit (or exit via System Tray)\n")

    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                if msg.wParam == ID_QUIT:
                    break
                show_busy_cursor()
                mode = "polish" if msg.wParam == ID_POLISH else "fix"
                jobs.put((mode, None))
    finally:
        if tray:
            try:
                tray.stop()
            except Exception:
                pass
        user32.UnregisterHotKey(None, ID_FIX)
        user32.UnregisterHotKey(None, ID_POLISH)
        user32.UnregisterHotKey(None, ID_QUIT)
        # Never leave the user staring at an hourglass because we crashed.
        restore_cursor()
        if ENGINE == "embedded":
            try:
                from engine import get_default_engine
                get_default_engine().stop()
            except Exception:
                pass
        print("bye")


if __name__ == "__main__":
    main()
