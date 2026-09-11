"""Multilingual accuracy benchmark (needs a downloaded model).

Run: python tests/multilingual_benchmark.py [3b|1.5b]

For each supported language: typo-laden sentences that must come back fixed,
correct sentences that must come back untouched, and a polish that must stay
in the same language and keep its key words. Unsupported languages must be
left exactly as they are.
"""

import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Windows" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import check_guard as G  # noqa: E402
import chunking  # noqa: E402
import engine as E  # noqa: E402

# python tests/multilingual_benchmark.py [3b|1.5b]   or   --model-path=path/to/any.gguf
MODEL_PATH = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--model-path=")), None)
PROFILE = next((a for a in sys.argv[1:] if not a.startswith("--")),
               pathlib.Path(MODEL_PATH).stem if MODEL_PATH else "3b")
PORT = {"3b": 18894, "1.5b": 18895}.get(PROFILE, 18896)

# (lang, input, words that must appear in the fix; a tuple means "any of these")
FIX = [
    ("es", "Ayer fuimos al sine con mis amigos y la pelicula fue muy buena", ["cine", "película"]),
    ("es", "No se si podre ir a la reunion de mañana", ["reunión", "podré"]),
    ("es", "Tengo que conprar leche y pan para el desayuno", ["comprar"]),
    ("fr", "Je voudrais reserver une table pour deux persones ce soir", ["réserver", "personnes"]),
    ("fr", "Nous avons parler avec le directeur hier", ["parlé"]),
    ("fr", "Il fait tres beau aujourd'hui", ["très"]),
    ("de", "Ich freue mich auf das Wochenende weil ich endlich ausschlafen kann", ["Wochenende,", "weil"]),
    ("de", "Kannst du mir bitte helfen, ich habe ein Problemm mit meinem Computer", ["Problem"]),
    ("de", "Wir haben gestern einen schönen Ausflug gemacht und viel gelacht", ["Ausflug"]),
    ("pt", "Eu gostaria de marcar uma reuniao para amanha de manha", ["reunião", "amanhã", "manhã"]),
    ("pt", "Voce pode me enviar o relatorio ate sexta?", ["Você", "relatório", "até"]),
    ("it", "Vorrei prenotare un tavolo per stasera, e possibile?", ["è"]),
    ("it", "Non ho ancora ricevuto la tua emial", ["email"]),
    ("ru", "Я не смог прийти на встречу потому что заболел", ["встречу,"]),
    ("ru", "Пожалуйста отправте мне отчёт до пятницы", ["отправьте"]),
    ("ru", "Мы вчера были в кино и фильм был очень интересный", ["интересный"]),
    ("uk", "Я не зміг прийти на зустріч тому що захворів", ["зустріч,"]),
    ("uk", "Будь ласка надішліть мені звіт до пятниці", [("п'ятниці", "п’ятниці")]),
]

KEEP = [
    ("es", "Gracias por tu ayuda, nos vemos el lunes."),
    ("fr", "Le rapport est prêt, je te l'envoie ce soir."),
    ("de", "Die Präsentation beginnt um 10 Uhr im Raum B."),
    ("pt", "Obrigado pela ajuda, até amanhã."),
    ("it", "La riunione è stata spostata a giovedì."),
    ("ru", "Привет, как дела? Встреча завтра в 10."),
    ("uk", "Дякую за допомогу, побачимося в понеділок."),
    ("uz", "Salom, qalaysan? Ertaga uchrashamiz."),
    ("uz", "Бугун ҳаво жуда яхши, кечқурун учрашамиз."),
    ("kk", "Сәлем, қалың қалай? Ертең кездесеміз."),
]

POLISH = [
    ("es", "oye no voy a poder ir mañana a la reunion porque tengo cita con el medico", ["mañana", "médico"]),
    ("fr", "salut je peux pas venir demain j'ai un rendez vous chez le dentiste", ["demain", "dentiste"]),
    ("de", "hallo ich kann morgen nicht kommen weil ich einen arzttermin habe", ["morgen"]),
    ("ru", "привет я не смогу завтра прийти потому что у меня встреча с врачом", ["завтра", "врач"]),
]


def any_word(out, options):
    return any(o in out for o in options)


def main():
    G.load_config = lambda: {"model_profile": PROFILE}
    eng = E.EmbeddedEngine(port=PORT, model_profile=PROFILE, model_path=MODEL_PATH)
    E._default_engine = eng
    fix = G.load_pipeline("qwen2.5", fast=False, beams=1, engine_type="embedded")
    rows, ms = [], []

    def run(text, mode):
        t0 = time.time()
        out = chunking.process(text, lambda t: fix(t, mode=mode), mode=mode)
        ms.append((time.time() - t0) * 1000)
        return out

    try:
        for lang, inp, need in FIX:
            out = run(inp, "fix")
            ok = all(any_word(out, w) if isinstance(w, tuple) else w in out for w in need)
            rows.append(("fix", lang, inp, out, ok))
        for lang, inp in KEEP:
            out = run(inp, "fix")
            rows.append(("keep", lang, inp, out, out == inp))
        for lang, inp, need in POLISH:
            out = run(inp, "polish")
            same = G.detect_language(out) == lang
            rows.append(("polish", lang, inp, out, same and all(w in out.lower() for w in need) and out != inp))
    finally:
        eng.stop()

    print(f"\nFixelect multilingual accuracy - model {PROFILE}")
    for kind, label in (("fix", "errors fixed"), ("keep", "left untouched"), ("polish", "polish same language")):
        r = [x for x in rows if x[0] == kind]
        print(f"  {label:<22} {sum(x[4] for x in r)}/{len(r)}")
    ms.sort()
    print(f"  latency median {ms[len(ms) // 2]:.0f} ms")
    for kind, lang, inp, out, ok in rows:
        if not ok:
            print(f"  FAIL [{kind}/{lang}] {inp!r}\n        -> {out!r}")


if __name__ == "__main__":
    main()
