"""
Recent fixes, kept only on this computer.

Every replacement Fixelect makes is appended to history.json in the config
folder: when, which app, what kind of change, and the text before and after.
The Settings window lists them so a bad fix can be recovered after Undo is
gone. Nothing here is ever sent anywhere; the file holds at most MAX_ENTRIES
and the writer can turn it off or clear it in Settings.
"""

import json
import os
import pathlib
import threading
import time

MAX_ENTRIES = 30
MAX_CHARS = 4000           # per side; longer texts are kept shortened
_lock = threading.Lock()


def _path(config_dir):
    return pathlib.Path(config_dir) / "history.json"


def load(config_dir):
    """Newest first. Never raises: a missing or broken file is an empty history."""
    try:
        with open(_path(config_dir), "r", encoding="utf-8") as f:
            data = json.load(f)
        items = [e for e in data if isinstance(e, dict) and "before" in e and "after" in e]
        return sorted(items, key=lambda e: e.get("time", 0), reverse=True)[:MAX_ENTRIES]
    except Exception:
        return []


def _clip(text):
    text = str(text or "")
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "…"


def add(config_dir, mode, app, before, after, now=None):
    """Record one replacement. Returns False if it couldn't be saved (never raises)."""
    if not before or not after or before == after:
        return False
    entry = {"time": now if now is not None else time.time(), "mode": str(mode or "fix"),
             "app": str(app or ""), "before": _clip(before), "after": _clip(after)}
    with _lock:
        items = [entry] + load(config_dir)
        return _save(config_dir, items[:MAX_ENTRIES])


def clear(config_dir):
    with _lock:
        try:
            _path(config_dir).unlink()
        except FileNotFoundError:
            pass
        except Exception:
            return False
        return True


def _save(config_dir, items):
    p = _path(config_dir)
    tmp = p.with_suffix(".json.tmp")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


MODE_LABELS = {"fix": "Fixed", "polish": "Polished", "action": "Action"}


def when(ts, now=None):
    """'just now', '5 min ago', '2 h ago', 'yesterday', or a date."""
    now = now if now is not None else time.time()
    d = max(0, now - ts)
    if d < 60:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)} min ago"
    if d < 86400:
        return f"{int(d // 3600)} h ago"
    if d < 2 * 86400:
        return "yesterday"
    return time.strftime("%d %b", time.localtime(ts)).lstrip("0")
