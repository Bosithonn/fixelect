"""
Model manager and downloader for Fixelect.
Resolves, discovers, and downloads GGUF models into %LOCALAPPDATA%\\Fixelect\\models\\.
"""

import hashlib
import os
import pathlib
import shutil
import time
import urllib.error
import urllib.request

MODELS = {
    "3b": {
        "name": "Qwen 2.5 3B — High Quality & Nuance",
        "short_name": "Qwen 2.5 3B",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "sha256": "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d",
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_bytes": 2104932768,
        "approx_mb": 2007,
        "badge_size": "2.0 GB",
        "badge_rec": "RECOMMENDED (GPU 4GB+)",
        "desc": "Preserves 100% of your voice, corrects nuanced grammar, sub-second on GPU.",
        "ollama_blob": "sha256-5ee4f07cdb9beadbbb293e85803c569b01bd37ed059d2715faa7bb405f31caa6",
    },
    "1.5b": {
        "name": "Qwen 2.5 1.5B — Fast & Compact",
        "short_name": "Qwen 2.5 1.5B",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_bytes": 1117320736,
        "approx_mb": 1065,
        "badge_size": "1.0 GB",
        "badge_rec": "FAST / LIGHTWEIGHT",
        "desc": "Minimal memory footprint, designed for lightweight laptops and CPU-only use.",
        "ollama_blob": "sha256-183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4",
    },
    "0.5b": {
        "name": "Qwen 2.5 0.5B — Ultra Light & Battery Saver",
        "short_name": "Qwen 2.5 0.5B",
        "filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "sha256": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "size_bytes": 491400032,
        "approx_mb": 468,
        "badge_size": "468 MB",
        "badge_rec": "ULTRA LIGHT (LOW RAM)",
        "desc": "Instant sub-100ms proofreading with near-zero memory footprint. Ideal for battery life.",
        "ollama_blob": "",
    },
    "7b": {
        "name": "Qwen 2.5 7B — Executive Pro & Complex Nuance",
        "short_name": "Qwen 2.5 7B",
        "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "sha256": "65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423",
        "url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "size_bytes": 4683074240,
        "approx_mb": 4466,
        "badge_size": "4.4 GB",
        "badge_rec": "EXECUTIVE PRO (GPU 8GB+)",
        "desc": "Maximum rhetoric mastery and sophisticated restructuring. Requires dedicated GPU.",
        "ollama_blob": "",
    },
    "llama-3b": {
        "name": "Llama 3.2 3B — Conversational Clarity & Flow",
        "short_name": "Llama 3.2 3B",
        "filename": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "sha256": "6c1a2b41161032677be168d354123594c0e6e67d2b9227c84f296ad037c728ff",
        "url": "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
        "size_bytes": 2019377696,
        "approx_mb": 1925,
        "badge_size": "1.9 GB",
        "badge_rec": "NATURAL DIALOGUE / FLOW",
        "desc": "Meta's edge model with superb conversational clarity and natural idiom flow.",
        "ollama_blob": "",
    },
    "deepseek-1.5b": {
        "name": "DeepSeek R1 Distill 1.5B — Precision & Logic",
        "short_name": "DeepSeek R1 1.5B",
        "filename": "DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf",
        "sha256": "1741e5b2d062b07acf048bf0d2c514dadf2a48f94e2b4aa0cfe069af3838ee2f",
        "url": "https://huggingface.co/bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF/resolve/main/DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf",
        "size_bytes": 1117320800,
        "approx_mb": 1065,
        "badge_size": "1.0 GB",
        "badge_rec": "REASONING & LOGIC",
        "desc": "Fine-tuned reasoning for logical clarity, precision phrasing, and technical writing.",
        "ollama_blob": "",
    },
}


def get_models_dir():
    """Return the directory where Fixelect stores GGUF models."""
    override = os.environ.get("FIXELECT_MODELS_DIR")
    if override:
        p = pathlib.Path(override)
    else:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            p = pathlib.Path(local_appdata) / "Fixelect" / "models"
        else:
            p = pathlib.Path.home() / ".fixelect" / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def find_cached_blob(blob_name):
    """Scan standard local directories for pre-existing GGUF blobs to avoid redownloading."""
    if not blob_name:
        return None
    candidates = [
        pathlib.Path.home() / "Downloads" / "Modelfile" / "blobs" / blob_name,
        pathlib.Path.home() / ".ollama" / "models" / "blobs" / blob_name,
        pathlib.Path(os.environ.get("OLLAMA_MODELS", "")) / "blobs" / blob_name,
    ]
    for c in candidates:
        try:
            if c.is_file() and c.stat().st_size > 100 * 1024 * 1024:
                return c
        except Exception:
            pass
    return None


def resolve_model(profile="3b"):
    """
    Find or link the specified model. Returns the absolute path to the GGUF file.
    If not present anywhere, returns None (caller should invoke download_model).
    """
    spec = MODELS.get(profile) or MODELS["3b"]
    target_path = get_models_dir() / spec["filename"]

    # 1. Check if already in Fixelect models directory
    if target_path.is_file() and target_path.stat().st_size > 100 * 1024 * 1024:
        return target_path

    # 2. Check local caches (e.g. existing Ollama cache on machine)
    blob_path = find_cached_blob(spec["ollama_blob"])
    if blob_path:
        print(f"Found local cached model at {blob_path.name} ({blob_path.stat().st_size / (1024*1024):.1f} MB)")
        try:
            # Try creating a hardlink or symlink to save disk space
            os.link(blob_path, target_path)
            print(f"Linked {blob_path.name} -> {target_path}")
            return target_path
        except Exception:
            try:
                target_path.symlink_to(blob_path)
                return target_path
            except Exception:
                # Direct pointer to cached blob
                return blob_path

    return None


class DownloadCancelled(Exception):
    pass


def _friendly_network_error(e):
    text = str(getattr(e, "reason", e))
    if "getaddrinfo" in text or "Name or service" in text or "nodename" in text:
        return "No internet connection. Check your network and try again."
    if "timed out" in text:
        return "The download server stopped responding. Try again."
    if isinstance(e, urllib.error.HTTPError):
        return f"Download server returned HTTP {e.code}. Try again later."
    return f"Download failed: {text}"


def download_model(profile="3b", progress_callback=None, cancel_event=None):
    """
    Download the GGUF model from Hugging Face with progress, resume and verification.

    The file is only moved into place once every byte announced by the server
    has arrived - an interrupted download used to be renamed to the final name,
    after which llama-server failed on the truncated file forever.
    """
    spec = MODELS.get(profile) or MODELS["3b"]
    models_dir = get_models_dir()
    target_path = models_dir / spec["filename"]
    part_path = models_dir / f"{spec['filename']}.part"

    existing = resolve_model(profile)
    if existing:
        return existing

    try:
        free = shutil.disk_usage(models_dir).free
        needed = spec["size_bytes"] - (part_path.stat().st_size if part_path.exists() else 0)
        if free < needed + 200 * 1024 * 1024:
            raise OSError(
                f"Not enough disk space: {spec['badge_size']} needed, "
                f"{free / (1024 ** 3):.1f} GB free on this drive."
            )
    except OSError as e:
        if "disk space" in str(e):
            raise

    initial_bytes = part_path.stat().st_size if part_path.exists() else 0
    headers = {"User-Agent": "Fixelect-Desktop/1.0"}
    if initial_bytes:
        headers["Range"] = f"bytes={initial_bytes}-"

    req = urllib.request.Request(spec["url"], headers=headers)
    chunk_size = 1024 * 1024
    try:
        response = urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as e:
        if e.code == 416 and initial_bytes:  # stale/complete partial: start over
            part_path.unlink(missing_ok=True)
            return download_model(profile, progress_callback, cancel_event)
        raise RuntimeError(_friendly_network_error(e)) from e
    except Exception as e:
        raise RuntimeError(_friendly_network_error(e)) from e

    with response:
        if initial_bytes and response.status != 206:
            initial_bytes = 0  # server ignored Range: appending would corrupt the file
        length = response.headers.get("Content-Length")
        total_bytes = (int(length) + initial_bytes) if length else spec["size_bytes"]

        # Hash while downloading (and the resumed part first), so the checksum
        # costs no extra pass over a multi-GB file.
        digest = hashlib.sha256()
        if initial_bytes:
            with open(part_path, "rb") as f:
                for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                    digest.update(block)

        downloaded = initial_bytes
        started, last_cb = time.time(), 0.0
        try:
            with open(part_path, "ab" if initial_bytes else "wb") as out_f:
                while True:
                    if cancel_event is not None and cancel_event.is_set():
                        raise DownloadCancelled("Download cancelled.")
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    now = time.time()
                    if progress_callback and (now - last_cb >= 0.1):
                        last_cb = now
                        elapsed = max(1e-6, now - started)
                        progress_callback(downloaded, total_bytes, (downloaded - initial_bytes) / elapsed)
        except DownloadCancelled:
            raise
        except Exception as e:
            raise RuntimeError(_friendly_network_error(e) + " Progress was saved; retry to resume.") from e

    if length and downloaded < total_bytes:
        raise RuntimeError("Download was interrupted. Retry to resume where it stopped.")
    if downloaded < 100 * 1024 * 1024:
        part_path.unlink(missing_ok=True)
        raise RuntimeError("The downloaded file is invalid. Please try again.")
    if spec.get("sha256") and digest.hexdigest() != spec["sha256"]:
        part_path.unlink(missing_ok=True)
        raise RuntimeError("The download was corrupted (checksum mismatch). Please try again.")

    os.replace(part_path, target_path)
    if progress_callback:
        progress_callback(total_bytes, total_bytes, 0)
    return target_path


if __name__ == "__main__":
    p = resolve_model("3b")
    if p:
        print(f"Model 3B ready: {p}")
    else:
        print("Model 3B not found locally. To download: python tools/downloader.py --download")
