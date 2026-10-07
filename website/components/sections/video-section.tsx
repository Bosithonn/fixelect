import { PromoVideo } from "@/components/promo-video";

export function VideoSection() {
  return (
    <section id="video" aria-labelledby="video-title" className="shell pb-[clamp(4.5rem,9vw,8.5rem)]">
      <h2 id="video-title" className="sr-only">
        Fixelect in 48 seconds
      </h2>
      <PromoVideo />
    </section>
  );
}
