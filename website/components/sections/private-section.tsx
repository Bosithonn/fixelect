import { links } from "@/lib/site";

const LEDGER = [
  {
    when: "Once, when you choose a model",
    where: "Hugging Face",
    what: "A request for the model file. The download is checked against its published SHA-256 checksum.",
  },
  {
    when: "At most once a day",
    where: "GitHub",
    what: "An anonymous question: is there a newer version? No identifiers, no text, no usage data. You can turn it off, and installs from the Microsoft Store skip it because the Store handles updates.",
  },
] as const;

const FACTS = [
  {
    title: "No keystroke logging",
    body: "Fixelect reads only the text you select and ask it to work on.",
  },
  {
    title: "Your clipboard, put back",
    body: "It borrows the clipboard for a moment to read and replace your text, then restores what was there. Clipboard history skips it.",
  },
  {
    title: "Works in airplane mode",
    body: "Once the model is downloaded, no connection is needed.",
  },
] as const;

export function PrivateSection() {
  return (
    <section id="private" aria-labelledby="private-title" className="border-y border-line bg-surface">
      <div className="shell section">
        <div className="max-w-[46rem]">
          <h2 id="private-title" className="h2">
            Your writing never leaves your computer.
          </h2>
          <p className="lead mt-5">
            Fixelect runs its AI model on your own machine. There is no account, no cloud and no telemetry. This is
            everything it ever sends over the network:
          </p>
        </div>

        <table role="table" className="mt-12 w-full border-collapse text-left lg:mt-16">
          <caption className="sr-only">Every network request Fixelect makes</caption>
          <thead role="rowgroup" className="max-md:sr-only">
            <tr role="row" className="border-b border-line-strong text-[0.875rem] text-ink-3">
              <th role="columnheader" scope="col" className="w-[26%] pb-3 pr-6 font-normal">
                When
              </th>
              <th role="columnheader" scope="col" className="w-[18%] pb-3 pr-6 font-normal">
                Where to
              </th>
              <th role="columnheader" scope="col" className="pb-3 font-normal">
                What is sent
              </th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {LEDGER.map((row) => (
              <tr key={row.where} role="row" className="border-b border-line max-md:block max-md:py-6 md:align-top">
                <th role="rowheader" scope="row" className="font-semibold text-ink max-md:block md:py-6 md:pr-6">
                  {row.when}
                </th>
                <td role="cell" className="text-ink-2 max-md:mt-1 max-md:block md:py-6 md:pr-6">
                  <span className="md:hidden">To </span>
                  {row.where}
                </td>
                <td role="cell" className="text-ink-2 max-md:mt-3 max-md:block md:py-6">
                  {row.what}
                </td>
              </tr>
            ))}
            <tr role="row" className="max-md:block max-md:pt-6 md:align-baseline">
              <th role="rowheader" scope="row" className="font-semibold text-ink max-md:block md:pr-6 md:pt-7">
                Your text
              </th>
              <td role="cell" className="text-ink-2 max-md:sr-only md:pr-6 md:pt-7">
                Nowhere
              </td>
              <td role="cell" className="h3 text-ink max-md:mt-1 max-md:block md:pt-7">
                Never sent.
              </td>
            </tr>
          </tbody>
        </table>

        <dl className="mt-16 grid gap-x-12 gap-y-10 sm:grid-cols-2 lg:mt-24 lg:grid-cols-4">
          {FACTS.map((fact) => (
            <div key={fact.title}>
              <dt className="font-semibold text-ink">{fact.title}</dt>
              <dd className="mt-2 text-[0.9375rem] text-ink-2">{fact.body}</dd>
            </div>
          ))}
          <div>
            <dt className="font-semibold text-ink">Open to inspection</dt>
            <dd className="mt-2 text-[0.9375rem] text-ink-2">
              The code is public under the MIT License.{" "}
              <a href={links.github} target="_blank" rel="noopener" className="text-link">
                Read it on GitHub
              </a>
              , or watch the network traffic yourself.
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
