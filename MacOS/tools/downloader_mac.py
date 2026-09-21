"""
Model manager and downloader for Fixelect on macOS.
Resolves, discovers, and downloads GGUF models into ~/Library/Application Support/Fixelect/models/.
Also discovers local models in Ollama's macOS storage (~/.ollama/models/).
"""

import hashlib
import os
import pathlib
import shutil
import subprocess
import urllib.error
import urllib.request

import modelfetch
import net
from version import APP_VERSION
from config_mac import get_models_dir, get_config_dir

MODELS = {
    "3b": {
        "name": "Qwen 2.5 3B",
        "full_name": "Qwen 2.5 3B — High Quality & Nuance",
        "short_name": "Qwen 2.5 3B",
        "filename": "qwen2.5-3b-instruct-q4_k_m.gguf",
        "sha256": "626b4a6678b86442240e33df819e00132d3ba7dddfe1cdc4fbb18e0a9615c62d",
        "url": "https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf",
        "size_bytes": 2104932768,
        "approx_mb": 2007,
        "badge_size": "2.0 GB",
        "badge_rec": "RECOMMENDED (Apple Silicon)",
        "desc": "Preserves 100% of your voice, corrects nuanced grammar, sub-second on Metal GPU.",
        "ollama_blob": "sha256-5ee4f07cdb9beadbbb293e85803c569b01bd37ed059d2715faa7bb405f31caa6",
    },
    "gemma4-e2b": {
        "name": "Gemma 4 E2B",
        "full_name": "Gemma 4 E2B — Best for other languages",
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
        "name": "Qwen 2.5 1.5B",
        "full_name": "Qwen 2.5 1.5B — Fast & Compact",
        "short_name": "Qwen 2.5 1.5B",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "sha256": "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e",
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
        "sha256": "74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db",
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
        "sha256": "65b8fcd92af6b4fefa935c625d1ac27ea29dcb6ee14589c55a8f115ceaaa1423",
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


DownloadCancelled = modelfetch.DownloadCancelled


def download_model(profile: str = "3b", progress_callback=None, cancel_event=None) -> pathlib.Path:
    """Download a model once, with resume and a checksum check (see shared/modelfetch.py)."""
    spec = MODELS.get(profile)
    if not spec:
        raise ValueError(f"Unknown model profile: {profile}")
    existing = resolve_model(profile)
    if existing:
        return existing
    return modelfetch.fetch(spec, get_models_dir(), progress_callback, cancel_event,
                            user_agent=f"Fixelect-macOS/{APP_VERSION}")


def get_bin_dir() -> pathlib.Path:
    """Return ~/Library/Application Support/Fixelect/bin/ directory."""
    b = get_config_dir() / "bin"
    b.mkdir(parents=True, exist_ok=True)
    return b


# Pinned llama.cpp Metal build. Release builds ship it inside Fixelect.app
# (build_dmg.sh); this download is only a fallback for source checkouts.
ENGINE_URL = "https://github.com/ggml-org/llama.cpp/releases/download/b10917/llama-b10917-bin-macos-arm64.tar.gz"
ENGINE_SHA256 = "3deb6ddac52ae7afa5768a10a26288214f2d635a4f7b13ceb96ddbb60ade993a"


def fetch_metal_engine(progress_callback=None) -> pathlib.Path | None:
    """Download the llama.cpp Metal build once into Application Support/Fixelect/bin.

    The whole archive is extracted so llama-server keeps its libggml/libllama
    dylibs next to it (moving the binary alone broke its @rpath lookups)."""
    bin_dir = get_bin_dir()
    for existing in sorted(bin_dir.rglob("llama-server")):
        if existing.is_file() and os.access(existing, os.X_OK):
            return existing

    archive = bin_dir / "llama_metal.tar.gz"
    dest = bin_dir / "llama.cpp"
    try:
        import tarfile
        req = urllib.request.Request(ENGINE_URL, headers={"User-Agent": "Fixelect-macOS/1.1"})
        digest = hashlib.sha256()
        with net.urlopen(req, timeout=60) as resp, open(archive, "wb") as out:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            done = 0
            while True:
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress_callback:
                    progress_callback(done, total or done)
        if digest.hexdigest() != ENGINE_SHA256:
            archive.unlink(missing_ok=True)
            raise RuntimeError("engine download failed its checksum")
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive) as tf:
            # keeps the dylib version symlinks; refuses paths escaping `dest`
            tf.extractall(dest, filter="data")
        archive.unlink(missing_ok=True)
        server = None
        for p in dest.rglob("*"):
            if p.is_file() and (p.name.startswith("llama-") or p.suffix == ".dylib"):
                os.chmod(p, 0o755)
            if p.name == "llama-server":
                server = p
        subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(dest)], capture_output=True)
        return server
    except Exception as e:
        print(f"Failed to fetch the Metal engine: {e}")
        return None
