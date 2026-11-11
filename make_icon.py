"""Draw the Nusuk Question Automation logo and save it as icon.ico + logo.png.

Run it once before building the exe (build_exe.bat does it for you):

    python make_icon.py

A golden "?" on a deep teal rounded square — the same gold-on-dark style
as the key tool's golden key icon.
"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))

SIZE = 256
TEAL_TOP = (23, 140, 120)      # #178C78
TEAL_BOTTOM = (10, 84, 72)     # #0A5448
GOLD = (242, 183, 5)           # #F2B705
RADIUS = 56

FONT_CANDIDATES = [
    os.path.join(HERE, "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arial.ttf",
]


def _load_font(size):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _gradient(size):
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(size - 1, 1)
        c = tuple(int(TEAL_TOP[i] + (TEAL_BOTTOM[i] - TEAL_TOP[i]) * t) for i in range(3))
        d.line([(0, y), (size, y)], fill=c)
    return img


def draw_logo(size=SIZE):
    # teal rounded square on a transparent canvas
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = _gradient(size).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, size - 1, size - 1],
                         radius=int(size * RADIUS / 256), fill=255)
    base.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(base)
    # thin gold border
    d.rounded_rectangle([4, 4, size - 5, size - 5],
                        radius=int(size * RADIUS / 256) - 4,
                        outline=GOLD + (255,), width=max(3, size // 64))
    # golden "?"
    font = _load_font(int(size * 0.62))
    q = "?"
    bbox = d.textbbox((0, 0), q, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1] - size * 0.04),
           q, font=font, fill=GOLD + (255,))
    return base


def main():
    logo = draw_logo()
    logo.save(os.path.join(HERE, "logo.png"))
    logo.save(os.path.join(HERE, "icon.ico"),
              sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("logo.png + icon.ico written")


if __name__ == "__main__":
    main()
