import type { ReactNode } from "react";

/**
 * A plain light app window standing in for "any app": the place where the
 * user is typing when Fixelect's dark cards appear on top.
 */
export function HostWindow({
  title,
  children,
  className = "",
}: {
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`overflow-hidden rounded-lg border border-paper-line bg-paper font-ui text-paper-ink shadow-[0_30px_60px_rgb(0_0_0/0.45)] ${className}`}
    >
      <div className="flex h-9 items-center justify-between gap-4 bg-paper-bar pl-3.5 pr-1 text-[0.8125rem] text-paper-ink-2">
        <span className="truncate">{title}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 96 20"
          className="h-5 w-24 flex-none"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.1"
        >
          <path d="M11 10.5h9M43.5 6.5h8v8h-8zM76 6l8.5 8.5M84.5 6L76 14.5" />
        </svg>
      </div>
      <div className="px-5 pb-6 pt-5 text-[1.0625rem] leading-[1.6] sm:px-7 sm:pt-6 sm:text-[1.125rem]">{children}</div>
    </div>
  );
}

/** Text shown as selected inside a HostWindow. */
export function Selected({ children }: { children: ReactNode }) {
  return <span className="box-decoration-clone bg-paper-select py-[0.14em]">{children}</span>;
}
