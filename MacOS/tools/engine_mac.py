"""
macOS Local Inference Engine Manager for Fixelect.
Supports:
1. Embedded llama-server with Apple Silicon Metal acceleration (-ngl 99)
2. Direct OpenAI-compatible /v1/chat/completions API with HTTP keep-alive
3. Dynamic port allocation (18888-18898)
4. Zero-telemetry offline loopback execution
"""

import atexit
import http.client
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

from config_mac import get_resource_path
from hardware_mac import detect_mac_hardware
from downloader_mac import resolve_model, MODELS

DEFAULT_PORT = 18888
DEFAULT_PORT_START = 18888
DEFAULT_PORT_END = 18898


def is_port_in_use(port: int) -> bool:
    """Check if a TCP port is currently occupied on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start: int = DEFAULT_PORT_START, end: int = DEFAULT_PORT_END) -> int:
    """Find the first available TCP port in range."""
    for port in range(start, end + 1):
        if not is_port_in_use(port):
            return port
    return start


class MacEmbeddedEngine:
    """
    Manages local standalone llama-server with Apple Silicon Metal GPU acceleration.
    """

    def __init__(self, port: int = None, model_profile: str = "3b"):
        self.host = "127.0.0.1"
        self.port = port or find_free_port()
        self.model_profile = model_profile
        self.base_url = f"http://{self.host}:{self.port}"
        self.process = None
        self.conn = None
        self._owns_process = False
        self.hw = detect_mac_hardware()
        atexit.register(self.stop)

    def is_healthy(self) -> bool:
        """Ping the server's /health endpoint and verify model is loaded and ready."""
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=0.8)
            conn.request("GET", "/health")
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
            if resp.status == 200:
                data = json.loads(raw.decode("utf-8"))
                return data.get("status") == "ok"
            return False
        except Exception:
            return False

    def _find_llama_server(self) -> pathlib.Path | None:
        """Locate llama-server on macOS (bundled or Homebrew)."""
        arch_dir = "darwin-arm64" if self.hw["is_apple_silicon"] else "darwin-x86_64"
        bundled = get_resource_path(f"resources/bin/{arch_dir}/llama-server")
        if bundled.is_file() and os.access(bundled, os.X_OK):
            return bundled

        generic_bundled = get_resource_path("resources/bin/llama-server")
        if generic_bundled.is_file() and os.access(generic_bundled, os.X_OK):
            return generic_bundled

        for brew_bin in ["/opt/homebrew/bin/llama-server", "/usr/local/bin/llama-server"]:
            p = pathlib.Path(brew_bin)
            if p.is_file() and os.access(p, os.X_OK):
                return p

        # Check Application Support bin
        try:
            from downloader_mac import get_bin_dir
            app_bin = get_bin_dir() / "llama-server"
            if app_bin.is_file() and os.access(app_bin, os.X_OK):
                return app_bin
        except Exception:
            pass

        which = shutil.which("llama-server")
        if which:
            return pathlib.Path(which)

        # Cross-platform development / testing fallback
        if sys.platform == "win32":
            win_bin = pathlib.Path(__file__).resolve().parent.parent.parent / "Windows" / "resources" / "bin" / "llama-server.exe"
            if win_bin.is_file():
                return win_bin

        return None

    def start(self, timeout: float = 25.0) -> bool:
        """Start llama-server with Metal GPU acceleration."""
        if self.is_healthy():
            print(f"  [EmbeddedEngine] Existing engine responsive on :{self.port}")
            return True

        model_path = resolve_model(self.model_profile)
        if not model_path:
            raise FileNotFoundError(f"Model '{self.model_profile}' not found on disk. Run setup first.")

        server_bin = self._find_llama_server()
        if not server_bin and self.hw.get("is_apple_silicon"):
            print("  [Engine] Fetching standalone Apple Silicon Metal engine...")
            try:
                from downloader_mac import fetch_metal_engine
                server_bin = fetch_metal_engine()
            except Exception as e:
                print(f"  ! Auto-fetch error: {e}")

        if not server_bin:
            # Check if ollama is available as alternative
            ollama_bin = shutil.which("ollama") or (
                pathlib.Path("/opt/homebrew/bin/ollama") if pathlib.Path("/opt/homebrew/bin/ollama").is_file() else None
            )
            if ollama_bin:
                print("  [Engine] llama-server not bundled; falling back to macOS Ollama.")
                return False
            raise FileNotFoundError(
                "Neither bundled llama-server nor Ollama was found on this Mac.\n"
                "Install llama.cpp or Ollama (brew install llama.cpp) to enable local inference."
            )

        cmd = [
            str(server_bin),
            "-m", str(model_path),
            "--port", str(self.port),
            "--host", self.host,
            "-c", "2048",
            "-b", "512",
            "--cont-batching",
            "--log-disable",
        ]

        if self.hw["is_apple_silicon"]:
            cmd.extend(["--n-gpu-layers", "99"])
        else:
            cmd.extend(["--threads", str(os.cpu_count() or 4)])

        env = os.environ.copy()
        env["PATH"] = str(server_bin.parent) + os.pathsep + env.get("PATH", "")
        env["GGML_METAL_DISABLE_CAPTURE"] = "1"

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=str(server_bin.parent),
                env=env,
            )
            self._owns_process = True
        except Exception as e:
            raise RuntimeError(f"Failed to launch llama-server: {e}")

        # Wait for model to load into RAM/VRAM
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.process.poll() is not None:
                raise RuntimeError(f"llama-server terminated unexpectedly with exit code {self.process.returncode}")
            if self.is_healthy():
                elapsed = time.time() - t0
                print(f"  [EmbeddedEngine] Model loaded in {elapsed:.1f}s. Ready for requests.")
                return True
            time.sleep(0.2)

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
        _default_engine = MacEmbeddedEngine(port=port, model_profile=p)
    elif model_profile is not None and getattr(_default_engine, "model_profile", None) != model_profile:
        try:
            _default_engine.stop()
        except Exception:
            pass
        _default_engine = MacEmbeddedEngine(port=port, model_profile=model_profile)
    return _default_engine
