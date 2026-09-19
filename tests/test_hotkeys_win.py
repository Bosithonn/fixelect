"""Model-free tests for the Windows double-taps (Alt Alt / Ctrl Ctrl / Shift Shift).

Drives WinHotkeyListener's callbacks directly with fake keys and Windows key
timestamps, so it runs on every platform. Run: python tests/test_hotkeys_win.py
"""

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Windows" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import config as C  # noqa: E402
import hotkey_win as H  # noqa: E402


class Key:
    def __init__(self, vk):
        self.vk = vk


ALT, CTRL, SHIFT, A = Key(164), Key(162), Key(160), Key(65)


class Data:
    """The KBDLLHOOKSTRUCT fields pynput hands the event filter."""

    def __init__(self, ms):
        self.time = ms


def make(**cfg):
    fired = []
    config = {"trigger_mode": "double_tap"}
    config.update(cfg)
    lst = H.WinHotkeyListener(on_fix=lambda: fired.append("fix"), on_polish=lambda: fired.append("polish"),
                              config=config, on_menu=lambda: fired.append("menu"))
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


QUICK = [(1000, 1050), (1150, 1200)]


def t_double_alt():
    lst, fired = make()
    taps(lst, ALT, QUICK)
    return fired == ["fix"], fired


def t_double_ctrl():
    lst, fired = make()
    taps(lst, CTRL, QUICK)
    return fired == ["polish"], fired


def t_double_shift_opens_menu():
    lst, fired = make()
    taps(lst, SHIFT, QUICK)
    return fired == ["menu"], fired


def t_menu_in_classic_mode():
    # Combos for Fix/Polish, but Shift Shift still opens the menu (and Alt Alt does nothing).
    lst, fired = make(trigger_mode="classic")
    taps(lst, ALT, QUICK)
    taps(lst, SHIFT, [(2000, 2050), (2150, 2200)])
    return fired == ["menu"], fired


def t_combo_menu_turns_off_shift_taps():
    lst, fired = make(menu_hotkey="Ctrl+Shift+M")
    taps(lst, SHIFT, QUICK)
    return fired == [] and lst._menu_tap is False, fired


def t_typing_capitals_never_opens_menu():
    lst, fired = make()
    for base in (1000, 1150):                 # Shift+A, Shift+S typed quickly
        key(lst, SHIFT, True, base)
        key(lst, A, True, base + 20)
        key(lst, A, False, base + 40)
        key(lst, SHIFT, False, base + 60)
    return fired == [], fired


def t_shift_click_never_opens_menu():
    lst, fired = make()
    taps(lst, SHIFT, [(1000, 1050)])
    lst._on_click(0, 0, None, True)           # Shift-click to extend a selection
    taps(lst, SHIFT, [(1150, 1200)])
    return fired == [], fired


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
    taps(lst, ALT, QUICK)
    return fired == ["fix"], fired


def t_suspended():
    lst, fired = make()
    lst.suspend(True)
    taps(lst, ALT, QUICK)
    taps(lst, SHIFT, [(2000, 2050), (2150, 2200)])
    return fired == [], fired


def t_config_default_and_migration():
    got = (C.get_menu_hotkey({}), C.get_menu_hotkey({"menu_hotkey": "Ctrl+Alt+Space"}),
           C.get_menu_hotkey({"menu_hotkey": "ctrl + alt + space"}), C.get_menu_hotkey({"menu_hotkey": "Ctrl+Shift+M"}),
           C.get_menu_label({}), C.get_menu_label({"menu_hotkey": "Ctrl+Shift+M"}))
    want = ("double_shift", "double_shift", "double_shift", "Ctrl+Shift+M", "Shift Shift", "Ctrl + Shift + M")
    return got == want, got


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
