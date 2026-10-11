"""Generate a few synthetic test images (+ ground truth) so you can run the evaluation right away.
Real phone photos are better - drop your own image + .txt pairs into data/samples/ too.
Run: python -m eval.make_samples"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = Path("data/samples")

SAMPLES = {
    "shopping_list": "Shopping List\n2 kg Rice\n1 L Milk\n500 g Sugar\n6 Eggs\n3 Tomatoes",
    "receipt": "FRESH MART\nBread 2 x 30.00 60.00\nMilk 1 x 55.00 55.00\nTotal 115.00",
    "table": "Name Qty Price\nPen 10 5.00\nBook 3 120.00\nBag 1 450.00",
}


def get_font(size):
    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def make(name, text, angle):
    img = Image.new("RGB", (900, 120 + 70 * len(text.splitlines())), "white")
    draw, font = ImageDraw.Draw(img), get_font(40)
    for i, line in enumerate(text.splitlines()):
        draw.text((60, 50 + i * 70), line, fill="black", font=font)
    img = img.rotate(angle, expand=True, fillcolor="white", resample=Image.BICUBIC)  # fake a crooked photo
    arr = np.array(img).astype(np.int16) + np.random.normal(0, 12, (img.height, img.width, 3)).astype(np.int16)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(OUT / f"{name}.png")
    (OUT / f"{name}.txt").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for (n, t), a in zip(SAMPLES.items(), (3, -2, 4)):
        make(n, t, a)
    print("Created", len(SAMPLES), "samples in", OUT)
