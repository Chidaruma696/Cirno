"""Genera cirno/assets/cirno.png y cirno.ico: un copo de nieve blanco sobre azul Cirno, esquinas 0, borde de tinta."""
import math
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "cirno" / "assets"
BLUE = (46, 125, 233, 255)
INK = (16, 35, 58, 255)
WHITE = (255, 255, 255, 255)


def snowflake(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = size * 0.03
    border = max(1, int(size * 0.045))
    d.rectangle([m, m, size - m, size - m], fill=BLUE, outline=INK, width=border)
    cx = cy = size / 2
    r = size * 0.33
    w = max(1, int(size * 0.05))
    for k in range(6):
        a = math.radians(k * 60)
        x2, y2 = cx + r * math.cos(a), cy + r * math.sin(a)
        d.line([cx, cy, x2, y2], fill=WHITE, width=w)
        for t in (0.5, 0.8):
            bx, by = cx + r * t * math.cos(a), cy + r * t * math.sin(a)
            for da in (math.radians(55), -math.radians(55)):
                ln = r * (0.28 if t == 0.5 else 0.18)
                lx, ly = bx + ln * math.cos(a + da), by + ln * math.sin(a + da)
                d.line([bx, by, lx, ly], fill=WHITE, width=w)
    d.ellipse([cx - w, cy - w, cx + w, cy + w], fill=WHITE)
    return img


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    big = snowflake(1024)
    big.resize((256, 256), Image.LANCZOS).save(ASSETS / "cirno.png")
    big.save(ASSETS / "cirno.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ok", ASSETS)


if __name__ == "__main__":
    main()
