"""Model-free tests for rich-text mapping, chunking, language detection and
styles. Run: python tests/test_text.py"""

import pathlib
import sys
import threading

# Test names include Cyrillic and Uzbek; a cp1252 console (Windows CI) can't print them
sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ("MacOS" if sys.platform == "darwin" else "Windows") / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import check_guard as G  # noqa: E402
import chunking  # noqa: E402
import richtext as R  # noqa: E402

CHROME = ("<html><body>\r\n<!--StartFragment--><p>I <b>recieved</b> teh package and "
          "<a href=\"https://x.com\">its</a> great</p><!--EndFragment-->\r\n</body></html>")
WORD = ("<html><body><!--StartFragment--><p class=MsoNormal><span style='font-family:Calibri'>Their going\r\n"
        "to the park</span> <i>later</i> today<o:p></o:p></p><!--EndFragment--></body></html>")


def _cf(markup):
    return R.build_cf_html(markup)


def _roundtrip(markup, old, new):
    out = R.rewrite_cf_html(_cf(markup), old, new)
    if out is None:
        return None
    return out.split(b"\0")[0].decode("utf-8")


def _fake_fix(t):
    return t.replace("teh", "the"), [], t


CASES = [
    # rich text
    ("word ops: single replace", lambda: R.word_ops("a teh b", "a the b"), [(2, 5, "the")]),
    ("word ops: duplicate delete", lambda: R.word_ops("the the task", "the task"), [(0, 4, "")]),
    ("html: formatting kept on fix", lambda: "<b>received</b> the package" in _roundtrip(
        CHROME, "I recieved teh package and its great", "I received the package and its great"), True),
    ("html: link text fixed inside link", lambda: '">it\'s</a>' in _roundtrip(
        CHROME, "I recieved teh package and its great", "I recieved teh package and it's great"), True),
    ("html: word wrapped source", lambda: "They're going" in _roundtrip(
        WORD, "Their going to the park later today", "They're going to the park later today"), True),
    ("html: edit across formatting refused", lambda: _roundtrip(
        CHROME, "I recieved teh package and its great", "I got it"), None),
    ("cf_html offsets valid", lambda: _check_offsets(R.rewrite_cf_html(_cf(CHROME),
        "I recieved teh package and its great", "I received the package and its great")), True),
    ("html entities survive", lambda: "&amp;" in _roundtrip(
        "<!--StartFragment--><p>Tom &amp; Jery</p><!--EndFragment-->", "Tom & Jery", "Tom & Jerry"), True),
    ("count changes", lambda: R.count_changes("i has a apple", "I have an apple"), 3),
    # the result card lists what changed
    ("summary: misspellings before capitals", lambda: R.change_summary(
        "i cant beleive teh wether", "I can't believe the weather."),
        "beleive → believe  ·  teh → the  ·  wether → weather.  ·  +2 more"),
    ("summary: removed duplicate", lambda: R.change_summary("see the the cat", "see the cat"), "removed “the”"),
    ("summary: added word", lambda: R.change_summary("I going home", "I am going home"), "added “am”"),
    ("summary: nothing changed", lambda: R.change_summary("All good here.", "All good here."), ""),
    ("summary: a rewrite is not a list of edits", lambda: R.change_summary(
        "hey can u send me the report by friday", "Could you send the report over by Friday, please?"), ""),
    ("summary: long words shortened", lambda: len(R.change_summary(
        "supercalifragilisticexpialidociuss", "supercalifragilisticexpialidocious")) < 45, True),
    # "copy the whole line" in code editors (nothing selected)
    ("line copy: VS Code metadata", lambda: R.is_line_copy(
        b'{"version":1,"isFromEmptySelection":true,"multicursorText":null,"mode":"python"}'), True),
    ("line copy: Chromium custom data (UTF-16)", lambda: R.is_line_copy(
        ("vscode-editor-data" + '{"version":1,"isFromEmptySelection":true}').encode("utf-16-le")), True),
    ("line copy: a real selection", lambda: R.is_line_copy(b'{"version":1,"isFromEmptySelection":false}'), False),
    ("line copy: no metadata", lambda: R.is_line_copy(None), False),
    # chunking
    ("chunk: short text unchanged path", lambda: chunking.process("teh cat", _fake_fix), "the cat"),
    ("chunk: long text reassembles", lambda: chunking.process(("teh cat sat. " * 120).strip(), _fake_fix)
     == ("the cat sat. " * 120).strip(), True),
    ("chunk: paragraphs and edges kept", lambda: chunking.process(
        "  " + "\n\n".join(["teh " + "x" * 450 + "."] * 3) + "\n", _fake_fix)
     == "  " + "\n\n".join(["the " + "x" * 450 + "."] * 3) + "\n", True),
    ("chunk: units join back", lambda: "".join(c + s for c, s in chunking.split_units(
        "One. Two! Three? " * 80, 200)) == "One. Two! Three? " * 80, True),
    ("chunk: cancel stops", lambda: _cancelled(), True),
    # languages
    ("lang: English", lambda: G.detect_language("I will send the report tomorrow morning."), "en"),
    ("lang: Spanish", lambda: G.detect_language("Mañana voy a la oficina porque tengo mucho trabajo."), "es"),
    ("lang: French", lambda: G.detect_language("Je suis allé au magasin hier mais il était fermé."), "fr"),
    ("lang: German", lambda: G.detect_language("Ich habe gestern mit meinem Kollegen gesprochen."), "de"),
    ("lang: Portuguese", lambda: G.detect_language("Eu não sei se vou conseguir chegar a tempo amanhã."), "pt"),
    ("lang: Italian", lambda: G.detect_language("Domani non posso venire perché ho un appuntamento."), "it"),
    ("lang: Russian", lambda: G.detect_language("Я вчера ходил в магазин и купил хлеб."), "ru"),
    ("lang: Ukrainian", lambda: G.detect_language("Я вчора ходив до магазину і купив хліб."), "uk"),
    ("lang: Uzbek latin", lambda: G.detect_language("Salom, qalaysan? Ertaga uchrashamiz."), "uz"),
    ("lang: Uzbek cyrillic", lambda: G.detect_language("Салом, қалайсан? Эртага учрашамиз."), "uz"),
    ("lang: typo English", lambda: G.detect_language("helo how r u im fne wht abt u"), "en"),
    ("lang: code stays English", lambda: G.detect_language("git commit -m 'fix login bug' && git push"), "en"),
    ("lang: shorthand is not German", lambda: G.detect_language("im fne"), "en"),
    ("lang: repeated word is one hit", lambda: G.detect_language("la la land is great"), "en"),
    ("lang: English with a French name", lambda: G.detect_language("The meeting is at la Brasserie de Paris."), "en"),
    # foreign guard
    ("foreign: accent fix accepted", lambda: G.consensus("il etait fermer", ["il était fermé"], lang="fr")[0],
     "il était fermé"),
    ("foreign: typo fix accepted", lambda: G.consensus("я купил малоко", ["я купил молоко"], lang="ru")[0],
     "я купил молоко"),
    ("foreign: capital never removed", lambda: G.consensus("Meeting завтра", ["meeting завтра"], lang="ru")[0],
     "Meeting завтра"),
    ("foreign: capital may be added", lambda: G.consensus("привет, как дела", ["Привет, как дела"], lang="ru")[0],
     "Привет, как дела"),
    ("foreign: word swap refused", lambda: G.consensus("я купил хлеб", ["я купил сыр"], lang="ru")[0],
     "я купил хлеб"),
    ("foreign: polish translation refused", lambda: G.polish_guard(
        "Mañana voy a la oficina porque tengo mucho trabajo", "Tomorrow I am going to the office", lang="es"),
     "Mañana voy a la oficina porque tengo mucho trabajo"),
    # Uzbek helpers
    ("uz: Cyrillic to Latin", lambda: G.L.uz_to_latin("Мен кеча дўконга бордим, ғалаба!"),
     "Men kecha do'konga bordim, g'alaba!"),
    ("uz: word-initial е is ye", lambda: G.L.uz_to_latin("Ер юзи"), "Yer yuzi"),
    ("uz: Latin to Cyrillic", lambda: G.L.uz_to_cyrillic("Bo'ldim, hafta, shahar, choy, g'isht"),
     "Бўлдим, ҳафта, шаҳар, чой, ғишт"),
    ("uz: fix carried back to Cyrillic", lambda: G.L.uz_apply_back(
        "Бу хафта жуда банд булдим", "Bu xafta juda band buldim", "Bu hafta juda band bo'ldim"),
     "Бу ҳафта жуда банд бўлдим"),
    ("uz: untouched Cyrillic words kept exactly", lambda: G.L.uz_apply_back(
        "Салом, дўстим", "Salom, do'stim", "Salom, do'stim"), "Салом, дўстим"),
    ("uz: key ignores apostrophes", lambda: G.L.uz_key("Oʻqib") == G.L.uz_key("oqib") == G.L.uz_key("Ўқиб"), True),
    ("uz: only with Gemma", lambda: ("uz" in G.L.supported_for("gemma4-e2b"), "uz" in G.L.supported_for("3b")),
     (True, False)),
    ("uz: Turkish letter refused", lambda: G.consensus("metro bekati ochildi", ["metro bekatı ochildi"], lang="uz")[0],
     "metro bekati ochildi"),
    ("uz: apostrophe fix accepted", lambda: G.consensus("Men dokonga bordim", ["Men do'konga bordim"], lang="uz")[0],
     "Men do'konga bordim"),
    # styles
    ("styles: all have prompts", lambda: all(G.build_messages("x", "polish", s)[0]["content"]
                                             for s in G.POLISH_STYLES), True),
    ("styles: custom note included", lambda: "British" in G.build_messages(
        "x", "polish", "friendly", "Use British spelling")[0]["content"], True),
    ("styles: shorter may shrink", lambda: G.polish_guard(
        "i think we should probably maybe move the meeting with the design team to thursday afternoon if that works",
        "Let's move the design team meeting to Thursday afternoon if that works.", style="shorter"),
     "Let's move the design team meeting to Thursday afternoon if that works."),
]


def _check_offsets(data):
    head = data[:200].decode("ascii")
    import re
    vals = {k: int(v) for k, v in re.findall(r"(StartHTML|EndHTML|StartFragment|EndFragment):(\d+)", head)}
    body = data.split(b"\0")[0]
    return (body[vals["StartHTML"]:vals["StartHTML"] + 6] == b"<html>"
            and body[vals["EndFragment"]:vals["EndFragment"] + 4] == b"<!--"
            and body[vals["StartFragment"] - 3:vals["StartFragment"]] == b"-->"
            and vals["EndHTML"] == len(body))


def _cancelled():
    ev = threading.Event()
    calls = []

    def fn(t):
        calls.append(t)
        ev.set()
        return t, [], t
    try:
        chunking.process("One sentence here. " * 200, fn, cancel=ev)
    except chunking.Cancelled:
        return len(calls) == 1
    return False


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
    print(f"\n{len(CASES) - failed}/{len(CASES)} text tests passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
