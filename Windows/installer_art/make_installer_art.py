"""Render the installer artwork in the app's palette.

Run: python Windows/installer_art/make_installer_art.py
Writes wizard_*.png (left panel of the Welcome/Finish pages) and small_*.png
(top-right icon of the inner pages) at 100-250 % scale, so Setup stays sharp
on every DPI. The PNGs are committed; builds do not need these fonts.
"""

import pathlib

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
RES = HERE.parent / "resources"

BG_TOP, BG = (15, 19, 32), (11, 13, 18)     # app BG #0B0D12, slightly lifted at the top
ACCENT = (61, 123, 255)                     # #3D7BFF
TEXT_2 = (163, 170, 184)                    # #A3AAB8
SCALES = (100, 125, 150, 175, 200, 250)
WIZARD = (164, 314)
SMALL = 55


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


def wizard(scale):
    w, h = (round(v * scale / 100) for v in WIZARD)
    ss = 3                                   # supersample for smooth gradients and glow
    W, H = w * ss, h * ss
    img = Image.new("RGB", (W, H), BG)
    top = Image.linear_gradient("L").resize((W, H)).point(lambda v: 255 - v)
    img.paste(Image.new("RGB", (W, H), BG_TOP), mask=top.point(lambda v: v * 0.8))

    symbol = fit(Image.open(RES / "brand_symbol.png").convert("RGBA"), round(W * 0.58))
    cx, cy = W // 2, round(H * 0.34)
    glow = Image.new("L", (W, H), 0)
    r = round(W * 0.46)
    ImageDraw.Draw(glow).ellipse((cx - r, cy - r, cx + r, cy + r), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(W * 0.16))
    img.paste(Image.new("RGB", (W, H), ACCENT), mask=glow)
    img.paste(symbol, (cx - symbol.width // 2, cy - symbol.height // 2), symbol)

    mark = fit(Image.open(RES / "brand_logo_transparent.png").convert("RGBA"), round(W * 0.70))
    my = round(H * 0.60)
    img.paste(mark, (cx - mark.width // 2, my), mark)

    d = ImageDraw.Draw(img)
    f = font(round(8.6 * ss * scale / 100))
    y = my + mark.height + round(14 * ss * scale / 100)
    for line in ("Fix and polish your writing", "in every app. Privately."):
        tw = d.textlength(line, font=f)
        d.text((cx - tw / 2, y), line, font=f, fill=TEXT_2)
        y += round(13.5 * ss * scale / 100)
    return img.resize((w, h), Image.Resampling.LANCZOS)


def small(scale):
    s = round(SMALL * scale / 100)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # 70 %: Setup places this image flush with the top edge, so leave breathing room
    sym = fit(Image.open(RES / "brand_symbol.png").convert("RGBA"), round(s * 0.70))
    img.paste(sym, ((s - sym.width) // 2, (s - sym.height) // 2), sym)
    return img


def main():
    for sc in SCALES:
        wizard(sc).save(HERE / f"wizard_{sc}.png", optimize=True)
        small(sc).save(HERE / f"small_{sc}.png", optimize=True)
    print("wrote", ", ".join(f"{sc}%" for sc in SCALES), "->", HERE)


if __name__ == "__main__":
    main()
