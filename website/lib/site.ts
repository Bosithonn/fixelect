/**
 * Site-wide facts and links. Everything a founder may need to change lives here.
 */

const GITHUB_REPO = "https://github.com/Bosithonn/fixelect";

export const site = {
  name: "Fixelect",
  url: "https://fixelect.app",
  title: "Fixelect: Fix and polish your writing in any app, offline",
  tagline: "Fix and polish your writing in every app. Privately.",
  description:
    "Select text in any app, double-tap Alt, and Fixelect fixes it in place. The AI runs on your computer, so your writing never leaves it. Free for Windows.",
  owner: "Bositxon Erkinxonov",
  copyrightYear: 2026,
  contactEmail: "founder@fixelect.app",
} as const;

export const links = {
  /** Fixelect's Microsoft Store listing (Store ID 9N3VTFXL9LQC). */
  microsoftStore: "https://apps.microsoft.com/detail/9n3vtfxl9lqc",
  github: GITHUB_REPO,
  releases: `${GITHUB_REPO}/releases`,
  issues: `${GITHUB_REPO}/issues`,
  license: `${GITHUB_REPO}/blob/main/LICENSE`,
  thirdPartyNotices: `${GITHUB_REPO}/blob/main/LICENSE.txt`,
  windowsInstaller: `${GITHUB_REPO}/releases/latest/download/FixelectSetup.exe`,
  macDmg: `${GITHUB_REPO}/releases/latest/download/Fixelect.dmg`,
} as const;

/**
 * Facts the legal pages need but the project does not state.
 * A section is only rendered once its value is filled in, so nothing
 * unverified is ever published.
 */
export const legal = {
  /** Shown as "Last updated" on /privacy and /terms. */
  lastUpdated: "October 2026",
  /** Company or person hosting this website, e.g. "Vercel Inc." */
  websiteHost: null as string | null,
  /** Governing law for the terms, e.g. "the laws of …". */
  governingLaw: null as string | null,
  /** Postal address of the publisher, if one must be shown. */
  postalAddress: null as string | null,
} as const;

export const navigation = [
  { href: "/#shortcuts", label: "How it works" },
  { href: "/#private", label: "Privacy" },
  { href: "/#faq", label: "FAQ" },
] as const;
