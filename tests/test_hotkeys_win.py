"""Model-free tests for the Windows double-tap (Alt Alt / Ctrl Ctrl).

Drives WinHotkeyListener's callbacks directly with fake keys and Windows key
timestamps, so it runs on every platform. Run: python tests/test_hotkeys_win.py
"""

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Windows" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import hotkey_win as H  # noqa: E402


class Key:
    def __init__(self, vk):
        self.vk = vk


ALT, CTRL, A = Key(164), Key(162), Key(65)


class Data:
    """The KBDLLHOOKSTRUCT fields pynput hands the event filter."""

    def __init__(self, ms):
        self.time = ms


def make():
    fired = []
    lst = H.WinHotkeyListener(on_fix=lambda: fired.append("fix"), on_polish=lambda: fired.append("polish"),
                              config={"trigger_mode": "double_tap"})
    lst._fire = lambda cb: cb()          # run callbacks inline
    return lst, fired


def key(lst, k, down, ms, injected=False):
    """One key event as pynput delivers it: the filter stamps it, then the callback runs."""
    lst._stamp(0, Data(ms))
    (lst._on_press if down else lst._on_release)(k, injected)


def taps(lst, k, times):
    for down_ms, up_ms in times:
        key(lst, k, True, down_ms)
        key(lst, k, False, up_ms)


def t_double_alt():
    lst, fired = make()
    taps(lst, ALT, [(1000, 1050), (1150, 1200)])
    return fired == ["fix"], fired


def t_double_ctrl():
    lst, fired = make()
    taps(lst, CTRL, [(1000, 1050), (1150, 1200)])
    return fired == ["polish"], fired


def t_late_callbacks_use_windows_time():
    # All four keys stamped quickly, callbacks run later in a burst (busy PC): still a double-tap.
    lst, fired = make()
    for ms in (1000, 1050, 1150, 1200):
        lst._stamp(0, Data(ms))
    lst._on_press(ALT)
    lst._on_release(ALT)
    lst._on_press(ALT)
    lst._on_release(ALT)
    return fired == ["fix"], fired


def t_slow_taps_rejected():
    lst, fired = make()
    taps(lst, ALT, [(1000, 1050), (1900, 1950)])
    return fired == [], fired


def t_long_hold_rejected():
    lst, fired = make()
    taps(lst, ALT, [(1000, 1500), (1550, 1600)])
    return fired == [], fired


def t_chord_rejected():
    lst, fired = make()
    key(lst, ALT, True, 1000)
    key(lst, A, True, 1020)              # Alt+A
    key(lst, A, False, 1040)
    key(lst, ALT, False, 1060)
    taps(lst, ALT, [(1150, 1200)])
    return fired == [], fired


def t_injected_keys_keep_stamps_in_step():
    # Our own Ctrl+C is injected and ignored, but its stamps must still be consumed.
    lst, fired = make()
    key(lst, CTRL, True, 900, injected=True)
    key(lst, CTRL, False, 910, injected=True)
    taps(lst, ALT, [(1000, 1050), (1150, 1200)])
    return fired == ["fix"], fired


def t_suspended():
    lst, fired = make()
    lst.suspend(True)
    taps(lst, ALT, [(1000, 1050), (1150, 1200)])
    return fired == [], fired


def main():
    tests = [(n[2:].replace("_", " "), f) for n, f in globals().items() if n.startswith("t_")]
    passed = 0
    for name, fn in tests:
        try:
            ok, got = fn()
        except Exception as e:  # a crash is a failure, not an abort
            ok, got = False, f"{type(e).__name__}: {e}"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n        got: {got!r}"))
        if not ok and os.environ.get("GITHUB_ACTIONS"):
            print(f"::error title=Windows hotkey test: {name}::{got!r}")
    print(f"\n{passed}/{len(tests)} Windows hotkey tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
