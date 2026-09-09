"""
Embedded local inference sidecar manager for Fixelect.
Manages the lifecycle of an embedded llama-server process on 127.0.0.1:18888,
providing zero-dependency, self-contained local LLM execution.
"""

import atexit
import http.client
import json
import os
import pathlib
import signal
import socket
import subprocess
import sys
import time
import urllib.request

# Ensure tools directory is on path
_tools_dir = pathlib.Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from hardware import detect_hardware, get_llama_args  # noqa: E402
from downloader import resolve_model  # noqa: E402
from config import get_resource_path  # noqa: E402

DEFAULT_PORT = 18888


class EmbeddedEngine:
    """Manages the embedded llama-server sidecar process."""

    def __init__(self, port=DEFAULT_PORT, model_profile="3b", model_path=None):
        self.port = port
        self.host = "127.0.0.1"
        self.base_url = f"http://{self.host}:{self.port}"
        self.process = None
        self.model_profile = model_profile
        self.model_path = model_path or resolve_model(model_profile)
        self.conn = None
        self._owns_process = False

    def find_server_binary(self):
        """Find pre-compiled llama-server.exe and configure environment."""
        # 1. Check system Ollama runtime if present (has full CUDA acceleration if installed)
        ollama_lib = pathlib.Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "lib" / "ollama"
        ollama_server = ollama_lib / "llama-server.exe"

        # 2. Bundled via PyInstaller / resources
        bundled = get_resource_path("resources/bin/llama-server.exe")
        if not bundled.is_file():
            bundled = get_resource_path("llama-server.exe")

        # 3. In %LOCALAPPDATA%/Fixelect/bin/
        local_app = os.environ.get("LOCALAPPDATA")
        appdata_server = None
        if local_app:
            appdata_bin = pathlib.Path(local_app) / "Fixelect" / "bin" / "llama-server.exe"
            if appdata_bin.is_file():
                appdata_server = appdata_bin

        # If Ollama has CUDA and system has CUDA, prioritize Ollama for peak performance
        try:
            hw = detect_hardware()
            if hw.get("backend") == "cuda" and ollama_server.is_file() and (ollama_lib / "cuda_v12").is_dir():
                return ollama_server, ollama_lib
        except Exception:
            pass

        if bundled.is_file():
            return bundled, bundled.parent

        if appdata_server:
            return appdata_server, appdata_server.parent

        if ollama_server.is_file():
            return ollama_server, ollama_lib

        return None, None


    def is_healthy(self):
        """Quick check if a server is already running and responsive."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health")
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.load(resp)
                return data.get("status") == "ok"
        except Exception:
            return False

    def start(self, timeout=35):
        """Launch the sidecar server process and wait until model is loaded."""
        if self.is_healthy():
            print(f"  [EmbeddedEngine] Existing engine responsive on :{self.port}")
            self._owns_process = False
            return True

        # Check port availability; if default port is occupied, scan next available port
        def test_port(p):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((self.host, p))
                    return True
                except Exception:
                    return False

        if not test_port(self.port):
            for candidate in range(18889, 18899):
                if test_port(candidate):
                    self.port = candidate
                    self.base_url = f"http://{self.host}:{self.port}"
                    break

        binary_path, bin_dir = self.find_server_binary()
        if not binary_path:
            raise FileNotFoundError(
                "Could not find llama-server.exe in resources/bin/, %LOCALAPPDATA%/Fixelect/bin/, or system."
            )

        if not self.model_path or not pathlib.Path(self.model_path).is_file():
            raise FileNotFoundError(
                f"Model file not found. Call tools.downloader.download_model() first. Path: {self.model_path}"
            )

        args, hw = get_llama_args(context_size=2048)

        cmd = [
            str(binary_path),
            "-m", str(self.model_path),
            "--host", self.host,
            "--port", str(self.port),
            "--log-disable",
        ]
        cmd.extend(args)

        # Set PATH and GGML_BACKEND_PATH so llama.cpp finds companion DLLs (CUDA / Vulkan / CPU)
        env = os.environ.copy()
        backend_label = hw["backend"].upper()
        if bin_dir:
            cuda_dir = bin_dir / "cuda_v12"
            vulkan_dir = bin_dir / "vulkan"
            extra_paths = [str(bin_dir)]

            if hw.get("backend") == "cuda":
                if cuda_dir.is_dir():
                    extra_paths.insert(0, str(cuda_dir))
                    cuda_dll = cuda_dir / "ggml-cuda.dll"
                    if cuda_dll.is_file():
                        env["GGML_BACKEND_PATH"] = str(cuda_dll)
                elif (bin_dir / "ggml-cuda.dll").is_file():
                    env["GGML_BACKEND_PATH"] = str(bin_dir / "ggml-cuda.dll")

                # Universal Vulkan GPU fallback for NVIDIA systems without Ollama / CUDA toolkit
                if "GGML_BACKEND_PATH" not in env:
                    v_dll = vulkan_dir / "ggml-vulkan.dll" if vulkan_dir.is_dir() else (bin_dir / "ggml-vulkan.dll")
                    if v_dll.is_file():
                        extra_paths.insert(0, str(v_dll.parent))
                        env["GGML_BACKEND_PATH"] = str(v_dll)
                        backend_label = "VULKAN (NVIDIA GPU Acceleration)"
            elif hw.get("backend") == "vulkan":
                if vulkan_dir.is_dir():
                    extra_paths.insert(0, str(vulkan_dir))
                    vulkan_dll = vulkan_dir / "ggml-vulkan.dll"
                    if vulkan_dll.is_file():
                        env["GGML_BACKEND_PATH"] = str(vulkan_dll)
                elif (bin_dir / "ggml-vulkan.dll").is_file():
                    env["GGML_BACKEND_PATH"] = str(bin_dir / "ggml-vulkan.dll")

            env["PATH"] = ";".join(extra_paths) + ";" + env.get("PATH", "")

        device_label = hw["gpu_name"]
        print(f"  [EmbeddedEngine] Starting llama-server on :{self.port} [{backend_label} - {device_label}]...")

        creationflags = 0
        if sys.platform == "win32":
            # Start detached/hidden without popping an empty console window
            creationflags = subprocess.CREATE_NO_WINDOW

        self.process = subprocess.Popen(
            cmd,
            env=env,
            cwd=str(bin_dir) if bin_dir else None,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._owns_process = True
        atexit.register(self.stop)

        # Wait for model to load into VRAM
        start_t = time.time()
        while time.time() - start_t < timeout:
            if self.process.poll() is not None:
                raise RuntimeError(f"llama-server terminated unexpectedly with exit code {self.process.returncode}")
            if self.is_healthy():
                elapsed = time.time() - start_t
                print(f"  [EmbeddedEngine] Model loaded in {elapsed:.1f}s. Ready for requests.")
                return True
            time.sleep(0.3)

        self.stop()
        raise TimeoutError(f"llama-server failed to initialize within {timeout}s.")

    def stop(self):
        """Terminate the server process cleanly."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

        if self._owns_process and self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
            self._owns_process = False

    def _get_conn(self):
        if self.conn is None:
            self.conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
        return self.conn

    def chat_completion(
        self,
        messages,
        temperature=0.0,
        max_tokens=512,
        top_k=20,
        top_p=0.9,
        seed=None,
    ):
        """
        Execute chat completion over persistent keep-alive connection.
        Returns the generated content string, or raises on error.
        """
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_k": top_k,
            "top_p": top_p,
            "stream": False,
        }
        if seed is not None:
            payload["seed"] = seed
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Connection": "keep-alive"}

        for attempt in range(2):
            conn = self._get_conn()
            try:
                conn.request("POST", "/v1/chat/completions", body=body, headers=headers)
                res = conn.getresponse()
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    choice = data.get("choices", [{}])[0]
                    content = choice.get("message", {}).get("content", "")
                    return content
                else:
                    res.read()
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                self.conn = http.client.HTTPConnection(self.host, self.port, timeout=30)
                if attempt == 1:
                    # Fallback to standard request
                    req = urllib.request.Request(
                        f"{self.base_url}/v1/chat/completions",
                        data=body,
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req, timeout=20) as r:
                        data = json.load(r)
                        choice = data.get("choices", [{}])[0]
                        return choice.get("message", {}).get("content", "")
        return ""


_default_engine = None


def get_default_engine(port=DEFAULT_PORT, model_profile=None):
    """Singleton getter for the embedded engine."""
    global _default_engine
    if _default_engine is None:
        p = model_profile or "3b"
        _default_engine = EmbeddedEngine(port=port, model_profile=p)
    elif model_profile is not None and getattr(_default_engine, "model_profile", None) != model_profile:
        try:
            _default_engine.stop()
        except Exception:
            pass
        _default_engine = EmbeddedEngine(port=port, model_profile=model_profile)
    return _default_engine


if __name__ == "__main__":
    print("Testing EmbeddedEngine...")
    engine = EmbeddedEngine()
    try:
        engine.start()
        print("Sending test request...")
        t0 = time.time()
        reply = engine.chat_completion(
            messages=[
                {"role": "system", "content": "You are a precise proofreader."},
                {"role": "user", "content": "Your welcome."},
            ],
            temperature=0.0,
            max_tokens=32,
        )
        took = (time.time() - t0) * 1000
        print(f"Reply in {took:.1f}ms: {reply!r}")
    finally:
        engine.stop()
        print("Engine stopped.")
