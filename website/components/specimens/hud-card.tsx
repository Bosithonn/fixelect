import type { ReactNode } from "react";

const tones = {
  success: "bg-green",
  polish: "bg-coral",
} as const;

/**
 * Fixelect's on-screen card: the small status card that appears next to
 * your text after a shortcut. Wording and colours match the app.
 */
export function HudCard({
  tone = "success",
  title,
  detail,
  action,
  className = "",
}: {
  tone?: keyof typeof tones;
  title: string;
  detail?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`hud ${className}`}>
      <span
        aria-hidden="true"
        className={`flex size-5 flex-none items-center justify-center self-start rounded-full ${tones[tone]} mt-0.5`}
      >
        <svg
          viewBox="0 0 12 12"
          className="size-3"
          fill="none"
          stroke="var(--color-bg)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M2.5 6.4l2.3 2.3 4.7-5" />
        </svg>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-[0.9375rem] font-semibold text-ink">{title}</span>
        {detail ? <span className="mt-0.5 block text-[0.8125rem] text-ink-2">{detail}</span> : null}
      </span>
      {action ? <span className="ml-1 flex-none">{action}</span> : null}
    </div>
  );
}
