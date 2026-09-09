"""
Model manager and downloader for Fixelect.
Resolves, discovers, and downloads GGUF models into %LOCALAPPDATA%\\Fixelect\\models\\.
"""

import os
import pathlib
import shutil
import sys
import time
import urllib.request

MODELS = {
    "3b": {
        "name": "Qwen 2.5 3B — High Quality & Nuance",
        "short_name": "Qwen 2.5 3B",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
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


def download_model(profile="3b", progress_callback=None):
    """
    Download the GGUF model from Hugging Face with progress tracking and resume support.
    """
    spec = MODELS.get(profile) or MODELS["3b"]
    target_path = get_models_dir() / spec["filename"]
    part_path = get_models_dir() / f"{spec['filename']}.part"

    # Quick check if already resolvable
    existing = resolve_model(profile)
    if existing:
        return existing

    url = spec["url"]
    print(f"\nDownloading {spec['filename']} (~{spec['approx_mb']} MB) from Hugging Face...")
    print(f"Destination: {target_path}\n")

    initial_bytes = 0
    headers = {"User-Agent": "Fixelect-Desktop/1.0"}
    if part_path.exists():
        initial_bytes = part_path.stat().st_size
        headers["Range"] = f"bytes={initial_bytes}-"
        print(f"Resuming download from byte {initial_bytes:,}...")

    req = urllib.request.Request(url, headers=headers)
    chunk_size = 1024 * 1024  # 1 MB chunks
    start_time = time.time()
    downloaded = initial_bytes

    mode = "ab" if initial_bytes > 0 else "wb"
    try:
        with urllib.request.urlopen(req, timeout=30) as response, open(part_path, mode) as out_f:
            total_size = response.headers.get("Content-Length")
            if total_size:
                total_bytes = int(total_size) + initial_bytes
            else:
                total_bytes = spec["size_bytes"]

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_f.write(chunk)
                downloaded += len(chunk)

                elapsed = time.time() - start_time
                speed = (downloaded - initial_bytes) / elapsed if elapsed > 0 else 0
                pct = (downloaded / total_bytes * 100) if total_bytes else 0
                eta = (total_bytes - downloaded) / speed if speed > 0 and total_bytes else 0

                bar_len = 30
                filled = int(bar_len * (pct / 100))
                bar = "=" * filled + ">" + " " * max(0, bar_len - filled - 1)

                status = (
                    f"\r[{bar[:bar_len]}] {pct:5.1f}% | "
                    f"{downloaded / (1024*1024):.1f}/{total_bytes / (1024*1024):.1f} MB | "
                    f"{speed / (1024*1024):.1f} MB/s | ETA: {eta:.0f}s"
                )
                sys.stdout.write(status)
                sys.stdout.flush()

                if progress_callback:
                    progress_callback(downloaded, total_bytes, speed)

        # Move part file to final file
        if part_path.exists():
            shutil.move(str(part_path), str(target_path))
        print(f"\nModel successfully saved to: {target_path}\n")
        return target_path
    except Exception as e:
        print(f"\nDownload error: {e}")
        raise


if __name__ == "__main__":
    p = resolve_model("3b")
    if p:
        print(f"Model 3B ready: {p}")
    else:
        print("Model 3B not found locally. To download: python tools/downloader.py --download")
