# Fixelect Privacy Policy & Security Architecture

**Last Updated**: September 2026  
**Author**: Bositxon Erkinxonov  

Fixelect was engineered from day one on a fundamental principle: **Your words, documents, and communications are strictly private and belong exclusively to you.**

Unlike cloud-based writing assistants that stream your keystrokes and sensitive text to remote third-party servers, Fixelect is **100% offline and runs completely on your device**.

---

## 1. Zero Cloud Transmission
- Fixelect **never** sends your text, clipboard contents, or system information to the cloud.
- All neural network inference, grammar correction, and dictionary checks execute locally on your machine via an embedded inference engine (llama-server) bound strictly to 127.0.0.1 (localhost loopback).
- Fixelect requires no account, no login, no API key, and no subscription.

## 2. Zero Telemetry & Keystroke Logging
- Fixelect **does not** contain any tracking scripts, analytics SDKs, advertising beacons, or telemetry loggers.
- Fixelect **does not** log keystrokes. It only reads text that you explicitly select and command it to process with its shortcuts (double-tap Alt/Ctrl, Option/Control on macOS, or the shortcuts you choose).
- **History (on by default, can be turned off).** So you can get an original back after Undo is gone, Fixelect keeps your last 30 changes (the text before and after, the app's name and the time) in `history.json` on your computer. It is never sent anywhere and is not included in "Copy diagnostics". Turn it off or clear it in Settings → History: turning it off stops saving new changes, and "Clear history" deletes the file.
- The local log file (`logs/fixelect.log`) records only errors and events such as "model unloaded", never your text. "Copy diagnostics" in the Help tab puts your settings and that log on your clipboard, and only when you click it; your custom style note and protected words are not included.

## 3. Clipboard & Selection Handling
- When you invoke a shortcut, Fixelect briefly uses the system clipboard to read your highlighted text (plain and, to keep formatting, its rich HTML/RTF version) and pastes the corrected version back. Your previous clipboard contents are restored afterwards.
- Fixelect's temporary clipboard entries are marked so Windows clipboard history, cloud clipboard and macOS clipboard managers skip them.
- Apart from History (above), Fixelect does not write your text to files on disk.

## 4. Local Files & Storage
Fixelect keeps its files on your computer, in `%LOCALAPPDATA%\Fixelect\` on Windows and `~/Library/Application Support/Fixelect/` on a Mac:
- config.json: your preferences (model, shortcuts, polish style, the optional style note you write, apps Fixelect is turned off in, update and memory settings).
- words.txt: the protected words you add.
- history.json: your recent changes, while History is on (see section 2).
- logs/: the error log described above.
- models/: The open-source GGUF neural network weights file downloaded directly from Hugging Face during initial setup.

## 5. Network Activity
Your text never leaves your device. Fixelect makes only these network requests:
- **Model download**: when you choose a model, its open-source GGUF weights are downloaded once from Hugging Face and checked against their published SHA-256 checksum.
- **Update check** (on by default, can be turned off in General → Check for updates): at most once a day, one anonymous request to the public GitHub releases API (`api.github.com/repos/Bosithonn/fixelect/releases/latest`) to see whether a newer version exists. It sends no identifiers, text or usage data. On Windows, if you click "Install update", the new installer is downloaded from GitHub and checked against its published SHA-256 checksum before it runs.

The AI engine itself ships inside the app. With updates turned off, Fixelect runs entirely in airplane mode.

## 6. Open Source Transparency
Fixelect is built on open standards and transparent open-source software. You are free to audit the source code, monitor local network traffic with Wireshark/Fiddler, or inspect local disk writes.

---

### Questions or Inquiries
If you have any questions or feedback regarding Fixelect's privacy practices, please contact the project maintainers via the Fixelect GitHub repository.
