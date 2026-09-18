"""Model-free tests for the macOS shortcut logic (double-tap and key combos).

The Quartz event tap only exists on macOS; this drives the listener's key
handlers directly with a fake clock, so it runs everywhere and never depends
on how fast the machine is. Run: python tests/test_hotkeys.py
"""

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "MacOS" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import hotkey_mac as H  # noqa: E402

OPT, CTRL, CMD, SHIFT = H._OPT, H._CTRL, H._CMD, H._SHIFT


class Clock:
    """Stands in for the time module inside hotkey_mac."""

    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


CLOCK = Clock()
H.time = CLOCK


def make(mode="double_tap", **cfg):
    fired = []
    lst = H.MacHotkeyListener(on_fix=lambda: fired.append("fix"), on_polish=lambda: fired.append("polish"),
                              config=dict(trigger_mode=mode, **cfg))
    lst._fire = lambda cb: cb()          # run callbacks inline
    lst._configure()
    return lst, fired


def tap(lst, bit, hold=0.05, gap=0.10):
    lst._on_flags(bit)
    CLOCK.sleep(hold)
    lst._on_flags(0)
    CLOCK.sleep(gap)


def t_double_option():
    lst, fired = make()
    tap(lst, OPT)
    tap(lst, OPT)
    return fired == ["fix"], fired


def t_double_shift():
    lst, fired = make()
    tap(lst, SHIFT)
    tap(lst, SHIFT)
    return fired == ["polish"], fired


def t_double_control_does_nothing():
    lst, fired = make()                  # ⌃⌃ is macOS's Dictation shortcut
    tap(lst, CTRL)
    tap(lst, CTRL)
    return fired == [], fired


def t_typing_capitals():
    lst, fired = make()
    for code in (0, 1):                  # ⇧A then ⇧S, typed quickly
        lst._on_flags(SHIFT)
        lst._on_key(code, SHIFT, False)
        CLOCK.sleep(0.05)
        lst._on_flags(0)
        CLOCK.sleep(0.08)
    return fired == [], fired


def t_shift_click_between():
    lst, fired = make()
    tap(lst, SHIFT)
    lst._on_key(-1, 0, False)            # a mouse click
    tap(lst, SHIFT)
    return fired == [], fired


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
    tap(lst, SHIFT)
    return fired == [], fired


def t_option_with_control_held():
    lst, fired = make()
    for flags in (CTRL, CTRL | OPT, CTRL, CTRL | OPT, CTRL, 0):
        lst._on_flags(flags)
        CLOCK.sleep(0.05)
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


def t_late_callbacks_use_event_time():
    lst, fired = make()                  # the Mac was busy: all callbacks ran at the same moment,
    base = CLOCK.now + 50                # but the keys were pressed 80 ms apart
    for i, flags in enumerate((OPT, 0, OPT, 0)):
        lst._on_flags(flags, ts=base + i * 0.08)
    return fired == ["fix"], fired


def t_event_time_still_rejects_slow_taps():
    lst, fired = make()
    base = CLOCK.now + 50
    for ts, flags in ((0.0, OPT), (0.05, 0), (0.9, OPT), (0.95, 0)):
        lst._on_flags(flags, ts=base + ts)
    return fired == [], fired


def t_capture_keys():
    lst, fired = make("classic")
    seen = []
    lst.capture_keys(lambda code, flags, repeat=False: seen.append(code) or code == 36)
    swallowed = lst._on_key(36, 0, False)            # Return: taken by the preview
    passed = lst._on_key(0, 0, False)                # "a": still reaches the app
    combo = lst._on_key(3, CMD | OPT, False)         # shortcuts keep working
    lst.capture_keys(None)
    after = lst._on_key(36, 0, False)
    ok = swallowed and not passed and combo and not after and seen == [36, 0, 3] and fired == ["fix"]
    return ok, (swallowed, passed, combo, after, seen, fired)


def t_menu_shortcut_in_every_mode():
    got = []
    for mode in ("double_tap", "option_space", "classic", "custom"):
        fired = []
        lst = H.MacHotkeyListener(on_fix=lambda: fired.append("fix"), on_polish=lambda: fired.append("polish"),
                                  config={"trigger_mode": mode}, on_menu=lambda: fired.append("menu"))
        lst._fire = lambda cb: cb()
        lst._configure()
        swallowed = lst._on_key(49, CTRL | OPT, False)   # ⌃⌥Space
        got.append((mode, fired, swallowed))
    return all(f == ["menu"] and s for _m, f, s in got), got


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
            print(f"::error title=Hotkey test: {name}::{got!r}")
    print(f"\n{passed}/{len(tests)} hotkey tests passed")
    return passed == len(tests)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
