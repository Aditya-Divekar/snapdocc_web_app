"""Generate a CSV file from structured data."""

import csv
from pathlib import Path
from .sanitize import sanitize_cell


def generate_csv(structured, output_path):
    out = Path(output_path)
    headers = structured.get("headers", [])
    data    = structured.get("data", [])

    with open(out, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if headers:
            writer.writerow([sanitize_cell(h) for h in headers])
        for row in data:
            if structured["type"] == "list":
                cells = [row.get("qty",""), row.get("unit",""), row.get("item","")]
            else:
                cells = row["cells"]
            writer.writerow([sanitize_cell(c) for c in cells])

    return out
