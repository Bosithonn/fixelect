"""
Notices when the chosen AI model is too slow for this computer.

Every request tells us how fast the engine produced its answer (tokens per
second, from llama-server's "timings"). That number describes the computer,
not the text: a one-line fix and a long email come out at the same speed, so
long texts never count as "slow" just for being long.

The model is only called too slow when that holds up over time:
  * the first answer after the model loads is skipped (it is always slower),
    and so are answers too short to time;
  * at least MIN_SAMPLES answers, from at least MIN_DAYS different days, and
    the typical (median) speed is slow on at least MIN_DAYS of those days
    - so one busy hour (a Windows update, a game) never triggers it.

Then Fixelect offers a smaller model once. It never switches by itself.
Stored in speed.json in the config folder: speeds and dates only, no text.
"""

import json
import os
import pathlib
import statistics
import threading
import time

SLOW_TOKENS_PER_SECOND = 6.0    # measured: at 9 tokens/s a one-line fix takes ~2 s (workable); below 6 it is 3 s+
MIN_TOKENS = 8                  # shorter answers are too quick to time reliably
MIN_SAMPLES = 10
MIN_DAYS = 2
MIN_PER_DAY = 3                 # a day's median needs a few answers behind it
MAX_SAMPLES = 60
ASK_AGAIN_DAYS = 7              # the card was missed (timed out): ask again after a week

# A smaller model that actually helps, per model. Nothing smaller than 0.5B.
SMALLER = {
    "gemma4-e2b": "1.5b",
    "3b": "1.5b",
    "llama-3b": "1.5b",
    "7b": "gemma4-e2b",
    "1.5b": "0.5b",
}

_lock = threading.Lock()


def _path(config_dir):
    return pathlib.Path(config_dir) / "speed.json"


def _load(config_dir):
    try:
        with open(_path(config_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("samples", {})
            data.setdefault("asked", {})
            data.setdefault("declined", [])
            return data
    except Exception:
        pass
    return {"samples": {}, "asked": {}, "declined": []}


def _save(config_dir, data):
    p = _path(config_dir)
    tmp = p.with_suffix(".json.tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, p)
    except Exception:
        pass


def usable(t):
    """A timing worth counting: not the first answer after loading, long enough to time."""
    try:
        return (not t.get("cold") and float(t.get("tps") or 0) > 0
                and int(t.get("n") or 0) >= MIN_TOKENS)
    except (TypeError, ValueError):
        return False


def record(config_dir, profile, timings, now=None):
    """Add this job's engine timings ({tps, n, cold} each) for `profile`."""
    good = [float(t["tps"]) for t in timings or () if usable(t)]
    if not good or not profile:
        return
    now = time.time() if now is None else now
    with _lock:
        data = _load(config_dir)
        samples = data["samples"].setdefault(profile, [])
        samples.extend([now, round(tps, 2)] for tps in good)
        del samples[:-MAX_SAMPLES]
        _save(config_dir, data)


def _day(ts):
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def verdict(samples):
    """(is_slow, median tokens/s) for a list of [time, tps]."""
    if len(samples) < MIN_SAMPLES:
        return False, None
    median = statistics.median(tps for _, tps in samples)
    by_day = {}
    for ts, tps in samples:
        by_day.setdefault(_day(ts), []).append(tps)
    slow_days = [d for d, v in by_day.items()
                 if len(v) >= MIN_PER_DAY and statistics.median(v) < SLOW_TOKENS_PER_SECOND]
    return median < SLOW_TOKENS_PER_SECOND and len(slow_days) >= MIN_DAYS, median


def suggestion(config_dir, profile, models, now=None):
    """The smaller model to offer, or None. `models` is the downloader's MODELS."""
    target = SMALLER.get(profile)
    if not target or target not in models:
        return None
    now = time.time() if now is None else now
    data = _load(config_dir)
    if profile in data["declined"]:
        return None
    asked = data["asked"].get(profile)
    if asked and now - asked < ASK_AGAIN_DAYS * 86400:
        return None
    slow, _ = verdict(data["samples"].get(profile, []))
    return target if slow else None


def mark_asked(config_dir, profile, now=None):
    with _lock:
        data = _load(config_dir)
        data["asked"][profile] = time.time() if now is None else now
        _save(config_dir, data)


def decline(config_dir, profile):
    """"Keep this model": never offer to replace it again."""
    with _lock:
        data = _load(config_dir)
        if profile not in data["declined"]:
            data["declined"].append(profile)
        _save(config_dir, data)


def typical_speed(config_dir, profile):
    """Median tokens/s for Settings/diagnostics, or None before enough answers."""
    samples = _load(config_dir)["samples"].get(profile, [])
    return round(statistics.median(tps for _, tps in samples), 1) if samples else None
