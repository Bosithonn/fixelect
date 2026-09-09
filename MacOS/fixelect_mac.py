#!/usr/bin/env python3
"""
Fixelect for macOS — Offline AI Grammar Correction & Executive Polish
Apple Silicon Metal Acceleration • macOS Menu Bar Item • Quartz Global Hotkeys

Hotkeys:
  Option x2 (⌥ ⌥)   ->  Default Fix Mode (Double-tap Option; 100% voice preserved)
  Control x2 (⌃ ⌃)  ->  Professional Polish Mode (Double-tap Control; executive clarity)
  Cmd + Option + Q  ->  Quit Fixelect (or customize shortcuts in Dashboard)

Author: Bositxon Erkinxonov
License: MIT / Apache 2.0 (100% Offline, Zero Telemetry)
"""

import atexit
import os
import pathlib
import queue
import re
import signal
import sys
import threading
import time

try:
    import fcntl
    _has_fcntl = True
except ImportError:
    _has_fcntl = False

try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Ensure tools directory is in sys.path
_tools_dir = pathlib.Path(__file__).resolve().parent / "tools"
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from config_mac import load_config, save_config, get_resource_path, play_sound
from hardware_mac import detect_mac_hardware
from downloader_mac import resolve_model, MODELS
from check_guard import load_pipeline, acceptable, polish_guard, normalise
from clipboard_mac import safe_copy, safe_paste, get_clipboard, set_clipboard
from hotkey_mac import MacHotkeyListener, check_accessibility_permissions
from status_bar import MacStatusBar

# --------------------------------------------------------------------------
# Configuration & Defaults
# --------------------------------------------------------------------------

CFG = load_config()
MODEL = CFG.get("model_profile", "3b")
ENGINE = CFG.get("engine", "embedded")
SOUND_ENABLED = CFG.get("sound_enabled", True)
BEAMS = 3
FAST = False
CANDIDATES = 2 if MODELS.get(MODEL, {}).get("kind") == "ollama" else BEAMS

_active_dashboard = [None]
_dashboard_lock = threading.Lock()
_lock_file_handle = None


def ensure_single_instance(on_duplicate=None):
    """
    Ensure only one instance of Fixelect runs using POSIX advisory lock.
    """
    global _lock_file_handle
    if not _has_fcntl:
        return

    lock_path = "/tmp/fixelect.lock"
    try:
        _lock_file_handle = open(lock_path, "w")
        fcntl.flock(_lock_file_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_file_handle.write(str(os.getpid()))
        _lock_file_handle.flush()
    except (IOError, BlockingIOError):
        print("  [Fixelect] Another instance is already running.")
        if on_duplicate:
            on_duplicate()
        sys.exit(0)


# --------------------------------------------------------------------------
# Text processing preserving exact whitespace and structure
# --------------------------------------------------------------------------

def fix_preserving_layout(text, fix_fn, mode="fix"):
    """Fix grammar and spelling while rigorously preserving line breaks and indentation."""
    if "\n" not in text:
        res = fix_fn(text)
        if isinstance(res, tuple):
            return res
        return res, [], text

    # In professional mode, if text has no bullet/numbered list items,
    # process the whole text in one unified pass to preserve paragraph coherence and maximize speed.
    if mode == "polish":
        has_list_items = any(
            re.match(r"^\s*(?:[-*+]\s+|\d+\.\s+)", line)
            for line in text.splitlines()
        )
        if not has_list_items:
            res = fix_fn(text)
            if isinstance(res, tuple):
                return res
            return res, [], text

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


# --------------------------------------------------------------------------
# Main Execution Pipeline
# --------------------------------------------------------------------------

def run_hotkey_action(mode: str = "fix", jobs_queue=None, cache=None):
    """
    Executes when user hits Cmd+Option+F or Cmd+Option+P:
    1. Grabs selected text via safe_copy()
    2. Runs inference through candidate guard
    3. Replaces text via safe_paste()
    4. Plays native macOS completion chime (afplay)
    """
    t0 = time.time()
    text = safe_copy()
    if not text or not text.strip():
        return

    # Check cache
    cache_key = (text, mode)
    if cache is not None and cache_key in cache:
        fixed = cache[cache_key]
        if fixed != text:
            safe_paste(fixed)
            play_sound(mode)
        return

    try:
        from check_guard import load_pipeline
        pipeline = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)

        fixed, applied, expanded = fix_preserving_layout(
            text,
            lambda t: pipeline(t, mode=mode),
            mode=mode
        )

        took_ms = (time.time() - t0) * 1000

        if fixed.strip() == text.strip():
            print(f"  = [Left alone] ({took_ms:.0f}ms)")
        else:
            safe_paste(fixed)
            play_sound(mode)
            label = "POLISHED" if mode == "polish" else "FIXED"
            print(f"  ~ [{label}] ({took_ms:.0f}ms)")
            print(f"    In:  {text[:60]}")
            print(f"    Out: {fixed[:60]}")

        if cache is not None:
            cache[cache_key] = fixed
            if len(cache) > 50:
                cache.pop(next(iter(cache)))

    except Exception as e:
        print(f"  ! Error during {mode} action: {e}")


# --------------------------------------------------------------------------
# Dashboard & Setup Openers
# --------------------------------------------------------------------------

def open_dashboard(fix_fn=None, on_quit=None, hotkey_listener=None):
    with _dashboard_lock:
        dash = _active_dashboard[0]
        if dash and dash.root:
            try:
                dash.root.lift()
                dash.root.focus_force()
                return
            except Exception:
                _active_dashboard[0] = None

        from ui_mac import DashboardWindow
        dash = DashboardWindow(fix_fn=fix_fn, on_quit=on_quit, hotkey_listener=hotkey_listener)
        _active_dashboard[0] = dash

    try:
        dash.show()
    finally:
        with _dashboard_lock:
            if _active_dashboard[0] is dash:
                _active_dashboard[0] = None


def open_setup():
    from ui_mac import SetupWindow
    SetupWindow().show()


# --------------------------------------------------------------------------
# Test Suite Validator
# --------------------------------------------------------------------------

def run_tests():
    print(f"Running Fixelect macOS self-tests with engine [{ENGINE.upper()}] (Default Mode + Professional Polish Mode)...")
    hw = detect_mac_hardware()
    print(f"  Device: {hw['device_name']} (RAM: {hw['ram_gb']} GB)")

    from check_guard import load_pipeline
    try:
        pipeline = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
    except Exception as e:
        print(f"Failed to load pipeline: {e}")
        return False

    fix_cases = [
        ("your welcome", "you're welcome"),
        ("i cant seem too focus on the the task", "I can't seem to focus on the task"),
        ("better then that", "better than that"),
        ("helo how are you", "hello how are you"),
        ("tobehonest its kinda really difficult to change someint in that isutation and you can do that too",
         "to be honest, it's kind of really difficult to change something in that situation, and you can do that too."),
        ("This sentence is perfectly fine already.", "This sentence is perfectly fine already."),
        ("- helo world\n- im fne", "- hello world\n- I'm fine"),
    ]
    all_passed = True
    print("\n--- [1/2] Default Fix Mode Tests (⌥⌘F) ---")
    for inp, exp in fix_cases:
        out, _, _ = fix_preserving_layout(inp, lambda t: pipeline(t, mode="fix"))
        ok = normalise(out) == normalise(exp)
        if not ok:
            all_passed = False
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] In: '{inp.replace(chr(10), ' | ')}' -> Out: '{out.replace(chr(10), ' | ')}'")

    print("\n--- [2/2] Professional Polish Mode Tests (⌥⌘P) ---")
    pro_cases = [
        ("tobehonest i think we need to change someint in that isutation cause it looks bad",
         ["situation", "honest"]),
        ("The MT300 SWIFT message failed validation in the PLSQL package.",
         ["MT300", "SWIFT", "PLSQL"]),
        ("im rly sorry for the delay i was stuck in traffic and my phone died so i couldnt email you earlier",
         ["delay", "traffic"]),
    ]
    for inp, required_tokens in pro_cases:
        out, _, _ = fix_preserving_layout(inp, lambda t: pipeline(t, mode="polish"), mode="polish")
        ok = all(tok.lower() in out.lower() for tok in required_tokens)
        if not ok:
            all_passed = False
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] In:  '{inp}'\n       Out: '{out}'")

    print(f"\nSelf-tests {'PASSED ALL CHECKS (10/10)' if all_passed else 'HAD FAILURES'}.")
    return all_passed


# --------------------------------------------------------------------------
# Main Entry Point
# --------------------------------------------------------------------------

def main():
    global MODEL, ENGINE, SOUND_ENABLED, CANDIDATES

    # CLI option parsing
    for i, a in enumerate(sys.argv):
        if a == "--model" and i + 1 < len(sys.argv):
            MODEL = sys.argv[i + 1]
            CANDIDATES = 2 if MODELS.get(MODEL, {}).get("kind") == "ollama" else BEAMS
            del sys.argv[i:i + 2]
            break

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
        print("""Fixelect — AI Offline Grammar & Executive Polish for macOS

Usage:
  python3 fixelect_mac.py                 Start Fixelect in macOS Menu Bar (default)
  python3 fixelect_mac.py --dashboard     Open Settings, Mode Guide & Live Playground
  python3 fixelect_mac.py --setup         Open Model Setup & Hardware Downloader
  python3 fixelect_mac.py "some text"     Fix text directly in console (Default Fix Mode)
  python3 fixelect_mac.py -p "some text"  Polish text directly (Professional Polish Mode)
  python3 fixelect_mac.py --test          Run macOS self-test validation suite

Global Hotkeys:
  Option x2 (⌥ ⌥)     Default Fix Mode (Double-tap Option; 100% voice preserved)
  Control x2 (⌃ ⌃)    Professional Polish Mode (Double-tap Control; executive clarity)
  Cmd + Option + Q    Quit Fixelect (or customize in Dashboard)
""")
        return

    if "--test" in sys.argv:
        sys.exit(0 if run_tests() else 1)

    # Direct console fixing
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--"):
        mode = "fix"
        text = sys.argv[1]
        if text == "-p" and len(sys.argv) > 2:
            mode = "polish"
            text = " ".join(sys.argv[2:])
        else:
            text = " ".join(sys.argv[1:])

        from check_guard import load_pipeline
        pipeline = load_pipeline(MODEL, fast=FAST, beams=CANDIDATES, engine_type=ENGINE)
        res, _, _ = fix_preserving_layout(text, lambda t: pipeline(t, mode=mode), mode=mode)
        print(res)
        return

    # Direct Setup
    if "--setup" in sys.argv:
        open_setup()
        return

    # Direct Dashboard
    if "--dashboard" in sys.argv:
        open_dashboard(on_quit=lambda: os.kill(os.getpid(), signal.SIGTERM))
        return

    # 0. Single-Instance Check
    ensure_single_instance(on_duplicate=lambda: open_dashboard())

    # 1. Onboarding check: ensure model is downloaded
    if ENGINE == "embedded":
        if not resolve_model(MODEL):
            print("  [Fixelect] Model not found. Launching initial setup window...")
            open_setup()
            if not resolve_model(MODEL):
                print("  [Fixelect] Setup cancelled or model not downloaded. Exiting.")
                return

    # 2. Check macOS Accessibility Permissions with interactive onboarding
    if sys.platform == "darwin" and not check_accessibility_permissions(prompt=False):
        if "--silent" not in sys.argv and "--autostart" not in sys.argv and "--test" not in sys.argv:
            try:
                from ui_mac import AccessibilityGuideWindow
                AccessibilityGuideWindow().show()
            except Exception as e:
                print(f"  ! Note on Accessibility: {e}")
    else:
        check_accessibility_permissions(prompt=True)

    cache = {}

    def handle_fix():
        run_hotkey_action(mode="fix", cache=cache)

    def handle_polish():
        run_hotkey_action(mode="polish", cache=cache)

    def handle_quit():
        print("\n  [Fixelect] Quitting...")
        os.kill(os.getpid(), signal.SIGTERM)

    # 3. Start Global Hotkey Listener
    listener = MacHotkeyListener(on_fix=handle_fix, on_polish=handle_polish, on_quit=handle_quit)
    listener_ok = listener.start()

    # 4. Start Menu Bar Extra item
    bar = None
    if "--no-bar" not in sys.argv and "--no-tray" not in sys.argv:
        bar = MacStatusBar(
            on_open_dashboard=lambda: open_dashboard(on_quit=handle_quit, hotkey_listener=listener),
            on_open_setup=open_setup,
            on_open_words=lambda: open_dashboard(on_quit=handle_quit, hotkey_listener=listener),
            on_quit=handle_quit,
        )
        bar.start()

    from config_mac import load_config, get_hotkey_label
    cfg = load_config()
    fix_lbl = get_hotkey_label("fix", cfg)
    pol_lbl = get_hotkey_label("polish", cfg)

    print("=======================================================")
    print(" Fixelect is active in the macOS Menu Bar")
    print(f" - Press {fix_lbl} to fix typos & grammar (Default: Double-tap Option)")
    print(f" - Press {pol_lbl} to polish into executive prose (Default: Double-tap Control)")
    print(" - Press ⌥⌘Q (Cmd + Option + Q) to quit")
    print(" - Custom shortcuts can be configured in the Dashboard")
    print("=======================================================")

    # Show dashboard on first manual launch
    if "--silent" not in sys.argv and "--autostart" not in sys.argv:
        open_dashboard(on_quit=handle_quit, hotkey_listener=listener)

    # Main thread keep-alive
    try:
        while True:
            time.sleep(1.0)
    except (KeyboardInterrupt, SystemExit):
        listener.stop()
        if bar:
            bar.stop()


if __name__ == "__main__":
    main()
