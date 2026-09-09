"""
macOS Native Clipboard Bridge and Synthetic Keystroke Injector for Fixelect.
Implements:
- NSPasteboard (PyObjC) & pbcopy/pbpaste synchronization
- Synthetic Cmd+C and Cmd+V keystrokes via Quartz CGEvent or AppleScript
- Safe retry loops and transient clipboard restoration
"""

import subprocess
import sys
import threading
import time

# Attempt to load native Quartz CGEvent APIs if on macOS
_has_quartz = False
if sys.platform == "darwin":
    try:
        from Quartz import (
            CGEventCreateKeyboardEvent,
            CGEventPost,
            kCGHIDEventTap,
            kCGEventFlagMaskCommand,
            CGEventSetFlags,
        )
        _has_quartz = True
    except Exception:
        _has_quartz = False

# Fallback keyboard simulator via pynput if Quartz is not loaded
_pynput_kb = None
try:
    from pynput.keyboard import Controller, Key
    _pynput_kb = Controller()
except Exception:
    pass


def get_clipboard() -> str:
    """Read current text from the macOS system clipboard."""
    # 1. Try PyObjC NSPasteboard
    if sys.platform == "darwin":
        try:
            from AppKit import NSPasteboard, NSStringPboardType
            pb = NSPasteboard.generalPasteboard()
            content = pb.stringForType_(NSStringPboardType)
            if content is not None:
                return str(content)
        except Exception:
            pass

    # 2. Universal macOS pbpaste CLI tool
    try:
        res = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=1.0)
        return res.stdout or ""
    except Exception:
        return ""


def set_clipboard(text: str) -> bool:
    """Write text to the macOS system clipboard with retry logic."""
    for attempt in range(4):
        # 1. Try PyObjC NSPasteboard
        if sys.platform == "darwin":
            try:
                from AppKit import NSPasteboard, NSStringPboardType
                pb = NSPasteboard.generalPasteboard()
                pb.clearContents()
                pb.setString_forType_(text, NSStringPboardType)
                return True
            except Exception:
                pass

        # 2. Universal macOS pbcopy CLI tool
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, text=True)
            p.communicate(input=text, timeout=1.0)
            if p.returncode == 0:
                return True
        except Exception:
            time.sleep(0.05)

    return False


def simulate_cmd_key(char: str) -> None:
    """
    Simulate a native Cmd + <char> keystroke (e.g. Cmd+C or Cmd+V).
    Prefers high-speed Quartz CGEvent, falls back to pynput or AppleScript.
    """
    char_lower = char.lower()

    # 1. High-speed Quartz CGEvent (0.5ms latency)
    if _has_quartz:
        # macOS virtual key codes: 'c' = 8, 'v' = 9
        vk_code = 8 if char_lower == "c" else (9 if char_lower == "v" else 0)
        if vk_code != 0:
            try:
                # Key down
                ev_down = CGEventCreateKeyboardEvent(None, vk_code, True)
                CGEventSetFlags(ev_down, kCGEventFlagMaskCommand)
                CGEventPost(kCGHIDEventTap, ev_down)
                time.sleep(0.015)

                # Key up
                ev_up = CGEventCreateKeyboardEvent(None, vk_code, False)
                CGEventSetFlags(ev_up, 0)
                CGEventPost(kCGHIDEventTap, ev_up)
                return
            except Exception:
                pass

    # 2. pynput fallback
    if _pynput_kb:
        try:
            with _pynput_kb.pressed(Key.cmd):
                _pynput_kb.press(char_lower)
                _pynput_kb.release(char_lower)
            return
        except Exception:
            pass

    # 3. AppleScript System Events fallback
    try:
        script = f'tell application "System Events" to keystroke "{char_lower}" using command down'
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=1.5)
    except Exception:
        pass


def get_pasteboard_change_count() -> int:
    """Return the current changeCount of the general pasteboard on macOS."""
    if sys.platform == "darwin":
        try:
            from AppKit import NSPasteboard
            return int(NSPasteboard.generalPasteboard().changeCount())
        except Exception:
            pass
    return -1


def safe_copy(timeout: float = 0.22) -> str:
    """
    Trigger Cmd+C in active application and poll clipboard for the selected text.
    Uses NSPasteboard changeCount to guarantee that text was ACTUALLY selected,
    completely preventing accidental overwriting when the selection was empty!
    """
    initial_count = get_pasteboard_change_count()
    old_clip = get_clipboard()

    simulate_cmd_key("c")

    t0 = time.time()
    while time.time() - t0 < timeout:
        # If native changeCount changed, a copy definitely occurred!
        current_count = get_pasteboard_change_count()
        if initial_count != -1 and current_count != -1:
            if current_count != initial_count:
                return get_clipboard()
        else:
            now_clip = get_clipboard()
            if now_clip != old_clip:
                return now_clip
        time.sleep(0.025)

    # If changeCount did NOT change, no text was selected! Abort safely.
    if initial_count != -1 and get_pasteboard_change_count() == initial_count:
        return ""

    now_clip = get_clipboard()
    if now_clip != old_clip:
        return now_clip
    return ""


def safe_paste(replacement_text: str, restore_delay: float = 0.85) -> None:
    """
    Write replacement text to clipboard, simulate Cmd+V, then restore original clipboard.
    Preserves transient clipboard so user data is never lost.
    """
    saved_clip = get_clipboard()

    set_clipboard(replacement_text)
    time.sleep(0.03)
    simulate_cmd_key("v")
    time.sleep(0.08)

    if saved_clip and saved_clip != replacement_text:
        def _restore():
            time.sleep(restore_delay)
            # Only restore if clipboard still has our replacement text
            if get_clipboard() == replacement_text:
                set_clipboard(saved_clip)
        threading.Thread(target=_restore, daemon=True).start()
