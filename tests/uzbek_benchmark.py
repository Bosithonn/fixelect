"""Uzbek accuracy benchmark (needs a model file). Uzbek is not enabled in the
app yet; this measures whether a model is good enough to enable it.

Run: python tests/uzbek_benchmark.py [3b|1.5b]   or   --model-path=path/to/any.gguf

Latin and Cyrillic script. Reports, separately:
  * the raw model output (what the model would do unguarded),
  * the final output after Fixelect's language-neutral guard,
  * how often the language detector recognises the sentence as Uzbek.
"""

import pathlib
import re
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Windows" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import check_guard as G  # noqa: E402
import chunking  # noqa: E402
import engine as E  # noqa: E402
import languages as L  # noqa: E402

MODEL_PATH = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--model-path=")), None)
PROFILE = next((a for a in sys.argv[1:] if not a.startswith("--")),
               pathlib.Path(MODEL_PATH).stem if MODEL_PATH else "3b")
PORT = 18897

# (input, words that must appear after the fix)  - apostrophe variants are treated alike
FIX = [
    ("Men ertaga ishga borolmayman chunki kasal bo'lib qoldim", ["borolmayman, chunki"]),
    ("Men kecha dokonga bordim va non sotib oldim", ["do'konga"]),
    ("Biz yigilishni ertaga soat 10 ga kochirdik", ["yig'ilishni", "ko'chirdik"]),
    ("Kitobni oqib chiqdim, juda qiziqarli ekan", ["o'qib"]),
    ("Xozir men uydaman, keyinroq qongiroq qilaman", ["hozir", "qo'ng'iroq"]),
    ("Bu xafta juda band bo'ldim lekin keyingi xafta bo'shman", ["hafta", "bo'ldim, lekin"]),
    ("Iltimos menga hisobotni jumagacha yuboring", ["iltimos,"]),
    ("Toshkentda havo bugun juda issiq boldi", ["bo'ldi"]),
    ("Men sizga ertaga malumot yuboraman", ["ma'lumot"]),
    ("Oqituvchimiz bizga uy vazifasini berdi", ["o'qituvchimiz"]),
    ("Bizning kompaniyamiz yangi loyixa ustida ishlayapti", ["loyiha"]),
    ("Uni korganimdan juda xursand boldim", ["ko'rganimdan", "bo'ldim"]),
    ("Мен кеча дуконга бордим ва нон сотиб олдим", ["дўконга"]),
    ("Эртага учрашувга боролмайман чунки касалман", ["боролмайман, чунки"]),
    ("Бу хафта жуда банд булдим", ["ҳафта", "бўлдим"]),
    ("Китобни укиб чикдим", ["ўқиб", "чиқдим"]),
]

KEEP = [
    "Bugun havo juda yaxshi.",
    "Iltimos, hisobotni juma kuni yuboring.",
    "Men sizga ertaga qo'ng'iroq qilaman.",
    "Loyiha bo'yicha yig'ilish soat 15:00 da boshlanadi.",
    "Rahmat, hammasi joyida.",
    "Toshkent shahrida yangi metro bekati ochildi.",
    "API kaliti yangilandi, iltimos, config.json faylini tekshiring.",
    "Салом, қалайсан? Эртага учрашамиз.",
    "Мен кеча дўконга бордим ва нон сотиб олдим.",
    "Раҳмат, ҳаммаси жойида.",
]

# (draft, stems that must survive)
POLISH = [
    ("salom men ertaga kelolmayman chunki onam kasal iltimos yigilishni boshqa kunga kochiring", ["ertaga", "onam"]),
    ("hisobotni juma kuni yuboraman lekin bazi raqamlar hali tayyor emas", ["juma", "raqam"]),
    ("Мен эртага кела олмайман чунки мажлисим бор", ["эртага", "мажлис"]),
]


def norm(s):
    return re.sub(r"[‘’ʻʼ`´]", "'", s).lower()


def has_all(out, need):
    o = norm(out)
    return all(norm(w) in o for w in need)


def same_script(a, b):
    pa, pb = L.script_profile(a), L.script_profile(b)
    return abs(pa["cyrillic"] - pb["cyrillic"]) < 0.3


def main():
    L.SUPPORTED = tuple(L.SUPPORTED) + ("uz",)   # enable Uzbek for this process only
    G.load_config = lambda: {"model_profile": PROFILE}
    eng = E.EmbeddedEngine(port=PORT, model_profile=PROFILE, model_path=MODEL_PATH)
    E._default_engine = eng
    G.load_pipeline("qwen2.5", fast=False, beams=1, engine_type="embedded")
    rows, ms = [], []

    def raw(text, mode):
        msgs = G.build_foreign_messages(text, mode, "uz")
        out = G.embedded_rewrites(eng, text, mode=mode, messages=msgs)
        return out[0] if out else ""

    def guarded(text, mode):
        t0 = time.time()
        out = chunking.process(text, lambda t: G.run_pipeline(lambda: eng, t, mode=mode, lang="uz"), mode=mode)
        ms.append((time.time() - t0) * 1000)
        return out

    try:
        for inp, need in FIX:
            r, g = raw(inp, "fix"), guarded(inp, "fix")
            rows.append(("fix", inp, r, g, has_all(r, need), has_all(g, need), G.detect_language(inp) == "uz"))
        for inp in KEEP:
            r, g = raw(inp, "fix"), guarded(inp, "fix")
            rows.append(("keep", inp, r, g, r.strip() == inp, g == inp, G.detect_language(inp) == "uz"))
        for inp, need in POLISH:
            r, g = raw(inp, "polish"), guarded(inp, "polish")
            ok_r = has_all(r, need) and same_script(inp, r) and G.detect_language(r) in ("uz", "other")
            ok_g = g != inp and has_all(g, need) and same_script(inp, g)
            rows.append(("polish", inp, r, g, ok_r, ok_g, G.detect_language(inp) == "uz"))
    finally:
        eng.stop()

    print(f"\nFixelect Uzbek accuracy - model {PROFILE}")
    for kind, label in (("fix", "errors fixed"), ("keep", "left untouched"), ("polish", "polish kept meaning")):
        r = [x for x in rows if x[0] == kind]
        print(f"  {label:<20} raw model {sum(x[4] for x in r)}/{len(r)}   after guard {sum(x[5] for x in r)}/{len(r)}")
    print(f"  detected as Uzbek    {sum(x[6] for x in rows)}/{len(rows)}")
    ms.sort()
    print(f"  latency median {ms[len(ms) // 2]:.0f} ms")
    for kind, inp, r, g, ok_r, ok_g, _ in rows:
        if not (ok_r and ok_g):
            print(f"  [{kind}] {inp}\n      raw  {'ok ' if ok_r else 'BAD'} {r}\n      final {'ok ' if ok_g else 'BAD'} {g}")


if __name__ == "__main__":
    main()
