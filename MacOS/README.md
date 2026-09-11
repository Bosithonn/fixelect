# Fixelect — macOS Platform (Phase 5)

**Fixelect** is an ultra-fast, 100% offline AI grammar correction and executive polish utility engineered specifically for macOS.

* **Author**: Bositxon Erkinxonov
* **License**: MIT / Apache 2.0 (Open Source)
* **Privacy**: 100% Local Inference • Zero Cloud Transmission • Zero Telemetry

---

## ⚡ Key Highlights on macOS

1. **Apple Silicon Hardware Acceleration (Metal Performance Shaders)**:
   - Uses native `llama-server` compiled with Metal backend support (`-ngl 99`).
   - Harnesses M1, M2, M3, and M4 Unified Memory Architecture (UMA) for sub-150ms instant inference.

2. **Frictionless Triggers & Hotkey Customization**:
   - **Default Fix Mode**: **Double-tap Option (`⌥ ⌥`)**
     Effortless 1-finger activation. Fixes typos, mis-keys, and grammar instantly while preserving 100% of your voice and jargon.
   - **Professional Polish Mode**: **Double-tap Control (`⌃ ⌃`)**
     Transforms rough notes into articulate, executive prose with smooth transitions and active voice.
   - **Quit Fixelect**: from the menu bar icon (a global ⌘⌥Q would also quit the app you are typing in)
   - **Full Customization**: Choose between Double-Tap, `Option + Space`, Classic 3-Key (`⌥⌘F`), or define your own custom shortcuts directly inside the Dashboard!

3. **Menu Bar Extra Item**:
   - Lives discreetly in the top-right macOS Menu Bar with an adaptive Light/Dark template icon.
   - 1-click access to Settings, Live Playground, Model Switcher, and Whitelist Manager.

4. **Protected Terms & Custom Whitelist**:
   - Curated vocabulary (`words.txt`) ensures names, proprietary terms, and company acronyms are never altered or deleted by the AI.

5. **Subtle Native Audio Feedback**:
   - Plays Apple's crisp system sound chimes (`afplay /System/Library/Sounds/Tink.aiff`) when text is corrected.

---

## 🚀 Getting Started

### Option 1: Run From Source

```bash
# 1. Clone repository and navigate to MacOS directory
cd Fixelect/MacOS

# 2. Install dependencies
pip install -r requirements.txt  # (pynput, Pillow, rumps)

# 3. Launch Fixelect daemon
python3 fixelect_mac.py
```

### Option 2: Command Line Options

```bash
python3 fixelect_mac.py --dashboard        # Open Settings & Live Playground
python3 fixelect_mac.py --setup            # Open Model Setup & Hardware Downloader
python3 fixelect_mac.py --test             # Run automated self-test suite (10/10 checks)
python3 fixelect_mac.py "some text to fix" # Direct CLI fix
python3 fixelect_mac.py -p "rough draft"   # Direct CLI polish
```

---

## 🔐 macOS Accessibility Permissions

To detect the double-tap triggers and automatically paste corrected text into your active app, macOS requires Accessibility authorization:

1. When first launched, macOS displays a prompt: *"Fixelect would like to control this computer using accessibility features."*
2. Click **Open System Settings**.
3. Navigate to **Privacy & Security → Accessibility**.
4. Toggle the switch next to **Fixelect** (or **Terminal** if running from source) to **ON**.

---

## 📦 Building `.app` and `.dmg` Packages

### 1. Build Standalone `Fixelect.app` Bundle
```bash
pyinstaller --clean Fixelect_Mac.spec -y
# Output: dist/Fixelect.app
```

### 2. Build Drag-and-Drop `Fixelect.dmg` Installer
```bash
chmod +x build_dmg.sh
./build_dmg.sh
# Output: dist/Fixelect.dmg
```

---

## 📁 Architecture Overview

```
MacOS/
├── fixelect_mac.py                # Menu bar daemon: hotkeys, engine, status panel, Polish preview
├── Fixelect_Mac.spec              # PyInstaller macOS bundle specification
├── build_dmg.sh                   # Builds the app with its engine inside, signs, notarizes, DMG
├── entitlements.plist             # Hardened runtime permissions
├── tools/                         # Pasteboard, hotkeys, Metal engine, native HUD, app detection
└── resources/
    ├── app_icon.icns              # Retina multi-resolution macOS ICNS icon
    ├── status_bar_template.png    # 18x18 Menu Bar adaptive icon
    ├── status_bar_template@2x.png # 36x36 Retina Menu Bar icon
    ├── brand_logo.png             # Brand artwork
    └── PRIVACY_POLICY.md          # Privacy policy

Shared with Windows (../shared): guard and prompts, languages, chunking, rich text,
dashboard UI, updater, diagnostics, dictionary and word lists.
```
