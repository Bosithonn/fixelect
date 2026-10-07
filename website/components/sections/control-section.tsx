import Image from "next/image";
import historyWindow from "@/public/media/history-window.png";

const CONTROLS = [
  {
    title: "See what changed",
    body: "After a fix, the card lists the corrected words, like teh → the.",
  },
  {
    title: "History",
    body: "Your last 30 changes stay on this computer, each with Copy original. Turn it off or clear it whenever you like.",
  },
  {
    title: "Protected words",
    body: "Add the names and jargon Fixelect should never touch.",
  },
  {
    title: "Careful by default",
    body: "Fix only makes changes it is sure about. Correct words, names and code are left alone.",
  },
  {
    title: "Off where it doesn't belong",
    body: "Fixelect ignores its shortcuts in terminals and password managers. Add any other app to the list.",
  },
] as const;

export function ControlSection() {
  return (
    <section aria-labelledby="control-title" className="shell section">
      <div className="grid items-start gap-x-16 gap-y-12 lg:grid-cols-12">
        <div className="lg:col-span-6">
          <h2 id="control-title" className="h2">
            Every change is yours to undo.
          </h2>
          <dl className="mt-10 lg:mt-12">
            {CONTROLS.map((item) => (
              <div
                key={item.title}
                className="grid gap-x-8 gap-y-1 border-t border-line py-5 sm:grid-cols-[11.5rem_1fr]"
              >
                <dt className="font-semibold text-ink">{item.title}</dt>
                <dd className="text-ink-2">{item.body}</dd>
              </div>
            ))}
          </dl>
        </div>

        <figure className="lg:col-span-6 lg:pt-3">
          {/* Phones show the top-left of the window at a readable size instead of shrinking it. */}
          <div className="overflow-hidden rounded-xl border border-line-strong shadow-[0_30px_60px_rgb(0_0_0/0.45)] max-sm:aspect-[5/6]">
            <Image
              src={historyWindow}
              alt="Fixelect's History screen: recent fixes, polishes and actions from Word, Outlook, Slack and Mail, each with Copy original and Copy result."
              sizes="(min-width: 64rem) 560px, (min-width: 40rem) 90vw, 150vw"
              className="h-auto w-full max-sm:w-[150%] max-sm:max-w-none"
            />
          </div>
          <figcaption className="mt-4 text-[0.9375rem] text-ink-3">
            Settings, History. Kept only on your computer.
          </figcaption>
        </figure>
      </div>
    </section>
  );
}
