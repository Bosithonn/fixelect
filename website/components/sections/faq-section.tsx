import { site } from "@/lib/site";

const FAQ = [
  {
    q: "Is Fixelect really free?",
    a: "Yes. Fixelect is free and open source under the MIT License. There is no account, no subscription and nothing to buy inside the app.",
  },
  {
    q: "Does my text ever leave my computer?",
    a: "No. The AI model runs on your computer. Fixelect goes online only to download the model you choose and, unless you turn it off, to check for updates. It has no telemetry and does not log your keystrokes.",
  },
  {
    q: "Which apps does it work in?",
    a: "Browsers, email, Slack, Word, Google Docs, Notion, code editors: anywhere you can select text. A few fields block copying, such as password boxes, some games and remote desktops, so Fixelect can't read them. It is switched off in terminals and password managers by default.",
  },
  {
    q: "Which languages does it support?",
    a: "English, Spanish, French, German, Portuguese, Italian, Russian and Ukrainian. Uzbek is in beta and needs the Gemma 4 model. Text in other languages is left unchanged on purpose.",
  },
  {
    q: "What does my computer need?",
    a: "Windows 10 or 11, 64-bit, and 1 to 3 GB of disk space for a model. A loaded model uses 1 to 4 GB of memory and is freed after a break. A graphics card makes fixes faster but is not required.",
  },
  {
    q: "How do I get my original text back?",
    a: "Click Undo on the card, or press Ctrl+Z in your app. Later on, open History: every change is listed there with Copy original.",
  },
  {
    q: "It said “Looks good”, but I can see a mistake.",
    a: "Fixelect only makes changes it is sure about and never rewrites correct words, names or code. Polish rewrites more freely, so try double-tapping Ctrl instead.",
  },
  {
    q: "The shortcut clashes with another app.",
    a: "Pick a different preset under Settings, Shortcuts, or record your own. The status line there shows conflicts.",
  },
  {
    q: "Why is the first fix after a break slower?",
    a: "Fixelect frees the model's memory when you haven't used it for a while and reloads it on your next fix. You can change how long it waits, or switch this off, under Settings, General.",
  },
  {
    q: "Is there a Mac version?",
    a: "A preview for Apple Silicon Macs is on GitHub. It installs and opens, but it is still a work in progress and not ready for everyday use. The Windows version is the stable one.",
  },
] as const;

export function FaqSection() {
  return (
    <section id="faq" aria-labelledby="faq-title" className="shell section">
      <div className="grid gap-x-16 gap-y-10 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <h2 id="faq-title" className="h2">
            Questions
          </h2>
          <p className="mt-5 text-ink-2">
            Something else? Write to{" "}
            <a href={`mailto:${site.contactEmail}`} className="text-link">
              {site.contactEmail}
            </a>
            .
          </p>
        </div>

        <div className="border-b border-line lg:col-span-8">
          {FAQ.map((item) => (
            <details key={item.q} className="faq-item group border-t border-line">
              <summary className="flex items-center justify-between gap-6 py-5 text-[1.125rem] font-semibold text-ink hover:text-white">
                {item.q}
                <span aria-hidden="true" className="faq-mark" />
              </summary>
              <p className="max-w-[44rem] pb-6 pr-10 text-ink-2">{item.a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
