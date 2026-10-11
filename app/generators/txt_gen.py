"""Generate a plain text file from structured data."""

from pathlib import Path


def generate_txt(structured, output_path):
    out   = Path(output_path)
    lines = []

    headers = structured.get("headers", [])
    data    = structured.get("data", [])

    if headers:
        lines.append("\t".join(headers))
        lines.append("-" * 40)

    for row in data:
        if structured["type"] == "list":
            parts = [row.get("qty",""), row.get("unit",""), row.get("item","")]
        else:
            parts = row["cells"]
        lines.append("\t".join(str(p) for p in parts))

    out.write_text("\n".join(lines), encoding="utf-8")
    return out
