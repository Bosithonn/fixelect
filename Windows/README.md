# Fixelect — Windows Platform

This directory contains the complete Windows implementation, runtime sidecar, UI, packaging, and installer assets for **Fixelect**.

## Directory Structure

```
Windows/
├── resources/
│   ├── bin/                 # Embedded llama-server sidecar binaries & Vulkan DLLs
│   └── *.png, *.ico         # Application icons, branding, and tray assets
├── tools/
│   ├── apps_win.py          # Which app is in front (per-app off switch, focus hand-back)
│   ├── clipboard_win.py     # 64-bit-safe clipboard: snapshot/restore, rich HTML, private writes
│   ├── config.py            # User configuration, paths, and Windows registry startup
│   ├── downloader.py        # Resumable, checksum-verified model downloader
│   ├── engine.py            # Embedded llama-server lifecycle, idle unload
│   ├── hardware.py          # Zero-subprocess Win32 ctypes CUDA / Vulkan / CPU detection
│   ├── hotkey_win.py        # Double-tap Alt / Ctrl detection
│   ├── hud_win.py           # On-screen status card and Polish preview
│   └── tray.py              # System tray menu
├── dist/                    # Built distribution outputs (PyInstaller folder + FixelectSetup.exe)
├── fixelect.py              # Main Windows application entry point & Win32 hotkey loop
├── Fixelect.spec            # PyInstaller build specification
├── file_version_info.txt    # Windows PE version and author metadata
├── installer.iss            # Inno Setup installer script (version / signing via ISCC defines)
└── run_python.bat           # 1-click developer launcher script

The guard, prompts, languages, chunking, rich text, dashboard UI, updater and
word lists are shared with macOS and live in ../shared.
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
