"""EasyOCR engine (deep-learning based)."""
import time

from .base import Word, make_result

_reader = None  # loading the model is slow, so we do it once and reuse it


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr  # imported here so Tesseract-only runs don't need PyTorch
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


def run_easyocr(img):
    reader = _get_reader()          # load first so model loading isn't counted in the timing
    start = time.time()
    words = []
    for box, text, conf in reader.readtext(img):   # box = 4 corner points
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        x1, y1, x2, y2 = int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))
        # EasyOCR returns whole phrases. Split into words and share the box by
        # character count so later phases can work with word-level boxes.
        parts = text.split()
        if not parts:
            continue
        total = sum(len(p) for p in parts) + len(parts) - 1
        cursor = float(x1)
        for p in parts:
            width = (x2 - x1) * len(p) / total
            words.append(Word(p, (int(cursor), y1, int(cursor + width), y2), float(conf)))
            cursor += (x2 - x1) * (len(p) + 1) / total
    return make_result("easyocr", words, start)
