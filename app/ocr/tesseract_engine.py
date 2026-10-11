"""Tesseract engine (via pytesseract)."""
import os
import time

import pytesseract
from pytesseract import Output

from .base import Word, make_result

# On Windows, set TESSERACT_CMD to e.g. C:\Program Files\Tesseract-OCR\tesseract.exe
if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]


def run_tesseract(img):
    start = time.time()
    # psm 6 = "assume a single uniform block of text" - works well for lists/receipts
    data = pytesseract.image_to_data(img, lang="eng", config="--oem 3 --psm 6",
                                     output_type=Output.DICT)
    words = []
    for i, text in enumerate(data["text"]):
        text, conf = text.strip(), float(data["conf"][i])
        if not text or conf < 0:      # conf -1 means "not a word" (layout rows)
            continue
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(text, (x, y, x + w, y + h), conf / 100))
    return make_result("tesseract", words, start)
