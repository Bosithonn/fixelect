"""
Hardware detection and Apple Silicon Metal acceleration profiler for macOS.
Detects:
- Apple Silicon (M1, M2, M3, M4, Pro, Max, Ultra) vs Intel Core Macs
- Unified Memory Architecture (UMA) RAM capacity via sysctl
- Metal acceleration availability
- Optimal model recommendation for macOS
"""

import os
import platform
import subprocess
import sys


def detect_mac_hardware() -> dict:
    """
    Detect macOS hardware specifications using sysctl and system_profiler.
    Returns a normalized hardware dictionary.
    """
    arch = platform.machine().lower()  # 'arm64' or 'x86_64'
    is_apple_silicon = (arch == "arm64")

    chip_name = "Apple Silicon" if is_apple_silicon else "Intel Mac"
    ram_gb = 16.0
    vram_gb = 0.0

    # 1. Query sysctl for CPU brand and total RAM
    try:
        res = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                             capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            chip_name = res.stdout.strip()
    except Exception:
        pass

    if chip_name == "Apple Silicon" or not chip_name:
        try:
            res = subprocess.run(["sysctl", "-n", "hw.model"],
                                 capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout.strip():
                chip_name = f"Mac ({res.stdout.strip()})"
        except Exception:
            pass

    try:
        res = subprocess.run(["sysctl", "-n", "hw.memsize"],
                             capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout.strip():
            bytes_val = int(res.stdout.strip())
            ram_gb = round(bytes_val / (1024 ** 3), 1)
    except Exception:
        pass

    # In Apple Silicon Unified Memory Architecture, GPU shares the entire RAM pool
    if is_apple_silicon:
        backend = "metal"
        gpu_name = f"{chip_name} (Unified Metal GPU)"
        vram_gb = ram_gb  # GPU has full access to unified memory
        is_gpu = True
    else:
        backend = "cpu"
        gpu_name = f"{chip_name} (CPU Mode)"
        vram_gb = 0.0
        is_gpu = False

    # 2. Intelligent Model Recommendation based on Unified Memory
    # Gemma 4 E2B fixes the most in tests/accuracy_benchmark.py and covers the
    # most languages; it needs about 3.5 GB of memory while it runs.
    if is_apple_silicon:
        rec_model = "gemma4-e2b" if ram_gb >= 8 else "1.5b"
    else:
        # Intel Mac fallback
        rec_model = "gemma4-e2b" if ram_gb >= 16 else "1.5b"

    return {
        "is_gpu": is_gpu,
        "is_apple_silicon": is_apple_silicon,
        "backend": backend,
        "device_name": gpu_name,
        "gpu_name": gpu_name,
        "ram_gb": ram_gb,
        "vram_gb": vram_gb,
        "recommended_model": rec_model,
        "arch": arch,
    }


def detect_hardware() -> dict:
    """Universal alias compatible with Windows interface."""
    return detect_mac_hardware()


if __name__ == "__main__":
    hw = detect_mac_hardware()
    print("Detected macOS Hardware:")
    for k, v in hw.items():
        print(f"  {k}: {v}")
