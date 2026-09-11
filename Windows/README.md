# Fixelect — Windows Platform

This directory contains the complete Windows implementation, runtime sidecar, UI, packaging, and installer assets for **Fixelect**.

## Directory Structure

```
Windows/
├── resources/
│   ├── bin/                 # Embedded llama-server sidecar binaries & Vulkan DLLs
│   └── *.png, *.ico         # Application icons, branding, and tray assets
├── tools/
│   ├── check_guard.py       # Core AI prompt engine, dual-mode consensus guard & diffing
│   ├── config.py            # User configuration, paths, and Windows registry startup
│   ├── downloader.py        # Resumable model downloader with progress callback
│   ├── engine.py            # Embedded llama-server process lifecycle manager
│   ├── hardware.py          # Zero-subprocess Win32 ctypes CUDA / Vulkan / CPU detection
│   ├── tray.py              # Windows System Tray menu with dynamic model switching
│   └── ui.py                # Fluent Windows 11 dark UI, Setup window & live playground
├── dist/                    # Built distribution outputs
│   ├── Fixelect/            # Standalone PyInstaller folder distribution
│   └── FixelectSetup.exe    # Inno Setup single-file installer (40 MB)
├── dictionary.txt           # Curated English dictionary for guard verification
├── freq.txt                 # Frequency corpus for spelling verification
├── shorthand.txt            # Pre-expansion dictionary (e.g. tbh -> to be honest)
├── words.txt                # User-protected terms whitelist
├── fixelect.py              # Main Windows application entry point & Win32 hotkey loop
├── Fixelect.spec            # PyInstaller build specification
├── file_version_info.txt    # Windows PE version and author metadata
├── installer.iss            # Inno Setup 7 installer compiler script
└── run_python.bat           # 1-click developer launcher script
```

## Running in Development

1. Ensure Python 3.10+ is installed:
   ```bash
   pip install -r requirements.txt
   ```
2. Launch Fixelect:
   ```bash
   python fixelect.py
   # Or double-click run_python.bat
   ```
3. Run automated self-tests:
   ```bash
   python fixelect.py --test
   ```

## Windows Hotkeys

| Trigger (default) | Action |
|---|---|
| **Alt, Alt** (double-tap) | **Fix**: typos, glued words and grammar, your voice preserved |
| **Ctrl, Ctrl** (double-tap) | **Polish**: rewrite into clear, professional English |
| **Ctrl + Alt + F / P** | Always-available backup for Fix / Polish |
| **Ctrl + Alt + Q** | Quit Fixelect |

Other presets (Alt + Space, Classic Ctrl + Alt + F/P) and fully custom shortcuts can be
recorded in **Dashboard → Shortcuts**. Conflicts with other apps are reported there.

## Building Production Packages

### 1. Standalone Executable (`Fixelect.exe`)
```bash
pyinstaller Fixelect.spec --clean
```
Output is generated in `dist/Fixelect/Fixelect.exe`.

### 2. Inno Setup Installer (`FixelectSetup.exe`)
Compile `installer.iss` using Inno Setup:
```bash
iscc installer.iss
```
Output is generated at `dist/FixelectSetup.exe`.
