"""
Model manager and downloader for Fixelect on macOS.
Resolves, discovers, and downloads GGUF models into ~/Library/Application Support/Fixelect/models/.
Also discovers local models in Ollama's macOS storage (~/.ollama/models/).
"""

import os
import pathlib
import shutil
import sys
import time
import urllib.request

from config_mac import get_models_dir, get_config_dir

MODELS = {
    "3b": {
        "name": "Qwen 2.5 3B",
        "full_name": "Qwen 2.5 3B — High Quality & Nuance",
        "short_name": "Qwen 2.5 3B",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_bytes": 2104932768,
        "approx_mb": 2007,
        "badge_size": "2.0 GB",
        "badge_rec": "RECOMMENDED (Apple Silicon)",
        "desc": "Preserves 100% of your voice, corrects nuanced grammar, sub-second on Metal GPU.",
        "ollama_blob": "sha256-5ee4f07cdb9beadbbb293e85803c569b01bd37ed059d2715faa7bb405f31caa6",
    },
    "1.5b": {
        "name": "Qwen 2.5 1.5B",
        "full_name": "Qwen 2.5 1.5B — Fast & Compact",
        "short_name": "Qwen 2.5 1.5B",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "size_bytes": 1117320736,
        "approx_mb": 1065,
        "badge_size": "1.0 GB",
        "badge_rec": "FAST / LIGHTWEIGHT",
        "desc": "Minimal memory footprint, designed for ultra-low battery drain and older Intel Macs.",
        "ollama_blob": "sha256-183715c435899236895da3869489cc30ac241476b4971a20285b1a462818a5b4",
    },
    "0.5b": {
        "name": "Qwen 2.5 0.5B",
        "full_name": "Qwen 2.5 0.5B — Ultra Light & Battery Saver",
        "short_name": "Qwen 2.5 0.5B",
        "filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "size_bytes": 491400032,
        "approx_mb": 468,
        "badge_size": "468 MB",
        "badge_rec": "ULTRA LIGHT (LOW RAM)",
        "desc": "Instant sub-100ms proofreading with near-zero memory footprint.",
        "ollama_blob": "",
    },
    "7b": {
        "name": "Qwen 2.5 7B",
        "full_name": "Qwen 2.5 7B — Executive Pro & Complex Nuance",
        "short_name": "Qwen 2.5 7B",
        "filename": "Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "url": "https://huggingface.co/bartowski/Qwen2.5-7B-Instruct-GGUF/resolve/main/Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        "size_bytes": 4683074240,
        "approx_mb": 4466,
        "badge_size": "4.4 GB",
        "badge_rec": "EXECUTIVE PRO (16GB+ RAM)",
        "desc": "Maximum rhetoric mastery and sophisticated restructuring. Best on M1/M2/M3/M4 Pro/Max.",
        "ollama_blob": "",
    },
}


def find_ollama_mac_model(profile: str = "3b") -> pathlib.Path | None:
    """Check if Ollama on macOS already downloaded this model."""
    spec = MODELS.get(profile)
    if not spec:
        return None

    ollama_home = pathlib.Path.home() / ".ollama" / "models"
    blob_id = spec.get("ollama_blob", "")
    if blob_id and (ollama_home / "blobs").is_dir():
        blob_path = ollama_home / "blobs" / blob_id.replace(":", "-")
        if blob_path.is_file() and blob_path.stat().st_size > 100_000_000:
            return blob_path

    # Check for direct tag manifest
    manifest_dir = ollama_home / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    tag = "3b" if profile == "3b" else ("7b" if profile == "7b" else ("1.5b" if profile == "1.5b" else "0.5b"))
    tag_file = manifest_dir / tag
    if tag_file.is_file():
        try:
            import json
            with open(tag_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for layer in data.get("layers", []):
                if layer.get("mediaType") == "application/vnd.ollama.image.model":
                    digest = layer.get("digest", "").replace(":", "-")
                    blob_file = ollama_home / "blobs" / digest
                    if blob_file.is_file():
                        return blob_file
        except Exception:
            pass
    return None


def resolve_model(profile: str = "3b") -> pathlib.Path | None:
    """
    Find existing model on macOS disk:
    1. Fixelect application models folder: ~/Library/Application Support/Fixelect/models/
    2. Local models relative to script or app bundle
    3. Existing Ollama cache
    """
    spec = MODELS.get(profile)
    if not spec:
        return None

    filename = spec["filename"]

    # 1. Check Application Support/Fixelect/models/
    models_dir = get_models_dir()
    target = models_dir / filename
    if target.is_file() and target.stat().st_size > 50_000_000:
        return target

    # 2. Check local relative directory (development / bundle)
    local_target = pathlib.Path(__file__).resolve().parent.parent / "models" / filename
    if local_target.is_file() and local_target.stat().st_size > 50_000_000:
        return local_target

    # 3. Check existing Ollama cache
    ollama_path = find_ollama_mac_model(profile)
    if ollama_path and ollama_path.is_file():
        return ollama_path

    # 4. Check user cache or Windows localappdata if testing cross-platform
    for alt_dir in [
        pathlib.Path.home() / ".cache" / "fixelect" / "models",
        pathlib.Path.home() / "AppData" / "Local" / "Fixelect" / "models",
    ]:
        alt_target = alt_dir / filename
        if alt_target.is_file() and alt_target.stat().st_size > 50_000_000:
            return alt_target

    return None


def download_model(profile: str = "3b", progress_callback=None, cancel_event=None) -> pathlib.Path:
    """
    Download model GGUF from Hugging Face with progress callbacks.
    Streams to .part file, then atomically renames upon verification.
    """
    spec = MODELS.get(profile)
    if not spec:
        raise ValueError(f"Unknown model profile: {profile}")

    url = spec["url"]
    filename = spec["filename"]
    expected_size = spec["size_bytes"]

    models_dir = get_models_dir()
    final_path = models_dir / filename
    part_path = models_dir / f"{filename}.part"

    # If already downloaded and valid
    if final_path.is_file() and final_path.stat().st_size >= expected_size * 0.98:
        if progress_callback:
            progress_callback(expected_size, expected_size, 0)
        return final_path

    # Check if Ollama already has it to avoid downloading twice
    ollama_model = find_ollama_mac_model(profile)
    if ollama_model and ollama_model.is_file():
        try:
            os.symlink(ollama_model, final_path)
            return final_path
        except Exception:
            shutil.copyfile(ollama_model, final_path)
            return final_path

    headers = {"User-Agent": "Fixelect-macOS/1.0"}
    req = urllib.request.Request(url, headers=headers)

    start_byte = 0
    if part_path.is_file():
        start_byte = part_path.stat().st_size
        if start_byte < expected_size:
            req.headers["Range"] = f"bytes={start_byte}-"
        else:
            start_byte = 0

    mode = "ab" if start_byte > 0 else "wb"
    downloaded = start_byte
    t_start = time.time()
    t_last = t_start
    bytes_last = downloaded

    with urllib.request.urlopen(req, timeout=30) as response:
        total_size = expected_size
        with open(part_path, mode) as f:
            while True:
                if cancel_event and cancel_event.is_set():
                    raise InterruptedError("Download cancelled by user.")

                chunk = response.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                now = time.time()
                if now - t_last >= 0.25:
                    speed = (downloaded - bytes_last) / (now - t_last)
                    t_last = now
                    bytes_last = downloaded
                    if progress_callback:
                        progress_callback(downloaded, total_size, speed)

    # Atomically rename .part to final file
    if part_path.is_file():
        part_path.replace(final_path)

    if progress_callback:
        progress_callback(expected_size, expected_size, 0)

    return final_path


def get_bin_dir() -> pathlib.Path:
    """Return ~/Library/Application Support/Fixelect/bin/ directory."""
    b = get_config_dir() / "bin"
    b.mkdir(parents=True, exist_ok=True)
    return b


def fetch_metal_engine(progress_callback=None) -> pathlib.Path | None:
    """
    Download standalone llama-server Metal binary for macOS if not already present.
    Installs into ~/Library/Application Support/Fixelect/bin/llama-server.
    """
    bin_dir = get_bin_dir()
    target = bin_dir / "llama-server"
    if target.is_file() and os.access(target, os.X_OK):
        return target

    # Official upstream release asset for llama.cpp macOS Metal binary
    url = "https://github.com/ggerganov/llama.cpp/releases/download/b4600/llama-b4600-bin-macos-arm64.zip"
    zip_path = bin_dir / "llama_metal.zip"

    try:
        import zipfile
        req = urllib.request.Request(url, headers={"User-Agent": "Fixelect-macOS/1.0"})
        with urllib.request.urlopen(req, timeout=40) as resp, open(zip_path, "wb") as out:
            total = int(resp.headers.get("Content-Length", 25_000_000))
            downloaded = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)

        # Extract llama-server and supporting Metal libraries
        with zipfile.ZipFile(zip_path, "r") as zf:
            for item in zf.namelist():
                if item.endswith("llama-server") or item.endswith(".metal") or item.endswith(".dylib"):
                    zf.extract(item, bin_dir)
                    extracted = bin_dir / item
                    if extracted.name == "llama-server":
                        if extracted != target:
                            extracted.replace(target)
                        os.chmod(target, 0o755)

        try:
            zip_path.unlink()
        except Exception:
            pass

        if target.is_file():
            os.chmod(target, 0o755)
            return target
    except Exception as e:
        print(f"Failed to auto-fetch Metal engine: {e}")

    return None
