import Image from "next/image";
import { StoreButton } from "@/components/buttons";
import { links } from "@/lib/site";
import tile from "@/public/brand/fixelect-tile.png";

const STEPS = [
  "Install Fixelect from the Microsoft Store.",
  "Choose a model. It downloads once, 1 to 3 GB.",
  "Select text in any app and double-tap Alt.",
] as const;

const OTHER_WAYS = [
  {
    title: "Windows installer",
    href: links.windowsInstaller,
    link: "Download FixelectSetup.exe",
    note: "From GitHub. It is not code-signed yet, so Windows may warn you before it runs. Every release file comes with a SHA-256 checksum.",
  },
  {
    title: "macOS preview",
    href: links.macDmg,
    link: "Download Fixelect.dmg",
    note: "For Apple Silicon Macs on macOS 11 or later. Still a work in progress, not ready for everyday use.",
  },
  {
    title: "Source code",
    href: links.github,
    link: "View on GitHub",
    note: "Run it from source with Python 3.11 or newer. Issues and pull requests are welcome.",
  },
] as const;

export function DownloadSection() {
  return (
    <section id="download" aria-labelledby="download-title" className="border-y border-line bg-surface">
      <div className="shell section">
        <div className="grid gap-x-16 gap-y-12 lg:grid-cols-12">
          <div className="lg:col-span-6">
            <Image src={tile} alt="" sizes="88px" className="size-[5.5rem] rounded-[1.25rem]" />
            <h2 id="download-title" className="h2 mt-8">
              Get Fixelect.
            </h2>
            <p className="lead mt-5">Free and open source. No account, no subscription.</p>
            <StoreButton className="mt-9 max-[30rem]:w-full" />
            <p className="mt-4 text-[0.9375rem] text-ink-3">Windows 10 and 11, 64-bit.</p>
          </div>

          <ol className="lg:col-span-6 lg:pt-2">
            {STEPS.map((step, i) => (
              <li
                key={step}
                className="flex items-baseline gap-6 border-t border-line py-6 text-[1.1875rem] leading-snug text-ink last:border-b"
              >
                <span aria-hidden="true" className="w-4 flex-none text-[0.9375rem] text-ink-3 tabular-nums">
                  {i + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>

        <h3 className="mt-20 text-[0.9375rem] text-ink-3 lg:mt-24">Other ways to get it</h3>
        <ul className="mt-5 grid gap-x-12 gap-y-10 border-t border-line pt-8 md:grid-cols-3">
          {OTHER_WAYS.map((way) => (
            <li key={way.title}>
              <p className="font-semibold text-ink">{way.title}</p>
              <p className="mt-2 text-[0.9375rem] text-ink-2">{way.note}</p>
              <a
                href={way.href}
                target="_blank"
                rel="noopener"
                className="text-link mt-3 inline-block text-[0.9375rem]"
              >
                {way.link}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
