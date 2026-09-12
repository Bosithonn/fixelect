"""Render the README banner in the app's palette.

Run: python docs/make_readme_art.py
Writes docs/banner.png (2x size; the README shows it at full width). The corners
are transparent, so it sits well on GitHub's light and dark themes.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
RES = HERE.parent / "Windows" / "resources"

BG_TOP, BG = (17, 22, 38), (11, 13, 18)     # app BG #0B0D12, lifted at the top
ACCENT = (61, 123, 255)                     # #3D7BFF
CORAL = (255, 92, 108)
TEXT_2 = (163, 170, 184)                    # #A3AAB8
BORDER = (38, 44, 58)
W, H, R = 1600, 500, 40


def font(size, bold=False):
    names = ["seguisb.ttf", "segoeuib.ttf"] if bold else ["segoeui.ttf"]
    for n in names:
        p = pathlib.Path("C:/Windows/Fonts") / n
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def fit(img, width):
    img = img.crop(img.getbbox())
    return img.resize((width, round(img.height * width / img.width)), Image.Resampling.LANCZOS)


def glow(size, center, radius, color, strength, blur):
    mask = Image.new("L", size, 0)
    cx, cy = center
    ImageDraw.Draw(mask).ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=strength)
    return Image.new("RGB", size, color), mask.filter(ImageFilter.GaussianBlur(blur))


def banner():
    img = Image.new("RGB", (W, H), BG)
    top = Image.linear_gradient("L").resize((W, H)).point(lambda v: round((255 - v) * 0.85))
    img.paste(Image.new("RGB", (W, H), BG_TOP), mask=top)
    for color, center, radius, strength in ((ACCENT, (W * 0.42, H * 0.36), 300, 60),
                                            (CORAL, (W * 0.60, H * 0.40), 220, 26)):
        layer, mask = glow((W, H), center, radius, color, strength, 150)
        img.paste(layer, mask=mask)

    mark = fit(Image.open(RES / "brand_logo_transparent.png").convert("RGBA"), 700)
    my = 84
    img.paste(mark, ((W - mark.width) // 2, my), mark)

    d = ImageDraw.Draw(img)
    f = font(40)
    line = "Fix and polish your writing in every app. Privately."
    y = my + mark.height + 36
    d.text(((W - d.textlength(line, font=f)) / 2, y), line, font=f, fill=TEXT_2)

    # Pills: platform and promise
    pf = font(26, bold=True)
    pills = ("Windows", "macOS", "100% offline", "Free & open source")
    pad, gap, ph = 26, 16, 52
    widths = [d.textlength(p, font=pf) + pad * 2 for p in pills]
    x = (W - sum(widths) - gap * (len(pills) - 1)) / 2
    py = y + 80
    for p, pw in zip(pills, widths):
        d.rounded_rectangle((x, py, x + pw, py + ph), radius=ph / 2, fill=(22, 27, 40), outline=BORDER, width=2)
        d.text((x + pad, py + ph / 2), p, font=pf, fill=(226, 230, 238), anchor="lm")
        x += pw + gap

    # Rounded card with a hairline border; transparent outside the corners
    out = img.convert("RGBA")
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=R, fill=255)
    out.putalpha(mask)
    ImageDraw.Draw(out).rounded_rectangle((1, 1, W - 2, H - 2), radius=R, outline=BORDER + (255,), width=2)
    return out


def main():
    banner().save(HERE / "banner.png", optimize=True)
    print("wrote", HERE / "banner.png")


if __name__ == "__main__":
    main()
