# Microsoft Store listing for Fixelect

Everything to paste into Partner Center. Screenshots are next to this file
(1920 × 1080): `1-fix.png`, `2-polish.png`, `3-quick-actions.png`, `4-private.png`.

## Properties

| Field | Value |
|---|---|
| Category | Productivity |
| Privacy policy URL | https://github.com/Bosithonn/fixelect/blob/main/PRIVACY_POLICY.md |
| Website | https://github.com/Bosithonn/fixelect |
| Support contact | https://github.com/Bosithonn/fixelect/issues |
| Pricing | Free |
| Markets | All |

## Store listing (English)

**Product name:** Fixelect

**Description**

```
Fix and polish your writing in any app with one shortcut. Fixelect runs its AI entirely on your computer: your text never leaves it, and there is no account, subscription or cloud.

Select text in any app — email, chat, browser, Word, Notion, a code editor — and double-tap Alt. The typos and grammar mistakes are fixed right where you typed them, and a small card shows exactly which words changed, with Undo one click away.

• Fix: spelling, typos, grammar and punctuation. Your words and your voice stay.
• Polish: a clearer rewrite in five styles (Professional, Friendly, Concise, Formal, Shorter), shown as a preview first.
• Quick actions: double-tap Shift to translate, turn text into bullet points, summarize, or run actions you write yourself.
• No selecting needed: just typed a line? Press the shortcut and Fixelect fixes it up to the cursor.
• History: your last changes stay on your computer, so you can get an original back later.
• Many languages: English, Spanish, French, German, Portuguese, Italian, Russian and Ukrainian, plus Uzbek (beta).
• Keeps formatting: bold, links and fonts survive in Word, Outlook, Gmail and Google Docs.

Private by design
The AI model is downloaded once from Hugging Face and checked against its official checksum. After that, Fixelect works in airplane mode. It never logs your keystrokes, never sends your text anywhere and contains no tracking.

Fixelect is free and open source (MIT License).
```

**Short description**

```
Fix and polish your writing in any app with one shortcut. Offline AI: your text never leaves your computer.
```

**Product features** (one per line in Partner Center)

```
Fixes typos, spelling and grammar in any app with one shortcut
Polish in five styles, with a preview before anything is replaced
Translate, bullet points, summaries and your own quick actions
Runs 100% offline: your text never leaves your computer
Shows exactly which words changed, with one-click Undo
Keeps bold, links and fonts in Word, Outlook and Gmail
Works in 8 languages, plus Uzbek (beta)
Free and open source, no account or subscription
```

**Search terms** (up to 7)

```
grammar checker
spell checker
offline AI
proofreading
writing assistant
translate
private
```

**Copyright:** © 2026 Bositxon Erkinxonov

## Submission options

**Restricted capability justification** (asked because of `runFullTrust`):

```
Fixelect is a classic desktop productivity app. It needs full trust to register global keyboard shortcuts, to read and replace the text the user has selected in any application (through the clipboard, restored afterwards), and to run its bundled on-device AI engine (llama-server) locally. It does not log keystrokes and sends no user data anywhere; see the privacy policy.
```

**Notes for certification:**

```
On first launch Fixelect asks the user to download an AI model (1–3 GB) from Hugging Face; the download is verified against its SHA-256. To test: open Notepad, type "i cant beleive teh wether", select it and double-tap Alt (or press Ctrl+Alt+F after choosing Settings → Shortcuts → Classic). Fixelect lives in the system tray.
```

## Age rating questionnaire (IARC)

- Category: Productivity / utility, not a game.
- Violence, sexual content, profanity, drugs, gambling: none.
- Users can interact or share content with each other: **No**.
- Shares the user's location: **No**.
- Digital purchases: **No**.
- Unrestricted internet access (a web browser): **No**. The app only downloads the AI model file.

Expected rating: 3+ / Everyone.
