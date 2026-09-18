<p align="center">
  <img src="docs/banner.png" alt="Fixelect: fix and polish your writing in every app, privately" width="100%">
</p>

<p align="center">
  <a href="https://github.com/Bosithonn/fixelect/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/Bosithonn/fixelect?style=flat-square&color=3D7BFF&label=release"></a>
  <a href="https://github.com/Bosithonn/fixelect/releases"><img alt="Downloads" src="https://img.shields.io/github/downloads/Bosithonn/fixelect/total?style=flat-square&color=3D7BFF"></a>
  <a href="https://github.com/Bosithonn/fixelect/actions/workflows/release.yml"><img alt="Build" src="https://img.shields.io/github/actions/workflow/status/Bosithonn/fixelect/release.yml?branch=main&style=flat-square&label=build"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-FF5C6C?style=flat-square"></a>
</p>

<p align="center">
  <a href="https://github.com/Bosithonn/fixelect/releases/latest/download/FixelectSetup.exe"><img alt="Download for Windows" src="https://img.shields.io/badge/Download_for_Windows-3D7BFF?style=for-the-badge"></a>
  &nbsp;
  <a href="https://github.com/Bosithonn/fixelect/releases/latest/download/Fixelect.dmg"><img alt="Download for macOS (preview)" src="https://img.shields.io/badge/macOS_preview-FF5C6C?style=for-the-badge"></a>
  <br>
  <sub>Windows 10 / 11 (64-bit) · macOS 11+ on Apple Silicon (preview) · Free, no account</sub>
</p>

> [!WARNING]
> **The macOS version is a work in progress and not ready for everyday use yet.** It installs and opens, but we are still fixing major problems. The Windows version is the stable one. If you try it on a Mac, please [report what goes wrong](https://github.com/Bosithonn/fixelect/issues).

<br>

Select text in any app, press a shortcut, and Fixelect fixes it in place. The AI model runs on your computer, so your writing never leaves it.

```
Its been a long day, and i cant seem too focus on the the task.
                     ↓  double-tap Alt
It's been a long day, and I can't seem to focus on the task.
```

## Shortcuts

| | Windows | macOS | |
| :--- | :--- | :--- | :--- |
| **Fix** | Double-tap `Alt` | Double-tap `⌥ Option` | Typos, spelling and grammar. Your words and voice stay. |
| **Polish** | Double-tap `Ctrl` | Double-tap `⇧ Shift` | A clearer rewrite, shown as a preview first. |
| **Quick actions** | `Ctrl + Alt + Space` | `⌃ ⌥ Space` | A menu: **Translate**, other Polish styles and **your own actions**. |

You can change both in Settings.

<p align="center">
  <img src="docs/polish-preview.png" alt="The Polish preview with five styles" width="640">
</p>
<p align="center">
  <img src="docs/result-card.png" alt="The result card with one-click Undo" width="298">
</p>

## Why Fixelect

- **Private.** Everything runs offline on your computer. No account, no cloud, no telemetry.
- **Works everywhere.** Browsers, email, Slack, Word, Google Docs, Notion. Bold, links and fonts are kept.
- **Your call.** Preview before replacing, and **Undo** in one click.
- **Translate and your own actions.** One shortcut opens a menu: translate into another language, or run actions you write yourself, like "Bullet points", "Summarize" or "Reply politely". All offline.
- **Five polish styles.** Professional, Friendly, Concise, Formal and Shorter, plus your own note like "Use British spelling".
- **Many languages.** English, Spanish, French, German, Portuguese, Italian, Russian and Ukrainian. Uzbek (beta) with the optional Gemma 4 model.
- **Free and open source** under the MIT License.

<p align="center">
  <img src="docs/settings.png" alt="Fixelect settings" width="560">
</p>

## Install

**Windows** (10 / 11, 64-bit)
1. Click **Download for Windows**. Fixelect is new and not code-signed yet, so Edge may say *"FixelectSetup.exe isn't commonly downloaded"*. Point at the download, click **⋯** → **Keep** → **Show more** → **Keep anyway**. In Chrome, click **Keep**.
2. Open `FixelectSetup.exe`. If Windows says *"Windows protected your PC"*, click **More info** → **Run anyway**.
3. Follow the installer. No administrator rights are needed.

`Fixelect.dmg` is the Mac version; Windows can't open it.

**macOS** (Apple Silicon, preview: not ready for everyday use yet)
1. Open `Fixelect.dmg` and drag Fixelect to Applications.
2. Open Fixelect. When macOS says it can't verify the app, click **Done**.
3. Go to **System Settings → Privacy & Security**, scroll down and click **Open Anyway** next to Fixelect.
4. Open Fixelect again and allow **Accessibility** when asked. Fixelect lives in the menu bar, not the Dock.

Or skip steps 2 and 3 by pasting this into Terminal:

```bash
xattr -dr com.apple.quarantine /Applications/Fixelect.app && open /Applications/Fixelect.app
```

On first launch, Fixelect downloads the AI model you choose. The recommended one, Qwen 2.5 3B, is 2 GB. Each download is checked against its official SHA-256.

The installers aren't code-signed yet, which is why those warnings appear. Every release file has a `.sha256` checksum next to it.

<details>
<summary><b>Run from source</b></summary>

<br>

Python 3.11 or newer.

```bash
cd Windows          # or: cd MacOS
pip install -r requirements.txt
python fixelect.py  # or: python3 fixelect_mac.py
```

Tests that need no model:

```bash
python tests/test_guard.py
python tests/test_text.py
```

`Windows/` and `MacOS/` hold each app; `shared/` holds the code both use. Releases are built by [GitHub Actions](.github/workflows/release.yml).

</details>

## Privacy

Fixelect only goes online to download the model you pick and, unless you turn it off, to check GitHub once a day for updates. Your text is never sent anywhere. See the [privacy policy](PRIVACY_POLICY.md).

## License

[MIT](LICENSE) © 2026 Bositxon Erkinxonov. Third-party notices are in [LICENSE.txt](LICENSE.txt).

Issues and pull requests are welcome.
