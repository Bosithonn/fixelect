"""
Long-text handling: split a selection into paragraph / sentence-group chunks,
fix them one by one with progress, and stop cleanly when the user cancels.

A small local model is both slower and less accurate on one huge request, and
a single 20-second request cannot show progress or be cancelled.
"""

import re

from check_guard import fix_preserving_layout, split_edges

LIMITS = {"fix": 500, "polish": 1400}   # characters per request

_PARA = re.compile(r"((?:\r?\n)[ \t]*(?:\r?\n)\s*)")
# Any sentence end followed by space: typo-heavy text often starts sentences in
# lower case, and a split in the wrong place only moves a chunk boundary.
_SENT = re.compile(r"(?<=[.!?…])(\s+)")


class Cancelled(Exception):
    pass


def split_units(core, limit):
    """[(chunk, separator_after)]; "".join(c + s) == core."""
    parts = _PARA.split(core)
    units = []
    for i in range(0, len(parts), 2):
        para = parts[i]
        sep = parts[i + 1] if i + 1 < len(parts) else ""
        if len(para) <= limit:
            units.append((para, sep))
            continue
        pieces = _SENT.split(para)
        cur, pending = "", ""
        for j in range(0, len(pieces), 2):
            sent = pieces[j]
            ws = pieces[j + 1] if j + 1 < len(pieces) else ""
            if cur and len(cur) + len(pending) + len(sent) > limit:
                units.append((cur, pending))
                cur = sent
            else:
                cur = cur + pending + sent if cur else sent
            pending = ws
        units.append((cur, pending + sep))
    return units


def process(text, fn, mode="fix", progress=None, cancel=None):
    """Like fix_preserving_layout, but chunked for long text.

    `progress(done, total)` is called before each chunk; `cancel` is a
    threading.Event checked between chunks (raises Cancelled)."""
    lead, core, trail = split_edges(text)
    limit = LIMITS.get(mode, LIMITS["fix"])
    if len(core) <= limit:
        return fix_preserving_layout(text, fn, mode=mode)[0]
    units = split_units(core, limit)
    total = len(units)
    out = []
    for i, (chunk, sep) in enumerate(units):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if progress:
            progress(i, total)
        fixed = fix_preserving_layout(chunk, fn, mode=mode)[0] if chunk.strip() else chunk
        out.append(fixed + sep)
    if progress:
        progress(total, total)
    return lead + "".join(out) + trail


def needs_chunking(text, mode):
    return len(text.strip()) > LIMITS.get(mode, LIMITS["fix"])
