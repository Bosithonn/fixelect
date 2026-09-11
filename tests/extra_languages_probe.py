"""Probe for languages Fixelect does not support yet (needs a model file).

Run: python tests/extra_languages_probe.py [3b]   or   --model-path=path/to/any.gguf

A small check, not a benchmark: per language two sentences with obvious
mistakes that must be fixed and one correct sentence that must stay as is,
all through Fixelect's language-neutral guard with the language forced.
"""

import pathlib
import sys

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
PORT = 18898

NAMES = {"tr": "Turkish", "pl": "Polish", "nl": "Dutch", "id": "Indonesian"}

# lang: [(input, must contain or None = must stay unchanged)]
CASES = {
    "tr": [("Yarın toplantıya gelemiycem çünkü hastayım", ["gelemeyeceğim"]),
           ("Bu kitabı çok beğendim, herkeze tavsiye ederim", ["herkese"]),
           ("Raporu cuma gününe kadar gönderebilir misiniz?", None)],
    "pl": [("Jutro nie moge przyjść na spotkanie", ["mogę"]),
           ("Dziękuje za pomoc, to było bardzo miłe", ["dziękuję"]),
           ("Czy możesz wysłać mi raport do piątku?", None)],
    "nl": [("Ik heb gisteren een nieuwe fiets gekocht en hij rijd heel goed", ["rijdt"]),
           ("Kun je me morgen even bellen, ik wil iets vragen", ["kun je me morgen even bellen"]),
           ("Bedankt voor je hulp, tot maandag.", None)],
    "id": [("Saya tidak bisa datang besok karna saya sakit", ["karena"]),
           ("Tolong kirimkan laporanya sebelum hari jumat", ["laporannya"]),
           ("Terima kasih atas bantuan Anda.", None)],
}


def main():
    L.NAMES.update(NAMES)
    L.SUPPORTED = tuple(L.SUPPORTED) + tuple(NAMES)
    G.load_config = lambda: {"model_profile": PROFILE}
    eng = E.EmbeddedEngine(port=PORT, model_profile=PROFILE, model_path=MODEL_PATH)
    E._default_engine = eng
    G.load_pipeline("qwen2.5", fast=False, beams=1, engine_type="embedded")
    totals = {}
    try:
        for lang, cases in CASES.items():
            for inp, need in cases:
                out = chunking.process(inp, lambda t: G.run_pipeline(lambda: eng, t, mode="fix", lang=lang))
                ok = out == inp if need is None else all(w.lower() in out.lower() for w in need)
                totals.setdefault(lang, []).append(ok)
                print(f"  [{lang}] {'ok ' if ok else 'BAD'} {inp}\n             -> {out}")
    finally:
        eng.stop()
    print(f"\nExtra languages - model {PROFILE}")
    for lang, oks in totals.items():
        print(f"  {NAMES[lang]:<11} {sum(oks)}/{len(oks)}")


if __name__ == "__main__":
    main()
