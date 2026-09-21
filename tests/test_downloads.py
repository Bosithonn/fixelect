"""Model-free tests for the code that changes files on the user's disk: model
downloads (resume, cancel, checksum), the self-updater and History.
No network: every server response is faked. Run: python tests/test_downloads.py"""

import hashlib
import io
import pathlib
import sys
import tempfile
import threading
import urllib.error

sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / ("MacOS" if sys.platform == "darwin" else "Windows") / "tools"))
sys.path.insert(0, str(ROOT / "shared"))

import history  # noqa: E402
import modelfetch  # noqa: E402
import net  # noqa: E402
import updater  # noqa: E402

modelfetch.MIN_MODEL_BYTES = 1000   # tests use small files
modelfetch.CHUNK = 4096
BLOB = bytes(range(256)) * 400      # 102,400 bytes
SHA = hashlib.sha256(BLOB).hexdigest()


class FakeResponse(io.BytesIO):
    def __init__(self, data, status=200, length=True, fail_after=None):
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Length": str(len(data))} if length else {}
        self._fail_after = fail_after

    def read(self, n=-1):
        if self._fail_after is not None and self.tell() >= self._fail_after:
            raise ConnectionResetError("connection reset")
        return super().read(n)

    def __exit__(self, *a):
        self.close()
        return False


class FakeServer:
    """Serves BLOB, honouring Range unless told not to. Records the requests."""

    def __init__(self, data=BLOB, honour_range=True, fail_after=None, refuse=None):
        self.data, self.honour_range, self.fail_after, self.refuse = data, honour_range, fail_after, refuse
        self.requests = []

    def __call__(self, req, timeout=None):
        rng = req.headers.get("Range") or req.headers.get("range")
        self.requests.append(rng)
        if self.refuse:
            code, self.refuse = self.refuse[0], self.refuse[1:]
            raise urllib.error.HTTPError(req.full_url, code, "no", {}, None)
        if rng and self.honour_range:
            start = int(rng.split("=")[1].rstrip("-"))
            return FakeResponse(self.data[start:], status=206, fail_after=self.fail_after)
        fail, self.fail_after = self.fail_after, None
        return FakeResponse(self.data, fail_after=fail)


def spec(sha=SHA):
    return {"url": "https://example.invalid/model.gguf", "filename": "model.gguf", "sha256": sha,
            "size_bytes": len(BLOB), "badge_size": "100 KB"}


def with_server(server, fn):
    old = net.urlopen
    net.urlopen = server
    try:
        with tempfile.TemporaryDirectory() as d:
            return fn(pathlib.Path(d))
    finally:
        net.urlopen = old


def expect_error(fn, *types):
    try:
        fn()
    except types as e:
        return type(e).__name__ + ": " + str(e)
    return None


# -- model downloads ------------------------------------------------------------

def t_download_ok():
    def run(d):
        seen = []
        path = modelfetch.fetch(spec(), d, progress_callback=lambda a, b, c: seen.append((a, b)))
        return path.read_bytes() == BLOB and not (d / "model.gguf.part").exists() and seen[-1] == (len(BLOB),) * 2
    return with_server(FakeServer(), run)


def t_checksum_mismatch_removed():
    def run(d):
        err = expect_error(lambda: modelfetch.fetch(spec("0" * 64), d), RuntimeError)
        return "checksum" in (err or "") and not any(d.iterdir())
    return with_server(FakeServer(), run)


def t_interrupted_then_resumed():
    server = FakeServer(fail_after=40000)

    def run(d):
        err = expect_error(lambda: modelfetch.fetch(spec(), d), RuntimeError)
        part = d / "model.gguf.part"
        kept = part.is_file() and 0 < part.stat().st_size < len(BLOB)
        path = modelfetch.fetch(spec(), d)
        return bool(err) and kept and path.read_bytes() == BLOB and server.requests[-1].startswith("bytes=")
    return with_server(server, run)


def t_server_ignores_range():
    """A 200 to a Range request must restart the file, never append to it."""
    def run(d):
        (d / "model.gguf.part").write_bytes(BLOB[:5000])
        return modelfetch.fetch(spec(), d).read_bytes() == BLOB
    return with_server(FakeServer(honour_range=False), run)


def t_stale_partial_416():
    server = FakeServer(refuse=[416])

    def run(d):
        (d / "model.gguf.part").write_bytes(b"x" * 5000)
        return modelfetch.fetch(spec(), d).read_bytes() == BLOB and server.requests == ["bytes=5000-", None]
    return with_server(server, run)


def t_cancel_keeps_progress():
    cancel = threading.Event()

    def progress(done, total, speed):
        cancel.set()

    def run(d):
        modelfetch.CHUNK, old = 1024, modelfetch.CHUNK
        try:
            err = expect_error(lambda: modelfetch.fetch(spec(), d, progress, cancel), modelfetch.DownloadCancelled)
        finally:
            modelfetch.CHUNK = old
        return bool(err) and not (d / "model.gguf").exists() and (d / "model.gguf.part").is_file()
    return with_server(FakeServer(), run)


def t_http_error_friendly():
    def run(d):
        return expect_error(lambda: modelfetch.fetch(spec(), d), RuntimeError)
    got = with_server(FakeServer(refuse=[503]), run) or ""
    return "HTTP 503" in got


def t_tiny_error_page_rejected():
    def run(d):
        err = expect_error(lambda: modelfetch.fetch(dict(spec(), sha256=""), d), RuntimeError)
        return "invalid" in (err or "") and not any(d.iterdir())
    return with_server(FakeServer(data=b"<html>Not found</html>"), run)


# -- updater --------------------------------------------------------------------

class FakeGet:
    def __init__(self, routes):
        self.routes = routes

    def __call__(self, url, timeout=10):
        data = self.routes[url]
        if isinstance(data, Exception):
            raise data
        return FakeResponse(data if isinstance(data, bytes) else data.encode())


def with_get(routes, fn):
    old = updater._get
    updater._get = FakeGet(routes)
    try:
        return fn()
    finally:
        updater._get = old


def release(tag, **extra):
    import json
    return json.dumps(dict({"tag_name": tag, "html_url": "https://github.com/x/releases/tag/" + tag,
                            "body": "notes", "assets": [
                                {"name": "FixelectSetup.exe", "browser_download_url": "https://dl/exe"},
                                {"name": "FixelectSetup.exe.sha256", "browser_download_url": "https://dl/sha"}]},
                           **extra))


def t_update_newer():
    info = with_get({updater.RELEASES_API: release("v99.0.0")}, updater.check)
    return info["version"] == "99.0.0" and "FixelectSetup.exe" in info["assets"]


def t_update_same_or_older():
    same = with_get({updater.RELEASES_API: release("v" + updater.APP_VERSION)}, updater.check)
    older = with_get({updater.RELEASES_API: release("v0.9.0")}, updater.check)
    return same is None and older is None


def t_update_prerelease_ignored():
    return with_get({updater.RELEASES_API: release("v99.0.0", prerelease=True)}, updater.check) is None


def t_version_parse():
    return (updater.parse_version("v1.2.10") > updater.parse_version("1.2.9")
            and updater.parse_version("1.3") == (1, 3, 0))


def t_update_verified_download():
    def run():
        with tempfile.TemporaryDirectory() as d:
            info = {"assets": {"FixelectSetup.exe": "https://dl/exe", "FixelectSetup.exe.sha256": "https://dl/sha"}}
            path = updater.download_asset(info, "FixelectSetup.exe", d)
            return path.read_bytes() == BLOB
    return with_get({"https://dl/exe": BLOB, "https://dl/sha": SHA + "  FixelectSetup.exe\n"}, run)


def t_update_bad_checksum_leaves_nothing():
    def run():
        with tempfile.TemporaryDirectory() as d:
            info = {"assets": {"FixelectSetup.exe": "https://dl/exe", "FixelectSetup.exe.sha256": "https://dl/sha"}}
            err = expect_error(lambda: updater.download_asset(info, "FixelectSetup.exe", d), RuntimeError)
            return "integrity" in (err or "") and not any(pathlib.Path(d).iterdir())
    return with_get({"https://dl/exe": BLOB, "https://dl/sha": "0" * 64}, run)


def t_update_cancel_leaves_nothing():
    def run():
        with tempfile.TemporaryDirectory() as d:
            info = {"assets": {"FixelectSetup.exe": "https://dl/exe"}}
            cancel = threading.Event()
            cancel.set()
            err = expect_error(lambda: updater.download_asset(info, "FixelectSetup.exe", d, cancel=cancel),
                               RuntimeError)
            return "cancelled" in (err or "") and not any(pathlib.Path(d).iterdir())
    return with_get({"https://dl/exe": BLOB}, run)


def t_update_due():
    return (updater.due({"check_updates": True, "last_update_check": 0}, now=10 ** 6)
            and not updater.due({"check_updates": False, "last_update_check": 0}, now=10 ** 6)
            and not updater.due({"check_updates": True, "last_update_check": 10 ** 6 - 60}, now=10 ** 6))


# -- history --------------------------------------------------------------------

def t_history_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        history.add(d, "fix", "Notepad", "teh cat", "the cat", now=100)
        history.add(d, "polish", "Slack", "hey u", "Hey, you", now=200)
        items = history.load(d)
        return [e["app"] for e in items] == ["Slack", "Notepad"] and items[1]["before"] == "teh cat"


def t_history_limit_and_unicode():
    with tempfile.TemporaryDirectory() as d:
        for i in range(history.MAX_ENTRIES + 5):
            history.add(d, "fix", "App", f"привет {i}", f"Привет {i}", now=i)
        items = history.load(d)
        return len(items) == history.MAX_ENTRIES and items[0]["before"] == f"привет {history.MAX_ENTRIES + 4}"


def t_history_skips_no_change_and_clears():
    with tempfile.TemporaryDirectory() as d:
        history.add(d, "fix", "App", "same", "same")
        empty = history.load(d) == []
        history.add(d, "fix", "App", "a", "b")
        history.clear(d)
        return empty and history.load(d) == []


def t_history_broken_file():
    with tempfile.TemporaryDirectory() as d:
        (pathlib.Path(d) / "history.json").write_text("{not json", encoding="utf-8")
        ok = history.load(d) == []
        history.add(d, "fix", "App", "a", "b")
        return ok and len(history.load(d)) == 1


def t_history_long_text_shortened():
    with tempfile.TemporaryDirectory() as d:
        history.add(d, "fix", "App", "x" * 10000, "y" * 10000)
        e = history.load(d)[0]
        return len(e["before"]) <= history.MAX_CHARS + 1 and e["after"].endswith("…")


def t_history_when():
    return (history.when(1000, now=1030) == "just now" and history.when(1000, now=1000 + 300) == "5 min ago"
            and history.when(1000, now=1000 + 7200) == "2 h ago" and history.when(1000, now=1000 + 90000) == "yesterday")


CASES = [
    ("download: complete and verified", t_download_ok),
    ("download: checksum mismatch leaves nothing", t_checksum_mismatch_removed),
    ("download: interrupted, then resumed", t_interrupted_then_resumed),
    ("download: server ignoring Range restarts", t_server_ignores_range),
    ("download: stale partial (416) starts over", t_stale_partial_416),
    ("download: cancel keeps progress, no model file", t_cancel_keeps_progress),
    ("download: HTTP error in plain words", t_http_error_friendly),
    ("download: error page instead of a model", t_tiny_error_page_rejected),
    ("update: newer release found", t_update_newer),
    ("update: same or older ignored", t_update_same_or_older),
    ("update: pre-release ignored", t_update_prerelease_ignored),
    ("update: version numbers compare", t_version_parse),
    ("update: installer checked against .sha256", t_update_verified_download),
    ("update: bad checksum leaves no installer", t_update_bad_checksum_leaves_nothing),
    ("update: cancelled download leaves nothing", t_update_cancel_leaves_nothing),
    ("update: checks at most daily, can be off", t_update_due),
    ("history: newest first", t_history_roundtrip),
    ("history: limit, non-English text", t_history_limit_and_unicode),
    ("history: no-op skipped, clear", t_history_skips_no_change_and_clears),
    ("history: broken file recovers", t_history_broken_file),
    ("history: long text shortened", t_history_long_text_shortened),
    ("history: relative times", t_history_when),
]


def main():
    passed = 0
    for name, fn in CASES:
        try:
            ok = fn() is True
        except Exception as e:
            ok = False
            name += f"  ({type(e).__name__}: {e})"
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n{passed}/{len(CASES)} download/update/history tests passed")
    return passed == len(CASES)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
