"""
Hardware detection for Fixelect embedded inference engine.
Detects GPU capabilities (CUDA / Vulkan / AVX2 CPU) and computes optimal inference flags.
Pure Win32 Ctypes implementation — zero subprocesses, zero console window flash.
"""

import ctypes
import functools
import os
import platform
import sys
from ctypes import wintypes


def _get_cuda_info():
    """Query NVIDIA CUDA driver directly via nvcuda.dll without spawning any subprocess."""
    if sys.platform != "win32":
        return None
    try:
        cuda = ctypes.windll.LoadLibrary("nvcuda.dll")
        if cuda.cuInit(0) == 0:
            dev = ctypes.c_int()
            if cuda.cuDeviceGet(ctypes.byref(dev), 0) == 0:
                name_buf = ctypes.create_string_buffer(256)
                cuda.cuDeviceGetName(name_buf, 256, dev)
                name = name_buf.value.decode("utf-8", errors="ignore").strip()
                mem = ctypes.c_size_t()
                cuda.cuDeviceTotalMem_v2(ctypes.byref(mem), dev)
                vram_gb = round(mem.value / (1024 ** 3), 1)
                return {
                    "backend": "cuda",
                    "gpu_name": name or "NVIDIA GeForce GPU",
                    "vram_gb": vram_gb,
                }
    except Exception:
        pass
    return None


def _get_display_devices():
    """Query display controllers via user32.EnumDisplayDevicesW without console flash."""
    if sys.platform != "win32":
        return []
    try:
        class DISPLAY_DEVICEW(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("DeviceName", wintypes.WCHAR * 32),
                ("DeviceString", wintypes.WCHAR * 128),
                ("StateFlags", wintypes.DWORD),
                ("DeviceID", wintypes.WCHAR * 128),
                ("DeviceKey", wintypes.WCHAR * 128),
            ]
        dd = DISPLAY_DEVICEW()
        dd.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        idx = 0
        devices = []
        while ctypes.windll.user32.EnumDisplayDevicesW(None, idx, ctypes.byref(dd), 0):
            if dd.StateFlags & 0x00000004:
                s = dd.DeviceString.strip()
                if s and s not in devices:
                    devices.append(s)
            idx += 1
        return devices
    except Exception:
        return []


def get_gpu_backend():
    """Detect the best available hardware acceleration backend."""
    # 1. NVIDIA CUDA
    cuda_info = _get_cuda_info()
    if cuda_info:
        return "cuda"

    # 2. Vulkan Loader (AMD Radeon, Intel Arc / Iris Xe, etc.)
    try:
        ctypes.windll.LoadLibrary("vulkan-1.dll")
        return "vulkan"
    except Exception:
        pass

    return "cpu"


def get_ram_gb():
    """Detect system physical RAM in gigabytes via Win32 GlobalMemoryStatusEx."""
    if sys.platform == "win32":
        try:
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", wintypes.DWORD),
                    ("dwMemoryLoad", wintypes.DWORD),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                return round(stat.ullTotalPhys / (1024 ** 3), 1)
        except Exception:
            pass

    try:
        import psutil
        return round(psutil.virtual_memory().total / (1024 ** 3), 1)
    except Exception:
        return 8.0


@functools.lru_cache(maxsize=1)
def detect_hardware():
    """Return a comprehensive hardware specification dict for Fixelect, cached for performance."""
    cuda_info = _get_cuda_info()
    cpu_cores = os.cpu_count() or 4
    recommended_threads = max(1, cpu_cores // 2 if cpu_cores > 4 else cpu_cores)
    ram = get_ram_gb()

    if cuda_info:
        backend = "cuda"
        gpu_name = cuda_info["gpu_name"]
        vram = cuda_info["vram_gb"]
    else:
        displays = _get_display_devices()
        gpu_name = displays[0] if displays else None
        backend = get_gpu_backend()
        vram = 0.0
        if not gpu_name:
            gpu_name = f"CPU ({platform.processor() or 'x86_64'})"

    hw = {
        "backend": backend,
        "gpu_name": gpu_name,
        "vram_gb": vram,
        "ram_gb": ram,
        "total_cores": cpu_cores,
        "threads": recommended_threads,
        "is_gpu": backend in ("cuda", "vulkan"),
    }
    hw["recommended_model"] = recommend_model(hw)
    return hw


def recommend_model(hw):
    """
    Recommend the model that fits this computer:
    - A graphics card with >= 3.5 GB, or 12 GB RAM and 6+ cores: Gemma 4 E2B. In
      tests/accuracy_benchmark.py it fixes the most (16/20 hard texts against Qwen
      2.5 3B's 10/20), covers the most languages and is as fast as the 3B, on a
      graphics card and on the processor alike.
    - Anything smaller: Qwen 2.5 1.5B, the fastest.
    """
    if hw["is_gpu"] and hw.get("vram_gb", 0) >= 3.5:
        return "gemma4-e2b"
    elif hw.get("ram_gb", 8) >= 12 and hw.get("total_cores", 4) >= 6:
        return "gemma4-e2b"
    return "1.5b"


def get_llama_args(context_size=2048):
    """Compute optimal llama-server CLI flags based on detected hardware."""
    hw = detect_hardware()
    args = [
        "-c", str(context_size),
        "-np", "1",
        "--host", "127.0.0.1",
    ]

    if hw["is_gpu"]:
        args.extend(["-ngl", "99"])
    else:
        # Generation is memory-bound (about one thread per core is best), but
        # reading the prompt is compute-bound: every logical core reads it ~20%
        # faster, which is most of a fix's wait after a model (re)load.
        args.extend(["-ngl", "0", "-t", str(hw["threads"]), "-tb", str(max(hw["threads"], hw["total_cores"]))])

    return args, hw


if __name__ == "__main__":
    hw = detect_hardware()
    flags, _ = get_llama_args()
    print("Fixelect Hardware Detection:")
    print(f"  Backend : {hw['backend'].upper()}")
    print(f"  Device  : {hw['gpu_name']}")
    print(f"  VRAM    : {hw['vram_gb']} GB")
    print(f"  RAM     : {hw['ram_gb']} GB")
    print(f"  Model   : {hw['recommended_model'].upper()}")
    print(f"  Cores   : {hw['total_cores']} (threads={hw['threads']})")
    print(f"  Flags   : {' '.join(flags)}")
