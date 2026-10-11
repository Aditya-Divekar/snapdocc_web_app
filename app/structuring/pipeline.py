"""
One entry point for the structuring module.

    result = structure(ocr_result)

Returns a dict with:
  result["type"]    -> "list" or "table"
  result["data"]    -> list of records (list) or 2-D grid (table)
  result["headers"] -> column headers (table only, guessed from first row)
  result["confs"]   -> per-cell confidence list (table) or per-row float (list)
"""

import argparse
import re

from app.ocr.pipeline import run_ocr
from .detector import detect_type
from .list_parser import parse_list
from .table_parser import parse_table

MIN_CONF = 0.10          # words below this confidence are almost always noise
_JUNK_PATTERN = re.compile(r"^([a-zA-Z])\1*$")   # "ee", "oo", "e" - repeated
                                                  # single letters, a common
                                                  # OCR misread of ruled lines,
                                                  # watermarks, or pen scribbles


def _clean_words(words):
    """Drop OCR 'words' that are almost certainly noise, not real text:
    very low confidence tokens, and single-letter-repeated junk like 'ee'
    (Tesseract often reads ruled paper lines or stray marks this way).
    Also trims stray line/pen characters stuck to a word ("1~" -> "1")."""
    cleaned = []
    for w in words:
        w.text = w.text.strip("~_|\u2014\u2013 ")
        if w.text and w.conf >= MIN_CONF and not _JUNK_PATTERN.match(w.text):
            cleaned.append(w)
    return cleaned


def _drop_empty_columns(headers, grid):
    """Remove columns that are empty in every row (and the header)."""
    if not grid:
        return headers, grid
    n = len(grid[0]["cells"])
    keep = [i for i in range(n)
            if any(r["cells"][i] for r in grid) or (i < len(headers) and headers[i])]
    if len(keep) == n:
        return headers, grid
    headers = [headers[i] for i in keep if i < len(headers)]
    grid = [{"cells": [r["cells"][i] for i in keep], "confs": [r["confs"][i] for i in keep]}
            for r in grid]
    return headers, grid


def structure(ocr_result):
    """ocr_result is a single OCRResult (not the dict from run_ocr)."""
    words = _clean_words(ocr_result.words)
    doc_type, rows = detect_type(words)

    if doc_type == "table":
        grid, col_centres = parse_table(rows)

        # Use the first row as headers if it looks like a header
        # (simple heuristic: all cells are non-numeric)
        headers = []
        if grid:
            first = grid[0]["cells"]
            if all(not c.replace(".", "").replace(",", "").isdigit() for c in first if c):
                headers = first
                grid = grid[1:]   # remove header row from data

        headers, grid = _drop_empty_columns(headers, grid)

        return {
            "type": "table",
            "headers": headers,
            "data": grid,
            "confs": [row["confs"] for row in grid],
        }

    else:   # list
        records = parse_list(rows)
        return {
            "type": "list",
            "headers": ["qty", "unit", "item"],
            "data": records,
            "confs": [r["conf"] for r in records],
        }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--engine", default="tesseract", choices=["tesseract", "easyocr"])
    ap.add_argument("--no-preprocess", action="store_true")
    args = ap.parse_args()

    results = run_ocr(args.image, args.engine, not args.no_preprocess)
    ocr = results[args.engine]
    out = structure(ocr)

    print(f"Type detected : {out['type']}")
    print(f"Headers       : {out['headers']}")
    print()

    if out["type"] == "list":
        print(f"{'QTY':<8}{'UNIT':<8}{'ITEM':<30}{'CONF':>6}")
        print("-" * 55)
        for r in out["data"]:
            print(f"{r['qty']:<8}{r['unit']:<8}{r['item']:<30}{r['conf']:>6.2f}")
    else:
        print("  |  ".join(f"{h:<14}" for h in out["headers"]))
        print("-" * (17 * max(1, len(out["headers"]))))
        for row in out["data"]:
            print("  |  ".join(f"{c:<14}" for c in row["cells"]))
