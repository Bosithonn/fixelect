import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";
import { pageMetadata } from "@/lib/metadata";
import { legal, links, site } from "@/lib/site";

export const metadata: Metadata = pageMetadata({
  title: "Privacy policy",
  description:
    "Fixelect runs entirely on your device. Your text is never sent anywhere, and there is no account, telemetry or tracking.",
  path: "/privacy",
});

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy policy"
      intro="Fixelect is built on one principle: your words, documents and messages are private and belong to you. This page covers the Fixelect app and this website."
    >
      <h2>The short version</h2>
      <ul>
        <li>Fixelect runs entirely on your device. Your text is never sent anywhere.</li>
        <li>There is no account, no telemetry, no analytics and no advertising.</li>
        <li>
          The app goes online for two things only: to download the AI model you choose and, unless you turn it off, to
          check for updates.
        </li>
        <li>This website has no accounts, forms, cookies or trackers.</li>
      </ul>

      <h2>The Fixelect app</h2>

      <h3>Your text stays on your device</h3>
      <ul>
        <li>Fixelect never sends your text, clipboard contents or system information to the cloud.</li>
        <li>
          All AI processing, grammar correction and dictionary checks run locally, through an engine built into the app
          (llama-server) that listens only on <code>127.0.0.1</code>, your own computer.
        </li>
        <li>Fixelect needs no account, no login, no API key and no subscription.</li>
      </ul>

      <h3>No telemetry, no keystroke logging</h3>
      <ul>
        <li>Fixelect contains no tracking scripts, analytics SDKs, advertising beacons or telemetry.</li>
        <li>
          Fixelect does not log keystrokes. It reads only the text you explicitly select and ask it to process with its
          shortcuts.
        </li>
        <li>
          <strong>History</strong> is on by default and can be turned off. So that you can get an original back after
          Undo is gone, Fixelect keeps your last 30 changes (the text before and after, the app&apos;s name and the
          time) in <code>history.json</code> on your computer. It is never sent anywhere and is not included in
          &ldquo;Copy diagnostics&rdquo;. In Settings, History, turning it off stops saving new changes and &ldquo;Clear
          history&rdquo; deletes the file.
        </li>
        <li>
          The local log file (<code>logs/fixelect.log</code>) records only errors and events such as &ldquo;model
          unloaded&rdquo;, never your text. &ldquo;Copy diagnostics&rdquo; in the Help tab puts your settings and that
          log on your clipboard, and only when you click it. Your custom style note and protected words are not
          included.
        </li>
      </ul>

      <h3>Clipboard and selection</h3>
      <ul>
        <li>
          When you use a shortcut, Fixelect briefly uses the system clipboard to read the text you highlighted (plain
          and, to keep formatting, its rich HTML or RTF version) and pastes the corrected version back. Your previous
          clipboard contents are restored afterwards.
        </li>
        <li>
          Fixelect&apos;s temporary clipboard entries are marked so that Windows clipboard history, cloud clipboard and
          macOS clipboard managers skip them.
        </li>
        <li>Apart from History, Fixelect does not write your text to files on disk.</li>
      </ul>

      <h3>Files Fixelect keeps on your computer</h3>
      <p>
        Fixelect stores its files in <code>%LOCALAPPDATA%\Fixelect\</code> on Windows and{" "}
        <code>~/Library/Application Support/Fixelect/</code> on a Mac. When Fixelect is installed from the Microsoft
        Store, Windows keeps this folder in the app&apos;s own private storage.
      </p>
      <ul>
        <li>
          <code>config.json</code>: your preferences (model, shortcuts, polish style, the optional style note you write,
          the apps Fixelect is turned off in, update and memory settings).
        </li>
        <li>
          <code>words.txt</code>: the protected words you add.
        </li>
        <li>
          <code>history.json</code>: your recent changes, while History is on.
        </li>
        <li>
          <code>speed.json</code>: how fast the AI model answers on this computer (numbers and dates only, never your
          text), so Fixelect can suggest a smaller model if yours is too slow.
        </li>
        <li>
          <code>prompt_cache/</code>: the AI engine&apos;s working memory for Fixelect&apos;s own built-in instructions
          and a fixed test sentence, saved so the model is ready faster after it reloads. It never contains your text:
          Fixelect checks this before keeping the file and deletes it otherwise.
        </li>
        <li>
          <code>logs/</code>: the error log described above.
        </li>
        <li>
          <code>models/</code>: the open-source model file you downloaded during setup.
        </li>
      </ul>

      <h3>Network activity</h3>
      <p>Your text never leaves your device. Fixelect makes only these network requests:</p>
      <ul>
        <li>
          <strong>Model download.</strong> When you choose a model, its open-source weights are downloaded once from
          Hugging Face and checked against their published SHA-256 checksum.
        </li>
        <li>
          <strong>Update check.</strong> On by default; turn it off under General, Check for updates. At most once a
          day, Fixelect sends one anonymous request to the public GitHub releases API (
          <code>api.github.com/repos/Bosithonn/fixelect/releases/latest</code>) to see whether a newer version exists.
          It sends no identifiers, text or usage data. On Windows, if you click &ldquo;Install update&rdquo;, the new
          installer is downloaded from GitHub and checked against its published SHA-256 checksum before it runs.
          Versions installed from the Microsoft Store do not make this check: the Store delivers their updates.
        </li>
      </ul>
      <p>
        As with any download, the service you download from sees the request itself, including your IP address, and
        handles it under its own privacy policy. The AI engine ships inside the app, so with updates turned off Fixelect
        runs entirely in airplane mode.
      </p>

      <h3>Open source</h3>
      <p>
        Fixelect is open source. You are free to{" "}
        <a href={links.github} target="_blank" rel="noopener" className="text-link">
          read the source code
        </a>
        , monitor its network traffic or inspect what it writes to disk.
      </p>

      <h2>This website</h2>
      <ul>
        <li>
          {new URL(site.url).host} is a static website. It has no accounts, no forms, no cookies, no analytics and no
          advertising trackers.
        </li>
        <li>Its fonts, images and video are served by the site itself, not by third-party services.</li>
        <li>
          Like every website, the server that delivers these pages
          {legal.websiteHost ? ` (operated by ${legal.websiteHost})` : ""} receives standard request data, such as your
          IP address, in order to respond.
        </li>
        <li>
          Links to the Microsoft Store, GitHub and Hugging Face take you to services with their own privacy policies.
        </li>
        <li>If you email us, we receive your address and whatever you choose to write.</li>
      </ul>

      <h2>Changes to this policy</h2>
      <p>If this policy changes, the new version is published on this page with a new date.</p>

      <h2>Contact</h2>
      <p>
        Questions about privacy? Write to{" "}
        <a href={`mailto:${site.contactEmail}`} className="text-link">
          {site.contactEmail}
        </a>{" "}
        or open an issue on{" "}
        <a href={links.issues} target="_blank" rel="noopener" className="text-link">
          GitHub
        </a>
        .
      </p>
      {legal.postalAddress ? <p>{legal.postalAddress}</p> : null}
    </LegalPage>
  );
}
