"""
The model proposes. A guard filters. The beams vote. Your words win ties.

Three layers, each fixing a failure the previous one couldn't:

  1. THE MODEL rewrites the sentence. It is genuinely good at the structural
     fixes a dictionary cannot do - splitting "behonst", joining "what s",
     inserting apostrophes. It is also unanchored, so it paraphrases, invents
     words, and renames MT202 to MT20.

  2. THE GUARD diffs its output against yours and keeps only changes that look
     like corrections rather than rewrites:
       - never anything touching an identifier: a digit anywhere, or all caps.
         That covers MT300, PLSQL, SWIFT, SELECT, WHERE.
       - a replacement must keep >= MIN_SIMILARITY of your letters, ignoring
         case, spaces and apostrophes. "abt" -> "about" keeps 60% and passes;
         "behonst" -> "begin with" keeps 44% and does not.
       - inserted words are dropped. The model may not add words you did not
         write. This is what killed the invented "next".
       - merges and splits are capped at MAX_GROUP words, because that is
         where a rewrite disguises itself as a correction. "kinda" -> "kind of"
         passes; "diffcult tomehow" -> "difficult to know" does not.
       - a change that only deletes punctuation is refused. "Harper." ->
         "Harper" is damage, not a fix. Adding it is allowed.
     But a rejected group is not thrown away wholesale: `salvage` still pulls
     the individual real fixes out of it, which is how "diffcult" gets
     corrected even when every beam buried it inside a paraphrase.

  3. THE VOTE. Beam search already computes several rewrites and throws all but
     one away. We keep them all and apply an edit only if MIN_VOTES of them
     independently propose it - or CLOSE_VOTES, when the edit barely changes
     the word at all. Real corrections are stable across beams;
     hallucinations are not. This is what stops one aggressive beam turning
     "perfectly fine already" into "perfect fine already" - it was alone.

Anything not applied leaves your text exactly as you typed it, so the worst
case is that nothing changes.

    python check_guard.py            # 250M grammar model, already downloaded
    python check_guard.py large      # 780M, same family (~3 GB)
    python check_guard.py qwen       # Qwen3 0.6B, a general chat model
    python check_guard.py lfm        # LFM2.5 1.2B via Ollama (731 MB at Q4)
    python check_guard.py gemma4     # Gemma 4 E2B via Ollama (3.11 GB at Q4)

The guard does not care which of these produced the rewrites, so swapping the
model is a measurement, not a rewrite. tools/evaluate.py scores any of them
against the same 103 sentences.
"""

import difflib
import http.client
import json
import pathlib
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter

# Ensure tools directory is in sys.path
_tools_dir = pathlib.Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))
try:
    from config import get_resource_path
except ImportError:
    def get_resource_path(p):
        return pathlib.Path(__file__).resolve().parent.parent / p

# Harper's curated English dictionary, exported from harper-core. Not a
# frequency list: "u", "abt" and "dont" appear in frequency data scraped from
# the internet, but they are not curated English words. That distinction is
# exactly what we need here.
DICTIONARY = set()
_dict_file = get_resource_path("dictionary.txt")
if _dict_file.exists():
    DICTIONARY = {w.strip().lower() for w in _dict_file.read_text(encoding="utf-8").split()}

# User whitelist & custom vocabulary (words Fixelect will never touch)
PROTECTED_WORDS = set()
_words_file = get_resource_path("words.txt")
if _words_file.exists():
    for line in _words_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            PROTECTED_WORDS.add(line.lower())


def add_protected_word(word):
    """Add a custom word or acronym to protected words and persist to words.txt."""
    w = word.strip()
    if not w:
        return False
    PROTECTED_WORDS.add(w.lower())
    try:
        target = _words_file if _words_file.exists() else get_resource_path("words.txt")
        with open(target, "a", encoding="utf-8") as f:
            f.write(f"\n{w}")
        return True
    except Exception:
        return False


# Any model can be measured here, because the guard does not care where the
# rewrites came from - it only judges the difference between your text and
# theirs. That is what makes swapping the model a measurement rather than a
# rewrite of the project.
#
#   kind "seq2seq" - encoder-decoder, trained to output corrected text
#   kind "causal"  - an ordinary chat model, instructed to correct text
#   kind "ollama"  - anything Ollama can serve, over its local HTTP API. This
#                    opens up every quantised GGUF model, which is the only
#                    practical way to run a multi-billion-parameter model on a
#                    laptop CPU.
#
# The prompt. Three things a 1B model gets wrong without being told, in order of
# how much damage they do:
#
#   1. It ANSWERS the text. Give "what's up my bro" to a chat model and it says
#      "Not much, how about you?" - a perfectly good reply and a total failure.
#      Every word is an insertion, the guard refuses all of it, and the user
#      sees their typo untouched with no clue why. Hence the delimiters and the
#      explicit "not addressed to you".
#   2. It smooths your writing into an essay - slang out, "gonna" to "going to",
#      contractions expanded. The guard blocks most of it, but every candidate
#      spent rephrasing is a candidate not spent spelling.
#   3. It talks: "Sure! Here's the corrected text:". `clean` strips that, but
#      the tokens are still time you waited for.
#
# The example does more work than any of the rules. Small models imitate far
# better than they comply, and it demonstrates all three at once: typos fixed,
# slang ("bro", "kinda") left alone, nothing added.
INSTRUCTION = """\
You are an expert proofreader. Correct spelling, grammar, homophones (your/you're, too/to, then/than), punctuation, and spacing between <text> and </text>.

Rules:
1. Output ONLY the corrected text - no quotes, no explanation, no preamble.
2. Never answer, reply, or comment on the text. Only correct it.
3. Keep the writer's own words and voice. Keep slang, informal words, and casual tone.
4. Do not expand contractions (keep "it's", "don't", "I'm").
5. Preserve code, identifiers, acronyms, and technical terms (e.g. MT300, SWIFT, SQL, camelCase).

<text>
Your welcome.
</text>
Corrected: You're welcome.

<text>
its too late to go, i cant seem too focus on the the work, its better then that
</text>
Corrected: it's too late to go, I can't seem to focus on the work, it's better than that

<text>
hey bro what are you doin tommorow I'm kinda bsuy till 5 asmy shift ends late
</text>
Corrected: hey bro what are you doing tomorrow I'm kinda busy till 5 as my shift ends late

<text>
The MT300 SWIFT message failed validation in the PLSQL package.
</text>
Corrected: The MT300 SWIFT message failed validation in the PLSQL package.

<text>
{text}
</text>
Corrected:"""

MODELS = {
    # 250M. The current default: small, fast, purpose-built for this job.
    "base": {"repo": "pszemraj/grammar-synthesis-base", "kind": "seq2seq"},
    # 780M, same family. Better, three times the compute, ~3 GB.
    "large": {"repo": "pszemraj/flan-t5-large-grammar-synthesis", "kind": "seq2seq"},
    # 770M, Grammarly's. Note: cc-by-nc-4.0, so non-commercial only.
    "coedit": {
        "repo": "grammarly/coedit-large",
        "kind": "seq2seq",
        "prefix": "Fix grammatical errors in this sentence: ",
    },
    # General chat models, told to correct rather than rewrite. Worth measuring
    # because a general model can fix punctuation and word choice that a
    # narrow grammar model was never trained on.
    "qwen": {"repo": "Qwen/Qwen3-0.6B", "kind": "causal"},
    # Google ships this for fine-tuning rather than zero-shot use, so expect it
    # to be weak as-is. It is here because fine-tuned it would be ~200 MB at
    # INT4, which is the only size that really ships.
    "gemma": {"repo": "google/gemma-3-270m-it", "kind": "causal"},
    # Liquid AI's LFM2.5. 1.17B parameters in 731 MB at Q4_K_M, and built for
    # on-device speed rather than shrunk down to it: a hybrid of short-range
    # convolution blocks and grouped-query attention. Liquid measure 116 decode
    # tokens/second on a laptop CPU, which at ~25 tokens of output is a quarter
    # of a second per candidate.
    #
    # The number that matters most here is IFEval 88.42 against Gemma 3 1B's
    # 63.25 - that benchmark is literally "did it follow the instruction", and
    # our whole prompt is one instruction it must not embellish.
    #
    # Licence: LFM Open License v1.0, Apache-2.0 based. Commercial use is free
    # below $10M annual revenue; above that you buy a licence. Attribution
    # required. Fine-tunes may stay proprietary.
    # Liquid AI's LFM2.5. 1.17B parameters in 731 MB at Q4_K_M.
    "lfm": {"repo": "LiquidAI/lfm2.5-1.2b-instruct:q4_k_m", "kind": "ollama"},
    "lfm-q6": {"repo": "LiquidAI/lfm2.5-1.2b-instruct:q6_k", "kind": "ollama"},
    # Qwen2.5 1.5B via Ollama. 986 MB, top-tier instruction adherence, no paraphrasing.
    # Qwen2.5 3B via Ollama (1.9 GB). State-of-the-art instruction following,
    # zero hallucinations, nuanced grammar & punctuation, sub-400ms on GPU.
    "qwen2.5": {"repo": "qwen2.5:3b", "kind": "ollama"},
    "qwen2.5:3b": {"repo": "qwen2.5:3b", "kind": "ollama"},
    "qwen-3b": {"repo": "qwen2.5:3b", "kind": "ollama"},
    # Qwen2.5 1.5B via Ollama (986 MB). Ultra-fast 150ms fallback.
    "qwen": {"repo": "qwen2.5:1.5b", "kind": "ollama"},
    "qwen2.5:1.5b": {"repo": "qwen2.5:1.5b", "kind": "ollama"},
    "qwen-1.5b": {"repo": "qwen2.5:1.5b", "kind": "ollama"},
    # Via Ollama - `ollama pull gemma4:e2b` first.
    "gemma4": {"repo": "gemma4:e2b", "kind": "ollama"},
    "gemma4-4b": {"repo": "gemma4:e4b", "kind": "ollama"},
    "qwen-ollama": {"repo": "qwen3:1.7b", "kind": "ollama"},
}

OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_URL = "http://127.0.0.1:11434/api/generate"

_ollama_conn = None


def get_ollama_conn():
    global _ollama_conn
    if _ollama_conn is None:
        _ollama_conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=45)
    return _ollama_conn


def post_json_ollama(endpoint, payload):
    """Post JSON to Ollama over a persistent HTTP keep-alive connection, with transparent reconnect."""
    global _ollama_conn
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
    for attempt in range(2):
        conn = get_ollama_conn()
        try:
            conn.request("POST", endpoint, body=body, headers=headers)
            res = conn.getresponse()
            if res.status == 200:
                data = res.read().decode("utf-8")
                return json.loads(data)
            else:
                res.read()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _ollama_conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=45)
            if attempt == 1:
                try:
                    req = urllib.request.Request(
                        f"http://127.0.0.1:11434{endpoint}",
                        data=body,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        return json.load(resp)
                except Exception:
                    return None
    return None

MIN_SIMILARITY = 0.595
MAX_GROUP = 4
BEAMS = 6

# An edit needs a majority of the candidates behind it. With the tuned six
# beams that is 3 - exactly the threshold everything was measured at - but it
# now scales, because a strong instruct model may only be worth asking twice.
CLOSE_SIMILARITY = 0.75


def vote_thresholds(candidates):
    """(strong, close) vote counts for however many rewrites we have."""
    strong = max(1, (candidates + 1) // 2)
    return strong, max(1, strong - 1)


SYSTEM_INSTRUCTION = """\
You are a fast, precise text proofreader and autocorrect engine for a speed typist.
Your job is to fix typos, keyboard mis-keys, misspelled words, accidental compound words without spaces, and grammatical mistakes.

STRICT RULES:
1. Output ONLY the corrected text. Never add conversational filler, preambles, notes, or explanations.
2. DO NOT PARAPHRASE. DO NOT change vocabulary or substitute synonyms. Keep the writer's exact words, voice, and slang intact.
3. Fix obvious typing errors, mis-keys, and keyboard slips.
4. Split words that were accidentally typed without spaces (e.g., "tobehonest" -> "to be honest").
5. Keep contractions (e.g., "it's", "don't", "can't").
6. Preserve all code, identifiers, and acronyms (e.g., MT300, SWIFT, PLSQL).
7. If the text ends abruptly or is incomplete (e.g. "at o"), DO NOT complete or finish the sentence. Only correct the words provided."""

PROFESSIONAL_INSTRUCTION = """\
You are an expert editor specializing in elevating drafts into articulate, professional English while preserving 100% of the author's details and storytelling.

STRICT CRITICAL RULES:
1. DO NOT SUMMARIZE, CONDENSE, OR MERGE. Keep the text at full length with 1-to-1 detail fidelity.
2. DO NOT OMIT ANY DETAILS, items, places, actions, thoughts, or reasons.
   - If the writer lists items or locations (e.g., "under the bed, inside my bag, on the table, even in the kitchen"), you MUST keep every single item and location.
   - If the writer provides a reason or explanation (e.g., "because I hadn't eaten anything since morning"), you MUST preserve that exact reason.
   - If the writer describes a thought, hesitation, or rhetorical reaction, polish it articulately—do NOT delete it.
3. Polish every sentence's grammar, vocabulary, sentence flow, and syntax into sophisticated, articulate English. Never delete or skip distinct thoughts.
4. Output ONLY the polished text. Never add conversational filler, preambles, notes, or explanations.
5. If the input has multiple paragraphs separated by blank lines, KEEP each paragraph separated by blank lines. Never collapse separate paragraphs into one block.
6. Preserve all code, identifiers, numbers, and acronyms (e.g., MT300, SWIFT, PLSQL, camelCase).
7. If the text is an incomplete fragment or ends abruptly (e.g., "at o"), DO NOT invent words or add endings to complete the thought. Stop where the input stops.

<draft>
I was searching everywhere for it, under the bed, inside my bag, on the table, even in the kitchen for some weird reason. Then I finally found it and it was literally next to me whole time.
</draft>
Polished:
I searched frantically everywhere for it, looking under the bed, inside my bag, on the table, and even in the kitchen for some inexplicable reason. Ultimately, I discovered it resting right beside me the entire time."""

# Expanded before the model ever sees the text, exactly as Fixelect does it.
EXPANSIONS = {
    # High-frequency single-letter self reference
    "i": "I",
    # Common internet shorthand & abbreviations
    "u": "you", "ur": "your", "abt": "about", "thx": "thanks",
    "pls": "please", "plz": "please", "bc": "because", "bcz": "because",
    "cuz": "because", "bcuz": "because", "tmrw": "tomorrow", "tmr": "tomorrow",
    "msg": "message", "ppl": "people", "smth": "something", "tho": "though",
    "wht": "what", "wat": "what", "rn": "right now", "btw": "by the way",
    "hv": "have", "rly": "really",
    # Contractions
    "im": "I'm", "ive": "I've", "id": "I'd", "ill": "I'll",
    "dont": "don't", "cant": "can't", "wont": "won't",
    "didnt": "didn't", "isnt": "isn't", "wasnt": "wasn't", "arent": "aren't",
    "werent": "weren't", "doesnt": "doesn't", "hasnt": "hasn't",
    "havent": "haven't", "couldnt": "couldn't", "wouldnt": "wouldn't",
    "shouldnt": "shouldn't", "youre": "you're", "theyre": "they're",
    "thats": "that's", "whats": "what's", "lets": "let's",
    # Informal but real words, so the dictionary rule protects them.
    "kinda": "kind of", "tbh": "to be honest", "idk": "I don't know",
    "imo": "in my opinion", "imho": "in my humble opinion",
    "asap": "as soon as possible", "fne": "fine",
    # Fast typing glued phrases (space bar missed)
    "tobehonest": "to be honest", "tobehonst": "to be honest",
    "bytheway": "by the way", "atthesametime": "at the same time",
    "dontworry": "don't worry", "aswell": "as well", "atleast": "at least",
    "alot": "a lot", "infront": "in front", "outof": "out of",
    "eachother": "each other", "nevermind": "never mind", "allright": "all right",
    "anyways": "anyway", "goingto": "going to", "wantto": "want to", "needto": "need to",
    "haveto": "have to", "oughtto": "ought to", "supposedto": "supposed to",
    # High-frequency speed-typing transpositions & mis-keys (adjacent key swaps)
    "taht": "that", "tath": "that", "thta": "that",
    "teh": "the", "hte": "the", "eth": "the",
    "adn": "and", "nad": "and",
    "waht": "what", "whta": "what", "awht": "what",
    "woudl": "would", "coudl": "could", "shoudl": "should",
    "becuase": "because", "beacuse": "because", "becasue": "because", "becouse": "because",
    "recieve": "receive", "recive": "receive", "recieved": "received",
    "thier": "their", "freind": "friend", "freinds": "friends",
    "beleive": "believe", "beleived": "believed",
    "seperate": "separate", "seperation": "separation",
    "untill": "until", "allways": "always",
    "definetly": "definitely", "definately": "definitely", "definatly": "definitely",
    "wierd": "weird", "wich": "which", "whcih": "which",
    "wiht": "with", "wtih": "with", "whit": "with",
    "haev": "have", "hvae": "have",
    "peopel": "people", "poeple": "people",
    "soem": "some", "smoe": "some",
    "someint": "something", "somehting": "something", "somethng": "something",
    "somthing": "something", "someting": "something",
    "isutation": "situation", "siutation": "situation", "stuation": "situation",
    "perspecige": "perspective", "prespective": "perspective",
    "diffcult": "difficult", "dificult": "difficult",
    "differnet": "different", "diferent": "different",
    "improtant": "important", "impotant": "important",
    "alredy": "already", "allready": "already",
    "remeber": "remember", "rember": "remember",
    "tommorow": "tomorrow", "tomorow": "tomorrow", "tomarrow": "tomorrow",
    "goverment": "government", "govrenment": "government",
    "occured": "occurred", "occuring": "occurring", "occurrance": "occurrence",
    "probly": "probably", "probaly": "probably", "problaly": "probably",
    "actaully": "actually", "actuly": "actually", "acutally": "actually", "actualy": "actually",
    "realy": "really", "relaly": "really", "reallly": "really",
    "truely": "truly", "basicly": "basically", "absolutly": "absolutely",
    "compleatly": "completely",
    "neccessary": "necessary", "necesary": "necessary",
    "suprise": "surprise", "suprised": "surprised",
    "concious": "conscious", "curiousity": "curiosity",
    "dissapear": "disappear", "dissappoint": "disappoint",
    "embarass": "embarrass", "enviroment": "environment",
    "guarentee": "guarantee", "happend": "happened",
    "intrest": "interest", "intresting": "interesting",
    "noticable": "noticeable", "privilege": "privilege",
    "pronounciation": "pronunciation", "publically": "publicly",
    "yesturday": "yesterday", "yesterdy": "yesterday",
    "minits": "minutes", "minit": "minute",
    "finnaly": "finally", "fianlly": "finally",
    "emberassing": "embarrassing", "emberass": "embarrass", "emberassed": "embarrassed",
    "stomache": "stomach",
    "finded": "found", "runned": "ran", "leaved": "left", "putted": "put",
    "catched": "caught", "bringed": "brought", "teached": "taught",
    "sleeped": "slept", "thinked": "thought",
}

_shorthand_file = get_resource_path("shorthand.txt")
if _shorthand_file.exists():
    for line in _shorthand_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            EXPANSIONS[k.strip().lower()] = v.strip()


def expand_word(word):
    m = re.match(r"^([^A-Za-z0-9]*)(.*?)([^A-Za-z0-9]*)$", word)
    if m:
        lead, core, trail = m.group(1), m.group(2), m.group(3)
        core_lower = core.lower()
        core_clean = core_lower.replace("'", "")
        swap = EXPANSIONS.get(core_lower) or EXPANSIONS.get(core_clean)
        if swap and not looks_like_code(core):
            if core[:1].isupper() and not swap.startswith("I"):
                swap = swap[0].upper() + swap[1:]
            return lead + swap + trail
    return word


def expand(text):
    """Rewrite known shorthand and common phrase mistakes, preserving casing, punctuation, and layout."""
    # High-confidence phrase fixes that are structurally always errors in English
    phrases = [
        (r"\byour welcome\b", "you're welcome"),
        (r"\bYour welcome\b", "You're welcome"),
        (r"\btobehonest\b", "to be honest"),
        (r"\bTobehonest\b", "To be honest"),
        (r"\btobehonst\b", "to be honest"),
        (r"\bTobehonst\b", "To be honest"),
        (r"\bto behonst\b", "to be honest"),
        (r"\bTo behonst\b", "To be honest"),
        (r"\bshould of\b", "should have"),
        (r"\bShould of\b", "Should have"),
        (r"\bcould of\b", "could have"),
        (r"\bCould of\b", "Could have"),
        (r"\bwould of\b", "would have"),
        (r"\bWould of\b", "Would have"),
    ]
    for pattern, repl in phrases:
        text = re.sub(pattern, repl, text)

    return re.sub(r"\S+", lambda m: expand_word(m.group(0)), text)



SHOULD_FIX = [
    "to behonst its kinda really strannge an i don know what s hapenning",
    "helo how are you im fne wht abt you",
    "to be honst its getting really diffcult tomehow how we can make sure that",
    "i will definately calll you tomorow abt the metting",
]

MUST_NOT_TOUCH = [
    "The MT300 SWIFT message failed validation in the PLSQL package.",
    "Update the MT202 handler in the PL/SQL package and rerun the regression suite.",
    "SELECT * FROM accounts WHERE status = 'ACTIVE';",
    "This sentence is perfectly fine already.",
    "Fixelect fixes grammar offline using Harper.",
]


def looks_like_code(word):
    """Identifiers, not English: MT300, ORA-01555, SWIFT, PLSQL, SELECT."""
    letters = [c for c in word if c.isalpha()]
    if not letters:
        return False
    return any(c.isdigit() for c in word) or (
        all(c.isupper() for c in letters) and len(letters) > 1
    )


def normalise(text):
    return "".join(c for c in text.lower() if c.isalnum())


def distance(a, b):
    """Damerau-Levenshtein: edits, where swapping two neighbours counts as one.

    Plain Levenshtein charges 2 for a transposition, because it can only see a
    delete plus an insert. That is wrong for typing, where hitting two keys in
    the wrong order is the single commonest slip there is - and it was actively
    breaking us: "yuor" -> "your" scored 2 edits over 4 letters = 50% similar,
    under the 59.5% bar, so the guard refused it. Every transposed typo in the
    language was unfixable by construction. Counting the swap as one edit puts
    the same pair at 75%.
    """
    a, b = normalise(a), normalise(b)
    if not a or not b:
        return max(len(a), len(b))

    # Three rows, because a transposition looks two back on both strings.
    before = None
    prev = list(range(len(b) + 1))

    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(
                prev[j] + 1,                        # delete
                cur[j - 1] + 1,                     # insert
                prev[j - 1] + (ca != cb),           # substitute
            )
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], before[j - 2] + 1)   # transpose
        before, prev = prev, cur
    return prev[len(b)]


def similarity(a, b):
    longest = max(len(normalise(a)), len(normalise(b)))
    return 1.0 if longest == 0 else 1 - distance(a, b) / longest


# The apostrophe forms are protected too, or the model simply undoes the
# expansion: "I'm" -> "I am" scores 67% similar and would sail through. Stored
# normalised ("im"), which still lets "im" -> "I'm" past, since that is an
# apostrophe-only change.
DICTIONARY.update(normalise(v) for v in EXPANSIONS.values())


# Recognised English homophone and grammar confusions (bidirectional).
# When both words are in the dictionary (e.g. your vs you're, too vs to),
# the normal dictionary rule would otherwise block the fix.
COMMON_GRAMMAR_PAIRS = {
    ("your", "you're"), ("you're", "your"),
    ("their", "there"), ("there", "their"),
    ("their", "they're"), ("they're", "their"),
    ("there", "they're"), ("they're", "there"),
    ("to", "too"), ("too", "to"),
    ("then", "than"), ("than", "then"),
    ("its", "it's"), ("it's", "its"),
    ("loose", "lose"), ("lose", "loose"),
    ("affect", "effect"), ("effect", "affect"),
    ("who's", "whose"), ("whose", "who's"),
    ("passed", "past"), ("past", "passed"),
    ("accept", "except"), ("except", "accept"),
    ("lead", "led"), ("led", "lead"),
    ("weather", "whether"), ("whether", "weather"),
    ("were", "we're"), ("we're", "were"),
    ("of", "have"),  # should of -> should have, could of -> could have
    ("finded", "found"), ("found", "finded"),
    ("runned", "ran"), ("ran", "runned"),
    ("leaved", "left"), ("left", "leaved"),
    ("putted", "put"), ("put", "putted"),
    ("tiered", "tired"), ("tired", "tiered"),
}


def is_grammar_swap(mine_str, theirs_str):
    m = mine_str.lower().strip()
    t = theirs_str.lower().strip()
    return (m, t) in COMMON_GRAMMAR_PAIRS


def acceptable(mine, theirs, short_words=True):
    """Is turning `mine` into `theirs` a correction rather than a rewrite?

    `short_words` enables the one-edit allowance for words under five letters.
    Callers that pair words up loosely (salvage) turn it off - see below.
    """
    if any(looks_like_code(w) or w.lower().strip(".,;:!?\"'()[]{}") in PROTECTED_WORDS for w in mine):
        return False

    ours, given = " ".join(mine), " ".join(theirs)

    # Recognized English homophone/grammar confusion (e.g. your -> you're, too -> to)
    if is_grammar_swap(ours, given):
        return True

    # If you already wrote a real English word, the model does not get to
    # replace it. This is the single biggest source of damage: the model
    # re-inflects correct words - "session" -> "sessions", "clearly" ->
    # "clear", "complained" -> "complains" - and each one scores as a plausible
    # small edit. It also blocks "fall" -> "call", where the typo happened to
    # land on a real word and no tool can know what you meant.
    #
    # Apostrophes and capitals are still allowed through, because "its" ->
    # "it's" and "dont" -> "don't" are corrections, not replacements.
    if all(normalise(w) in DICTIONARY for w in mine if normalise(w)):
        if normalise(ours) != normalise(given):
            return False

    # Punctuation check: only reject if actual punctuation marks were deleted.
    # Removing whitespace around punctuation ("hello ," -> "hello,") is a valid fix!
    punct_ours = sum(1 for c in ours if not c.isalnum() and not c.isspace())
    punct_given = sum(1 for c in given if not c.isalnum() and not c.isspace())
    if normalise(ours) == normalise(given) and punct_given < punct_ours:
        return False

    if similarity(ours, given) >= MIN_SIMILARITY:
        return True

    # A percentage bar is unfair to short words. One wrong letter in a two-letter
    # word is 50% of it, so "uo" -> "up" could never pass however obvious it was
    # - the shorter the word, the stricter the guard got, which is backwards.
    # Below five letters, judge by edits instead: one edit is a typo.
    return short_words and len(normalise(ours)) <= 4 and distance(ours, given) <= 1


def salvage(mine, theirs, base):
    """Rescue individual word fixes buried inside a rewrite we won't take whole."""
    edits, cursor = [], 0

    for offset, word in enumerate(mine):
        if looks_like_code(word):
            continue

        best = None
        for j in range(cursor, len(theirs)):
            score = similarity(word, theirs[j])
            if best is None or score > best[0]:
                best = (score, j)

        if best and theirs[best[1]] != word and acceptable(
            [word], [theirs[best[1]]], short_words=False
        ):
            edits.append((base + offset, base + offset + 1, (theirs[best[1]],)))
            cursor = best[1] + 1

    return edits


def proposed_edits(original, rewritten):
    """Edits this rewrite wants that survive the guard, as (start, end, words)."""
    src, dst = original.split(), rewritten.split()
    edits = []

    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(a=src, b=dst).get_opcodes():
        mine, theirs = src[i1:i2], dst[j1:j2]

        if tag == "delete":
            # Check for duplicate repeated word deletion: "the the" -> "the"
            if len(mine) == 1:
                del_word = normalise(mine[0])
                prev_word = normalise(src[i1 - 1]) if i1 > 0 else ""
                next_word = normalise(src[i2]) if i2 < len(src) else ""
                if del_word and (del_word == prev_word or del_word == next_word):
                    edits.append((i1, i2, ()))
            continue

        if tag != "replace":
            continue

        if len(mine) == len(theirs):
            # Same word count - judge each alone, so one bad guess can't drag
            # its neighbours down with it.
            for k, (a, b) in enumerate(zip(mine, theirs)):
                if a != b and acceptable([a], [b]):
                    edits.append((i1 + k, i1 + k + 1, (b,)))
        elif len(mine) == len(theirs) + 1 and len(mine) >= 2:
            # Check for duplicate word deletion combined with a word edit/punctuation
            # E.g. mine = ['the', 'task'], theirs = ['task.'] where src[i1 - 1] == 'the'
            if i1 > 0 and normalise(mine[0]) == normalise(src[i1 - 1]) and acceptable(mine[1:], theirs):
                edits.append((i1, i1 + 1, ()))
                for k, (a, b) in enumerate(zip(mine[1:], theirs)):
                    if a != b and acceptable([a], [b]):
                        edits.append((i1 + 1 + k, i1 + 1 + k + 1, (b,)))
            elif i2 < len(src) and normalise(mine[-1]) == normalise(src[i2]) and acceptable(mine[:-1], theirs):
                edits.append((i2 - 1, i2, ()))
                for k, (a, b) in enumerate(zip(mine[:-1], theirs)):
                    if a != b and acceptable([a], [b]):
                        edits.append((i1 + k, i1 + k + 1, (b,)))
            elif max(len(mine), len(theirs)) <= MAX_GROUP and acceptable(mine, theirs):
                edits.append((i1, i2, tuple(theirs)))
            else:
                edits.extend(salvage(mine, theirs, i1))
        elif max(len(mine), len(theirs)) <= MAX_GROUP and acceptable(mine, theirs):
            # A small, believable merge or split: "kinda" -> "kind of".
            edits.append((i1, i2, tuple(theirs)))
        else:
            # Too big to take whole, but there may be real fixes inside it.
            edits.extend(salvage(mine, theirs, i1))

    return edits


def consensus(original, rewrites):
    """Apply only the edits that MIN_VOTES rewrites independently agree on."""
    votes = Counter()
    for rewrite in rewrites:
        for edit in set(proposed_edits(original, rewrite)):
            votes[edit] += 1

    src = original.split()

    strong_votes, close_votes = vote_thresholds(len(rewrites))

    def convincing(count, edit):
        if count >= strong_votes:
            return True
        start, end, words = edit
        if not words:
            return count >= close_votes
        return count >= close_votes and similarity(
            " ".join(src[start:end]), " ".join(words)
        ) >= CLOSE_SIMILARITY

    # Most-agreed first, so a popular edit beats an overlapping rare one.
    ranked = sorted(
        ((count, edit) for edit, count in votes.items() if convincing(count, edit)),
        key=lambda pair: (-pair[0], pair[1][0]),
    )

    applied, claimed = [], set()
    for count, (start, end, words) in ranked:
        span = set(range(start, end))
        if span & claimed:
            continue
        claimed |= span
        applied.append((start, end, words, count))
    applied.sort()

    out, cursor = [], 0
    for start, end, words, _ in applied:
        out.extend(src[cursor:start])
        out.extend(words)
        cursor = end
    out.extend(src[cursor:])

    outvoted = [(e, c) for e, c in votes.items() if not convincing(c, e)]
    return " ".join(out), applied, outvoted


def clean(reply, preserve_newlines=False):
    """Strip the scaffolding a chat model puts around its answer.

    Small models say "Sure! Here is the corrected text:" and wrap the result in
    quotes. None of that is a correction, and left in place it would look like
    a huge insertion to the guard, which would then refuse the whole sentence.
    """
    text = reply.strip()

    # Reasoning models emit a thinking block first; the answer is what follows.
    for marker in ("</think>", "</thinking>"):
        if marker in text:
            text = text.split(marker)[-1].strip()

    # The model imitating our own prompt back at us.
    for tag in ("<text>", "<draft>"):
        text = text.split(tag)[0]
    text = text.replace("</text>", "").replace("</draft>", "")

    for label in ("Corrected:", "corrected:", "Output:", "Polished:", "polished:"):
        if text.startswith(label):
            text = text[len(label):].strip()

    # Drop a leading "Here is the corrected text:" style line.
    lines = text.splitlines()
    if len(lines) > 1 and lines[0].strip().endswith(":"):
        first_line = lines[0].strip().lower()
        if any(w in first_line for w in ("here", "corrected", "polished", "revised", "version")):
            lines = lines[1:]

    if preserve_newlines:
        text = "\n".join(lines).strip()
    else:
        non_empty = [l.strip() for l in lines if l.strip()]
        text = " ".join(non_empty)

    return text.strip().strip('"').strip("'").strip()


def check_ollama_available():
    """Quick check whether local Ollama daemon is reachable on port 11434."""
    s = socket.socket()
    s.settimeout(0.3)
    try:
        ok = s.connect_ex(("127.0.0.1", 11434)) == 0
    except Exception:
        ok = False
    finally:
        s.close()
    return ok


def polish_guard(original, candidate):
    """Guard for Professional Mode:
    - Protects all code tokens, identifiers, acronyms, and numbers.
    - Rejects empty output or unreasonable length drift.
    """
    if not candidate or not candidate.strip():
        return original

    orig_words = original.split()
    cand_words = candidate.split()

    # Reject extreme length explosions or collapses
    if len(cand_words) > max(20, len(orig_words) * 3) or len(cand_words) < max(1, len(orig_words) // 3):
        return original

    # Ensure all code-like identifiers (MT300, SWIFT, SQL) and protected words are strictly preserved
    for w in orig_words:
        clean_w = w.strip(".,;:!?\"'()[]{}")
        if looks_like_code(clean_w) and clean_w not in candidate:
            return original
        if clean_w.lower() in PROTECTED_WORDS and clean_w.lower() not in candidate.lower():
            return original

    return candidate


def ollama_rewrites(repo, text, candidates, mode="fix"):
    """Ask a local Ollama model for corrections of `text`.

    mode="fix": Strict fast proofreading (keeps author's exact voice, 0% paraphrase).
    mode="polish": Executive professional rewriting (improves flow, tone, and syntax).
    """
    sys_prompt = PROFESSIONAL_INSTRUCTION if mode == "polish" else SYSTEM_INSTRUCTION
    word_count = len(text.split())
    # Generation budget scales with input length (generous headroom for detail preservation)
    budget = min(2048, max(64, int(word_count * 1.8 + 64)))
    # STATIC 2048 context window: Prevents Ollama from unloading/reloading KV cache in VRAM (saves ~3.7s per request)
    context_tokens = 2048
    out = []

    actual_candidates = 1 if mode == "polish" else candidates

    for index in range(actual_candidates):
        temp = 0.15 if mode == "polish" else (0.0 if index == 0 else 0.2)
        chat_payload = {
            "model": repo,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": text},
            ],
            "stream": False,
            "keep_alive": -1,
            "options": {
                "num_ctx": context_tokens,
                "temperature": temp,
                "seed": index,
                "num_predict": budget,
                "top_k": 20,
                "top_p": 0.9,
            },
        }
        res_data = post_json_ollama("/api/chat", chat_payload)
        if res_data:
            content = res_data.get("message", {}).get("content", "")
            cleaned = clean(content, preserve_newlines=(mode == "polish"))
            if cleaned:
                out.append(cleaned)
        else:
            # Fallback to /api/generate if /api/chat fails
            prompt_fmt = f"{sys_prompt}\n\nText to process:\n{text}\n\nOutput:" if mode == "polish" else INSTRUCTION.format(text=text)
            gen_payload = {
                "model": repo,
                "prompt": prompt_fmt,
                "stream": False,
                "keep_alive": -1,
                "options": {
                    "num_ctx": context_tokens,
                    "temperature": temp,
                    "seed": index,
                    "num_predict": budget,
                    "top_k": 20,
                    "top_p": 0.9,
                    "stop": ["<text>", "</text>", "<draft>", "</draft>", "Corrected:", "Output:", "Polished:"],
                },
            }
            res_gen = post_json_ollama("/api/generate", gen_payload)
            if res_gen:
                cleaned = clean(res_gen.get("response", ""), preserve_newlines=(mode == "polish"))
                if cleaned:
                    out.append(cleaned)

        if mode == "polish":
            break

        # Fast path: If greedy candidate 0 matches or proposes straightforward fixes,
        # return immediately without paying latency for redundant candidates.
        if index == 0 and candidates > 1 and out:
            edits = proposed_edits(text, out[0])
            if not edits or all(
                similarity(" ".join(text.split()[s:e]), " ".join(words)) >= 0.7
                for s, e, words in edits
            ):
                break

    return out


def embedded_rewrites(engine, text, candidates=1, mode="fix"):
    """Ask embedded llama-server for corrections of `text`."""
    sys_prompt = PROFESSIONAL_INSTRUCTION if mode == "polish" else SYSTEM_INSTRUCTION
    word_count = len(text.split())
    budget = min(2048, max(64, int(word_count * 1.8 + 64)))
    out = []

    for index in range(candidates):
        temp = 0.15 if mode == "polish" else 0.0
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": text},
        ]
        content = engine.chat_completion(
            messages=messages,
            temperature=temp,
            max_tokens=budget,
            top_k=20,
            top_p=0.9,
        )
        if content:
            cleaned = clean(content, preserve_newlines=(mode == "polish"))
            if cleaned:
                out.append(cleaned)
        if mode == "polish":
            break

    return out


def load_pipeline(model_key="qwen2.5", fast=True, beams=BEAMS, engine_type="embedded"):
    """Build a `fix(text, mode='fix') -> (corrected, applied_edits, expanded)` callable.

    engine_type:
      - 'embedded': Native embedded llama-server on 127.0.0.1:18888 (Phase 2 default, 100% self-contained)
      - 'ollama': External Ollama daemon on 127.0.0.1:11434 (backward compatibility)
      - 'seq2seq': In-process PyTorch model
    """
    if engine_type == "embedded":
        try:
            try:
                from engine_mac import get_default_engine
            except ImportError:
                from engine import get_default_engine
            try:
                try:
                    from config_mac import load_config
                except ImportError:
                    from config import load_config
                cfg = load_config()
                model_profile = cfg.get("model_profile") or ("1.5b" if "1.5" in model_key else "3b")
            except Exception:
                model_profile = "1.5b" if "1.5" in model_key else "3b"
            eng = get_default_engine(model_profile=model_profile)
            eng.start()

            def fix_embedded(text, mode="fix"):
                current_eng = get_default_engine()
                expanded = expand(text)
                if mode == "polish":
                    rewrites = embedded_rewrites(current_eng, expanded, candidates=1, mode="polish")
                    if rewrites:
                        guarded = polish_guard(expanded, rewrites[0])
                        applied = [(0, len(expanded.split()), tuple(guarded.split()), 1)]
                        return guarded, applied, expanded
                    # Fallback to fix mode if polish rewrite was empty
                    rewrites = embedded_rewrites(current_eng, expanded, beams, mode="fix")
                    final, applied, _ = consensus(expanded, rewrites)
                    return final, applied, expanded

                rewrites = embedded_rewrites(current_eng, expanded, beams, mode="fix")
                final, applied, _ = consensus(expanded, rewrites)
                return final, applied, expanded

            fix_embedded("this is a warm up sentence")
            return fix_embedded
        except Exception as e:
            print(f"  [EmbeddedEngine] Notice: {e}. Falling back to Ollama...")
            engine_type = "ollama"

    spec_kind = MODELS[model_key]["kind"]

    if engine_type == "ollama" or spec_kind == "ollama":
        if not check_ollama_available():
            print(f"  (Ollama not responding on port 11434; falling back to local 'base' model)")
            model_key = "base"
            spec_kind = "seq2seq"
        else:
            repo = MODELS[model_key]["repo"]

            def fix(text, mode="fix"):
                expanded = expand(text)
                if mode == "polish":
                    rewrites = ollama_rewrites(repo, expanded, candidates=1, mode="polish")
                    if rewrites:
                        guarded = polish_guard(expanded, rewrites[0])
                        applied = [(0, len(expanded.split()), tuple(guarded.split()), 1)]
                        return guarded, applied, expanded
                    # Fallback to fix mode if polish rewrite was empty
                    rewrites = ollama_rewrites(repo, expanded, beams, mode="fix")
                    final, applied, _ = consensus(expanded, rewrites)
                    return final, applied, expanded

                rewrites = ollama_rewrites(repo, expanded, beams, mode="fix")
                final, applied, _ = consensus(expanded, rewrites)
                return final, applied, expanded

            fix("this is a warm up sentence")
            return fix

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    # One thread per physical core. The default oversubscribes on laptops with
    # hyperthreading and the threads end up fighting over cache.
    torch.set_num_threads(max(1, (torch.get_num_threads() or 4) // 2))

    spec = MODELS[model_key]
    repo, kind = spec["repo"], spec["kind"]
    prefix = spec.get("prefix")

    tok = AutoTokenizer.from_pretrained(repo)
    if kind == "seq2seq":
        model = AutoModelForSeq2SeqLM.from_pretrained(repo).eval()
    else:
        from transformers import AutoModelForCausalLM

        model = AutoModelForCausalLM.from_pretrained(repo).eval()

    if fast:
        try:
            model = torch.ao.quantization.quantize_dynamic(
                model, {torch.nn.Linear}, dtype=torch.qint8
            )
        except Exception as e:
            print(f"  (int8 unavailable, staying float32: {e})")

    @torch.inference_mode()
    def fix(text, mode="fix"):
        expanded = expand(text)

        if kind == "seq2seq":
            prompt = f"{prefix}{expanded}" if prefix else expanded
            ids = tok(prompt, return_tensors="pt", truncation=True, max_length=512)
        else:
            chat = [{"role": "user", "content": INSTRUCTION.format(text=expanded)}]
            prompt = tok.apply_chat_template(
                chat, tokenize=False, add_generation_prompt=True
            )
            ids = tok(prompt, return_tensors="pt", truncation=True, max_length=1024)

        prompt_length = ids.input_ids.shape[1]
        budget = min(256, int(prompt_length * 1.4) + 12)

        out = model.generate(
            **ids,
            max_new_tokens=budget,
            num_beams=beams,
            num_return_sequences=beams,
            do_sample=False,
            pad_token_id=tok.pad_token_id or tok.eos_token_id,
        )

        if kind == "seq2seq":
            rewrites = [tok.decode(s, skip_special_tokens=True) for s in out]
        else:
            # A causal model echoes the prompt, so only the new tokens matter.
            rewrites = [
                clean(tok.decode(s[prompt_length:], skip_special_tokens=True))
                for s in out
            ]

        final, applied, _ = consensus(expanded, rewrites)
        return final, applied, expanded

    # The first call is always slow: lazy kernel setup, allocator warm-up,
    # quantised operator selection. Pay it now rather than on the user's first
    # hotkey press.
    fix("this is a warm up sentence")

    return fix


def main():
    try:
        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
    except ImportError as e:
        sys.exit(f"Missing deps ({e}). Run:\n  pip install torch transformers sentencepiece")

    key = next((a for a in sys.argv[1:] if a in MODELS), "base")
    print(f"loading {MODELS[key]['repo']} ...")
    pipeline = load_pipeline(key, fast=False, beams=BEAMS)
    print(f"ready - {BEAMS} candidates, {vote_thresholds(BEAMS)[0]} votes needed\n")

    print("=" * 78)
    print("SHOULD FIX")
    print("=" * 78)
    for text in SHOULD_FIX:
        started = time.time()
        final, applied, expanded = pipeline(text)
        print(f"  yours  : {text}")
        print(f"  RESULT : {final}")
        for start, end, rep, count in applied:
            print(f"           + {' '.join(expanded.split()[start:end])!r} -> "
                  f"{' '.join(rep)!r} ({count}/{BEAMS})")
        print(f"           [{(time.time() - started) * 1000:.0f}ms]\n")

    print("=" * 78)
    print("MUST NOT TOUCH")
    print("=" * 78)
    kept = 0
    for text in MUST_NOT_TOUCH:
        final, applied, _ = pipeline(text)
        same = " ".join(final.split()) == " ".join(text.split())
        kept += same
        print(f"  [{'OK   ' if same else 'BROKE'}] {text}")
        if not same:
            print(f"           got: {final}")

    print(f"\n  survived intact: {kept}/{len(MUST_NOT_TOUCH)}")
    print("\nPaste this whole output back into the chat.")


if __name__ == "__main__":
    main()
