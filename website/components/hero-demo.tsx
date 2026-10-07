"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { HudCard } from "@/components/specimens/hud-card";

/**
 * The headline fixes itself the way Fixelect fixes text in any app:
 * typos, a selection, a double-tap of Alt, and the words are corrected in place.
 * Undo and a real double-tap of Alt both work.
 */

type Phase =
  | "intro" // first paint: typos, waiting for the opening sequence
  | "autoSelected" // opening sequence: selection sweeps, key caps press
  | "typo" // after Undo
  | "selected" // the visitor asked for a fix
  | "fixed";

type Flash = "undone" | "looksGood" | null;

type Token = { kind: "word"; text: string; wrong?: string } | { kind: "break"; show: "mobile" | "desktop" | "always" };

const word = (text: string, wrong?: string): Token => ({ kind: "word", text, wrong });
const lineBreak = (show: "mobile" | "desktop" | "always"): Token => ({ kind: "break", show });

const HEADLINE: Token[] = [
  word("Fix"),
  word("and"),
  word("polish", "poilsh"),
  lineBreak("mobile"),
  word("your", "yuor"),
  lineBreak("desktop"),
  word("writing", "wirting"),
  word("in"),
  lineBreak("mobile"),
  word("every", "evrey"),
  word("app."),
  lineBreak("always"),
  word("Privately.", "Privatley."),
];

const SENTENCE = "Fix and polish your writing in every app. Privately.";

const BREAK_CLASS = {
  mobile: "sm:hidden",
  desktop: "max-sm:hidden",
  always: "",
} as const;

const DOUBLE_TAP_MS = 450;

/** Dip a key cap, as if it had just been pressed. */
function pressCap(cap: HTMLElement | null | undefined) {
  if (!cap || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  cap.animate(
    [
      { transform: "translateY(0)", backgroundColor: "var(--color-surface-4)" },
      { transform: "translateY(2px)", backgroundColor: "var(--color-accent-press)", offset: 0.35 },
      { transform: "translateY(0)", backgroundColor: "var(--color-surface-4)" },
    ],
    { duration: 260, easing: "ease-out" },
  );
}

export function HeroDemo() {
  const [phase, setPhase] = useState<Phase>("intro");
  const [flash, setFlash] = useState<Flash>(null);
  const [interacted, setInteracted] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const capRefs = useRef<(HTMLElement | null)[]>([]);
  const inView = useRef(true);

  // Each phase schedules the next one, so leaving a phase cancels what it started.
  useEffect(() => {
    if (phase === "intro") {
      const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const id = window.setTimeout(() => setPhase(reduced ? "fixed" : "autoSelected"), reduced ? 0 : 800);
      return () => window.clearTimeout(id);
    }
    if (phase === "autoSelected") {
      const ids = [
        window.setTimeout(() => pressCap(capRefs.current[0]), 640),
        window.setTimeout(() => pressCap(capRefs.current[1]), 820),
        window.setTimeout(() => setPhase("fixed"), 1120),
      ];
      return () => ids.forEach((id) => window.clearTimeout(id));
    }
    if (phase === "selected") {
      const id = window.setTimeout(() => setPhase("fixed"), 540);
      return () => window.clearTimeout(id);
    }
  }, [phase]);

  // Like the app's card, short messages leave by themselves.
  useEffect(() => {
    if (!flash) return;
    const id = window.setTimeout(() => setFlash(null), flash === "undone" ? 1800 : 2200);
    return () => window.clearTimeout(id);
  }, [flash]);

  const runShortcut = () => {
    setInteracted(true);
    if (phase === "typo") {
      setFlash(null);
      setPhase("selected");
    } else if (phase === "fixed") {
      setFlash("looksGood");
    }
  };

  const undo = () => {
    setInteracted(true);
    setPhase("typo");
    setFlash("undone");
  };

  const onDoubleTap = useEffectEvent(runShortcut);

  // A real double-tap of Alt, the way the app listens for it.
  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;

    const observer = new IntersectionObserver(([entry]) => {
      inView.current = entry.isIntersecting;
    });
    observer.observe(root);

    let lastTap = 0;
    let cleanPress = false;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Alt") {
        cleanPress = false;
        lastTap = 0;
        return;
      }
      if (event.repeat) return;
      cleanPress = !event.ctrlKey && !event.shiftKey && !event.metaKey;
      // Keep a lone Alt from moving focus to the browser's menu between taps.
      if (inView.current) event.preventDefault();
    };

    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key !== "Alt" || !inView.current) return;
      event.preventDefault();
      if (!cleanPress) return;
      const isSecondTap = lastTap > 0 && event.timeStamp - lastTap < DOUBLE_TAP_MS;
      pressCap(capRefs.current[isSecondTap ? 1 : 0]);
      if (isSecondTap) {
        lastTap = 0;
        onDoubleTap();
      } else {
        lastTap = event.timeStamp;
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      observer.disconnect();
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const cssPhase = phase === "autoSelected" ? "selected" : phase;
  const showsTypos = phase === "typo";

  return (
    <div ref={rootRef} className="hero" data-phase={cssPhase}>
      <h1 className="hero-title" aria-label={SENTENCE}>
        <span aria-hidden="true" className="hero-selection">
          {HEADLINE.map((token, i) =>
            token.kind === "break" ? (
              <br key={i} className={BREAK_CLASS[token.show]} />
            ) : (
              <span key={i}>
                {token.wrong ? (
                  <span className="hero-word" data-wrong={token.wrong}>
                    <span className="hero-word-right">{token.text}</span>
                  </span>
                ) : (
                  token.text
                )}{" "}
              </span>
            ),
          )}
        </span>
        <span aria-hidden="true" className="hero-frame">
          <i />
          <i />
          <i />
          <svg viewBox="0 0 24 24">
            <path
              d="M4 2v17.2l4.6-4.1 3 7 3-1.3-3-6.8H18L4 2z"
              fill="#f2f4f8"
              stroke="var(--color-bg)"
              strokeWidth="1.2"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </h1>

      <div className="hero-status mt-6 flex flex-col gap-3 sm:mt-9 sm:flex-row sm:items-center sm:gap-6">
        <button
          type="button"
          onClick={runShortcut}
          aria-label={showsTypos ? "Fix the headline" : "Run Fix on the headline"}
          className="group -m-1.5 flex w-fit items-center gap-3 rounded-xl p-1.5 text-left"
        >
          <span className="flex gap-1.5 text-[0.9375rem]">
            {[0, 1].map((i) => (
              <kbd
                key={i}
                ref={(node) => {
                  capRefs.current[i] = node;
                }}
                className="keycap transition-colors group-hover:border-accent-hover"
              >
                Alt
              </kbd>
            ))}
          </span>
          <span className="text-[0.9375rem] leading-snug text-ink-2">
            {showsTypos ? (
              <>
                <span className="[@media(hover:none)]:hidden">Double-tap Alt, or click, to fix it</span>
                <span className="[@media(hover:hover)]:hidden">Tap to fix it</span>
              </>
            ) : (
              "Double-tap Alt"
            )}
          </span>
        </button>

        <div className="flex min-h-[4.25rem] items-center" aria-live={interacted ? "polite" : "off"}>
          {showsTypos ? (
            flash === "undone" ? (
              <HudCard title="Undone" detail="Your original text is back." />
            ) : (
              <p className="text-[0.9375rem] text-ink-3">The typos are back. Your turn.</p>
            )
          ) : flash === "looksGood" && phase === "fixed" ? (
            <HudCard title="Looks good" detail="No changes needed." />
          ) : (
            <HudCard
              title="Fixed 5 words"
              detail="poilsh → polish · yuor → your · +3 more"
              action={
                <button type="button" onClick={undo} className="hud-button">
                  Undo
                </button>
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
