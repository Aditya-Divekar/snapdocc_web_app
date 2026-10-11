"""
Single entry point for all file generators.

    path = convert(structured_data, fmt, output_dir)

fmt can be: "excel", "xlsx", "word", "docx", "pdf", "csv", "txt"
"""

from pathlib import Path
from .excel   import generate_excel
from .word    import generate_word
from .pdf     import generate_pdf
from .csv_gen import generate_csv
from .txt_gen import generate_txt

FORMAT_MAP = {
    "excel": "xlsx", "xlsx": "xlsx",
    "word":  "docx", "docx": "docx",
    "pdf":   "pdf",
    "csv":   "csv",
    "txt":   "txt",
}

GENERATORS = {
    "xlsx": generate_excel,
    "docx": generate_word,
    "pdf":  generate_pdf,
    "csv":  generate_csv,
    "txt":  generate_txt,
}


def convert(structured, fmt, output_dir="data/output", stem="document"):
    """
    structured : dict from app.structuring.pipeline.structure()
    fmt        : format string (see FORMAT_MAP above)
    output_dir : folder to save the file in (created if missing)
    stem       : base file name without extension
    Returns    : Path of the generated file
    """
    fmt = fmt.strip().lower()
    ext = FORMAT_MAP.get(fmt)
    if ext is None:
        raise ValueError(f"Unsupported format '{fmt}'. Choose: {', '.join(FORMAT_MAP)}")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{stem}.{ext}"

    return GENERATORS[ext](structured, out_path)


if __name__ == "__main__":
    """Quick demo: generate all 5 formats from a sample image."""
    import argparse
    from app.ocr.pipeline import run_ocr
    from app.structuring.pipeline import structure

    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--engine", default="tesseract")
    ap.add_argument("--fmt", default="all")
    args = ap.parse_args()

    ocr_results = run_ocr(args.image, args.engine)
    ocr         = ocr_results[args.engine]
    structured  = structure(ocr)
    stem        = Path(args.image).stem

    fmts = list(FORMAT_MAP) if args.fmt == "all" else [args.fmt]
    seen = set()
    for f in fmts:
        ext = FORMAT_MAP[f]
        if ext in seen:
            continue
        seen.add(ext)
        out = convert(structured, f, stem=stem)
        print(f"Generated: {out}")
