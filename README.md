# Fixelect

**Fixelect** is an ultra-fast, 100% offline, privacy-first AI desktop assistant that fixes grammar, spelling, typos, and style directly inside any app with a single global shortcut or effortless double-tap. Nothing ever leaves your machine.

Select some text anywhere — browser, email, Slack, Telegram, Notes, Microsoft Office, code editor — press your shortcut, and it is instantly replaced with the refined version.

```
Its been a long day, and i cant seem too focus on the the task.
      ↓  Alt Alt (Win) or ⌥ ⌥ (Mac)
It's been a long day, and I can't seem to focus on the task.
```

---

## 🚀 Downloads (Latest Release)

Pre-built, standalone installers are automatically generated for every release:

| Platform | Format | Package | Requirements |
| :--- | :--- | :--- | :--- |
| **Windows** | Portable Installer | [**FixelectSetup.exe**](https://github.com/Bosithonn/fixelect/releases/latest) | Windows 10 / 11 (64-bit) |
| **macOS** | Drag-and-Drop DMG | [**Fixelect.dmg**](https://github.com/Bosithonn/fixelect/releases/latest) | macOS 11.0+ (Apple Silicon M1–M4 & Intel) |

---

## ⚡ Key Capabilities

### 1. Instant Global Triggers & Customization
- **Effortless Double-Taps (Default on Windows & macOS)**:
  - Double-tap `Alt` (`Alt Alt` on Windows) or `⌥ Option` (`⌥ ⌥` on Mac) → Instant Grammar & Typo Fix
  - Double-tap `Ctrl` (`Ctrl Ctrl` on Windows) or `⌃ Control` (`⌃ ⌃` on Mac) → Executive & Professional Polish
  - `Ctrl + Alt + Q` (Windows) or the menu bar icon (Mac) → Quit
- **Flexible Presets & Full Customization**:
  - Double-Tap Modifiers (Fastest, 1-hand thumb triggers)
  - `Alt + Space` / `⌥ Space` quick combos
  - Classic 3-Key (`Ctrl + Alt + F` / `Ctrl + Alt + P`)
  - Remap to any custom key combination anytime via the visual Settings Dashboard.

### 2. Dual-Mode Correction Engine
- **Proofread Mode**: Corrects typos, run-on words (`tobehonest` → `to be honest`), punctuation, and homophones (`your/you're`, `their/there/they're`) while preserving 100% of your authentic voice, slang, bullet points, and code fragments.
- **Executive Polish Mode**: Elevates tone and diction into articulate, boardroom-ready English without truncating nuances or lists.

### 3. Local Hardware Acceleration (Zero Dependencies)
- **Zero Cloud, Zero Subscriptions**: Powered by embedded `llama-server` running quantized GGUF models locally on `127.0.0.1`.
- **Apple Silicon Metal**: Full GPU offloading (`-ngl 99`) on M1/M2/M3/M4 chips with sub-second response times.
- **Windows Acceleration**: Automatic detection of NVIDIA CUDA GPU, Vulkan, and AVX2 CPU SIMD instructions.
- **Smart Model Setup**: Built-in interactive setup wizard to download and switch models (0.5B, 1.5B, or 3B parameters).

### 4. Native Desktop Experience
- **Windows**: Windows 11 Fluent Dark interface, Per-Monitor High-DPI V2 ClearType rendering, and system tray integration.
- **macOS**: Native Aqua Dark SF Pro interface, menu bar status item, and guided Accessibility permissions helper.

---

## 🏗️ Project Architecture

```
Fixelect/
├── .github/
│   └── workflows/
│       └── release.yml      # Multi-platform CI/CD for Windows .exe and macOS .dmg
│
├── Windows/                 # Native Windows Application
│   ├── resources/           # Fluent dark assets, app icon, bundled engine
│   ├── tools/               # Guard validation, hardware detection, downloader, UI
│   ├── fixelect.py          # Main daemon & Win32 global hotkeys
│   ├── Fixelect.spec        # PyInstaller packaging configuration
│   ├── installer.iss        # Inno Setup 7 installer script
│   └── requirements.txt     # Windows dependencies
│
├── MacOS/                   # Native macOS Application
│   ├── resources/           # Apple ICNS icon, template menu bar icons
│   ├── tools/               # Accessibility input monitor, NSPasteboard, Metal engine, UI
│   ├── fixelect_mac.py      # Main daemon & event tap triggers
│   ├── Fixelect_Mac.spec    # PyInstaller bundle specification
│   ├── build_dmg.sh         # Standalone drag-and-drop DMG packaging script
│   ├── entitlements.plist   # Hardened runtime permissions
│   └── requirements.txt     # macOS dependencies
│
├── LICENSE                  # MIT License
├── LICENSE.txt              # Attribution & license notice
└── PRIVACY_POLICY.md        # 100% Local & Zero-Telemetry Privacy Guarantee
```

---

## 💻 Running from Source

### Windows
```bash
cd Windows
pip install -r requirements.txt
python fixelect.py
```

### macOS
```bash
cd MacOS
pip install -r requirements.txt
python3 fixelect_mac.py
```

---

## 🔒 Privacy Guarantee

Fixelect is engineered with strict zero-telemetry principles:
1. **No External Network Calls**: The AI model runs entirely on local loopback (`127.0.0.1`).
2. **No Data Retention**: Text passed through the engine is processed in RAM and never written to disk or logs.
3. **Open Source**: Every line of code is inspectable under the MIT License.

---

## 📄 License & Attribution

- **Author**: Bositxon Erkinxonov
- **License**: MIT License. See [LICENSE](LICENSE).

