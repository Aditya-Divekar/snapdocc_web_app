"""
A "grid" is the simple shape the edit page works with:
    {"headers": ["Item", "Qty"], "rows": [["Bag", "2"], ["Pen", "3"]],
     "confs": [[1.0, 1.0], [0.5, 1.0]]}          <- confs is optional

confs says how sure the reader was about each cell (0-1). Cells below 0.75
are highlighted yellow in the Excel file and on the edit page.

These helpers convert between a grid and the `structured` dict that the
file generators (convert.py) already understand.
"""

MAX_ROWS, MAX_COLS, MAX_CELL = 500, 20, 500   # safety limits for web input


def normalize_grid(headers, rows, confs=None):
    """Make every row the same width, strip whitespace, drop fully-empty rows
    (keeping confs lined up with the rows that stay)."""
    headers = [str(h).strip() for h in (headers or [])]

    kept = []   # (cells, confidences)
    for i, row in enumerate(rows or []):
        if not isinstance(row, (list, tuple)):
            continue
        cells = [str(c).strip() for c in row]
        if not any(cells):
            continue
        row_confs = list(confs[i]) if confs is not None and i < len(confs) else []
        kept.append((cells, row_confs))

    width = min(max([len(headers)] + [len(c) for c, _ in kept] + [1]), MAX_COLS)
    headers = (headers + [""] * width)[:width]
    headers = [h or f"Column {i + 1}" for i, h in enumerate(headers)]
    kept = kept[:MAX_ROWS]

    grid = {
        "headers": headers,
        "rows": [[c[:MAX_CELL] for c in (cells + [""] * width)[:width]] for cells, _ in kept],
    }
    if confs is not None:
        grid["confs"] = [(rc + [1.0] * width)[:width] for _, rc in kept]
    return grid


def structured_to_grid(structured):
    """structured dict (list or table type) -> grid, keeping confidences."""
    if structured["type"] == "list":
        headers = ["Qty", "Unit", "Item"]
        rows = [[r["qty"], r["unit"], r["item"]] for r in structured["data"]]
        confs = [[r["conf"]] * 3 for r in structured["data"]]
    else:
        headers = structured.get("headers", [])
        rows = [r["cells"] for r in structured["data"]]
        confs = [r["confs"] for r in structured["data"]]
    return normalize_grid(headers, rows, confs)


def grid_to_structured(grid):
    """grid -> structured dict (always 'table' type) for the file generators.
    Without confs, every cell counts as fully confident (e.g. after a human edit)."""
    grid = normalize_grid(grid["headers"], grid["rows"], grid.get("confs"))
    confs = grid.get("confs") or [[1.0] * len(r) for r in grid["rows"]]
    return {
        "type": "table",
        "headers": grid["headers"],
        "data": [{"cells": r, "confs": c} for r, c in zip(grid["rows"], confs)],
        "confs": confs,
    }
