#!/usr/bin/env python3
"""Bikin aset brand Sokkin (icon, logo, banner).

Dev-only: butuh Pillow (`pip install pillow`). Aplikasi Sokkin sendiri tetap
tanpa dependensi — file yang dihasilkan sudah ikut di repo.

Jalankan dari root project:
    python tools/make_brand.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "sokkin" / "assets"
SHOWCASE = ROOT / "showcase"

FONT_SEMIBOLD = r"C:\Windows\Fonts\seguisb.ttf"
FONT_REGULAR = r"C:\Windows\Fonts\segoeui.ttf"

ACCENT = (91, 124, 250, 255)
INK = (31, 40, 74, 255)
CARD = (248, 250, 255, 255)


def _lerp(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))


def _gradient(size: int, c1: tuple, c2: tuple) -> Image.Image:
    im = Image.new("RGBA", (size, size), c1)
    d = ImageDraw.Draw(im)
    for y in range(size):
        d.line([(0, y), (size, y)], fill=_lerp(c1, c2, y / max(1, size - 1)))
    return im


def _rounded_gradient(size: int, radius: int, margin: int,
                      c1=(44, 58, 140, 255), c2=(10, 13, 26, 255)) -> Image.Image:
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = _gradient(size, c1, c2)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (margin, margin, size - margin, size - margin), radius=radius, fill=255)
    im.paste(grad, (0, 0), mask)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((size * .10, -size * .25, size * .90, size * .55),
               fill=(91, 124, 250, 80))
    glow = glow.filter(ImageFilter.GaussianBlur(size // 12))
    im.alpha_composite(Image.composite(
        glow, Image.new("RGBA", (size, size), (0, 0, 0, 0)), mask))

    ImageDraw.Draw(im).rounded_rectangle(
        (margin, margin, size - margin, size - margin), radius=radius,
        outline=(255, 255, 255, 30), width=max(2, size // 500))
    return im


def icon_master(size: int = 2048) -> Image.Image:
    """Ikon prompt-card + tombol play, digambar besar lalu diperkecil."""
    S = size
    im = _rounded_gradient(S, radius=int(S * 0.215), margin=int(S * 0.039))

    # bayangan kartu
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (S * .146, S * .245, S * .854, S * .655), radius=S * .075,
        fill=(0, 0, 0, 120))
    im.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S // 55)))

    d = ImageDraw.Draw(im)
    # balon prompt
    d.rounded_rectangle((S * .146, S * .230, S * .854, S * .635),
                        radius=S * .075, fill=CARD)
    d.polygon([(S * .342, S * .625), (S * .527, S * .625), (S * .371, S * .762)],
              fill=CARD)

    # tiga baris teks: dua tinta, satu aksen
    d.rounded_rectangle((S * .220, S * .303, S * .700, S * .342),
                        radius=S * .020, fill=INK)
    d.rounded_rectangle((S * .220, S * .379, S * .611, S * .418),
                        radius=S * .020, fill=INK)
    d.rounded_rectangle((S * .220, S * .455, S * .493, S * .494),
                        radius=S * .020, fill=ACCENT)

    # tombol play
    cx, cy, r = S * .742, S * .708, S * .078
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)
    d.polygon([(cx - r * .24, cy - r * .42), (cx - r * .24, cy + r * .42),
               (cx + r * .46, cy)], fill=(255, 255, 255, 255))
    return im


def rounded_icon(im: Image.Image, px: int) -> Image.Image:
    return im.resize((px, px), Image.LANCZOS)


def icon_compact(px: int) -> Image.Image:
    """Versi sederhana untuk 16/20/24 px: dua baris tebal, tanpa detail kecil.

    Ikon penuh kalau diperkecil ke 16px jadi abu-abu semua; versi ini menjaga
    kontras di system tray.
    """
    S = px * 24
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    full = _gradient(S, (44, 58, 140, 255), (10, 13, 26, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S, S), radius=int(S * .22), fill=255)
    im.paste(full, (0, 0), mask)

    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((S * .05, -S * .35, S * .95, S * .45),
                                 fill=(91, 124, 250, 95))
    im.alpha_composite(Image.composite(
        glow.filter(ImageFilter.GaussianBlur(S // 14)),
        Image.new("RGBA", (S, S), (0, 0, 0, 0)), mask))

    d = ImageDraw.Draw(im)
    d.rounded_rectangle((S * .07, S * .16, S * .93, S * .70),
                        radius=int(S * .085), fill=CARD)
    if px >= 24:
        d.polygon([(S * .28, S * .68), (S * .50, S * .68), (S * .34, S * .84)],
                  fill=CARD)

    d.rounded_rectangle((S * .18, S * .28, S * .74, S * .36),
                        radius=S * .04, fill=INK)
    d.rounded_rectangle((S * .18, S * .44, S * .60, S * .52),
                        radius=S * .04, fill=ACCENT)

    if px >= 24:
        cx, cy, r = S * .78, S * .755, S * .13
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ACCENT)
        d.polygon([(cx - r * .25, cy - r * .40), (cx - r * .25, cy + r * .40),
                   (cx + r * .42, cy)], fill=(255, 255, 255, 255))
    return im.resize((px, px), Image.LANCZOS)


def make_icon_files() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    master = icon_master()
    logo = rounded_icon(master, 1024)
    logo.save(ASSETS / "sokkin.png")
    logo.save(SHOWCASE / "sokkin-logo.png")

    # ICO multi-size. Ukuran kecil pakai desain ringkas supaya tetap kebaca;
    # ukuran besar pakai desain penuh. Shell/tray memilih ukuran yang pas.
    sizes = [16, 20, 24, 32, 40, 48, 64, 96, 128, 256]
    frames = [icon_compact(s) if s <= 24 else rounded_icon(master, s)
              for s in sizes]
    frames[-1].save(ASSETS / "sokkin.ico", format="ICO",
                    append_images=frames[:-1],
                    sizes=[(s, s) for s in sizes])
    print(f"icon  -> {ASSETS / 'sokkin.ico'}")
    print(f"logo  -> {ASSETS / 'sokkin.png'}")
    print(f"logo  -> {SHOWCASE / 'sokkin-logo.png'}")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def banner() -> None:
    W, H = 1600, 520
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    gd = ImageDraw.Draw(grad)
    for y in range(H):
        gd.line([(0, y), (W, y)], fill=_lerp((40, 52, 126, 255),
                                             (9, 12, 24, 255), y / (H - 1)))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=48, fill=255)
    im.paste(grad, (0, 0), mask)

    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-200, -380, 900, 420), fill=(91, 124, 250, 90))
    im.alpha_composite(Image.composite(
        glow.filter(ImageFilter.GaussianBlur(120)), Image.new("RGBA", (W, H), (0, 0, 0, 0)), mask))

    icon = rounded_icon(icon_master(), 300)
    im.alpha_composite(icon, (96, 110))

    d = ImageDraw.Draw(im)
    d.text((452, 118), "Sokkin", font=_font(FONT_SEMIBOLD, 172),
           fill=(248, 250, 255, 255))
    d.text((458, 318), "Teleprompter overlay untuk wawancara & presentasi",
           font=_font(FONT_REGULAR, 44), fill=(178, 190, 226, 255))
    d.text((458, 392), "Tanpa dependensi  ·  Hotkey global  ·  Sembunyi ke tray",
           font=_font(FONT_REGULAR, 32), fill=(112, 132, 194, 255))

    im.save(SHOWCASE / "sokkin-banner.png")
    print(f"banner -> {SHOWCASE / 'sokkin-banner.png'}")


def social() -> None:
    W, H = 1280, 640
    im = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    for y in range(H):
        d.line([(0, y), (W, y)], fill=_lerp((36, 48, 120, 255),
                                            (7, 10, 20, 255), y / (H - 1)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((240, -420, 1040, 380), fill=(91, 124, 250, 100))
    im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(130)))

    icon = rounded_icon(icon_master(), 210)
    im.alpha_composite(icon, (535, 66))

    d = ImageDraw.Draw(im)
    title = "Sokkin"
    f = _font(FONT_SEMIBOLD, 112)
    tw = d.textbbox((0, 0), title, font=f)[2]
    d.text(((W - tw) / 2, 298), title, font=f, fill=(248, 250, 255, 255))
    sub = "Overlay teleprompter selalu-di-depan untuk wawancara"
    f2 = _font(FONT_REGULAR, 30)
    sw = d.textbbox((0, 0), sub, font=f2)[2]
    d.text(((W - sw) / 2, 430), sub, font=f2, fill=(178, 190, 226, 255))
    url = "github.com/kandarlubis31/Sokkin"
    f3 = _font(FONT_REGULAR, 26)
    uw = d.textbbox((0, 0), url, font=f3)[2]
    d.text(((W - uw) / 2, 552), url, font=f3, fill=(112, 132, 194, 255))

    im.save(SHOWCASE / "sokkin-social.png")
    print(f"social -> {SHOWCASE / 'sokkin-social.png'}")


if __name__ == "__main__":
    make_icon_files()
    banner()
    social()
