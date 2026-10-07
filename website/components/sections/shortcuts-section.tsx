import type { ReactNode } from "react";
import { Keycaps } from "@/components/keycaps";
import { HostWindow } from "@/components/specimens/host-window";
import { HudCard } from "@/components/specimens/hud-card";
import { PolishDemo } from "@/components/specimens/polish-demo";
import { QuickMenuSpecimen } from "@/components/specimens/quick-menu";

function Chapter({
  id,
  keys,
  keysLabel,
  title,
  summary,
  points,
  children,
}: {
  id: string;
  keys: readonly string[];
  keysLabel: string;
  title: string;
  summary: string;
  points: readonly string[];
  children: ReactNode;
}) {
  return (
    <article
      aria-labelledby={id}
      className="grid gap-x-12 gap-y-10 border-t border-line py-14 lg:grid-cols-12 lg:py-20"
    >
      <div className="lg:col-span-5 xl:col-span-4">
        <Keycaps keys={keys} label={keysLabel} className="text-[1.0625rem]" />
        <h3 id={id} className="h3 mt-6">
          {title}
        </h3>
        <p className="mt-3 text-ink-2">{summary}</p>
        <ul className="mt-6 space-y-3 text-[0.9375rem] text-ink-2">
          {points.map((point) => (
            <li key={point} className="flex gap-3">
              <span aria-hidden="true" className="mt-[0.68em] h-px w-3 flex-none bg-ink-3" />
              {point}
            </li>
          ))}
        </ul>
      </div>
      <div className="min-w-0 lg:col-span-7 xl:col-span-8 xl:pl-6">{children}</div>
    </article>
  );
}

function FixSpecimen() {
  return (
    <div>
      <HostWindow title="Message to Sarah - Mail">
        <p>Hi Sarah,</p>
        <p className="mt-4 pb-14 sm:pb-12">
          I can&apos;t believe the meeting got moved again. Could you send me the updated agenda until Friday? I&apos;m
          not sure whether the budget was approved.
        </p>
      </HostWindow>
      <div className="relative z-10 -mt-9 flex justify-end px-2 sm:px-8">
        <HudCard
          title="Fixed 5 words"
          detail="beleive → believe · teh → the · +3 more"
          action={
            <span aria-hidden="true" className="hud-button">
              Undo
            </span>
          }
        />
      </div>
    </div>
  );
}

export function ShortcutsSection() {
  return (
    <section id="shortcuts" aria-labelledby="shortcuts-title" className="shell section">
      <div className="max-w-[44rem] pb-14 lg:pb-20">
        <h2 id="shortcuts-title" className="h2">
          A double-tap for each job.
        </h2>
        <p className="lead mt-5">
          Fixelect has no window to switch to. It waits in the system tray until you select some text and tap.
        </p>
      </div>

      <Chapter
        id="fix"
        keys={["Alt", "Alt"]}
        keysLabel="Double-tap Alt"
        title="Fix"
        summary="Typos, spelling, grammar and punctuation, corrected right where you typed them. Your words and your voice stay yours."
        points={[
          "A card next to your text lists the words that changed.",
          "Undo with one click, or with Ctrl+Z in your app.",
          "Nothing selected? Fixelect fixes the line you are typing, up to the cursor.",
          "Bold, links and fonts are kept in Word, Outlook, Gmail and Google Docs.",
        ]}
      >
        <FixSpecimen />
      </Chapter>

      <Chapter
        id="polish"
        keys={["Ctrl", "Ctrl"]}
        keysLabel="Double-tap Ctrl"
        title="Polish"
        summary="A clearer rewrite in the style you choose. You see it as a preview first, and nothing is replaced until you press Enter."
        points={[
          "Five styles. Try each one in the preview.",
          "Add a standing note of your own, such as “Use British spelling”.",
          "Not quite right? Try again gives you another version.",
        ]}
      >
        <PolishDemo />
      </Chapter>

      <Chapter
        id="quick-actions"
        keys={["Shift", "Shift"]}
        keysLabel="Double-tap Shift"
        title="Quick actions"
        summary="One menu for everything else. Translate the selection, polish it in another style, or run an action you wrote yourself."
        points={[
          "Translate into any supported language, right where you type.",
          "Starts with two actions: Bullet points and Summarize.",
          "Write your own in plain words, like “Reply politely”. Each one gets a number in the menu.",
        ]}
      >
        <QuickMenuSpecimen />
      </Chapter>

      <p className="border-t border-line pt-8 text-[0.9375rem] text-ink-2">
        Prefer other keys? Switch to Alt + Space or Ctrl + Alt + F, or record your own shortcuts in Settings.
      </p>
    </section>
  );
}
