import type { Metadata } from "next";
import { site } from "@/lib/site";

/** Title, description, canonical URL and social cards for one page. */
export function pageMetadata({
  title,
  description = site.description,
  path,
}: {
  /** Omit on the home page to use the site's own title. */
  title?: string;
  description?: string;
  path: string;
}): Metadata {
  const fullTitle = title ? `${title} | ${site.name}` : site.title;

  return {
    ...(title ? { title } : {}),
    description,
    alternates: { canonical: path },
    openGraph: {
      type: "website",
      siteName: site.name,
      locale: "en_US",
      url: path,
      title: fullTitle,
      description,
    },
    twitter: {
      card: "summary_large_image",
      title: fullTitle,
      description,
    },
  };
}
