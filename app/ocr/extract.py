"""
One call for the bot: extract_grid(image_path) -> grid + info.

Order of attempts:
  1. Groq (Qwen vision)  - if GROQ_API_KEY is set. Best for handwriting.
  2. Tesseract + OpenCV   - free local fallback (also used if Groq fails).
"""

import time

from app.ocr.groq_engine import read_with_groq
from app.ocr.pipeline import run_ocr
from app.structuring.pipeline import structure
from app.utils.grid import structured_to_grid
from app.utils import groq_client
from app.utils.groq_client import groq_available
from app.utils.spellcheck import correct_structured


def extract_grid(image_path):
    """Returns dict: headers, rows, doc_type, engine, avg_conf, note.
    rows == [] means no readable text was found.
    note is "" normally, or a short warning when we had to fall back to
    basic OCR (so the user knows why accuracy may be lower)."""
    note = ""
    if groq_available():
        try:
            result = read_with_groq(image_path)
        except Exception as e:
            groq_client.LAST_ERROR = f"{type(e).__name__}: {e}"
            result = None
        if result is not None:
            cells = [c for row in result.get("confs", []) for c in row]
            avg = sum(cells) / len(cells) if cells else 1.0
            return {**result, "engine": "groq-qwen", "avg_conf": avg, "note": ""}
        note = f"AI reading failed ({groq_client.LAST_ERROR}), so I used basic OCR (less accurate)."
        print(f"[extract] {note}")
    else:
        note = "AI reading is not set up (no GROQ_API_KEY), so I used basic OCR (less accurate)."

    ocr = run_ocr(image_path, engine="tesseract")["tesseract"]
    if not ocr.words:
        return {"headers": [], "rows": [], "doc_type": "unknown",
                "engine": "tesseract", "avg_conf": 0.0, "note": note}
    structured = correct_structured(structure(ocr))   # local spelling fix
    grid = structured_to_grid(structured)
    return {**grid, "doc_type": structured["type"],
            "engine": "tesseract", "avg_conf": ocr.avg_conf, "note": note}
