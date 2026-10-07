# fixelect.app

The public website for [Fixelect](https://github.com/Bosithonn/fixelect): one landing page plus the privacy policy and terms.

It is a self-contained Next.js project. Nothing here is imported by the app, and the site imports nothing from the app; the logo, icons, video and screenshot under `public/` and `app/` are copies.

## Run it

```bash
npm install
npm run dev      # http://localhost:3000
```

```bash
npm run build    # production build
npm run start    # serve the production build
npm run lint
npm run format
```

Node.js 20.9 or newer.

## Deploy to Vercel

1. In Vercel, choose **Add New → Project** and import the `fixelect` repository.
2. Set **Root Directory** to `website`. The framework is detected as Next.js; keep the default build settings.
3. Deploy. No environment variables are needed.
4. Under **Settings → Domains**, add `fixelect.app` (and `www.fixelect.app` if you want it to redirect).

## Where things live

| Path                         | What it is                                                                                                                                  |
| :--------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------ |
| `lib/site.ts`                | Every link and fact a founder may need to change: the Microsoft Store URL, GitHub links, the contact address and the optional legal fields. |
| `app/page.tsx`               | The landing page: the order of its sections and its structured data.                                                                        |
| `components/sections/`       | One file per section of the landing page.                                                                                                   |
| `components/hero-demo.tsx`   | The headline that fixes itself, with a working Undo and double-tap Alt.                                                                     |
| `components/specimens/`      | Fixelect's own UI (status card, Polish preview, quick-action menu) drawn in HTML with the app's colours.                                    |
| `app/privacy/`, `app/terms/` | The legal pages. Their text follows `PRIVACY_POLICY.md`, `LICENSE` and `LICENSE.txt` in the repository root.                                |
| `app/globals.css`            | Design tokens, taken from `shared/ui_kit.py`, and the few hand-written component styles.                                                    |

## Keeping it true

The site only says what the app does. When the app changes, check these against it:

- Shortcuts, Polish styles, quick actions and card wording: `components/sections/shortcuts-section.tsx` and `components/specimens/`.
- Models and languages: `components/sections/engine-section.tsx`.
- Network requests and stored files: `components/sections/private-section.tsx` and `app/privacy/page.tsx`.
- Questions and answers: `components/sections/faq-section.tsx`.

## Assets

| File                                               | Copied from                                       |
| :------------------------------------------------- | :------------------------------------------------ |
| `public/brand/fixelect-logo.png`                   | `Windows/resources/brand_logo.png`                |
| `public/brand/fixelect-tile.png`                   | `docs/store/tile-300.png`                         |
| `public/media/fixelect-intro.mp4`                  | `docs/fixelect-intro.mp4`                         |
| `public/media/intro-poster.jpg`                    | A frame of that video, at 13 seconds              |
| `public/media/history-window.png`                  | The app window in `docs/store/4-private.png`      |
| `app/icon.png`, `app/favicon.ico`                  | `Windows/resources/app_icon.png`                  |
| `app/apple-icon.png`                               | `docs/store/tile-300.png`                         |
| `app/opengraph-image.png`, `app/twitter-image.png` | `docs/store/hero-16x9.png`, cropped to 1200 × 630 |
