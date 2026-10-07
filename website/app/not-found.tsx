import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = {
  title: "Page not found",
  robots: { index: false },
};

export default function NotFound() {
  return (
    <>
      <SiteHeader />
      <main id="main" className="shell flex flex-1 flex-col justify-center py-28">
        <h1 className="text-[clamp(2.25rem,4vw+1rem,3.5rem)] font-bold leading-[1.05] tracking-[-0.032em]">
          This page isn&apos;t here.
        </h1>
        <p className="lead mt-5 max-w-[34rem]">
          The address may be mistyped, which is one mistake Fixelect can&apos;t reach. The home page has everything.
        </p>
        <Link
          href="/"
          className="mt-9 inline-flex h-[3.25rem] w-fit items-center rounded-[10px] bg-accent-fill px-6 text-[1.0625rem] font-semibold text-white transition-colors hover:bg-accent-fill-hover"
        >
          Go to the home page
        </Link>
      </main>
      <SiteFooter />
    </>
  );
}
