"""Build shared/data/uz_words.txt from a uz-crawl sample (Apache-2.0).

Run: python tests/build_uz_wordlist.py path/to/uz_docs.jsonl

Input: JSON lines {"split": "news" | "telegram_blogs", "text": "..."} sampled
from https://huggingface.co/datasets/tahrirchi/uz-crawl. Only the edited
news split is used, so common misspellings from informal posts do not end up
protected as "correct". Apostrophe variants are normalised to ASCII.
"""

import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "shared"))

import languages as L  # noqa: E402

OUT = ROOT / "shared" / "data" / "uz_words.txt"
WORD = re.compile(r"[a-z]+(?:'[a-z]+)*")
MIN_COUNT = 3


def main(src):
    counts = collections.Counter()
    docs = 0
    with open(src, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row.get("split") != "news":
                continue
            text = row["text"]
            if L.script_profile(text)["latin"] < 0.8:
                continue  # skip Cyrillic (often Russian) and mixed documents
            docs += 1
            norm = re.sub(r"[‘’ʻʼ`´]", "'", text.lower())
            counts.update(w for w in WORD.findall(norm) if 2 <= len(w) <= 30)
    words = [w for w, c in counts.most_common() if c >= MIN_COUNT]
    header = ("# Frequent Uzbek (Latin) words, most common first. Used for language detection\n"
              "# and to stop Fixelect replacing correctly spelled Uzbek words.\n"
              f"# Derived from {docs:,} news documents of tahrirchi/uz-crawl (Apache-2.0).\n")
    OUT.write_text(header + "\n".join(words) + "\n", encoding="utf-8")
    print(f"{docs:,} documents -> {len(words):,} words (seen {MIN_COUNT}+ times) -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
