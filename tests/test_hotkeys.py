"""Model-free tests for the macOS shortcut logic (double-tap and key combos).

The Quartz event tap only exists on macOS; this drives the listener's key
handlers directly, so it runs everywhere. Run: python tests/test_hotkeys.py
"""

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "MacOS" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import hotkey_mac as H  # noqa: E402

OPT, CTRL, CMD, SHIFT = H._OPT, H._CTRL, H._CMD, H._SHIFT


def make(mode="double_tap", **cfg):
    fired = []
    lst = H.MacHotkeyListener(on_fix=lambda: fired.append("fix"), on_polish=lambda: fired.append("polish"),
                              config=dict(trigger_mode=mode, **cfg))
    lst._fire = lambda cb: cb()          # run callbacks inline
    lst._configure()
    return lst, fired


def tap(lst, bit, hold=0.05, gap=0.10):
    lst._on_flags(bit)
    time.sleep(hold)
    lst._on_flags(0)
    time.sleep(gap)


def t_double_option():
    lst, fired = make()
    tap(lst, OPT)
    tap(lst, OPT)
    return fired == ["fix"], fired


def t_double_control():
    lst, fired = make()
    tap(lst, CTRL)
    tap(lst, CTRL)
    return fired == ["polish"], fired


def t_single_tap():
    lst, fired = make()
    tap(lst, OPT)
    return fired == [], fired


def t_slow_taps():
    lst, fired = make()
    tap(lst, OPT, gap=0.6)
    tap(lst, OPT)
    return fired == [], fired


def t_long_hold():
    lst, fired = make()
    tap(lst, OPT, hold=0.45)
    tap(lst, OPT)
    return fired == [], fired


def t_chord():
    lst, fired = make()
    lst._on_flags(OPT)
    lst._on_key(14, OPT, False)          # ⌥E
    lst._on_flags(0)
    tap(lst, OPT)
    return fired == [], fired


def t_typing_between():
    lst, fired = make()
    tap(lst, OPT)
    lst._on_key(0, 0, False)             # "a"
    tap(lst, OPT)
    return fired == [], fired


def t_mixed_modifiers():
    lst, fired = make()
    tap(lst, OPT)
    tap(lst, CTRL)
    return fired == [], fired


def t_option_with_control_held():
    lst, fired = make()
    lst._on_flags(CTRL)
    lst._on_flags(CTRL | OPT)
    lst._on_flags(CTRL)
    lst._on_flags(CTRL | OPT)
    lst._on_flags(CTRL)
    lst._on_flags(0)
    return fired == [], fired


def t_three_taps_fire_once():
    lst, fired = make()
    for _ in range(3):
        tap(lst, OPT)
    return fired == ["fix"], fired


def t_suspended():
    lst, fired = make()
    lst.suspend(True)
    tap(lst, OPT)
    tap(lst, OPT)
    return fired == [], fired


def t_parse_combo():
    cases = {"<cmd>+<alt>+f": (CMD | OPT, 3), "Cmd+Option+F": (CMD | OPT, 3),
             "<alt>+<shift>+<space>": (OPT | SHIFT, 49), "ctrl+f5": (CTRL, 96), "f": None, "cmd+??": None}
    got = {k: H.parse_combo(k) for k in cases}
    return got == cases, got


def t_combo_fires_and_swallows():
    lst, fired = make("classic")
    swallowed = lst._on_key(3, CMD | OPT, False)      # ⌘⌥F
    repeat = lst._on_key(3, CMD | OPT, True)          # held down: swallowed, not fired again
    other = lst._on_key(3, CMD, False)                # ⌘F belongs to the app
    return fired == ["fix"] and swallowed and repeat and not other, (fired, swallowed, repeat, other)


def t_option_space_mode_ignores_double_tap():
    lst, fired = make("option_space")
    tap(lst, OPT)
    tap(lst, OPT)
    lst._on_key(49, OPT | SHIFT, False)
    return fired == ["polish"], fired


def t_escape():
    lst, fired = make()
    lst.watch_escape(lambda: fired.append("esc"))
    lst._on_key(53, 0, False)
    lst.watch_escape(None)
    lst._on_key(53, 0, False)
    return fired == ["esc"], fired


def main():
    tests = [(n[2:].replace("_", " "), f) for n, f in globals().items() if n.startswith("t_")]
    passed = 0
    for name, fn in tests:
        ok, got = fn()
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n        got: {got!r}"))
    print(f"\n{passed}/{len(tests)} hotkey tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
