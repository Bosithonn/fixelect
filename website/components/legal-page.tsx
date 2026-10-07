import type { ReactNode } from "react";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { legal } from "@/lib/site";

/** Shared frame for the long-form legal pages. */
export function LegalPage({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
  return (
    <>
      <SiteHeader />
      <main id="main" className="shell pb-28 pt-[clamp(3.5rem,8vw,6rem)]">
        <article className="max-w-[44rem]">
          <h1 className="text-[clamp(2.25rem,4vw+1rem,3.5rem)] font-bold leading-[1.05] tracking-[-0.032em]">
            {title}
          </h1>
          <p className="mt-4 text-[0.9375rem] text-ink-3">Last updated: {legal.lastUpdated}</p>
          <p className="lead mt-8">{intro}</p>
          <div className="prose-legal">{children}</div>
        </article>
      </main>
      <SiteFooter />
    </>
  );
}
