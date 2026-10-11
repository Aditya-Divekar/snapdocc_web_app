"""Generate a PDF file from structured data using ReportLab."""

from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

CONF_THRESHOLD = 0.75
LOW_CONF_BG    = colors.HexColor("#FFFF00")   # yellow
HEADER_BG      = colors.HexColor("#4472C4")   # blue


def generate_pdf(structured, output_path):
    out  = Path(output_path)
    doc  = SimpleDocTemplate(str(out), pagesize=A4,
                             leftMargin=2*cm, rightMargin=2*cm,
                             topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = [Paragraph("SnapDocc – Digitized Document", styles["Title"])]

    headers = structured.get("headers", [])
    data    = structured.get("data", [])

    table_data  = [headers] if headers else []
    cell_styles = []          # list of TableStyle commands we'll build

    for row_i, row in enumerate(data, 1):   # 0 = header row
        if structured["type"] == "list":
            cells     = [row.get("qty", ""), row.get("unit", ""), row.get("item", "")]
            conf_vals = [row.get("conf", 1.0)] * 3
        else:
            cells     = row["cells"]
            conf_vals = row["confs"]

        table_data.append([str(c) for c in cells])

        for col_i, conf in enumerate(conf_vals):
            if conf < CONF_THRESHOLD:
                cell_styles.append(
                    ("BACKGROUND", (col_i, row_i), (col_i, row_i), LOW_CONF_BG)
                )

    if not table_data:
        doc.build(story)
        return out

    tbl = Table(table_data, repeatRows=1)
    base_style = [
        ("BACKGROUND",  (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN",       (0, 0), (-1, -1), "LEFT"),
        ("GRID",        (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
    ]
    tbl.setStyle(TableStyle(base_style + cell_styles))
    story.append(tbl)
    doc.build(story)
    return out
