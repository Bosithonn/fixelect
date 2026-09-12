"""End-to-end test of Fix and Polish on a real macOS session (GitHub Actions).

Expects Fixelect.app in /Applications and running, with Accessibility granted,
a model downloaded and onboarding done - the workflow sets that up the way a
user would. Opens TextEdit with a sentence full of typos, selects it and
double-taps Option like a person; then does the same with Shift and accepts
the Polish preview with Return while TextEdit is still in front. Screenshots go to the directory given.

Run: python3 tests/mac_e2e.py [screenshot_dir]
"""

import os
import pathlib
import subprocess
import sys
import time

import Quartz
from AppKit import NSRunningApplication
from ApplicationServices import (AXUIElementCopyAttributeValue, AXUIElementCreateApplication,
                                 kAXFocusedUIElementAttribute, kAXValueAttribute)

TYPOS = "i cant beleive teh wether is so nice today, lets go outside and enjoy it"
ROUGH = "hey can u send me the report by friday i need it for the meeting"
OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "e2e-shots")
OPT, SHIFT, CMD = Quartz.kCGEventFlagMaskAlternate, Quartz.kCGEventFlagMaskShift, Quartz.kCGEventFlagMaskCommand
KEY_OPT, KEY_SHIFT, KEY_A, KEY_RETURN = 58, 56, 0, 36
failures = []


def log(msg):
    print(msg, flush=True)


def annotate(level, title, msg):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title={title}::" + str(msg).replace("%", "%25").replace("\n", "%0A"), flush=True)


def shot(name):
    subprocess.run(["screencapture", "-x", str(OUT / f"{name}.png")], capture_output=True)


def post(keycode, down, flags, etype=None):
    e = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
    if etype is not None:
        Quartz.CGEventSetType(e, etype)
    Quartz.CGEventSetFlags(e, flags)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, e)


def press(keycode, flags=0):
    post(keycode, True, flags)
    time.sleep(0.03)
    post(keycode, False, flags)
    time.sleep(0.05)


def double_tap(flag, keycode):
    """Two quick taps of a modifier, as a person does it."""
    for _ in range(2):
        post(keycode, True, flag, Quartz.kCGEventFlagsChanged)
        time.sleep(0.06)
        post(keycode, False, 0, Quartz.kCGEventFlagsChanged)
        time.sleep(0.12)


def textedit():
    apps = NSRunningApplication.runningApplicationsWithBundleIdentifier_("com.apple.TextEdit")
    return apps[0] if len(apps) else None


def text_of(app):
    """The focused text area's content, read through Accessibility."""
    el = AXUIElementCreateApplication(app.processIdentifier())
    err, focused = AXUIElementCopyAttributeValue(el, kAXFocusedUIElementAttribute, None)
    if err or focused is None:
        return None
    err, value = AXUIElementCopyAttributeValue(focused, kAXValueAttribute, None)
    return None if err or value is None else str(value)


def fixelect_windows():
    info = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    return [w for w in info if w.get("kCGWindowOwnerName") == "Fixelect"]


def preview_window(existing):
    """The Polish preview: a new, tall Fixelect window. The dashboard was already
    open (it is in `existing`) and the progress card is short."""
    for w in fixelect_windows():
        if w.get("kCGWindowNumber") not in existing and w.get("kCGWindowBounds", {}).get("Height", 0) >= 150:
            return w
    return None


def open_document(name, text):
    path = pathlib.Path("/tmp") / f"{name}.txt"
    path.write_text(text)
    subprocess.run(["open", "-a", "TextEdit", str(path)], check=True)
    for _ in range(30):
        app = textedit()
        if app and text_of(app) == text:
            app.activateWithOptions_(Quartz.NSApplicationActivateIgnoringOtherApps
                                     if hasattr(Quartz, "NSApplicationActivateIgnoringOtherApps") else 2)
            time.sleep(1.0)
            return app
        time.sleep(1.0)
    raise RuntimeError(f"TextEdit did not show {path}")


def wait_for_change(app, before, seconds, name, on_poll=None):
    t0 = time.time()
    shot_at = {10, 30, 60, 120}
    while time.time() - t0 < seconds:
        now = text_of(app)
        if now is not None and now.strip() and now.strip() != before.strip():
            time.sleep(1.5)      # let the paste settle
            return text_of(app), time.time() - t0
        if on_poll:
            on_poll()
        elapsed = int(time.time() - t0)
        for s in sorted(shot_at):
            if elapsed >= s:
                shot(f"{name}-waiting-{s}s")
                shot_at.discard(s)
        time.sleep(1.0)
    return text_of(app), None


def test_fix():
    app = open_document("fixelect-fix", TYPOS)
    press(KEY_A, CMD)
    shot("fix-1-selected")
    log("Double-tapping Option on the selected typos…")
    double_tap(OPT, KEY_OPT)
    after, took = wait_for_change(app, TYPOS, 240, "fix")
    shot("fix-2-result")
    log(f"  before: {TYPOS}\n  after:  {after}")
    words = (after or "").lower().replace(",", " ").split()
    if took is None:
        failures.append("Fix: the text was not replaced within 240 s (the double-tap was not detected, "
                        "or the model did not answer).")
    elif "beleive" in words or "teh" in words or "believe" not in words:
        failures.append(f"Fix: text changed but typos remain: {after!r}")
    else:
        log(f"  PASS: fixed in {took:.1f} s")
        annotate("notice", "E2E fix", f"{TYPOS} -> {after} ({took:.1f} s)")


def test_polish():
    app = open_document("fixelect-polish", ROUGH)
    press(KEY_A, CMD)
    shot("polish-1-selected")
    existing = {w.get("kCGWindowNumber") for w in fixelect_windows()}
    log("Double-tapping Shift on the selected text…")
    double_tap(SHIFT, KEY_SHIFT)
    state = {"accepted": False}

    def accept_preview():
        # Return while TextEdit is still in front: Fixelect must catch it for the preview
        if not state["accepted"] and preview_window(existing):
            time.sleep(1.5)
            shot("polish-2-preview")
            press(KEY_RETURN)
            state["accepted"] = True

    after, took = wait_for_change(app, ROUGH, 300, "polish", accept_preview)
    shot("polish-3-result")
    log(f"  before: {ROUGH}\n  after:  {after}")
    if took is None:
        failures.append("Polish: the text was not replaced within 300 s"
                        + ("" if state["accepted"] else " (no preview appeared)") + ".")
    elif after.count("\n") > ROUGH.count("\n") + 1 or len(after.strip()) < 20:
        failures.append(f"Polish: unexpected result: {after!r}")
    else:
        log(f"  PASS: polished in {took:.1f} s")
        annotate("notice", "E2E polish", f"{ROUGH} -> {after} ({took:.1f} s)")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shot("0-desktop")
    for name, test in (("fix", test_fix), ("polish", test_polish)):
        try:
            test()
        except Exception as e:
            failures.append(f"{name}: {type(e).__name__}: {e}")
        subprocess.run(["osascript", "-e", 'tell application "TextEdit" to quit saving no'], capture_output=True)
        time.sleep(2)
    for f in failures:
        log("FAIL " + f)
        annotate("error", "E2E", f)
    if failures:
        # Fixelect's own log explains what it did (job logs need a signed-in viewer)
        for path in (pathlib.Path.home() / "Library" / "Application Support" / "Fixelect").rglob("*.log"):
            tail = path.read_text(errors="replace")[-2500:]
            log(f"--- {path.name}\n{tail}")
            annotate("warning", f"Fixelect log {path.name}", tail)
    log("E2E " + ("passed" if not failures else f"failed ({len(failures)})"))
    return not failures


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
