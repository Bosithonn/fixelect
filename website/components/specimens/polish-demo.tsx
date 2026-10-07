"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";
import { HostWindow, Selected } from "@/components/specimens/host-window";

/**
 * The Polish preview with its five styles. The draft and every rewrite are
 * the app's own worked examples for each style (shared/check_guard.py).
 */

type Part = { text: string; changed?: boolean };

const kept = (text: string): Part => ({ text });
const changed = (text: string): Part => ({ text, changed: true });

const DRAFT = "can u check the numbers before monday i need them for the board call with david";

const STYLES: { id: string; label: string; note: string; parts: Part[] }[] = [
  {
    id: "professional",
    label: "Professional",
    note: "Clear, articulate business writing.",
    parts: [
      changed("Could you please"),
      kept(" check the numbers before "),
      changed("Monday? I"),
      kept(" need them for the board call with "),
      changed("David."),
    ],
  },
  {
    id: "friendly",
    label: "Friendly",
    note: "Warm and natural, like a helpful colleague.",
    parts: [
      changed("Could you"),
      kept(" check the numbers before "),
      changed("Monday? I"),
      kept(" need them for the board call with "),
      changed("David. Thanks so much!"),
    ],
  },
  {
    id: "concise",
    label: "Concise",
    note: "Direct and to the point. No filler.",
    parts: [
      changed("Please"),
      kept(" check the numbers before "),
      changed("Monday; I"),
      kept(" need them for the board call with "),
      changed("David."),
    ],
  },
  {
    id: "formal",
    label: "Formal",
    note: "Polite and official, for formal letters.",
    parts: [
      changed("Could you please review"),
      kept(" the "),
      changed("figures"),
      kept(" before "),
      changed("Monday? I require"),
      kept(" them for the board call with "),
      changed("David."),
    ],
  },
  {
    id: "shorter",
    label: "Shorter",
    note: "About half the length, every fact kept.",
    parts: [
      changed("Please"),
      kept(" check the numbers before "),
      changed("Monday; I"),
      kept(" need them for "),
      changed("David's board call."),
    ],
  },
];

export function PolishDemo() {
  const [index, setIndex] = useState(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const baseId = useId();
  const style = STYLES[index];

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const last = STYLES.length - 1;
    const next =
      event.key === "ArrowRight"
        ? (index + 1) % STYLES.length
        : event.key === "ArrowLeft"
          ? (index + last) % STYLES.length
          : event.key === "Home"
            ? 0
            : event.key === "End"
              ? last
              : null;
    if (next === null) return;
    event.preventDefault();
    setIndex(next);
    tabRefs.current[next]?.focus();
  };

  return (
    <div>
      <HostWindow title="New message - Mail">
        <p className="pb-24 sm:pb-28">
          <Selected>{DRAFT}</Selected>
        </p>
      </HostWindow>

      <div className="relative z-10 -mt-24 px-2 sm:-mt-28 sm:px-8">
        <div className="mx-auto max-w-[35rem] rounded-xl border border-line-strong bg-surface p-4 font-ui shadow-[0_24px_50px_rgb(0_0_0/0.5)] sm:p-5">
          <div className="flex items-center gap-2.5 text-[0.9375rem] font-semibold text-ink">
            <span aria-hidden="true" className="size-2 rounded-full bg-coral" />
            Polish
          </div>

          <div
            role="tablist"
            aria-label="Polish style"
            onKeyDown={onKeyDown}
            className="-mx-1 mt-3 flex flex-wrap gap-x-1 gap-y-0.5"
          >
            {STYLES.map((item, i) => (
              <button
                key={item.id}
                ref={(node) => {
                  tabRefs.current[i] = node;
                }}
                type="button"
                role="tab"
                id={`${baseId}-tab-${item.id}`}
                aria-selected={i === index}
                aria-controls={`${baseId}-panel`}
                tabIndex={i === index ? 0 : -1}
                onClick={() => setIndex(i)}
                className={`h-9 rounded-[9px] px-3 text-[0.875rem] font-semibold transition-colors ${
                  i === index ? "bg-surface-3 text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>

          <div
            role="tabpanel"
            id={`${baseId}-panel`}
            aria-labelledby={`${baseId}-tab-${style.id}`}
            className="mt-3 min-h-[5.75rem] rounded-[10px] border border-line bg-field px-3.5 py-3 text-[0.9375rem] leading-[1.55] text-ink sm:min-h-[4.5rem]"
          >
            {style.parts.map((part, i) => (
              <span key={i} className={part.changed ? "text-coral" : undefined}>
                {part.text}
              </span>
            ))}
          </div>

          <div aria-hidden="true" className="mt-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
            <span className="text-[0.75rem] text-ink-3">Enter replace · R try again · Esc cancel</span>
            <span className="ml-auto flex gap-2">
              <span className="hud-button">Try again</span>
              <span className="hud-button border-transparent bg-coral text-white">Replace</span>
            </span>
          </div>
        </div>
      </div>

      <p className="mt-5 px-2 text-[0.9375rem] text-ink-2 sm:px-8" aria-live="polite">
        <span className="font-semibold text-ink">{style.label}.</span> {style.note}
      </p>
    </div>
  );
}
