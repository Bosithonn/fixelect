import { SecondaryButton, StoreButton } from "@/components/buttons";
import { HeroDemo } from "@/components/hero-demo";

export function Hero() {
  return (
    <section className="relative">
      {/* The one glow on the site: the navy light from Fixelect's own key art. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[46rem] bg-[radial-gradient(ellipse_75%_62%_at_50%_-10%,rgb(46_70_160/0.5),transparent_72%)]"
      />
      <div className="shell relative pb-[clamp(3.25rem,5vw,4.5rem)] pt-[clamp(1.75rem,6vw,5rem)]">
        <HeroDemo />

        <div className="mt-6 max-w-[39rem] sm:mt-12">
          <p className="lead">
            Select text in any app and double-tap Alt. Fixelect corrects it right where you typed it. The AI model runs
            on your computer, so your writing never leaves it.
          </p>
          <div className="mt-6 flex flex-col gap-3 min-[30rem]:flex-row min-[30rem]:flex-wrap sm:mt-8">
            <StoreButton />
            <SecondaryButton href="#video">Watch the 48-second video</SecondaryButton>
          </div>
          <p className="mt-5 text-[0.9375rem] text-ink-3">Free and open source. Windows 10 and 11. No account.</p>
        </div>
      </div>

      {/* Without JavaScript the headline cannot fix itself, so show it fixed. */}
      <noscript>
        <style>{`.hero[data-phase="intro"] .hero-word::before{visibility:hidden}.hero[data-phase="intro"] .hero-word-right{visibility:visible}.hero[data-phase="intro"] .hero-status .hud{opacity:1;transform:none;visibility:visible}`}</style>
      </noscript>
    </section>
  );
}
