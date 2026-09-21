"""
Model manager and downloader for Fixelect.
Resolves, discovers, and downloads GGUF models into %LOCALAPPDATA%\\Fixelect\\models\\.
"""

import os
import pathlib

import modelfetch
from version import APP_VERSION

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
    "gemma4-e2b": {
        "name": "Gemma 4 E2B — Best for other languages",
        "short_name": "Gemma 4 E2B",
        "filename": "gemma-4-E2B-it-Q4_K_M.gguf",
        "sha256": "740185b21d22ceb83a11c3aa62ad5842ef32c70f6096d756bbee85a1e4ec34b8",
        "url": "https://huggingface.co/unsloth/gemma-4-E2B-it-GGUF/resolve/main/gemma-4-E2B-it-Q4_K_M.gguf",
        "size_bytes": 3106738272,
        "approx_mb": 2963,
        "badge_size": "3.1 GB",
        "badge_rec": "MORE LANGUAGES",
        "tag": "More languages",
        "desc": "Google's Gemma 4. Best for Spanish, French, German, Russian and more, plus Uzbek (beta). A little slower.",
        "ollama_blob": "",
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


DownloadCancelled = modelfetch.DownloadCancelled


def download_model(profile="3b", progress_callback=None, cancel_event=None):
    """Download a model once, with resume and a checksum check (see shared/modelfetch.py)."""
    spec = MODELS.get(profile) or MODELS["3b"]
    existing = resolve_model(profile)
    if existing:
        return existing
    return modelfetch.fetch(spec, get_models_dir(), progress_callback, cancel_event,
                            user_agent=f"Fixelect-Windows/{APP_VERSION}")


if __name__ == "__main__":
    p = resolve_model("3b")
    if p:
        print(f"Model 3B ready: {p}")
    else:
        print("Model 3B not found locally. To download: python tools/downloader.py --download")
