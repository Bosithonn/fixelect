import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/legal-page";
import { pageMetadata } from "@/lib/metadata";
import { legal, links, site } from "@/lib/site";

export const metadata: Metadata = pageMetadata({
  title: "Terms",
  description: "Fixelect is free, open-source software under the MIT License. These are the terms that come with it.",
  path: "/terms",
});

const MIT_LICENSE = `MIT License

Copyright (c) ${site.copyrightYear} ${site.owner}

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.`;

const THIRD_PARTY = [
  ["Qwen 2.5 language models", "Alibaba Cloud", "Apache License 2.0"],
  ["Gemma 4 language model (optional download)", "Google DeepMind", "Apache License 2.0"],
  ["llama.cpp and llama-server", "Georgi Gerganov and contributors", "MIT License"],
  ["Harper English dictionary and curated word lists", "", "Apache License 2.0"],
  ["Uzbek word list, derived from the uz-crawl corpus", "Tahrirchi", "Apache License 2.0"],
  ["Pillow", "Jeffrey A. Clark and contributors", "HPND License"],
  ["Pystray", "Moses Palmér", "LGPL v3"],
  ["Pyperclip", "Al Sweigart", "BSD 3-Clause License"],
  ["Comtypes", "Thomas Heller", "MIT License"],
] as const;

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms"
      intro="Fixelect is free, open-source software. These terms are short, because the MIT License does most of the work."
    >
      <h2>The license</h2>
      <p>
        Fixelect is licensed under the MIT License. You may use it, copy it, change it and share it, for any purpose, as
        long as the copyright notice and the license text stay with it.
      </p>
      <p className="whitespace-pre-line rounded-xl border border-line bg-surface p-5 text-[0.875rem] leading-[1.65] sm:p-6">
        {MIT_LICENSE}
      </p>

      <h2>No warranty</h2>
      <p>
        Fixelect is provided as it is, without warranty of any kind. As the license above says, its authors are not
        liable for any claim or damages arising from the software or its use. The app&apos;s own license notice names
        loss of data, business interruption and accidental alteration of text content among them.
      </p>

      <h2>Review what Fixelect writes</h2>
      <p>
        Fixelect uses AI language models, and such models can make errors or produce text you did not intend. You are
        responsible for reviewing any text Fixelect changes before you rely on it or send it. Undo and History exist to
        make that easy.
      </p>

      <h2>Third-party software and models</h2>
      <p>Fixelect includes or works with these open-source projects, each under its own license:</p>
      <ul>
        {THIRD_PARTY.map(([name, author, license]) => (
          <li key={name}>
            <strong>{name}</strong>
            {author ? `, ${author}` : ""}. {license}.
          </li>
        ))}
      </ul>
      <p>
        The complete notices ship with the app and are{" "}
        <a href={links.thirdPartyNotices} target="_blank" rel="noopener" className="text-link">
          published on GitHub
        </a>
        .
      </p>

      <h2>The Microsoft Store</h2>
      <p>
        If you install Fixelect from the Microsoft Store, Microsoft&apos;s own terms apply to your use of the Store.
        Microsoft, Windows and Microsoft Store are trademarks of the Microsoft group of companies.
      </p>

      <h2>This website</h2>
      <p>
        This website describes Fixelect and links to places where you can get it. It is provided for information,
        without warranty. How the site and the app handle data is covered in the{" "}
        <Link href="/privacy" className="text-link">
          privacy policy
        </Link>
        .
      </p>

      {legal.governingLaw ? (
        <>
          <h2>Governing law</h2>
          <p>These terms are governed by {legal.governingLaw}.</p>
        </>
      ) : null}

      <h2>Contact</h2>
      <p>
        Questions about these terms? Write to{" "}
        <a href={`mailto:${site.contactEmail}`} className="text-link">
          {site.contactEmail}
        </a>
        .
      </p>
      {legal.postalAddress ? <p>{legal.postalAddress}</p> : null}
    </LegalPage>
  );
}
