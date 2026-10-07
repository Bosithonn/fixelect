"use client";

import Image from "next/image";
import { useState } from "react";
import poster from "@/public/media/intro-poster.jpg";

/**
 * The 48-second product video. Nothing but the poster is downloaded
 * until the visitor asks to play it.
 */
export function PromoVideo() {
  const [playing, setPlaying] = useState(false);

  return (
    <div className="relative aspect-video overflow-hidden rounded-xl border border-line bg-surface sm:rounded-2xl">
      {playing ? (
        <video
          ref={(node) => node?.focus()}
          src="/media/fixelect-intro.mp4"
          poster={poster.src}
          controls
          autoPlay
          playsInline
          preload="auto"
          className="size-full"
          aria-label="Fixelect product video"
        />
      ) : (
        <button
          type="button"
          onClick={() => setPlaying(true)}
          className="group absolute inset-0 size-full rounded-[inherit]"
        >
          <Image
            src={poster}
            alt=""
            fill
            sizes="(min-width: 80rem) 1136px, 100vw"
            placeholder="blur"
            className="object-cover"
          />
          <span className="absolute bottom-3 left-3 flex sm:bottom-6 sm:left-6">
            <span className="flex items-center gap-3 rounded-full bg-accent-fill py-2 pl-2.5 pr-5 text-[0.9375rem] font-semibold text-white shadow-[0_10px_30px_rgb(0_0_0/0.45)] transition-colors group-hover:bg-accent-fill-hover sm:text-[1.0625rem]">
              <span className="flex size-9 items-center justify-center rounded-full bg-white/15">
                <svg aria-hidden="true" viewBox="0 0 16 16" className="ml-0.5 size-4" fill="currentColor">
                  <path d="M4 2.6v10.8a.6.6 0 00.92.5l8.4-5.4a.6.6 0 000-1L4.92 2.1A.6.6 0 004 2.6z" />
                </svg>
              </span>
              Play video
              <span className="font-normal">0:48, with sound</span>
            </span>
          </span>
        </button>
      )}
    </div>
  );
}
