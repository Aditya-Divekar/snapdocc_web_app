"""One entry point for the OCR module: run_ocr(image_path) -> {engine_name: OCRResult}."""
import argparse

from .preprocess import load_image, resize_max, preprocess, blur_score
from .tesseract_engine import run_tesseract
from .easyocr_engine import run_easyocr

ENGINES = {"tesseract": run_tesseract, "easyocr": run_easyocr}


def run_ocr(image_path, engine="both", use_preprocess=True):
    img = resize_max(load_image(image_path))
    ready = preprocess(img) if use_preprocess else img
    names = list(ENGINES) if engine == "both" else [engine]
    return {name: ENGINES[name](ready) for name in names}


if __name__ == "__main__":   # quick manual test: python -m app.ocr.pipeline photo.jpg
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--engine", default="both", choices=["both", *ENGINES])
    ap.add_argument("--no-preprocess", action="store_true")
    args = ap.parse_args()
    print(f"blur score: {blur_score(load_image(args.image)):.0f} (below ~100 = blurry)\n")
    for name, res in run_ocr(args.image, args.engine, not args.no_preprocess).items():
        print(f"=== {name} | {len(res.words)} words | avg conf {res.avg_conf:.2f} | {res.seconds:.1f}s ===")
        print(res.text, "\n")
