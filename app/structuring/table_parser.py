"""
Convert a list-of-rows (each row = sorted Word objects) into a 2-D grid.

Column detection:
  Collect all word left-edges (x1). Cluster nearby x1 values using a simple
  sweep: start a new cluster whenever the gap to the previous x1 exceeds
  col_gap_px. The centre of each cluster is a column boundary.
  Then assign each word to the nearest column.
"""

from statistics import median


def _find_column_boundaries(rows, col_gap_px=None):
    """Return a sorted list of column X-centres."""
    # Collect every word's left edge
    all_x1 = sorted(w.bbox[0] for row in rows for w in row)
    if not all_x1:
        return []

    gap = col_gap_px or median(
        w.bbox[2] - w.bbox[0] for row in rows for w in row) * 0.8

    clusters = [[all_x1[0]]]
    for x in all_x1[1:]:
        if x - clusters[-1][-1] > gap:
            clusters.append([])
        clusters[-1].append(x)

    return [sum(c) / len(c) for c in clusters]


def parse_table(rows):
    """
    Return a 2-D list: result[row_idx][col_idx] = text string (empty if nothing there).
    Also returns column boundaries so the generator can highlight low-confidence cells.
    """
    col_centres = _find_column_boundaries(rows)
    if not col_centres:
        return [], []

    n_cols = len(col_centres)
    grid = []

    for row in rows:
        cells = [""] * n_cols
        confs = [1.0] * n_cols    # default confidence = perfect (will be overwritten)

        for w in row:
            # Assign word to the column whose centre is closest to the word's left edge
            col = min(range(n_cols), key=lambda i: abs(col_centres[i] - w.bbox[0]))
            cells[col] = (cells[col] + " " + w.text).strip()
            confs[col] = min(confs[col], w.conf)   # use worst confidence in cell

        grid.append({"cells": cells, "confs": confs})

    return grid, col_centres
