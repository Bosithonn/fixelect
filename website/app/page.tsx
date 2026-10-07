import type { Metadata } from "next";
import { ControlSection } from "@/components/sections/control-section";
import { DownloadSection } from "@/components/sections/download-section";
import { EngineSection } from "@/components/sections/engine-section";
import { FaqSection } from "@/components/sections/faq-section";
import { Hero } from "@/components/sections/hero";
import { PrivateSection } from "@/components/sections/private-section";
import { ShortcutsSection } from "@/components/sections/shortcuts-section";
import { VideoSection } from "@/components/sections/video-section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { pageMetadata } from "@/lib/metadata";
import { links, site } from "@/lib/site";

export const metadata: Metadata = pageMetadata({ path: "/" });

const structuredData = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: site.name,
  url: site.url,
  description: site.description,
  image: `${site.url}/opengraph-image.png`,
  applicationCategory: "UtilitiesApplication",
  operatingSystem: "Windows 10, Windows 11",
  isAccessibleForFree: true,
  license: links.license,
  installUrl: links.microsoftStore,
  sameAs: [links.github, links.microsoftStore],
  offers: {
    "@type": "Offer",
    price: "0",
    priceCurrency: "USD",
  },
  author: {
    "@type": "Person",
    name: site.owner,
  },
};

export default function HomePage() {
  return (
    <>
      <SiteHeader />
      <main id="main">
        <Hero />
        <VideoSection />
        <ShortcutsSection />
        <PrivateSection />
        <ControlSection />
        <EngineSection />
        <DownloadSection />
        <FaqSection />
      </main>
      <SiteFooter />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(structuredData).replace(/</g, "\\u003c") }}
      />
    </>
  );
}
