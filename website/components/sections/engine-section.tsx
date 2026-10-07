const MODELS = [
  {
    name: "Gemma 4 E2B",
    size: "3.1 GB",
    note: "Recommended. It fixed the most mistakes in our tests and is the model that handles Uzbek.",
  },
  {
    name: "Qwen 2.5 3B",
    size: "2.0 GB",
    note: "The previous default. Quick and careful, but fixes fewer mistakes in long sentences.",
  },
  {
    name: "Qwen 2.5 1.5B",
    size: "1.0 GB",
    note: "For lighter laptops and computers without a graphics card.",
  },
] as const;

const LANGUAGES = [
  { name: "English", lang: "en" },
  { name: "Español", lang: "es" },
  { name: "Français", lang: "fr" },
  { name: "Deutsch", lang: "de" },
  { name: "Português", lang: "pt" },
  { name: "Italiano", lang: "it" },
  { name: "Русский", lang: "ru" },
  { name: "Українська", lang: "uk" },
] as const;

export function EngineSection() {
  return (
    <div className="shell">
      <div className="section border-t border-line">
        <section aria-labelledby="engine-title" className="grid gap-x-16 gap-y-10 lg:grid-cols-12">
          <div className="lg:col-span-5">
            <h2 id="engine-title" className="h2">
              A model that fits your computer.
            </h2>
            <p className="lead mt-5">
              On first launch you choose the AI model Fixelect will use. It runs on your graphics card if you have one,
              and on the processor if you don&apos;t.
            </p>
          </div>

          <div className="lg:col-span-7 lg:pt-2">
            <table role="table" className="w-full border-collapse text-left">
              <caption className="sr-only">Models Fixelect recommends</caption>
              <thead role="rowgroup" className="sr-only">
                <tr role="row">
                  <th role="columnheader" scope="col">
                    Model
                  </th>
                  <th role="columnheader" scope="col">
                    Download size
                  </th>
                  <th role="columnheader" scope="col">
                    Best for
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {MODELS.map((model) => (
                  <tr key={model.name} role="row" className="border-t border-line align-top max-sm:block max-sm:py-5">
                    <th
                      role="rowheader"
                      scope="row"
                      className="whitespace-nowrap font-semibold text-ink max-sm:inline sm:py-5 sm:pr-6"
                    >
                      {model.name}
                    </th>
                    <td
                      role="cell"
                      className="whitespace-nowrap text-ink-3 tabular-nums max-sm:ml-3 max-sm:inline sm:py-5 sm:pr-6"
                    >
                      {model.size}
                    </td>
                    <td role="cell" className="text-ink-2 max-sm:mt-1 max-sm:block sm:py-5">
                      {model.note}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="border-t border-line pt-5 text-[0.9375rem] text-ink-3">
              A loaded model uses 1 to 4 GB of memory. Fixelect frees it after a break and reloads it in a few seconds.
              If fixes are slow on your computer, it offers a smaller model. It never switches by itself.
            </p>
          </div>
        </section>

        <section
          aria-labelledby="languages-title"
          className="mt-20 grid gap-x-16 gap-y-10 border-t border-line pt-16 lg:mt-28 lg:grid-cols-12 lg:pt-24"
        >
          <div className="lg:col-span-5">
            <h2 id="languages-title" className="h2">
              Eight languages, and a ninth in beta.
            </h2>
            <p className="mt-5 text-ink-2">
              Fix, Polish and Translate work in all of them. Uzbek needs the Gemma 4 model. Text in any other language
              is left unchanged on purpose.
            </p>
          </div>

          <ul className="flex flex-wrap content-start gap-x-[0.75em] gap-y-[0.1em] text-[clamp(1.625rem,2vw+1.1rem,2.75rem)] font-semibold leading-[1.3] tracking-[-0.025em] text-ink lg:col-span-7">
            {LANGUAGES.map((language) => (
              <li key={language.lang} lang={language.lang}>
                {language.name}
              </li>
            ))}
            <li className="text-ink-2">
              <span lang="uz">Oʻzbekcha</span>{" "}
              <span className="text-[0.5em] font-normal tracking-normal text-ink-3">beta</span>
            </li>
          </ul>
        </section>
      </div>
    </div>
  );
}
