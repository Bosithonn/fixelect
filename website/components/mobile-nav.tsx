"use client";

import Link from "next/link";
import { useEffect, useId, useState } from "react";
import { links, navigation } from "@/lib/site";

/** Menu button and panel for small screens. */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const close = () => setOpen(false);
  const itemClass = "flex min-h-12 items-center rounded-lg px-3 text-[1.0625rem] text-ink hover:bg-surface-2";

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
        className="flex size-10 items-center justify-center rounded-[10px] border border-line-strong bg-surface-3 text-ink hover:bg-surface-4"
      >
        <span className="sr-only">{open ? "Close menu" : "Open menu"}</span>
        <svg
          aria-hidden="true"
          viewBox="0 0 20 20"
          className="size-5"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          strokeLinecap="round"
        >
          {open ? <path d="M5 5l10 10M15 5L5 15" /> : <path d="M3.5 6.5h13M3.5 13.5h13" />}
        </svg>
      </button>

      <nav
        id={panelId}
        aria-label="Main"
        hidden={!open}
        className="absolute inset-x-0 top-full border-b border-line bg-bg px-3 pb-4 pt-2 shadow-[0_24px_40px_rgb(0_0_0/0.5)]"
      >
        <ul>
          {navigation.map((item) => (
            <li key={item.href}>
              <Link href={item.href} onClick={close} className={itemClass}>
                {item.label}
              </Link>
            </li>
          ))}
          <li>
            <a href={links.github} target="_blank" rel="noopener" onClick={close} className={itemClass}>
              GitHub
            </a>
          </li>
        </ul>
      </nav>
    </div>
  );
}
