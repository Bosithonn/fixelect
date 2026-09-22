"""Tests for the "this model is too slow for this computer" check (shared/speedwatch.py).
No model needed: engine timings are made up. Run: python tests/test_speedwatch.py"""

import pathlib
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))

import speedwatch as S  # noqa: E402

MODELS = {"gemma4-e2b": {}, "3b": {}, "1.5b": {}, "0.5b": {}}
DAY = 86400
T0 = time.mktime((2026, 9, 1, 10, 0, 0, 0, 0, -1))   # a morning, local time


def t(tps, n=30, cold=False):
    return {"tps": tps, "n": n, "cold": cold}


def feed(d, profile, per_day, days, tps, start=T0, n=30):
    """`per_day` answers a day at `tps` tokens/s, spread over the working day."""
    for day in range(days):
        for i in range(per_day):
            S.record(d, profile, [t(tps, n)], now=start + day * DAY + i * 600)


def run(fn):
    with tempfile.TemporaryDirectory() as d:
        return fn(d)


def slow_for_days(d):
    feed(d, "gemma4-e2b", 6, 2, 5.0)
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 2 * DAY) == "1.5b"


def fast_computer(d):
    feed(d, "gemma4-e2b", 10, 5, 40.0)
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 5 * DAY) is None


def one_bad_hour(d):
    """A Windows update made one afternoon slow; the next days were fine."""
    feed(d, "gemma4-e2b", 12, 1, 4.0)
    feed(d, "gemma4-e2b", 6, 2, 35.0, start=T0 + DAY)
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 3 * DAY) is None


def one_slow_day_only(d):
    """Slow all of one day, but only one day so far: not enough to judge."""
    feed(d, "gemma4-e2b", 20, 1, 4.0)
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 0.5 * DAY) is None


def too_few_answers(d):
    feed(d, "gemma4-e2b", 3, 2, 3.0)     # 6 answers over 2 days
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 2 * DAY) is None


def long_texts_not_slow(d):
    """Long texts take long, but come out at the same speed: never counted as slow."""
    feed(d, "gemma4-e2b", 6, 3, 35.0, n=900)
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 3 * DAY) is None


def cold_and_tiny_ignored(d):
    for day in range(3):
        for i in range(6):
            now = T0 + day * DAY + i * 600
            S.record(d, "gemma4-e2b", [t(2.0, cold=True), t(2.0, n=3), t(30.0)], now=now)
    return (S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 3 * DAY) is None
            and S.typical_speed(d, "gemma4-e2b") == 30.0)


def asked_once_then_quiet(d):
    feed(d, "gemma4-e2b", 6, 2, 5.0)
    S.mark_asked(d, "gemma4-e2b", now=T0 + 2 * DAY)
    again_soon = S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 3 * DAY)
    after_week = S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 10 * DAY)
    return again_soon is None and after_week == "1.5b"


def keep_means_never(d):
    feed(d, "gemma4-e2b", 6, 2, 5.0)
    S.decline(d, "gemma4-e2b")
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 30 * DAY) is None


def chain_of_smaller(d):
    feed(d, "1.5b", 6, 2, 4.0)
    feed(d, "3b", 6, 2, 4.0)
    return (S.suggestion(d, "1.5b", MODELS, now=T0 + 2 * DAY) == "0.5b"
            and S.suggestion(d, "3b", MODELS, now=T0 + 2 * DAY) == "1.5b")


def nothing_smaller(d):
    feed(d, "0.5b", 6, 2, 2.0)
    return S.suggestion(d, "0.5b", MODELS, now=T0 + 2 * DAY) is None


def per_model(d):
    """Slowness of the old model says nothing about the new one."""
    feed(d, "gemma4-e2b", 6, 2, 5.0)
    return S.suggestion(d, "1.5b", MODELS, now=T0 + 2 * DAY) is None


def unknown_target_skipped(d):
    feed(d, "gemma4-e2b", 6, 2, 5.0)
    return S.suggestion(d, "gemma4-e2b", {"gemma4-e2b": {}}, now=T0 + 2 * DAY) is None


def broken_file(d):
    (pathlib.Path(d) / "speed.json").write_text("{nope", encoding="utf-8")
    feed(d, "gemma4-e2b", 6, 2, 5.0)
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 2 * DAY) == "1.5b"


def capped(d):
    feed(d, "gemma4-e2b", 50, 3, 30.0)
    import json
    data = json.loads((pathlib.Path(d) / "speed.json").read_text(encoding="utf-8"))
    return len(data["samples"]["gemma4-e2b"]) == S.MAX_SAMPLES


def recovers_when_fast_again(d):
    """Slow last week (driver problem), fast since: the recent answers decide."""
    feed(d, "gemma4-e2b", 6, 2, 5.0)
    feed(d, "gemma4-e2b", 30, 2, 35.0, start=T0 + 5 * DAY)
    return S.suggestion(d, "gemma4-e2b", MODELS, now=T0 + 7 * DAY) is None


CASES = [
    ("slow for days -> offer the smaller model", slow_for_days),
    ("fast computer -> nothing", fast_computer),
    ("one bad hour -> nothing", one_bad_hour),
    ("one slow day only -> wait", one_slow_day_only),
    ("too few answers -> wait", too_few_answers),
    ("long texts are not 'slow'", long_texts_not_slow),
    ("first answer after loading and tiny answers ignored", cold_and_tiny_ignored),
    ("asked once, then quiet for a week", asked_once_then_quiet),
    ("'Keep' means never again", keep_means_never),
    ("1.5B -> 0.5B, 3B -> 1.5B", chain_of_smaller),
    ("nothing smaller than 0.5B", nothing_smaller),
    ("judged per model", per_model),
    ("smaller model missing on this platform", unknown_target_skipped),
    ("broken speed.json recovers", broken_file),
    ("stored samples are capped", capped),
    ("fast again after a slow spell", recovers_when_fast_again),
]


def main():
    passed = 0
    for name, fn in CASES:
        try:
            ok = run(fn) is True
        except Exception as e:
            ok, name = False, f"{name}  ({type(e).__name__}: {e})"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(CASES)} speed tests passed")
    return passed == len(CASES)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
