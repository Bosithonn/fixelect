"""End-to-end test on Windows (GitHub Actions).

Expects Fixelect installed from the real installer and running, with a model
downloaded and onboarding done - the workflow sets that up. Notepad gets some
text; the test selects it and uses Fixelect the way a person does:

  Fix        Ctrl+Alt+F
  Polish     Ctrl+Alt+P, then Enter in the preview
  Translate  Ctrl+Alt+M, 4 (Translate…), 7 (Russian)
  Action     Ctrl+Alt+M, 5 ("Bullet points")
  No select  cursor at the end of the line, nothing selected, Ctrl+Alt+F
  History    every change above is listed in history.json

Synthetic modifier taps can't trigger a double-tap (Fixelect ignores injected
keys on purpose), so Fix and Polish use their always-on backup shortcuts and
the workflow sets the menu to a custom shortcut, Ctrl+Alt+M. The default,
double-tap Shift, is covered by tests/test_hotkeys_win.py.
Run: python tests/win_e2e.py [screenshot_dir]
"""

import ctypes
import os
import pathlib
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes as w

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32.GetForegroundWindow.restype = w.HWND
user32.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
user32.GetWindowThreadProcessId.restype = w.DWORD
user32.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
user32.SendMessageW.restype = ctypes.c_ssize_t
user32.SetForegroundWindow.argtypes = [w.HWND]
user32.BringWindowToTop.argtypes = [w.HWND]
user32.AttachThreadInput.argtypes = [w.DWORD, w.DWORD, w.BOOL]
user32.IsWindowVisible.argtypes = [w.HWND]
user32.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
_ENUM = ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "e2e-shots")
VK = {"ctrl": 0x11, "alt": 0x12, "a": 0x41, "f": 0x46, "m": 0x4D, "p": 0x50, "space": 0x20, "enter": 0x0D,
      "4": 0x34, "5": 0x35, "7": 0x37, "end": 0x23}
EXTENDED = {"end"}
failures = []


def log(msg):
    print(msg, flush=True)


def annotate(level, title, msg):
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::{level} title={title}::" + str(msg).replace("%", "%25").replace("\r", "").replace("\n", "%0A"),
              flush=True)


def shot(name):
    try:
        from PIL import ImageGrab
        ImageGrab.grab().save(OUT / f"{name}.png")
    except Exception as e:
        log(f"  (screenshot failed: {e})")


def key(name, up=False):
    vk = VK[name]
    flags = (2 if up else 0) | (1 if name in EXTENDED else 0)
    user32.keybd_event(vk, user32.MapVirtualKeyW(vk, 0) & 0xFF, flags, 0)


def combo(*names):
    for n in names:
        key(n)
        time.sleep(0.03)
    for n in reversed(names):
        key(n, up=True)
        time.sleep(0.03)
    time.sleep(0.1)


def class_of(hwnd):
    buf = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, buf, 128)
    return buf.value


def pid_of(hwnd):
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def foreground_pid():
    return pid_of(user32.GetForegroundWindow())


def windows_of(pid):
    found = []

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and pid_of(hwnd) == pid:
            found.append(hwnd)
        return True
    user32.EnumWindows(_ENUM(cb), 0)
    return found


def edit_of(hwnd):
    found = []

    def cb(child, _):
        if class_of(child) in ("Edit", "RichEditD2DPT"):
            found.append(child)
        return True
    user32.EnumChildWindows(hwnd, _ENUM(cb), 0)
    return found[0] if found else None


def text_of(edit):
    n = user32.SendMessageW(edit, 0x000E, 0, 0)            # WM_GETTEXTLENGTH
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.SendMessageW(edit, 0x000D, n + 1, ctypes.cast(buf, ctypes.c_void_p).value)   # WM_GETTEXT
    return buf.value


def bring(hwnd):
    fg = user32.GetForegroundWindow()
    me = kernel32.GetCurrentThreadId()
    other = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(other and other != me and user32.AttachThreadInput(me, other, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, other, False)


def open_notepad(name, text):
    path = pathlib.Path(tempfile.gettempdir()) / f"{name}.txt"
    path.write_text(text, encoding="utf-8")
    proc = subprocess.Popen(["notepad.exe", str(path)])
    for _ in range(60):
        wins = [h for h in windows_of(proc.pid) if class_of(h) == "Notepad"]
        if wins and edit_of(wins[0]):
            bring(wins[0])
            time.sleep(1.0)
            return proc, wins[0], edit_of(wins[0])
        time.sleep(0.5)
    raise RuntimeError("Notepad did not open")


def run_case(name, text, trigger, check, menu_keys=(), accept_preview=False, seconds=300, select=True):
    proc, hwnd, edit = open_notepad(f"fixelect-{name}", text)
    try:
        before = text_of(edit)
        bring(hwnd)
        combo("ctrl", "a") if select else combo("ctrl", "end")
        time.sleep(0.5)
        shot(f"{name}-1-selected")
        log(f"{name}: {' + '.join(trigger)}" + (f", then {' '.join(menu_keys)}" if menu_keys else ""))
        combo(*trigger)
        if menu_keys:
            t0 = time.time()
            while foreground_pid() == proc.pid and time.time() - t0 < 30:
                time.sleep(0.3)          # the menu takes focus when it opens
            if foreground_pid() == proc.pid:
                raise RuntimeError("the quick-action menu did not open")
            time.sleep(0.8)
            shot(f"{name}-menu")
            for k in menu_keys:
                combo(k)
                time.sleep(1.0)
        t0, after, took = time.time(), before, None
        while time.time() - t0 < seconds:
            now = text_of(edit)
            if now.strip() and now.strip() != before.strip():
                time.sleep(1.5)
                after, took = text_of(edit), time.time() - t0
                break
            if accept_preview and foreground_pid() not in (proc.pid, 0):
                combo("enter")           # the preview has focus: Enter replaces once it's ready
            time.sleep(2.5)
        shot(f"{name}-2-result")
        log(f"  before: {before!r}\n  after:  {after!r}")
        if took is None:
            failures.append(f"{name}: the text was not replaced within {seconds} s.")
            return
        problem = check(after)
        if problem:
            failures.append(f"{name}: {problem}: {after!r}")
        else:
            log(f"  PASS in {took:.1f} s")
            annotate("notice", f"Windows E2E {name}", f"{before} -> {after} ({took:.1f} s)")
    finally:
        proc.kill()
        time.sleep(1.0)


def check_history(expected):
    """Every replacement above must be listed in History, newest first."""
    import json
    path = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Fixelect" / "history.json"
    try:
        items = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        failures.append(f"history: {path} unreadable ({type(e).__name__})")
        return
    modes = [e.get("mode") for e in items]
    all_replaced = not failures  # a failed case writes no entry; that failure is already reported
    if all_replaced and (len(items) < expected or "action" not in modes or "polish" not in modes):
        failures.append(f"history: expected {expected} entries with fix, polish and action, got {modes}")
    else:
        log(f"  history: {len(items)} entries ({', '.join(modes)})")
        annotate("notice", "Windows E2E history", f"{len(items)} entries: {', '.join(modes)}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shot("0-desktop")
    cases = [
        ("fix", "i cant beleive teh wether is so nice today, lets go outside and enjoy it", ("ctrl", "alt", "f"),
         lambda t: None if "believe" in t.lower() and "beleive" not in t.lower() else "typos remain", (), False),
        ("polish", "hey can u send me the report by friday i need it for the meeting", ("ctrl", "alt", "p"),
         lambda t: None if len(t.strip()) >= 20 else "unexpected result", (), True),
        ("translate", "Good morning, I will send you the report tomorrow before the meeting.",
         ("ctrl", "alt", "m"),
         lambda t: None if sum(1 for c in t.lower() if "а" <= c <= "я" or c == "ё") >= 15 else "not Russian",
         ("4", "7"), False),
        ("action", "We need to buy milk, eggs and bread, then call the plumber about the kitchen sink and pay "
                   "the electricity bill before Friday.", ("ctrl", "alt", "m"),
         lambda t: None if sum(1 for ln in t.splitlines() if ln.strip().startswith(("-", "•", "*"))) >= 2
         else "no bulleted list", ("5",), False),
        ("noselect", "i cant beleive teh wether is so nice today", ("ctrl", "alt", "f"),
         lambda t: None if "believe" in t.lower() and "beleive" not in t.lower() else "typos remain", (), False),
    ]
    for name, text, trigger, check, menu_keys, accept in cases:
        try:
            run_case(name, text, trigger, check, menu_keys, accept, select=name != "noselect")
        except Exception as e:
            failures.append(f"{name}: {type(e).__name__}: {e}")
            shot(f"{name}-error")
    check_history(len(cases))
    for f in failures:
        log("FAIL " + f)
        annotate("error", "Windows E2E", f)
    if failures:
        logf = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Fixelect" / "logs" / "fixelect.log"
        if logf.is_file():
            tail = logf.read_text(encoding="utf-8", errors="replace")[-2500:]
            log(f"--- fixelect.log\n{tail}")
            annotate("warning", "Fixelect log", tail)
    log("Windows E2E " + ("passed" if not failures else f"failed ({len(failures)})"))
    return not failures


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
