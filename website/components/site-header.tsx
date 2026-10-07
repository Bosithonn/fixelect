import Link from "next/link";
import { links, navigation } from "@/lib/site";
import { Logo } from "@/components/logo";
import { MobileNav } from "@/components/mobile-nav";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line bg-bg">
      <div className="shell flex h-16 items-center justify-between gap-6">
        <Link href="/" aria-label="Fixelect home" className="-ml-1 flex items-center rounded-md p-1">
          <Logo eager className="h-7 w-auto" />
        </Link>

        <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-lg px-3 py-2 text-[0.9375rem] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
            >
              {item.label}
            </Link>
          ))}
          <a
            href={links.github}
            target="_blank"
            rel="noopener"
            className="rounded-lg px-3 py-2 text-[0.9375rem] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
          >
            GitHub
          </a>
        </nav>

        <div className="flex items-center gap-2">
          <Link
            href="/#download"
            className="inline-flex h-10 items-center rounded-[10px] bg-accent-fill px-4 text-[0.9375rem] font-semibold text-white transition-colors hover:bg-accent-fill-hover"
          >
            Download
          </Link>
          <MobileNav />
        </div>
      </div>
    </header>
  );
}
