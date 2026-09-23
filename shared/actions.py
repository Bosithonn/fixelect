"""
Quick actions: the one-shortcut menu (Fix, Polish, Translate, the user's own
actions) and the two kinds of request behind it that Fix and Polish don't cover.

  * Translate turns the selection into another supported language.
  * Custom actions apply the user's own instruction ("Turn into bullet points").

Unlike Fix and Polish these change the text on purpose, so the meaning guard
does not apply. Instead the reply is cleaned of chat scaffolding, must not be
empty, and a translation must come back in the language that was asked for.
"""

import re

import chunking
import languages as L
from check_guard import POLISH_STYLES, clean, detect_language, split_edges

MAX_CUSTOM_ACTIONS = 12
MAX_NAME = 40
MAX_PROMPT = 400
MAX_ACTION_CHARS = 6000     # a custom action sees the whole text at once (4k-token context)
TRANSLATE_CHUNK = 1400      # longer text is translated paragraph by paragraph

DEFAULT_ACTIONS = [
    {"name": "Bullet points", "prompt": "Turn this into a short bulleted list: one point per line, each with its "
                                        "own details such as dates, names and numbers. Keep every fact."},
    {"name": "Summarize", "prompt": "Summarize this in one or two sentences."},
]


class ActionError(Exception):
    """A user-facing reason an action could not finish."""


# ---------------------------------------------------------------------------
# The menu
# ---------------------------------------------------------------------------

def custom_actions(cfg):
    """The user's actions from the config (the examples until they change them)."""
    items = cfg.get("custom_actions")
    if not isinstance(items, list):
        items = DEFAULT_ACTIONS
    out = []
    for a in items:
        if not isinstance(a, dict):
            continue
        name = " ".join(str(a.get("name", "")).split())[:MAX_NAME]
        prompt = " ".join(str(a.get("prompt", "")).split())[:MAX_PROMPT]
        if name and prompt:
            out.append({"name": name, "prompt": prompt})
    return out[:MAX_CUSTOM_ACTIONS]


def translate_targets(profile):
    return ["en"] + list(L.supported_for(profile))


def menu_items(cfg):
    style = cfg.get("polish_style", "professional")
    if style not in POLISH_STYLES:
        style = "professional"
    items = [
        {"kind": "fix", "label": "Fix spelling & grammar"},
        {"kind": "polish", "style": style, "label": f"Polish · {POLISH_STYLES[style]['label']}"},
        {"kind": "styles", "label": "Polish in another style…"},
        {"kind": "translate_menu", "label": "Translate…"},
    ]
    items += [{"kind": "custom", "label": a["name"], "prompt": a["prompt"]} for a in custom_actions(cfg)]
    return items


def submenu(item, cfg):
    """The items behind "Polish in another style…" / "Translate…", or None for a final choice."""
    kind = item.get("kind")
    if kind == "styles":
        return [{"kind": "polish", "style": k, "label": v["label"]} for k, v in POLISH_STYLES.items()]
    if kind == "translate_menu":
        return [{"kind": "translate", "target": c,
                 "label": L.NAMES.get(c, c) + (" (beta)" if c in L.BETA else "")}
                for c in translate_targets(cfg.get("model_profile"))]
    return None


def verb(item):
    return "Translating" if item.get("kind") == "translate" else "Working"


def done_title(item):
    if item.get("kind") == "translate":
        return f"Translated to {L.NAMES.get(item.get('target'), item.get('target'))}"
    return f"{item.get('label', 'Action')} done"


def is_long(item, text):
    """Long enough to show progress and offer Esc (only translations are chunked)."""
    return item.get("kind") == "translate" and len(text.strip()) > TRANSLATE_CHUNK


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def translate_messages(text, target):
    name = L.NAMES.get(target, target)
    system = (f"You are a professional translator. Translate the user's text into natural, grammatically "
              f"correct {name}, the way a native speaker would write it. "
              "Keep the meaning, the tone and the layout: line breaks, lists, names, numbers, links, "
              f"email addresses and code stay exactly as they are. Parts already in {name} stay as they are. "
              "Reply with the translation only: no notes, no quotes, no explanations.")
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"<text>\n{text}\n</text>"}]


def custom_messages(text, instruction):
    system = ("You are a writing assistant that edits text inside other apps. Apply the instruction to the "
              "user's text and reply with the resulting text only: no preface, no notes, no quotes. "
              "Write in the same language as the text unless the instruction says otherwise, with correct "
              "grammar, capitalization and punctuation. "
              "Keep names, numbers, links and code exactly as written. Plain text only: start bullet points "
              "with \"- \" and use no Markdown headings or bold.")
    # Small models follow what they read last: the instruction comes after the text.
    return [{"role": "system", "content": system},
            {"role": "user", "content": f"<text>\n{text}\n</text>\n\nInstruction: {instruction}\n"
                                        "Write it with correct capitalization and punctuation."}]


def _budget(text, factor):
    return min(2048, max(96, int(len(text.split()) * factor + 96)))


def _ask(engine, messages, budget, temperature, source=None):
    reply = engine.chat_completion(messages=messages, temperature=temperature, max_tokens=budget,
                                   top_k=40, top_p=0.95)
    return clean(reply or "", preserve_newlines=True, source=source)


def _plain(text):
    """Markdown the model slipped in, as plain text that pastes cleanly anywhere."""
    lines = []
    for line in text.splitlines():
        s = line.replace("**", "").replace("__", "")
        s = re.sub(r"^\s*#{1,6}\s+", "", s)
        m = re.match(r"^(\s*)[*•]\s+", s)
        if m:
            s = m.group(1) + "- " + s[m.end():]
        lines.append(s)
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# Running an action
# ---------------------------------------------------------------------------

def run(engine, text, item, progress=None, cancel=None):
    """Run a translate / custom item on `text` and return the new text.
    Raises ActionError with a message for the user, chunking.Cancelled on Esc."""
    engine.ensure_running()
    kind = item.get("kind")
    if kind == "translate":
        return _translate(engine, text, item["target"], progress, cancel)
    if kind == "custom":
        return _custom(engine, text, item["prompt"])
    raise ValueError(f"not an action: {kind}")


def _in_language(result, target):
    if len(result.split()) < 4:
        return True   # too short to tell reliably
    return detect_language(result) == target


def _translate_one(engine, text, target, source):
    result = ""
    for temperature in (0.0, 0.4):
        result = _ask(engine, translate_messages(text, target), _budget(text, 3.0), temperature, source=text)
        if result and _in_language(result, target):
            return result
    # The detector is unsure, but the text did change language: accept it.
    if result and result.strip() != text.strip() and detect_language(result) != source:
        return result
    raise ActionError(f"Couldn't translate this into {L.NAMES.get(target, target)}. "
                      "Try again, or select less text.")


def _translate(engine, text, target, progress=None, cancel=None):
    lead, core, trail = split_edges(text)
    if not core:
        return text
    source = detect_language(core)
    units = chunking.split_units(core, TRANSLATE_CHUNK) if len(core) > TRANSLATE_CHUNK else [(core, "")]
    out = []
    for i, (chunk, sep) in enumerate(units):
        if cancel is not None and cancel.is_set():
            raise chunking.Cancelled()
        if progress:
            progress(i, len(units))
        out.append((_translate_one(engine, chunk, target, source) if chunk.strip() else chunk) + sep)
    if progress:
        progress(len(units), len(units))
    return lead + "".join(out) + trail


def _custom(engine, text, instruction):
    lead, core, trail = split_edges(text)
    if len(core) > MAX_ACTION_CHARS:
        raise ActionError(f"Select up to {MAX_ACTION_CHARS:,} characters for this action.")
    result = _plain(_ask(engine, custom_messages(core, instruction), _budget(core, 2.0), 0.3, source=core))
    if not result:
        raise ActionError("The AI returned nothing. Try again.")
    return lead + result + trail
