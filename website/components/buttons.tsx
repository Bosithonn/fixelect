import type { ReactNode } from "react";
import { links } from "@/lib/site";

const base =
  "inline-flex items-center justify-center gap-2.5 rounded-[10px] font-semibold whitespace-nowrap transition-colors duration-150";

const sizes = {
  md: "h-11 px-4 text-[0.9375rem]",
  lg: "h-[3.25rem] px-6 text-[1.0625rem]",
} as const;

type Size = keyof typeof sizes;

/** The primary action everywhere on the site: open Fixelect's Microsoft Store page. */
export function StoreButton({
  size = "lg",
  className = "",
  children = "Get it from Microsoft Store",
}: {
  size?: Size;
  className?: string;
  children?: ReactNode;
}) {
  return (
    <a
      href={links.microsoftStore}
      target="_blank"
      rel="noopener"
      className={`${base} ${sizes[size]} bg-accent-fill text-white hover:bg-accent-fill-hover ${className}`}
    >
      {children}
    </a>
  );
}

export function SecondaryButton({
  href,
  size = "lg",
  className = "",
  children,
}: {
  href: string;
  size?: Size;
  className?: string;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      className={`${base} ${sizes[size]} border border-line-strong bg-surface-3 text-ink hover:bg-surface-4 ${className}`}
    >
      {children}
    </a>
  );
}
