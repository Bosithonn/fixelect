"""Model-free tests for quick actions: the menu, the prompts, and running
Translate / custom actions against a stand-in engine.
Run: python tests/test_actions.py
"""

import os
import pathlib
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ("MacOS" if sys.platform == "darwin" else "Windows") / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import actions as A  # noqa: E402
import chunking  # noqa: E402

EN = "Good morning, I will send you the report tomorrow morning."
RU = "Доброе утро, я отправлю вам отчёт завтра утром."


class Engine:
    """Replays scripted replies (the last one repeats) and records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def ensure_running(self):
        return True

    def chat_completion(self, messages, **kw):
        self.calls.append((messages, kw))
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return reply(messages) if callable(reply) else reply


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


def _translate_long():
    text = " ".join(["Good morning, the report is ready."] * 60)      # ~2,100 characters
    eng = Engine(lambda m: " ".join(["Доброе утро, отчёт готов."] * m[-1]["content"].count("Good morning")))
    seen = []
    out = A.run(eng, text, {"kind": "translate", "target": "ru"}, progress=lambda i, n: seen.append((i, n)))
    return len(eng.calls) >= 2 and "Good" not in out and out.count("Доброе") == 60 and seen[-1][0] == seen[-1][1]


def _translate_cancel():
    ev = threading.Event()
    ev.set()
    return raises(lambda: A.run(Engine(RU), " ".join([EN] * 40), {"kind": "translate", "target": "ru"},
                                cancel=ev), chunking.Cancelled)


CASES = [
    # the menu
    ("menu: order", lambda: [i["kind"] for i in A.menu_items({})],
     ["fix", "polish", "styles", "translate_menu", "custom", "custom"]),
    ("menu: polish uses the chosen style", lambda: A.menu_items({"polish_style": "friendly"})[1]["label"],
     "Polish · Friendly"),
    ("menu: unknown style falls back", lambda: A.menu_items({"polish_style": "nope"})[1]["style"], "professional"),
    ("menu: styles submenu", lambda: [i["kind"] for i in A.submenu({"kind": "styles"}, {})], ["polish"] * 5),
    ("menu: translate targets (Qwen)", lambda: [i["target"] for i in A.submenu({"kind": "translate_menu"}, {})],
     ["en", "es", "fr", "de", "pt", "it", "ru", "uk"]),
    ("menu: Russian is key 7", lambda: A.submenu({"kind": "translate_menu"}, {})[6]["label"], "Russian"),
    ("menu: Uzbek with Gemma", lambda: A.submenu({"kind": "translate_menu"}, {"model_profile": "gemma4-e2b"})[-1]["label"],
     "Uzbek (beta)"),
    ("menu: final items have no submenu", lambda: A.submenu({"kind": "fix"}, {}), None),
    # the user's actions
    ("actions: examples by default", lambda: [a["name"] for a in A.custom_actions({})], ["Bullet points", "Summarize"]),
    ("actions: deleting all stays empty", lambda: A.custom_actions({"custom_actions": []}), []),
    ("actions: bad entries dropped", lambda: A.custom_actions({"custom_actions": [
        {"name": "Ok", "prompt": "Do it"}, {"name": "", "prompt": "x"}, "junk", {"name": "No prompt"}]}),
     [{"name": "Ok", "prompt": "Do it"}]),
    ("actions: limits", lambda: (len(A.custom_actions({"custom_actions": [{"name": "n" * 99, "prompt": "p"}] * 20})),
                                 len(A.custom_actions({"custom_actions": [{"name": "n" * 99, "prompt": "p"}]})[0]["name"])),
     (A.MAX_CUSTOM_ACTIONS, A.MAX_NAME)),
    ("actions: shown in the menu", lambda: A.menu_items({"custom_actions": [{"name": "Reply", "prompt": "Reply"}]})[-1],
     {"kind": "custom", "label": "Reply", "prompt": "Reply"}),
    # prompts
    ("prompt: names the language", lambda: "Russian" in A.translate_messages("x", "ru")[0]["content"], True),
    ("prompt: instruction comes after the text", lambda: A.custom_messages("x", "Reply politely")[-1]["content"].index(
        "Reply politely") > A.custom_messages("x", "Reply politely")[-1]["content"].index("</text>"), True),
    # translate
    ("translate: result", lambda: A.run(Engine(RU), EN, {"kind": "translate", "target": "ru"}), RU),
    ("translate: selection edges kept", lambda: A.run(Engine(RU), "  " + EN + "\n", {"kind": "translate", "target": "ru"}),
     "  " + RU + "\n"),
    ("translate: retries an empty reply", lambda: A.run(Engine("", RU), EN, {"kind": "translate", "target": "ru"}), RU),
    ("translate: refuses an untranslated reply", lambda: raises(
        lambda: A.run(Engine(EN), EN, {"kind": "translate", "target": "ru"}), A.ActionError), True),
    ("translate: long text in chunks", _translate_long, True),
    ("translate: Esc cancels", _translate_cancel, True),
    # custom
    ("custom: markdown made plain", lambda: A.run(Engine("**Shopping:**\n* milk\n* eggs"), "buy milk and eggs",
                                                  {"kind": "custom", "prompt": "Bullets"}), "Shopping:\n- milk\n- eggs"),
    ("custom: too long refused", lambda: raises(lambda: A.run(Engine("x"), "word " * 1300,
                                                              {"kind": "custom", "prompt": "Summarize"}), A.ActionError),
     True),
    ("custom: empty reply refused", lambda: raises(lambda: A.run(Engine(""), "some text here",
                                                                {"kind": "custom", "prompt": "Summarize"}), A.ActionError),
     True),
    # card texts
    ("titles", lambda: (A.done_title({"kind": "translate", "target": "ru"}),
                        A.done_title({"kind": "custom", "label": "Bullet points"})),
     ("Translated to Russian", "Bullet points done")),
    ("long only for translations", lambda: (A.is_long({"kind": "translate"}, "x" * 2000),
                                            A.is_long({"kind": "custom"}, "x" * 2000)), (True, False)),
]


def main():
    failed = 0
    for name, fn, want in CASES:
        try:
            got = fn()
        except Exception as e:  # a crash is a failure, not a test-runner abort
            got = f"{type(e).__name__}: {e}"
        ok = got == want
        failed += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n        got:  {got!r}\n        want: {want!r}"))
        if not ok and os.environ.get("GITHUB_ACTIONS"):
            print(f"::error title=Actions test: {name}::{got!r}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} action tests passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
