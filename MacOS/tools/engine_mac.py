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
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time

from config_mac import get_config_dir, get_resource_path, load_config, get_lock_path, get_runtime_path, log_error
from version import APP_VERSION
from hardware_mac import detect_mac_hardware
from downloader_mac import resolve_model, get_bin_dir

DEFAULT_PORT = 18888
CONTEXT_SIZE = 4096
REQUEST_TIMEOUT = 180
LOAD_TIMEOUT = 120
TRUST_SECONDS = 10.0   # a server we own that answered this recently is not probed again


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
        self.last_used = time.time()
        self.hw = detect_mac_hardware()
        self.backend_label = "METAL" if self.hw.get("is_apple_silicon") else "CPU"
        self.publish = False  # set by the daemon: write runtime.json for window processes
        self._timings, self._timings_lock = [], threading.Lock()
        self._cold = True   # the first answer after the model loads is always slower
        self._ok_at = 0.0       # monotonic time the server we own last answered
        self._stopped = False   # we stopped our own server (idle unload): nothing to probe
        # Set by the pipeline: one fixed warm-up request whose prompt cache is kept
        # on disk (see _prime). None: no prompt cache.
        self.primer = None
        self._slot_dir = None
        self._slot_model = None
        self._last_total = None  # tokens in the last answer's context (prompt + reply)
        atexit.register(self.stop)

    def _note_timings(self, data):
        """Keep how fast this answer came out (shared/speedwatch.py decides if that is slow)."""
        t = data.get("timings") or {}
        if t.get("predicted_per_second"):
            with self._timings_lock:
                self._timings.append({"tps": t["predicted_per_second"], "n": t.get("predicted_n", 0),
                                      "cold": self._cold})
                del self._timings[:-50]
        self._cold = False

    def take_timings(self):
        """The timings noted since the last call, oldest first."""
        with self._timings_lock:
            out, self._timings = self._timings, []
        return out

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

    def is_healthy(self, port=None, timeout=0.8) -> bool:
        data = self._get_json("/health", port, timeout=timeout)
        ok = bool(data) and data.get("status") == "ok"
        if ok and self._owns_process and port in (None, self.port):
            self._ok_at = time.monotonic()
        return ok

    def _serves(self, model_path, port=None):
        props = self._get_json("/props", port, timeout=1.5) or {}
        path = props.get("model_path") or ""
        return not path or pathlib.Path(path).name == pathlib.Path(model_path).name

    def is_running(self):
        if self._owns_process:
            if self.process is None or self.process.poll() is not None:
                return False
            if time.monotonic() - self._ok_at < TRUST_SECONDS:
                return True   # several checks per fix: skip the HTTP round trip
        elif self._stopped:
            return False      # we unloaded our own server: nothing to probe
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
        """(path, pinned): pinned is True for the llama.cpp build Fixelect ships or
        downloads itself, whose command-line flags are known."""
        arch_dir = "darwin-arm64" if self.hw["is_apple_silicon"] else "darwin-x86_64"
        bundled = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent.parent)) / "llama"
        candidates = [
            (bundled / "llama-server", True),              # shipped inside Fixelect.app (Contents/Frameworks/llama)
            (get_resource_path(f"resources/bin/{arch_dir}/llama-server"), True),
            (get_resource_path("resources/bin/llama-server"), True),
            (pathlib.Path("/opt/homebrew/bin/llama-server"), False),
            (pathlib.Path("/usr/local/bin/llama-server"), False),
        ]
        try:
            candidates += [(p, True) for p in sorted(get_bin_dir().rglob("llama-server"))]  # fetch_metal_engine
        except Exception:
            pass
        which = shutil.which("llama-server")
        if which:
            candidates.append((pathlib.Path(which), False))
        for p, pinned in candidates:
            if p.is_file() and os.access(p, os.X_OK):
                return p, pinned
        return None, False

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
                self._stopped = False
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
            # If the daemon unloaded an idle model, SIGUSR2 asks it to load again.
            if not self.publish:
                dpid = daemon_pid()
                if dpid and not self._attach(model_path, 0):
                    try:
                        os.kill(dpid, signal.SIGUSR2)
                    except Exception:
                        pass
                if self._attach(model_path, 90 if dpid else 0):
                    return True
            if self.is_healthy() and self._serves(model_path):
                self._owns_process = False
                self._stopped = False
                return True

            server_bin, pinned = self._find_llama_server()
            if not server_bin and self.hw.get("is_apple_silicon"):
                from downloader_mac import fetch_metal_engine
                server_bin, pinned = fetch_metal_engine(), True
            if not server_bin:
                if shutil.which("ollama") or pathlib.Path("/opt/homebrew/bin/ollama").is_file():
                    return False  # caller falls back to Ollama
                raise FileNotFoundError("The Fixelect engine is missing. Reinstall Fixelect or run `brew install llama.cpp`.")

            self._close_conn()
            base = [str(server_bin), "-m", str(model_path), "--host", self.host,
                    "-c", str(CONTEXT_SIZE), "-np", "1", "--log-disable", "--jinja"]
            self._slot_dir, self._slot_model = None, model_path
            if pinned:
                # Keep Gemma 4's whole sliding-window cache so the prompt prefix stays
                # reusable: without it the second fix after every polish re-read the
                # entire prompt. Only for our pinned build (an old Homebrew one may not
                # know the flags and would refuse to start).
                base.append("--swa-full")
                self._slot_dir = self._prompt_cache_dir()
                if self._slot_dir:
                    base += ["--slot-save-path", str(self._slot_dir)]
            cores = os.cpu_count() or 4
            # One thread per performance core generates fastest; reading the prompt
            # is compute-bound and gains from every core.
            threads = ["-t", str(max(1, cores // 2)), "-tb", str(cores)]
            # Metal first; if the GPU cannot start (virtual Macs, driver trouble) use the CPU.
            attempts = [["-ngl", "99"], ["-ngl", "0"] + threads] if self.hw["is_apple_silicon"] else [threads]
            env = os.environ.copy()
            env["PATH"] = str(server_bin.parent) + os.pathsep + env.get("PATH", "")
            env["DYLD_LIBRARY_PATH"] = str(server_bin.parent) + os.pathsep + env.get("DYLD_LIBRARY_PATH", "")
            env["GGML_METAL_DISABLE_CAPTURE"] = "1"

            for n, extra in enumerate(attempts):
                last = n == len(attempts) - 1
                self.port = self._free_port()
                cmd = base + ["--port", str(self.port)] + extra
                print(f"  [Engine] Starting llama-server on :{self.port} [{self.backend_label}] {' '.join(extra)}")
                self.process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.DEVNULL, cwd=str(server_bin.parent), env=env,
                                                start_new_session=False)
                self._owns_process = True
                self._stopped = False
                t0 = time.time()
                while time.time() - t0 < timeout:
                    if self.process.poll() is not None:
                        self._owns_process = False
                        if last:
                            raise RuntimeError(f"llama-server exited with code {self.process.returncode}")
                        print("  [Engine] GPU start failed - retrying on the CPU")
                        log_error(f"llama-server exited with code {self.process.returncode} on Metal; using the CPU")
                        break
                    if self.is_healthy():
                        print(f"  [Engine] Model loaded in {time.time() - t0:.1f}s")
                        self._cold = True
                        # Before runtime.json names the port: window processes can't
                        # send a request of their own in between.
                        self._prime()
                        if self.process.poll() is not None:
                            self._owns_process = False
                            raise RuntimeError(f"llama-server exited with code {self.process.returncode} "
                                               "while loading its prompt cache")
                        if self.publish:
                            try:
                                get_runtime_path().write_text(json.dumps(
                                    {"port": self.port, "pid": os.getpid(), "model_path": str(model_path)}))
                            except Exception:
                                pass
                        return True
                    time.sleep(0.2)
                else:
                    self.stop()
                    if last:
                        raise TimeoutError(f"llama-server was not ready within {timeout:.0f}s")
                    # Metal can hang instead of failing (virtual Macs, a stuck GPU): use the CPU.
                    print("  [Engine] GPU start timed out - retrying on the CPU")
                    log_error(f"llama-server not ready within {timeout:.0f}s on Metal; using the CPU")

    # -- prompt cache on disk --------------------------------------------------------
    # Every fix starts with the same ~550 tokens of instructions and examples.
    # Reading them again after every (re)load, including each wake-up after an idle
    # unload, is the slowest part of the first fix; a saved copy of the engine's
    # cache for them restores in milliseconds. Only the start-up warm-up request is
    # ever saved - never anything the user wrote (checked by its size in tokens).

    @staticmethod
    def _prompt_cache_dir():
        try:
            d = get_config_dir() / "prompt_cache"
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            return None

    def _slot_file(self):
        stem = re.sub(r"[^A-Za-z0-9._-]+", "_", pathlib.Path(str(self._slot_model)).stem)
        return f"{stem}-{APP_VERSION}.slot"

    def _slot(self, action):
        """Save or restore slot 0's prompt cache. The server's JSON answer, or None."""
        conn = http.client.HTTPConnection(self.host, self.port, timeout=60)
        try:
            conn.request("POST", f"/slots/0?action={action}", body=json.dumps({"filename": self._slot_file()}),
                         headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read() or b"{}")
            return data if resp.status == 200 else None
        finally:
            conn.close()

    def _prime(self):
        """Fill the prompt cache right after a load: from the saved copy when there is
        one, otherwise by running the primer once and saving the result."""
        if not self._slot_dir:
            return
        path = self._slot_dir / self._slot_file()
        try:
            if path.is_file():
                if self._slot("restore"):
                    return
                path.unlink(missing_ok=True)   # unreadable (another llama.cpp build?): make a new one
            if self.primer is None:
                return
            self._last_total = None
            self.primer()
            expected = self._last_total
            saved = self._slot("save") or {}
            # The slot holds the last request: the warm-up is prompt + reply - 1
            # tokens. Anything else means another request got in between.
            if not expected or saved.get("n_saved") not in (expected - 1, expected):
                path.unlink(missing_ok=True)
                return
            for old in self._slot_dir.glob("*.slot"):
                if old != path:
                    old.unlink(missing_ok=True)   # one model's cache at a time
        except Exception as e:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            log_error(f"prompt cache skipped: {type(e).__name__}")

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
            self._stopped = True
        self.process = None
        self._owns_process = False
        self._ok_at = 0.0

    # -- inference ---------------------------------------------------------------------

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
        # enable_thinking=False: reasoning models (Gemma 4, Qwen 3) otherwise spend the
        # whole token budget "thinking" and return an empty answer. Ignored by other models.
        payload = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens,
                   "top_k": top_k, "top_p": top_p, "stream": False, "cache_prompt": True,
                   "chat_template_kwargs": {"enable_thinking": False}}
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
                    self._close_conn()
                    if attempt == 1:
                        raise ConnectionError("The AI engine is not responding.")
                    continue
                if res.status == 200:
                    self.last_used = time.time()
                    if self._owns_process:
                        self._ok_at = time.monotonic()
                    data = json.loads(raw.decode("utf-8"))
                    self._last_total = (data.get("usage") or {}).get("total_tokens")
                    self._note_timings(data)
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
