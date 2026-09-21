"""Fast guard tests (no AI model needed). Run: python tests/test_guard.py

These pin down the rules that decide which of the model's edits reach the
user. They run in CI before every release build.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "Windows" / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import check_guard as G  # noqa: E402

CASES = [
    # Grammar fixes the guard must let through
    ("He go -> goes", lambda: G.consensus("He go to school", ["He goes to school"])[0], "He goes to school"),
    ("they was -> were", lambda: G.consensus("they was late", ["they were late"])[0], "they were late"),
    ("she don't -> doesn't", lambda: G.consensus("she don't know", ["she doesn't know"])[0], "she doesn't know"),
    ("go -> went (irregular)", lambda: G.consensus("Yesterday I go home", ["Yesterday I went home"])[0], "Yesterday I went home"),
    ("comma moved, not doubled", lambda: G.consensus("hello ,how are you", ["hello, how are you"])[0], "hello, how are you"),
    ("the the removed", lambda: G.consensus("the the task", ["the task"])[0], "the task"),
    # Edits the guard must refuse
    ("tense change refused", lambda: G.consensus("the report is ready", ["the report was ready"])[0], "the report is ready"),
    ("correct noun not re-inflected", lambda: G.consensus("the session ended", ["the sessions ended"])[0], "the session ended"),
    ("legit 'that that' kept", lambda: G.consensus("I think that that is right", ["I think that is right"])[0], "I think that that is right"),
    ("email untouched", lambda: G.consensus("mail john.doe@example.com now", ["mail john.doe@example.com, now"])[0],
     "mail john.doe@example.com now"),
    ("identifier untouched", lambda: G.consensus("the MT300 failed", ["the MT301 failed"])[0], "the MT300 failed"),
    # Common learner mistakes, allowed only in the exact spot they occur
    ("had already left", lambda: G.consensus("the train already left", ["the train had already left"])[0],
     "the train had already left"),
    ("I going -> I am going", lambda: G.consensus("I going home", ["I am going home"])[0], "I am going home"),
    ("terse note untouched", lambda: G.consensus("Report attached", ["Report is attached"])[0], "Report attached"),
    ("terse note keeps its capital", lambda: G.consensus("Meeting tomorrow at 10", ["The meeting is tomorrow at 10"])[0],
     "Meeting tomorrow at 10"),
    ("no 'will' added", lambda: G.consensus("we going soon", ["we will going soon"])[0], "we going soon"),
    ("depend of -> on", lambda: G.consensus("It depends of the weather", ["It depends on the weather"])[0],
     "It depends on the weather"),
    ("'of' kept elsewhere", lambda: G.consensus("a list of items", ["a list on items"])[0], "a list of items"),
    ("discussed about -> discussed", lambda: G.consensus("we discussed about the plan", ["we discussed the plan"])[0],
     "we discussed the plan"),
    ("'about' kept elsewhere", lambda: G.consensus("we talked about the plan", ["we talked the plan"])[0],
     "we talked about the plan"),
    ("excepted. -> accepted.", lambda: G.consensus("the payment is excepted.", ["the payment is accepted."])[0],
     "the payment is accepted."),
    ("confusion fix keeps the full stop", lambda: G.consensus("keep it loose.", ["keep it lose"])[0], "keep it loose."),
    ("I am agree -> I agree", lambda: G.consensus("I am agree with you", ["I agree with you"])[0], "I agree with you"),
    ("'am' kept elsewhere", lambda: G.consensus("I am happy with you", ["I happy with you"])[0], "I am happy with you"),
    ("r u -> are you", lambda: G.expand("r u coming tonite?"), "are you coming tonight?"),
    ("jargon compound kept", lambda: G.consensus("pods keep crashlooping", ["pods keep crashing"])[0],
     "pods keep crashlooping"),
    ("jargon compound may be split", lambda: G.consensus("the healthcheck failed", ["the health check failed"])[0],
     "the health check failed"),
    ("glued typo still fixed", lambda: G.consensus("be more carefull next time", ["be more careful next time"])[0],
     "be more careful next time"),
    # Shorthand must not corrupt real words
    ("'id' stays", lambda: G.expand("enter your user id"), "enter your user id"),
    ("'ill' stays", lambda: G.expand("i feel ill"), "I feel ill"),
    ("'lets' stays", lambda: G.expand("she lets me go"), "she lets me go"),
    # Articles
    ("a apple -> an apple", lambda: G.fix_articles("I ate a apple and an banana"), "I ate an apple and a banana"),
    ("a honest -> an honest", lambda: G.fix_articles("She is a honest person"), "She is an honest person"),
    ("an user -> a user", lambda: G.fix_articles("an user and a university"), "a user and a university"),
    ("letter label untouched", lambda: G.fix_articles("pick option a or b"), "pick option a or b"),
    # Language gate
    ("uzbek skipped", lambda: G.is_probably_english("Salom, qalaysan? Ertaga uchrashamiz."), False),
    ("russian skipped", lambda: G.is_probably_english("Привет, как дела?"), False),
    ("typo-heavy english kept", lambda: G.is_probably_english("helo how r u im fne wht abt u"), True),
    # Polish must keep meaning
    ("polish role flip refused", lambda: G.polish_guard("can you send the report by friday i need it",
                                                         "I need to send the report by Friday."),
     "can you send the report by friday i need it"),
    ("polish answer refused", lambda: G.polish_guard("what time is the meeting tomorrow", "The meeting is at 10 AM."),
     "what time is the meeting tomorrow"),
    ("polish translation refused", lambda: G.polish_guard("translate this to french: the server is down",
                                                           "le serveur est down"),
     "translate this to french: the server is down"),
    ("good polish kept", lambda: G.polish_guard("can you send the report by friday i need it",
                                                 "Could you send the report by Friday? I need it."),
     "Could you send the report by Friday? I need it."),
    ("number as word kept", lambda: G.polish_guard("we lost 3 clients in march and revenue fell",
                                                    "We lost three clients in March, and revenue fell."),
     "We lost three clients in March, and revenue fell."),
    # Layout
    ("trailing space kept", lambda: G.fix_preserving_layout("helo ", lambda t: ("hello", [], t))[0], "hello "),
]


def main():
    failed = 0
    for name, fn, want in CASES:
        got = fn()
        ok = got == want
        failed += not ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n        got:  {got!r}\n        want: {want!r}"))
    print(f"\n{len(CASES) - failed}/{len(CASES)} guard tests passed")
    return failed == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
