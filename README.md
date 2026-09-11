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
| **macOS** | Drag-and-Drop DMG | [**Fixelect.dmg**](https://github.com/Bosithonn/fixelect/releases/latest) | macOS 11.0+ on Apple Silicon (M1–M4). Intel Macs: run from source. |

Every download has a `.sha256` checksum next to it. Builds are code-signed (Windows) and notarized (macOS) when the release pipeline has signing certificates configured.

---

## ⚡ Key Capabilities

### 1. Instant Global Triggers & Customization
- **Effortless Double-Taps (Default on Windows & macOS)**:
  - Double-tap `Alt` (`Alt Alt` on Windows) or `⌥ Option` (`⌥ ⌥` on Mac) → Instant Grammar & Typo Fix
  - Double-tap `Ctrl` (`Ctrl Ctrl` on Windows) or `⌃ Control` (`⌃ ⌃` on Mac) → Polish, with a preview first
  - `Ctrl + Alt + Q` (Windows) or the menu bar icon (Mac) → Quit
- **Flexible Presets & Full Customization**:
  - Double-Tap Modifiers (Fastest, 1-hand thumb triggers)
  - `Alt + Space` / `⌥ Space` quick combos
  - Classic 3-Key (`Ctrl + Alt + F` / `Ctrl + Alt + P`)
  - Remap to any custom key combination anytime via the visual Settings Dashboard.

### 2. Fix and Polish
- **Fix**: Corrects typos, run-on words (`tobehonest` → `to be honest`), punctuation, agreement and homophones (`your/you're`, `their/there/they're`) while keeping your voice, slang, bullet points and code.
- **Polish**: Rewrites in the style you pick — Professional, Friendly, Concise, Formal or Shorter — plus your own style note ("Use British spelling"). A preview shows the result first: Enter replaces, R tries another version, Esc cancels. A meaning guard refuses rewrites that answer, translate or change who does what.
- **Languages**: English, Spanish, French, German, Portuguese, Italian, Russian and Ukrainian. Other languages are left untouched with a clear message.

### 3. Feedback you can trust
- A small card near your text shows progress and the result ("Fixed 3 words") with one-click **Undo**, and says exactly why nothing changed (nothing selected, language not supported, app turned off…).
- **Formatting is kept**: bold, links and fonts survive in Word, Outlook, Google Docs, Gmail and Notion.
- **Long text** is processed in chunks with a progress bar; Esc cancels.
- **Per-app off switch**: terminals and password managers are off by default; add any app in General.
- **Help tab** with "Why wasn't my text fixed?", an interactive first-run tutorial and "Copy diagnostics".

### 4. Local Hardware Acceleration (Zero Dependencies)
- **Zero Cloud, Zero Subscriptions**: Powered by embedded `llama-server` running quantized GGUF models locally on `127.0.0.1`.
- **Apple Silicon Metal**: Full GPU offloading (`-ngl 99`) on M1/M2/M3/M4 chips with sub-second response times.
- **Windows Acceleration**: Automatic detection of NVIDIA CUDA GPU, Vulkan, and AVX2 CPU SIMD instructions.
- **Smart Model Setup**: Built-in setup wizard downloads and switches models (0.5B to 7B), each verified against its official SHA-256.
- **Frees memory when idle**: the model is unloaded after 10 minutes without use (configurable) and reloads in seconds.
- **Updates**: a daily check against GitHub releases (can be turned off); Windows installs the verified update in one click.

### 5. Native Desktop Experience
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
├── shared/                  # Code used by both apps (one copy, no drift)
│   ├── check_guard.py       # Prompts, guard rules, consensus, polish styles
│   ├── languages.py         # Language detection and per-language prompts
│   ├── chunking.py          # Long text: chunks, progress, cancel
│   ├── richtext.py          # Keeps formatting (HTML / RTF) when replacing text
│   ├── ui.py, ui_kit.py     # Dashboard, setup, tutorial and components
│   ├── updater.py           # Update check and verified download
│   ├── diagnostics.py       # "Copy diagnostics" report (never includes your text)
│   ├── version.py           # App version and release location
│   └── data/                # Dictionary, protected words, shorthand
│
├── Windows/                 # Native Windows Application
│   ├── resources/           # Fluent dark assets, app icon, bundled engine
│   ├── tools/               # Engine, clipboard, hotkeys, status card, tray, per-app detection
│   ├── fixelect.py          # Main daemon & Win32 global hotkeys
│   ├── Fixelect.spec        # PyInstaller packaging configuration
│   ├── installer.iss        # Inno Setup 7 installer script
│   └── requirements.txt     # Windows dependencies
│
├── MacOS/                   # Native macOS Application
│   ├── resources/           # Apple ICNS icon, template menu bar icons
│   ├── tools/               # Hotkeys, NSPasteboard, Metal engine, native status panel
│   ├── fixelect_mac.py      # Main daemon & event tap triggers
│   ├── Fixelect_Mac.spec    # PyInstaller bundle specification
│   ├── build_dmg.sh         # Builds the app with its engine inside, signs, notarizes, DMG
│   ├── entitlements.plist   # Hardened runtime permissions
│   └── requirements.txt     # macOS dependencies
│
├── tests/                   # Model-free tests (CI) and accuracy benchmarks
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

### Tests
```bash
python tests/test_guard.py          # guard rules (no model needed)
python tests/test_text.py           # rich text, chunking, languages, styles
python tests/accuracy_benchmark.py  # English accuracy with a downloaded model
python tests/multilingual_benchmark.py
```

---

## 🔒 Privacy Guarantee

Fixelect is engineered with strict zero-telemetry principles:
1. **Your text never leaves your computer**: the AI model runs on local loopback (`127.0.0.1`). The only network requests are the one-time model download and an optional, anonymous daily update check — see [PRIVACY_POLICY.md](PRIVACY_POLICY.md).
2. **No Data Retention**: Text passed through the engine is processed in RAM and never written to disk or logs.
3. **Open Source**: Every line of code is inspectable under the MIT License.

---

## 📄 License & Attribution

- **Author**: Bositxon Erkinxonov
- **License**: MIT License. See [LICENSE](LICENSE).

