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
- Fixelect **does not** log keystrokes. It only reads text that you explicitly select and command it to process by pressing the hotkeys (Ctrl+Alt+F or Ctrl+Alt+P).
- Fixelect does not store history of the text you fix. Once text replacement completes, the text buffer is cleared from memory.

## 3. Clipboard & Selection Handling
- When you invoke a hotkey, Fixelect temporarily uses the Windows OS clipboard API to fetch your highlighted text and pastes back the corrected version.
- Fixelect does not write your text to persistent files on disk.

## 4. Local Files & Storage
Fixelect stores only your non-sensitive application preferences locally on your PC under:
%LOCALAPPDATA%\Fixelect\
- config.json: Selected model profile (e.g., 3B vs 1.5B), sound notification preference, and auto-start preference.
- models/: The open-source GGUF neural network weights file downloaded directly from Hugging Face during initial setup.

## 5. Network Activity
The only network activity Fixelect ever performs is an optional, one-time download of the open-source GGUF model weights from Hugging Face during the initial setup wizard if the model is not already installed. Once downloaded, you can run Fixelect entirely in airplane mode with all internet connections disabled.

## 6. Open Source Transparency
Fixelect is built on open standards and transparent open-source software. You are free to audit the source code, monitor local network traffic with Wireshark/Fiddler, or inspect local disk writes.

---

### Questions or Inquiries
If you have any questions or feedback regarding Fixelect's privacy practices, please contact the project maintainers via the Fixelect GitHub repository.
