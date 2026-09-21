"""
Downloading a model file: resume, progress, cancel and SHA-256 check.

Shared by both apps (Windows/tools/downloader.py, MacOS/tools/downloader_mac.py
decide where models live and which one to fetch). The file is only moved into
place once every byte announced by the server has arrived and the checksum
matches - an interrupted download used to be renamed to the final name, after
which llama-server failed on the truncated file forever.
"""

import hashlib
import os
import pathlib
import shutil
import time
import urllib.error
import urllib.request

import net

MIN_MODEL_BYTES = 50 * 1024 * 1024    # anything smaller is an error page, not a model
SPARE_DISK_BYTES = 200 * 1024 * 1024
CHUNK = 1024 * 1024


class DownloadCancelled(Exception):
    pass


def friendly_error(e):
    text = str(getattr(e, "reason", e))
    if "getaddrinfo" in text or "Name or service" in text or "nodename" in text:
        return "No internet connection. Check your network and try again."
    if "timed out" in text:
        return "The download server stopped responding. Try again."
    if isinstance(e, urllib.error.HTTPError):
        return f"Download server returned HTTP {e.code}. Try again later."
    return f"Download failed: {text}"


def fetch(spec, models_dir, progress_callback=None, cancel_event=None, user_agent="Fixelect"):
    """Download spec["url"] to models_dir/spec["filename"]. Returns the path.
    Raises DownloadCancelled, OSError (disk space) or RuntimeError (friendly message)."""
    models_dir = pathlib.Path(models_dir)
    target = models_dir / spec["filename"]
    part = models_dir / f"{spec['filename']}.part"

    for _attempt in range(2):   # a second pass only after a stale partial was thrown away
        start = part.stat().st_size if part.is_file() else 0
        try:
            free = shutil.disk_usage(models_dir).free
        except OSError:
            free = None
        if free is not None and free < spec["size_bytes"] - start + SPARE_DISK_BYTES:
            raise OSError(f"Not enough disk space: {spec['badge_size']} needed, "
                          f"{free / 1024 ** 3:.1f} GB free on this drive.")

        headers = {"User-Agent": user_agent}
        if start:
            headers["Range"] = f"bytes={start}-"
        try:
            response = net.urlopen(urllib.request.Request(spec["url"], headers=headers), timeout=30)
        except urllib.error.HTTPError as e:
            if e.code == 416 and start:   # the partial is stale or already complete: start over
                part.unlink(missing_ok=True)
                continue
            raise RuntimeError(friendly_error(e)) from e
        except Exception as e:
            raise RuntimeError(friendly_error(e)) from e
        return _receive(response, spec, part, target, start, progress_callback, cancel_event)
    raise RuntimeError("The download server keeps rejecting the request. Try again later.")


def _receive(response, spec, part, target, start, progress_callback, cancel_event):
    with response:
        if start and getattr(response, "status", 200) != 206:
            start = 0   # the server ignored Range: appending would corrupt the file
        length = response.headers.get("Content-Length")
        total = (int(length) + start) if length else spec["size_bytes"]

        # Hash while downloading (and the resumed part first), so the checksum
        # costs no extra pass over a multi-GB file.
        digest = hashlib.sha256()
        if start:
            with open(part, "rb") as f:
                for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                    digest.update(block)
        done, t0, last = start, time.time(), 0.0
        try:
            with open(part, "ab" if start else "wb") as out:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled("Download cancelled.")
                    chunk = response.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    now = time.time()
                    if progress_callback and now - last >= 0.1:
                        last = now
                        progress_callback(done, total, (done - start) / max(1e-6, now - t0))
        except DownloadCancelled:
            raise
        except Exception as e:
            raise RuntimeError(friendly_error(e) + " Progress was saved; retry to resume.") from e

    if length and done < total:
        raise RuntimeError("Download was interrupted. Retry to resume where it stopped.")
    if done < MIN_MODEL_BYTES:
        part.unlink(missing_ok=True)
        raise RuntimeError("The downloaded file is invalid. Please try again.")
    if spec.get("sha256") and digest.hexdigest() != spec["sha256"]:
        part.unlink(missing_ok=True)
        raise RuntimeError("The download was corrupted (checksum mismatch). Please try again.")
    os.replace(part, target)
    if progress_callback:
        progress_callback(total, total, 0)
    return target
