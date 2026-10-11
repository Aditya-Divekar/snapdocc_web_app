"""Compare OCR engines on a folder of images that have ground-truth text.

Layout:  data/samples/receipt1.jpg  +  data/samples/receipt1.txt  (the correct text)
Run:     python -m eval.evaluate [--folder data/samples] [--engine both] [--no-preprocess]
"""
import argparse
import csv
from pathlib import Path

from app.ocr.pipeline import run_ocr
from app.utils.metrics import cer, wer

IMAGE_EXT = {".jpg", ".jpeg", ".png"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="data/samples")
    ap.add_argument("--engine", default="both", choices=["both", "tesseract", "easyocr"])
    ap.add_argument("--no-preprocess", action="store_true")
    args = ap.parse_args()

    rows = []
    images = sorted(p for p in Path(args.folder).iterdir() if p.suffix.lower() in IMAGE_EXT)
    for img in images:
        truth_file = img.with_suffix(".txt")
        if not truth_file.exists():
            print(f"skip {img.name}: no {truth_file.name} ground-truth file")
            continue
        truth = truth_file.read_text(encoding="utf-8")
        for name, res in run_ocr(img, args.engine, not args.no_preprocess).items():
            rows.append({"image": img.name, "engine": name,
                         "CER": cer(truth, res.text), "WER": wer(truth, res.text),
                         "conf": res.avg_conf, "seconds": res.seconds})
    if not rows:
        print("No images evaluated. Add images + .txt files to", args.folder)
        return

    # Per-image rows, then the average per engine
    print(f"\n{'image':<22}{'engine':<11}{'CER':>7}{'WER':>7}{'conf':>7}{'sec':>7}")
    print("-" * 61)
    for r in rows:
        print(f"{r['image']:<22}{r['engine']:<11}{r['CER']:>7.3f}{r['WER']:>7.3f}"
              f"{r['conf']:>7.2f}{r['seconds']:>7.1f}")
    print("-" * 61)
    for name in sorted({r["engine"] for r in rows}):
        mine = [r for r in rows if r["engine"] == name]
        avg = lambda k: sum(r[k] for r in mine) / len(mine)
        print(f"{'AVERAGE':<22}{name:<11}{avg('CER'):>7.3f}{avg('WER'):>7.3f}"
              f"{avg('conf'):>7.2f}{avg('seconds'):>7.1f}")

    with open("eval/results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print("\nSaved eval/results.csv")


if __name__ == "__main__":
    main()
