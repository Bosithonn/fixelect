"""
Keep formatting when Fixelect replaces text.

Pasting the result as plain text wiped bold, links, fonts and list styling in
Word, Outlook, Google Docs, Gmail and Notion. A fix changes only a few words,
so instead we take the rich (HTML) version the app itself put on the
clipboard, change exactly those words inside its text nodes, and paste it back
alongside the plain text. Anything we cannot map with certainty (an edit that
straddles a formatting boundary, unexpected markup) returns None and the
caller falls back to plain text - formatting is never guessed.
"""

import difflib
import html as _html
import re

_WORD = re.compile(r"\S+")
_TOKEN = re.compile(r"<!--.*?-->|<![^>]*>|<[^>]*>", re.S)
_SKIP_TAGS = ("script", "style", "title", "head", "xml")
_START_FRAG = "<!--StartFragment-->"
_END_FRAG = "<!--EndFragment-->"


def word_ops(old, new):
    """Word-level edits turning `old` into `new`: [(start, end, replacement)] as
    character spans of `old`, sorted. Insertions have start == end."""
    a = [(m.start(), m.end()) for m in _WORD.finditer(old)]
    b = [(m.start(), m.end()) for m in _WORD.finditer(new)]
    aw = [old[s:e] for s, e in a]
    bw = [new[s:e] for s, e in b]
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, aw, bw, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        if tag == "replace" and i2 - i1 == j2 - j1:
            for k in range(i2 - i1):
                if aw[i1 + k] != bw[j1 + k]:
                    ops.append((a[i1 + k][0], a[i1 + k][1], bw[j1 + k]))
            continue
        repl = new[b[j1][0]:b[j2 - 1][1]] if j2 > j1 else ""
        if i2 > i1:
            s, e = a[i1][0], a[i2 - 1][1]
            if not repl:  # deletion: take one neighbouring gap with it
                if i2 < len(a):
                    e = a[i2][0]
                elif i1 > 0:
                    s = a[i1 - 1][1]
            ops.append((s, e, repl))
        elif i1 < len(a):
            ops.append((a[i1][0], a[i1][0], repl + " "))
        elif a:
            ops.append((a[-1][1], a[-1][1], " " + repl))
    return sorted(ops, key=lambda op: (op[0], op[1]))


def count_changes(old, new):
    return len(word_ops(old, new))


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def _segments(markup):
    out, pos = [], 0
    for m in _TOKEN.finditer(markup):
        if m.start() > pos:
            out.append([True, markup[pos:m.start()]])
        out.append([False, m.group(0)])
        pos = m.end()
    if pos < len(markup):
        out.append([True, markup[pos:]])
    return out


def _text_nodes(segs):
    """Indices of visible text segments (inside the fragment, outside head/script/style)."""
    has_markers = any(not t and raw == _START_FRAG for t, raw in segs)
    inside = not has_markers
    skip = None
    nodes = []
    for i, (is_text, raw) in enumerate(segs):
        if not is_text:
            if raw == _START_FRAG:
                inside = True
            elif raw == _END_FRAG:
                inside = False
            else:
                m = re.match(r"<\s*(/)?\s*([a-zA-Z0-9:]+)", raw)
                if m:
                    name = m.group(2).lower()
                    if skip is None and not m.group(1) and name in _SKIP_TAGS and not raw.rstrip().endswith("/>"):
                        skip = name
                    elif skip == name and m.group(1):
                        skip = None
            continue
        if inside and skip is None:
            nodes.append(i)
    return nodes


def rewrite_html(markup, old, new):
    """Apply the word edits between `old` and `new` to the text of `markup`.
    Returns the new markup, or None when the edits cannot be mapped safely."""
    if old == new:
        return markup
    ops = word_ops(old, new)
    if not ops:
        return markup
    segs = _segments(markup)
    node_ids = _text_nodes(segs)
    texts = {i: _html.unescape(segs[i][1]) for i in node_ids}

    vis_pos, vis_chars = [], []
    for i in node_ids:
        for off, c in enumerate(texts[i]):
            if not c.isspace():
                vis_pos.append((i, off))
                vis_chars.append(c)
    plain_idx = [k for k, c in enumerate(old) if not c.isspace()]
    plain_chars = [old[k] for k in plain_idx]
    if not plain_chars or not vis_chars:
        return None

    # Map every non-space character of the plain text to one in the HTML.
    char_map = {}
    if plain_chars == vis_chars:
        char_map = {p: q for p, q in zip(plain_idx, range(len(vis_chars)))}
    else:
        if len(plain_chars) > 30000 or len(vis_chars) > 60000:
            return None
        sm = difflib.SequenceMatcher(None, plain_chars, vis_chars, autojunk=False)
        for blk in sm.get_matching_blocks():
            for d in range(blk.size):
                char_map[plain_idx[blk.a + d]] = blk.b + d
        if len(char_map) < 0.9 * len(plain_chars):
            return None

    edits = {}  # node -> [(start, end, text)]
    for s, e, repl in ops:
        if s == e:
            if s > 0 and not old[s - 1].isspace() and (s - 1) in char_map:
                node, off = vis_pos[char_map[s - 1]]
                edits.setdefault(node, []).append((off + 1, off + 1, repl))
            elif s < len(old) and not old[s].isspace() and s in char_map:
                node, off = vis_pos[char_map[s]]
                edits.setdefault(node, []).append((off, off, repl))
            else:
                return None
            continue
        inside = [k for k in range(s, e) if not old[k].isspace()]
        if not inside or inside[0] not in char_map or inside[-1] not in char_map:
            return None
        n1, o1 = vis_pos[char_map[inside[0]]]
        n2, o2 = vis_pos[char_map[inside[-1]]]
        if n1 != n2:
            return None  # the edit straddles a formatting boundary
        node_text = texts[n1]
        if [c for c in node_text[o1:o2 + 1] if not c.isspace()] != [old[k] for k in inside]:
            return None
        start, end = o1, o2 + 1
        if s < inside[0]:
            while start > 0 and node_text[start - 1].isspace():
                start -= 1
        if e - 1 > inside[-1]:
            while end < len(node_text) and node_text[end].isspace():
                end += 1
        if s < inside[0] and repl and not repl[0].isspace():
            repl = " " + repl if start > 0 else repl
        if e - 1 > inside[-1] and repl and not repl[-1].isspace() and end < len(node_text):
            repl = repl + " "
        edits.setdefault(n1, []).append((start, end, repl))

    for node, changes in edits.items():
        text = texts[node]
        last = len(text) + 1
        for start, end, repl in sorted(changes, key=lambda c: (c[0], c[1]), reverse=True):
            if end > last:
                return None  # overlapping edits
            text = text[:start] + repl + text[end:]
            last = start
        segs[node][1] = _html.escape(text, quote=False)
    return "".join(raw for _t, raw in segs)


# ---------------------------------------------------------------------------
# Windows CF_HTML ("HTML Format") wrapper
# ---------------------------------------------------------------------------

def _header_value(header, key):
    m = re.search(key + r":(-?\d+)", header)
    return int(m.group(1)) if m else None


def rewrite_cf_html(data, old, new):
    """Rewrite a Windows "HTML Format" clipboard payload. Returns bytes or None."""
    if not data:
        return None
    raw = data.split(b"\0", 1)[0]
    try:
        head = raw[:400].decode("ascii", errors="ignore")
        start_html = _header_value(head, "StartHTML")
        end_html = _header_value(head, "EndHTML")
        if start_html is None or start_html < 0 or start_html >= len(raw):
            start_frag = _header_value(head, "StartFragment")
            if start_frag is None:
                return None
            start_html = raw.rfind(b"<", 0, start_frag) if b"<html" not in raw.lower() else raw.lower().find(b"<html")
            if start_html < 0:
                return None
        body_bytes = raw[start_html:end_html] if end_html and end_html > start_html else raw[start_html:]
        markup = body_bytes.decode("utf-8")
    except (UnicodeDecodeError, ValueError):
        return None
    source = re.search(r"SourceURL:([^\r\n]*)", head)

    rewritten = rewrite_html(markup, old, new)
    if rewritten is None:
        return None
    return build_cf_html(rewritten, source.group(1) if source else None)


def build_cf_html(markup, source_url=None):
    """Wrap an HTML document (with or without fragment markers) as CF_HTML bytes."""
    if _START_FRAG not in markup:
        markup = f"<html><body>{_START_FRAG}{markup}{_END_FRAG}</body></html>"
    template = ("Version:0.9\r\nStartHTML:{:010d}\r\nEndHTML:{:010d}\r\n"
                "StartFragment:{:010d}\r\nEndFragment:{:010d}\r\n")
    if source_url:
        template += f"SourceURL:{source_url}\r\n"
    header_len = len(template.format(0, 0, 0, 0).encode("utf-8"))
    body = markup.encode("utf-8")
    sf = header_len + body.index(_START_FRAG.encode()) + len(_START_FRAG)
    ef = header_len + body.index(_END_FRAG.encode())
    header = template.format(header_len, header_len + len(body), sf, ef).encode("utf-8")
    return header + body + b"\0"


def map_spans(target, old, new):
    """Word edits between `old` and `new`, expressed as spans of `target` - a
    rich document's plain string that may differ from `old` in whitespace
    (e.g. an NSAttributedString read from RTF). None when not safely mappable."""
    ops = word_ops(old, new)
    if target == old:
        return ops
    plain_idx = [k for k, c in enumerate(old) if not c.isspace()]
    tgt_idx = [k for k, c in enumerate(target) if not c.isspace()]
    a = [old[k] for k in plain_idx]
    b = [target[k] for k in tgt_idx]
    if not a or not b:
        return None
    if a == b:
        char_map = dict(zip(plain_idx, tgt_idx))
    else:
        if len(a) > 30000:
            return None
        char_map = {}
        for blk in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
            for d in range(blk.size):
                char_map[plain_idx[blk.a + d]] = tgt_idx[blk.b + d]
        if len(char_map) < 0.9 * len(a):
            return None
    spans = []
    for s, e, repl in ops:
        if s == e:
            if s > 0 and (s - 1) in char_map and not old[s - 1].isspace():
                pos = char_map[s - 1] + 1
            elif s in char_map:
                pos = char_map[s]
            else:
                return None
            spans.append((pos, pos, repl))
            continue
        inside = [k for k in range(s, e) if not old[k].isspace()]
        if not inside or inside[0] not in char_map or inside[-1] not in char_map:
            return None
        ts, te = char_map[inside[0]], char_map[inside[-1]] + 1
        if e - 1 > inside[-1]:  # the edit swallowed a following gap
            while te < len(target) and target[te].isspace():
                te += 1
        spans.append((ts, te, repl))
    spans.sort()
    for (s1, e1, _), (s2, _e2, _) in zip(spans, spans[1:]):
        if s2 < e1:
            return None
    return spans


_LINE_COPY_MARK = '"isFromEmptySelection":true'


def is_line_copy(raw):
    """True when clipboard metadata says the editor copied the whole line because
    nothing was selected (VS Code, Cursor and other Chromium-based editors store
    it as JSON, UTF-8 or UTF-16). Fixing that copy and pasting it back would
    duplicate the line in the user's code."""
    if not raw:
        return False
    return _LINE_COPY_MARK.encode("utf-8") in raw or _LINE_COPY_MARK.encode("utf-16-le") in raw


def utf16_offset(text, index):
    """Python str index -> NSString (UTF-16) index, for macOS attributed strings."""
    return len(text[:index].encode("utf-16-le")) // 2
