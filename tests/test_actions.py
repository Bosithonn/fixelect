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
    ("menu: every language, with any model", lambda: [i["target"] for i in A.submenu({"kind": "translate_menu"}, {})],
     ["en", "es", "fr", "de", "pt", "it", "ru", "uk", "uz"]),
    ("menu: Russian is key 7", lambda: A.submenu({"kind": "translate_menu"}, {})[6]["label"], "Russian"),
    ("menu: Uzbek is key 9", lambda: A.submenu({"kind": "translate_menu"}, {"model_profile": "3b"})[8]["label"],
     "Uzbek (beta)"),
    ("menu: Uzbek asks for Gemma 4 on other models", lambda: (
        A.needs_model({"kind": "translate", "target": "uz"}, "3b"),
        A.needs_model({"kind": "translate", "target": "uz"}, "gemma4-e2b"),
        A.needs_model({"kind": "translate", "target": "it"}, "1.5b", "en"),
        A.needs_model({"kind": "translate", "target": "en"}, None),
        A.needs_model({"kind": "translate", "target": "ru"}, "3b", "uz"),        # from Uzbek text
        A.needs_model({"kind": "translate", "target": "ru"}, "gemma4-e2b", "uz"),
        A.needs_model({"kind": "custom", "prompt": "x"}, "3b")), ("uz", None, None, None, "uz", None, None)),
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
    ("prompt: names the source language", lambda: "from Spanish into French" in
     A.translate_messages("hola", "fr", "es")[-1]["content"], True),
    ("prompt: no source when unknown", lambda: " from " in A.translate_messages("x", "fr", "other")[-1]["content"],
     False),
    ("prompt: the request comes after the text", lambda: A.translate_messages("x", "it", "en")[-1]["content"]
     .endswith("into Italian."), True),
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
    # Real Gemma 4 translations the old language check threw away ("Couldn't translate
    # this into Spanish / Italian"), and real failures that must still be caught.
    ("translate: good translations accepted", lambda: [not A.translation_ok(src, out, tgt, s) for src, out, tgt, s in (
        (EN, "Buenos días, te enviaré el informe mañana antes de la reunión.", "es", "en"),
        ("Meeting moved to 3pm", "Réunion déplacée à 15h", "fr", "en"),
        ("Meeting moved to 3pm", "Riunione spostata alle 15:00", "it", "en"),
        ("Could you please confirm whether the hotel booking in Rome includes breakfast?",
         "Potrebbe per favore confermare se la prenotazione dell'hotel a Roma include la colazione?", "it", "en"),
        ("I'm running late, stuck in traffic. Start without me!",
         "Estou atrasado, preso no trânsito. Comecem sem mim!", "pt", "en"),
        ("Happy birthday! I hope you have a wonderful day with your family.",
         "З днем народження! Бажаю вам чудового дня з родиною.", "uk", "en"),
        ("Привет! Я сегодня не смогу прийти на встречу, давай перенесём на завтра.",
         "Привіт! Я сьогодні не зможу прийти на зустріч, давай перенесемо на завтра.", "uk", "ru"),
        ("Hola, ¿puedes enviarme el contrato antes del viernes? Lo necesito para la reunión.",
         "Olá, você pode me enviar o contrato antes de sexta-feira? Preciso dele para a reunião.", "pt", "es"),
        (EN, "Xayrli tong, men uchrashuvdan oldin ertaga sizga hisobotni yuboraman.", "uz", "en"),
        ("Thanks!", "Grazie!", "it", "en"),
        ("Hola, ¿cómo estás?", "Hi, how are you?", "en", "es"))], [False] * 11),
    ("translate: failures still refused", lambda: [A.translation_ok(src, out, tgt, s) for src, out, tgt, s in (
        ("Hola, ¿puedes enviarme el contrato antes del viernes? Lo necesito para la reunión.",
         "Hola, ¿puedes enviarme el contrato antes del viernes? Lo necesito para la reunión.", "it", "es"),
        ("Salom, ertaga uchrashuvga kela olmayman, iltimos boshqa vaqtga ko'chiraylik.",
         "Салом, эртага учрашувга кела олмайман, илтимос бошқа вақтка кўчирайлик.", "ru", "uz"),
        (EN, "Good morning, I will send you the report tomorrow.", "es", "en"),
        (EN, "Доброе утро, я пришлю вам отчёт завтра, это важно.", "uk", "en"),   # Russian: ё, э
        (EN, "Доброго ранку, я надішлю вам звіт завтра.", "ru", "en"),
        (EN, "", "de", "en"),
        (EN, "Good morning, I will send you the report tomorrow.", "uz", "en"),
        ("Salom, men hozir yordam bera olmayman, iltimos kuting.",           # Russian for Ukrainian
         "Здравствуйте, не могу помочь вам сейчас, пожалуйста, подождите.", "uk", "uz"),
        (EN, "Доброго ранку, я надішлю вам звіт завтра, дякую.", "ru", "en"),
        ("Ciao, domani non posso venire in ufficio perché ho un appuntamento dal medico.",
         "Ciao, domani non posso venire in ufficio perché ho un appuntamento dal medico.", "en", "it"))],
     [False] * 10),
    ("translate: same language in and out is fine", lambda: A.translation_ok(
        "Hola, ¿cómo estás hoy?", "Hola, ¿cómo estás hoy?", "es", "es"), True),
    ("translate: an echo is retried with a firmer request", lambda: (lambda eng: (
        A.run(eng, "Hola, ¿puedes enviarme el contrato antes del viernes?", {"kind": "translate", "target": "it"}),
        "It is not in Italian yet" in eng.calls[-1][0][-1]["content"]))(
        Engine("Hola, ¿puedes enviarme el contrato antes del viernes?",
               "Ciao, puoi inviarmi il contratto prima di venerdì?")),
     ("Ciao, puoi inviarmi il contratto prima di venerdì?", True)),
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
