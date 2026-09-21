"""
Update check against the public GitHub releases of Fixelect.

One anonymous HTTPS request to api.github.com at most once a day (and only
when "Check for updates" is on). No identifiers, no text, no telemetry. On
Windows the new installer can be downloaded, checked against the SHA-256
published with the release, and run; on macOS the release page is opened.
"""

import hashlib
import json
import pathlib
import re
import time
import urllib.request

import net
from version import APP_VERSION, RELEASES_API, RELEASES_URL

CHECK_INTERVAL = 20 * 3600


def parse_version(tag):
    nums = [int(n) for n in re.findall(r"\d+", tag or "")[:3]]
    return tuple(nums + [0] * (3 - len(nums)))


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": f"Fixelect/{APP_VERSION}",
                                               "Accept": "application/vnd.github+json"})
    return net.urlopen(req, timeout=timeout)


def check(timeout=10):
    """Newer release info {version, url, notes, assets} or None if up to date.
    Raises on network errors (callers decide whether to show them)."""
    with _get(RELEASES_API, timeout) as resp:
        data = json.load(resp)
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or ""
    if parse_version(tag) <= parse_version(APP_VERSION):
        return None
    return {
        "version": tag.lstrip("vV"),
        "url": data.get("html_url") or RELEASES_URL,
        "notes": (data.get("body") or "").strip()[:800],
        "assets": {a.get("name"): a.get("browser_download_url") for a in data.get("assets") or []},
    }


def due(cfg, now=None):
    now = time.time() if now is None else now
    return bool(cfg.get("check_updates", True)) and now - float(cfg.get("last_update_check", 0) or 0) > CHECK_INTERVAL


def download_asset(info, name, dest_dir, progress=None, cancel=None):
    """Download a release asset, verifying it against `<name>.sha256` when the
    release publishes one. Returns the local path."""
    url = (info.get("assets") or {}).get(name)
    if not url:
        raise RuntimeError(f"This release has no {name}. Download it from the release page.")
    expected = None
    sha_url = info["assets"].get(name + ".sha256")
    if sha_url:
        with _get(sha_url) as resp:
            expected = resp.read().decode("ascii", "ignore").split()[0].lower()
    dest = pathlib.Path(dest_dir) / name
    part = dest.with_suffix(dest.suffix + ".part")
    digest = hashlib.sha256()
    try:
        with _get(url, timeout=30) as resp, open(part, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if cancel is not None and cancel.is_set():
                    raise RuntimeError("Update download cancelled.")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    except BaseException:
        part.unlink(missing_ok=True)  # a half-downloaded installer must never be run
        raise
    if total and done < total:
        part.unlink(missing_ok=True)
        raise RuntimeError("The update download was interrupted. Try again.")
    if expected and digest.hexdigest() != expected:
        part.unlink(missing_ok=True)
        raise RuntimeError("The downloaded update failed its integrity check. Try again later.")
    part.replace(dest)
    return dest
