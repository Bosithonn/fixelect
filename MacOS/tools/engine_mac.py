"""
macOS local inference engine manager for Fixelect.

  * Embedded llama-server with Apple Silicon Metal acceleration (-ngl 99).
  * The menu-bar daemon owns the server and publishes its port in runtime.json;
    the Dashboard / Setup windows (separate processes) attach to it instead of
    loading a second copy of a multi-GB model.
  * Automatic restart if the server dies, sane timeouts, prompt caching.
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
import threading
import time

from config_mac import get_resource_path, load_config, get_lock_path, get_runtime_path
from hardware_mac import detect_mac_hardware
from downloader_mac import resolve_model, get_bin_dir

DEFAULT_PORT = 18888
CONTEXT_SIZE = 4096
REQUEST_TIMEOUT = 180
LOAD_TIMEOUT = 120


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except Exception:
        return False


def daemon_pid():
    """PID of the running menu-bar daemon (not us), or None."""
    try:
        pid = int(get_lock_path().read_text().strip() or 0)
    except Exception:
        return None
    return pid if pid and pid != os.getpid() and _pid_alive(pid) else None


def read_runtime():
    try:
        return json.loads(get_runtime_path().read_text())
    except Exception:
        return {}


class MacEmbeddedEngine:
    def __init__(self, port: int = DEFAULT_PORT, model_profile: str = "3b"):
        self.host = "127.0.0.1"
        self.port = port
        self.model_profile = model_profile
        self.process = None
        self.conn = None
        self._owns_process = False
        self._lock = threading.RLock()
        self._conn_lock = threading.Lock()
        self.hw = detect_mac_hardware()
        self.backend_label = "METAL" if self.hw.get("is_apple_silicon") else "CPU"
        self.publish = False  # set by the daemon: write runtime.json for window processes
        atexit.register(self.stop)

    # -- health ------------------------------------------------------------------

    def _get_json(self, path, port=None, timeout=0.8):
        try:
            conn = http.client.HTTPConnection(self.host, port or self.port, timeout=timeout)
            conn.request("GET", path)
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
            if resp.status == 200:
                return json.loads(raw.decode("utf-8"))
        except Exception:
            pass
        return None

    def is_healthy(self, port=None) -> bool:
        data = self._get_json("/health", port)
        return bool(data) and data.get("status") == "ok"

    def _serves(self, model_path, port=None):
        props = self._get_json("/props", port, timeout=1.5) or {}
        path = props.get("model_path") or ""
        return not path or pathlib.Path(path).name == pathlib.Path(model_path).name

    def is_running(self):
        if self._owns_process and self.process is not None and self.process.poll() is not None:
            return False
        return self.is_healthy()

    def ensure_running(self):
        if self.is_running():
            return True
        with self._lock:
            if self.is_running():
                return True
            self.stop()
            return self.start()

    # -- discovery -----------------------------------------------------------------

    def _find_llama_server(self):
        arch_dir = "darwin-arm64" if self.hw["is_apple_silicon"] else "darwin-x86_64"
        candidates = [
            get_resource_path(f"resources/bin/{arch_dir}/llama-server"),
            get_resource_path("resources/bin/llama-server"),
            pathlib.Path("/opt/homebrew/bin/llama-server"),
            pathlib.Path("/usr/local/bin/llama-server"),
        ]
        try:
            candidates += sorted(get_bin_dir().rglob("llama-server"))
        except Exception:
            pass
        which = shutil.which("llama-server")
        if which:
            candidates.append(pathlib.Path(which))
        for p in candidates:
            if p.is_file() and os.access(p, os.X_OK):
                return p
        return None

    # -- lifecycle -------------------------------------------------------------------

    def _attach(self, model_path, wait):
        """Use the daemon's server if one is (or is about to be) running."""
        deadline = time.time() + wait
        while True:
            rt = read_runtime()
            port = rt.get("port")
            if port and _pid_alive(rt.get("pid", 0)) and self.is_healthy(port) and self._serves(model_path, port):
                self.port = port
                self._owns_process = False
                return True
            if time.time() >= deadline:
                return False
            time.sleep(0.5)

    def _free_port(self):
        for p in range(DEFAULT_PORT, DEFAULT_PORT + 20):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind((self.host, p))
                    return p
                except OSError:
                    continue
        return DEFAULT_PORT

    def start(self, timeout: float = LOAD_TIMEOUT) -> bool:
        with self._lock:
            if self._owns_process and self.process is not None and self.process.poll() is None and self.is_healthy():
                return True
            model_path = resolve_model(self.model_profile)
            if not model_path:
                raise FileNotFoundError(f"Model '{self.model_profile}' is not downloaded yet. Open Model settings.")

            # A window process attaches to the daemon (waiting while it loads).
            if not self.publish and self._attach(model_path, 90 if daemon_pid() else 0):
                return True
            if self.is_healthy() and self._serves(model_path):
                self._owns_process = False
                return True

            server_bin = self._find_llama_server()
            if not server_bin and self.hw.get("is_apple_silicon"):
                from downloader_mac import fetch_metal_engine
                server_bin = fetch_metal_engine()
            if not server_bin:
                if shutil.which("ollama") or pathlib.Path("/opt/homebrew/bin/ollama").is_file():
                    return False  # caller falls back to Ollama
                raise FileNotFoundError("The Fixelect engine is missing. Reinstall Fixelect or run `brew install llama.cpp`.")

            self.port = self._free_port()
            self._close_conn()
            cmd = [str(server_bin), "-m", str(model_path), "--host", self.host, "--port", str(self.port),
                   "-c", str(CONTEXT_SIZE), "-np", "1", "--log-disable"]
            if self.hw["is_apple_silicon"]:
                cmd += ["-ngl", "99"]
            else:
                cmd += ["-t", str(max(1, (os.cpu_count() or 4) // 2))]
            env = os.environ.copy()
            env["PATH"] = str(server_bin.parent) + os.pathsep + env.get("PATH", "")
            env["DYLD_LIBRARY_PATH"] = str(server_bin.parent) + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
            env["GGML_METAL_DISABLE_CAPTURE"] = "1"

            print(f"  [Engine] Starting llama-server on :{self.port} [{self.backend_label}]")
            self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL, cwd=str(server_bin.parent), env=env,
                                            start_new_session=False)
            self._owns_process = True
            t0 = time.time()
            while time.time() - t0 < timeout:
                if self.process.poll() is not None:
                    self._owns_process = False
                    raise RuntimeError(f"llama-server exited with code {self.process.returncode}")
                if self.is_healthy():
                    print(f"  [Engine] Model loaded in {time.time() - t0:.1f}s")
                    if self.publish:
                        try:
                            get_runtime_path().write_text(json.dumps(
                                {"port": self.port, "pid": os.getpid(), "model_path": str(model_path)}))
                        except Exception:
                            pass
                    return True
                time.sleep(0.2)
            self.stop()
            raise TimeoutError(f"llama-server was not ready within {timeout:.0f}s")

    def _close_conn(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def stop(self):
        self._close_conn()
        if self._owns_process and self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            if self.publish:
                try:
                    get_runtime_path().unlink()
                except Exception:
                    pass
        self.process = None
        self._owns_process = False

    # -- inference ---------------------------------------------------------------------

    def chat_completion(self, messages, temperature=0.0, max_tokens=512, top_k=20, top_p=0.9, seed=None):
        payload = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens,
                   "top_k": top_k, "top_p": top_p, "stream": False, "cache_prompt": True}
        if seed is not None:
            payload["seed"] = seed
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
        with self._conn_lock:
            for attempt in range(2):
                if self.conn is None:
                    self.conn = http.client.HTTPConnection(self.host, self.port, timeout=REQUEST_TIMEOUT)
                try:
                    self.conn.request("POST", "/v1/chat/completions", body=body, headers=headers)
                    res = self.conn.getresponse()
                    raw = res.read()
                except socket.timeout:
                    self._close_conn()
                    raise TimeoutError("The AI engine took too long to respond.")
                except (ConnectionError, http.client.HTTPException, OSError):
                    self._close_conn()
                    if attempt == 1:
                        raise ConnectionError("The AI engine is not responding.")
                    continue
                if res.status == 200:
                    data = json.loads(raw.decode("utf-8"))
                    return (data.get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
                if res.status in (400, 413):
                    raise ValueError("The selected text is too long for the AI model.")
                if attempt == 1:
                    raise RuntimeError(f"AI engine error (HTTP {res.status}).")
        return ""


_default_engine = None
_engine_lock = threading.Lock()


def get_default_engine(port=DEFAULT_PORT, model_profile=None):
    global _default_engine
    with _engine_lock:
        if _default_engine is None:
            _default_engine = MacEmbeddedEngine(port=port, model_profile=model_profile or load_config().get("model_profile", "3b"))
        elif model_profile is not None and _default_engine.model_profile != model_profile:
            publish = _default_engine.publish
            try:
                _default_engine.stop()
            except Exception:
                pass
            _default_engine = MacEmbeddedEngine(port=port, model_profile=model_profile)
            _default_engine.publish = publish
        return _default_engine
