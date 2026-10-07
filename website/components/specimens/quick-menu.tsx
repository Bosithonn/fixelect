import { HostWindow, Selected } from "@/components/specimens/host-window";

const ITEMS = [
  { label: "Fix spelling & grammar" },
  { label: "Polish · Professional" },
  { label: "Polish in another style…", submenu: true },
  { label: "Translate…", submenu: true },
  { label: "Bullet points" },
  { label: "Summarize" },
];

/** The quick-action menu as it opens next to the selected text. */
export function QuickMenuSpecimen() {
  return (
    <div>
      <HostWindow title="Message to Sarah - Mail">
        <p className="pb-40 sm:pb-36">
          <Selected>Good morning! I will send you the report tomorrow before the meeting.</Selected>
        </p>
      </HostWindow>

      <div className="relative z-10 -mt-36 flex justify-end px-2 sm:-mt-32 sm:px-8">
        <div className="w-full max-w-[19.5rem] rounded-xl border border-line-strong bg-surface p-2 font-ui shadow-[0_24px_50px_rgb(0_0_0/0.5)]">
          <p className="px-3 pb-1.5 pt-2 text-[0.8125rem] font-semibold text-ink-2">Fixelect</p>
          <ol aria-label="Quick actions">
            {ITEMS.map((item, i) => (
              <li
                key={item.label}
                className={`flex h-10 items-center gap-3.5 rounded-lg px-3 text-[0.9375rem] text-ink ${
                  i === 0 ? "bg-accent-soft" : ""
                }`}
              >
                <span aria-hidden="true" className="w-2 text-[0.8125rem] text-ink-3">
                  {i + 1}
                </span>
                <span className="flex-1">{item.label}</span>
                {item.submenu ? (
                  <svg
                    aria-hidden="true"
                    viewBox="0 0 8 12"
                    className="h-2.5 w-1.5 text-ink-3"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M1.5 1.5L6 6l-4.5 4.5" />
                  </svg>
                ) : null}
              </li>
            ))}
          </ol>
          <p aria-hidden="true" className="px-3 pb-1.5 pt-2.5 text-[0.75rem] text-ink-3">
            1–9 or ↑↓ Enter · Esc close
          </p>
        </div>
      </div>
    </div>
  );
}
