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
import socket
import subprocess
import sys
import threading
import time

# Ensure tools directory is on path
_tools_dir = pathlib.Path(__file__).resolve().parent
if str(_tools_dir) not in sys.path:
    sys.path.insert(0, str(_tools_dir))

from hardware import detect_hardware, get_llama_args  # noqa: E402
from downloader import resolve_model  # noqa: E402
from config import get_resource_path, load_config  # noqa: E402

DEFAULT_PORT = 18888
CONTEXT_SIZE = 4096          # room for multi-paragraph polish (prompt + output)
REQUEST_TIMEOUT = 180        # CPU-only polish of a long paragraph can take a while
LOAD_TIMEOUT = 120           # first load from a cold HDD / large model


class _KillOnCloseJob:
    """Windows Job Object that kills its processes when Fixelect exits.

    Without it, a crash, a Task Manager "End task" or an installer upgrade
    leaves a 2-5 GB llama-server running in the background forever.
    """

    def __init__(self):
        self.handle = None
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes as w

            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
            k32.CreateJobObjectW.restype = w.HANDLE
            k32.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
            k32.SetInformationJobObject.restype = w.BOOL
            k32.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            k32.AssignProcessToJobObject.restype = w.BOOL

            class IO_COUNTERS(ctypes.Structure):
                _fields_ = [(n, ctypes.c_ulonglong) for n in (
                    "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                    "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

            class BASIC(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_longlong),
                    ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", w.DWORD),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", w.DWORD),
                    ("Affinity", ctypes.c_size_t),
                    ("PriorityClass", w.DWORD),
                    ("SchedulingClass", w.DWORD),
                ]

            class EXTENDED(ctypes.Structure):
                _fields_ = [
                    ("BasicLimitInformation", BASIC),
                    ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t),
                ]

            job = k32.CreateJobObjectW(None, None)
            if not job:
                return
            info = EXTENDED()
            info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
                self.handle = job
                self._k32 = k32
        except Exception:
            self.handle = None

    def adopt(self, popen):
        if not self.handle:
            return
        try:
            self._k32.AssignProcessToJobObject(self.handle, int(popen._handle))
        except Exception:
            pass


_job = None


def _get_job():
    global _job
    if _job is None:
        _job = _KillOnCloseJob()
    return _job


class EmbeddedEngine:
    """Manages the embedded llama-server sidecar process."""

    def __init__(self, port=DEFAULT_PORT, model_profile="3b", model_path=None):
        self.port = port
        self.host = "127.0.0.1"
        self.process = None
        self.model_profile = model_profile
        self.model_path = model_path or resolve_model(model_profile)
        self.conn = None
        self._owns_process = False
        self._lock = threading.RLock()
        self._conn_lock = threading.Lock()
        self.last_used = time.time()
        self.backend_label = ""

    @property
    def base_url(self):
        return f"http://{self.host}:{self.port}"

    # -- discovery -------------------------------------------------------------

    def server_candidates(self):
        """Ordered (binary, directory, is_bundled) candidates for llama-server."""
        found = []
        ollama_lib = pathlib.Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "lib" / "ollama"
        ollama_server = ollama_lib / "llama-server.exe"

        bundled = get_resource_path("resources/bin/llama-server.exe")
        if not bundled.is_file():
            bundled = get_resource_path("llama-server.exe")

        appdata_server = None
        local_app = os.environ.get("LOCALAPPDATA")
        if local_app:
            p = pathlib.Path(local_app) / "Fixelect" / "bin" / "llama-server.exe"
            if p.is_file():
                appdata_server = p

        # An installed Ollama ships CUDA kernels we do not bundle: prefer it on NVIDIA.
        try:
            if (detect_hardware().get("backend") == "cuda" and ollama_server.is_file()
                    and any(ollama_lib.glob("cuda_v*"))):
                found.append((ollama_server, ollama_lib, False))
        except Exception:
            pass
        if bundled.is_file():
            found.append((bundled, bundled.parent, True))
        if appdata_server:
            found.append((appdata_server, appdata_server.parent, False))
        if ollama_server.is_file() and all(c[0] != ollama_server for c in found):
            found.append((ollama_server, ollama_lib, False))
        return found

    def find_server_binary(self):
        c = self.server_candidates()
        return (c[0][0], c[0][1]) if c else (None, None)

    # -- health ----------------------------------------------------------------

    def _get_json(self, path, timeout=0.8):
        try:
            conn = http.client.HTTPConnection(self.host, self.port, timeout=timeout)
            conn.request("GET", path)
            resp = conn.getresponse()
            raw = resp.read()
            conn.close()
            if resp.status == 200:
                return json.loads(raw.decode("utf-8"))
        except Exception:
            pass
        return None

    def is_healthy(self):
        data = self._get_json("/health")
        return bool(data) and data.get("status") == "ok"

    def _serves_our_model(self):
        """A server already on our port is only reusable if it runs the model we want."""
        props = self._get_json("/props", timeout=1.5) or {}
        path = props.get("model_path") or ""
        if not path or not self.model_path:
            return True  # old servers don't report it; assume it is a previous Fixelect run
        try:
            return pathlib.Path(path).resolve() == pathlib.Path(self.model_path).resolve()
        except Exception:
            return pathlib.Path(path).name == pathlib.Path(self.model_path).name

    def is_running(self):
        if self._owns_process and self.process is not None and self.process.poll() is not None:
            return False
        return self.is_healthy()

    def ensure_running(self):
        """Restart the sidecar if it crashed (GPU driver reset, OOM, killed by the user)."""
        if self.is_running():
            return True
        with self._lock:
            if self.is_running():
                return True
            self.stop()
            return self.start()

    # -- lifecycle ---------------------------------------------------------------

    def _port_free(self, p):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((self.host, p))
                return True
            except OSError:
                return False

    def start(self, timeout=LOAD_TIMEOUT):
        """Launch the sidecar (or adopt a compatible running one) and wait until it serves."""
        with self._lock:
            if self._owns_process and self.process is not None and self.process.poll() is None and self.is_healthy():
                return True

            if not self.model_path or not pathlib.Path(self.model_path).is_file():
                self.model_path = resolve_model(self.model_profile)
            if not self.model_path or not pathlib.Path(self.model_path).is_file():
                raise FileNotFoundError(
                    f"Model file for '{self.model_profile}' not found. Open Model settings to download it."
                )

            if self.is_healthy() and self._serves_our_model():
                print(f"  [EmbeddedEngine] Reusing engine already running on :{self.port}")
                self._owns_process = False
                return True

            if not self._port_free(self.port):
                for candidate in range(DEFAULT_PORT + 1, DEFAULT_PORT + 20):
                    if self._port_free(candidate):
                        self.port = candidate
                        break
                self._close_conn()

            candidates = self.server_candidates()
            if not candidates:
                raise FileNotFoundError(
                    "Could not find llama-server.exe in resources/bin/, %LOCALAPPDATA%/Fixelect/bin/, or Ollama."
                )

            last_error = None
            for binary, bin_dir, bundled in candidates:
                try:
                    self._launch(binary, bin_dir, bundled, timeout)
                    return True
                except Exception as e:  # try the next binary (e.g. an outdated Ollama build)
                    last_error = e
                    print(f"  [EmbeddedEngine] {binary.name} failed: {e}")
                    self.stop()
            raise RuntimeError(f"llama-server could not start: {last_error}")

    def _launch(self, binary_path, bin_dir, bundled, timeout):
        args, hw = get_llama_args(context_size=CONTEXT_SIZE)
        cmd = [str(binary_path), "-m", str(self.model_path), "--port", str(self.port), "--log-disable"]
        cmd.extend(args)
        if bundled:
            cmd.append("--no-webui")  # flags our pinned build is known to support

        env = os.environ.copy()
        backend_label = hw["backend"].upper()
        cuda_dir = bin_dir / "cuda_v12"
        vulkan_dir = bin_dir / "vulkan"
        extra_paths = [str(bin_dir)]
        if hw.get("backend") == "cuda":
            if cuda_dir.is_dir():
                extra_paths.insert(0, str(cuda_dir))
                if (cuda_dir / "ggml-cuda.dll").is_file():
                    env["GGML_BACKEND_PATH"] = str(cuda_dir / "ggml-cuda.dll")
            elif (bin_dir / "ggml-cuda.dll").is_file():
                env["GGML_BACKEND_PATH"] = str(bin_dir / "ggml-cuda.dll")
            if "GGML_BACKEND_PATH" not in env:
                v_dll = vulkan_dir / "ggml-vulkan.dll" if vulkan_dir.is_dir() else (bin_dir / "ggml-vulkan.dll")
                if v_dll.is_file():
                    extra_paths.insert(0, str(v_dll.parent))
                    env["GGML_BACKEND_PATH"] = str(v_dll)
                    backend_label = "VULKAN"
        elif hw.get("backend") == "vulkan":
            if vulkan_dir.is_dir():
                extra_paths.insert(0, str(vulkan_dir))
                if (vulkan_dir / "ggml-vulkan.dll").is_file():
                    env["GGML_BACKEND_PATH"] = str(vulkan_dir / "ggml-vulkan.dll")
            elif (bin_dir / "ggml-vulkan.dll").is_file():
                env["GGML_BACKEND_PATH"] = str(bin_dir / "ggml-vulkan.dll")
        env["PATH"] = ";".join(extra_paths) + ";" + env.get("PATH", "")
        self.backend_label = backend_label

        print(f"  [EmbeddedEngine] Starting {binary_path.name} on :{self.port} [{backend_label} - {hw['gpu_name']}]...")
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.process = subprocess.Popen(
            cmd, env=env, cwd=str(bin_dir), creationflags=creationflags,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        self._owns_process = True
        _get_job().adopt(self.process)
        atexit.register(self.stop)

        start_t = time.time()
        while time.time() - start_t < timeout:
            if self.process.poll() is not None:
                raise RuntimeError(f"exited with code {self.process.returncode}")
            if self.is_healthy():
                print(f"  [EmbeddedEngine] Model loaded in {time.time() - start_t:.1f}s.")
                return
            time.sleep(0.25)
        raise TimeoutError(f"not ready within {timeout}s")

    def _close_conn(self):
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            self.conn = None

    def stop(self):
        """Terminate the server process cleanly (only if we started it)."""
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
        self.process = None
        self._owns_process = False

    # -- inference ---------------------------------------------------------------

    def idle_seconds(self):
        return time.time() - self.last_used

    def owns_server(self):
        return self._owns_process and self.process is not None and self.process.poll() is None

    def unload(self):
        """Free the model's memory (GPU/RAM). The next request loads it again."""
        with self._lock:
            if not self.owns_server():
                return False
            with self._conn_lock:
                self.stop()
            return True

    def chat_completion(self, messages, temperature=0.0, max_tokens=512, top_k=20, top_p=0.9, seed=None):
        """Run one chat completion over a keep-alive connection. Returns the reply text."""
        payload = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_k": top_k,
            "top_p": top_p,
            "stream": False,
            "cache_prompt": True,  # reuse the system prompt's KV cache between requests
        }
        if seed is not None:
            payload["seed"] = seed
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Connection": "keep-alive"}
        self.last_used = time.time()

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
                    # Stale keep-alive socket or the server restarted: reconnect once.
                    self._close_conn()
                    if attempt == 1:
                        raise ConnectionError("The AI engine is not responding.")
                    continue
                if res.status == 200:
                    self.last_used = time.time()
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
    """Singleton getter. Passing a different model_profile swaps the running model."""
    global _default_engine
    with _engine_lock:
        if _default_engine is None:
            p = model_profile or load_config().get("model_profile") or "3b"
            _default_engine = EmbeddedEngine(port=port, model_profile=p)
        elif model_profile is not None and _default_engine.model_profile != model_profile:
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
        t0 = time.time()
        reply = engine.chat_completion(
            messages=[
                {"role": "system", "content": "You are a precise proofreader."},
                {"role": "user", "content": "Your welcome."},
            ],
            max_tokens=32,
        )
        print(f"Reply in {(time.time() - t0) * 1000:.1f}ms: {reply!r}")
    finally:
        engine.stop()
