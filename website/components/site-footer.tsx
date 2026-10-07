import Link from "next/link";
import { Logo } from "@/components/logo";
import { links, site } from "@/lib/site";

const COLUMNS = [
  {
    title: "Product",
    items: [
      { label: "How it works", href: "/#shortcuts" },
      { label: "Privacy by design", href: "/#private" },
      { label: "Download", href: "/#download" },
      { label: "Questions", href: "/#faq" },
    ],
  },
  {
    title: "Project",
    items: [
      { label: "Source on GitHub", href: links.github },
      { label: "Releases", href: links.releases },
      { label: "Report a problem", href: links.issues },
      { label: "MIT License", href: links.license },
    ],
  },
  {
    title: "Legal",
    items: [
      { label: "Privacy policy", href: "/privacy" },
      { label: "Terms", href: "/terms" },
      { label: site.contactEmail, href: `mailto:${site.contactEmail}` },
    ],
  },
] as const;

const linkClass = "inline-flex min-h-8 items-center text-ink-2 transition-colors hover:text-ink";

export function SiteFooter() {
  return (
    <footer className="mt-auto border-t border-line">
      <div className="shell grid gap-x-12 gap-y-12 py-16 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <Logo className="h-8 w-auto" />
          <p className="mt-5 max-w-[22rem] text-ink-2">{site.tagline}</p>
        </div>

        <nav aria-label="Footer" className="grid grid-cols-2 gap-x-8 gap-y-10 sm:grid-cols-3 lg:col-span-7">
          {COLUMNS.map((column) => (
            <div key={column.title}>
              <p className="text-[0.9375rem] font-semibold text-ink">{column.title}</p>
              <ul className="mt-3 text-[0.9375rem]">
                {column.items.map((item) => (
                  <li key={item.label}>
                    {item.href.startsWith("/") ? (
                      <Link href={item.href} className={linkClass}>
                        {item.label}
                      </Link>
                    ) : (
                      <a
                        href={item.href}
                        className={`${linkClass} break-all`}
                        {...(item.href.startsWith("http") ? { target: "_blank", rel: "noopener" } : {})}
                      >
                        {item.label}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
      </div>

      <div className="border-t border-line">
        <div className="shell flex flex-col gap-2 py-6 text-[0.875rem] text-ink-3 md:flex-row md:justify-between">
          <p>
            © {site.copyrightYear} {site.owner}. Fixelect is open source under the MIT License.
          </p>
          <p>Microsoft, Windows and Microsoft Store are trademarks of the Microsoft group of companies.</p>
        </div>
      </div>
    </footer>
  );
}
