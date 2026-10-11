"""
Detect whether OCR output is a LIST or a TABLE.

Decision rule (transparent, column-based):
- Group words into rows by Y-coordinate.
- Find global column positions by clustering every word's left edge across
  ALL rows (same approach the table parser itself uses, so detection and
  parsing agree on where the columns are).
- For each row, count how many distinct columns it touches.
- If most rows touch 3+ columns  -> TABLE.
- Otherwise                      -> LIST.

Why not just look for "one big gap per row" (the old approach)? Printed
receipts and price tables often have TIGHT column spacing - the gap between
"NESTLE" and its price can be smaller than the gap between two words inside
a long product name. A single per-row gap check misses that. Building
columns from the whole document first is far more reliable.
"""

from statistics import median

from app.structuring.table_parser import _find_column_boundaries


def _cluster_rows(words, line_tol=None):
    """Group Word objects into rows by their vertical centre.
    Returns a list of lists, each inner list = one row, sorted top to bottom."""
    if not words:
        return []

    heights = [w.bbox[3] - w.bbox[1] for w in words]
    tol = line_tol or 0.6 * median(heights)

    rows = []
    for w in sorted(words, key=lambda w: (w.bbox[1] + w.bbox[3]) / 2):
        cy = (w.bbox[1] + w.bbox[3]) / 2
        if rows:
            avg = sum((x.bbox[1] + x.bbox[3]) / 2 for x in rows[-1]) / len(rows[-1])
            if abs(cy - avg) <= tol:
                rows[-1].append(w)
                continue
        rows.append([w])

    # Sort words inside each row left to right
    for row in rows:
        row.sort(key=lambda w: w.bbox[0])

    return rows


def _columns_touched(row, col_centres):
    """How many distinct global columns this row's words land in."""
    if not col_centres:
        return 1
    cols = {min(range(len(col_centres)), key=lambda i: abs(col_centres[i] - w.bbox[0]))
            for w in row}
    return len(cols)


def _row_is_noise(row, min_avg_conf=0.25):
    """A row is treated as noise (e.g. OCR misreading a dashed divider line
    as garbled text) if its average word confidence is very low. Real data
    rows - even messy ones - are consistently higher confidence than this."""
    if not row:
        return True
    avg_conf = sum(w.conf for w in row) / len(row)
    return avg_conf < min_avg_conf


def detect_type(words, min_columns_for_table=3, table_row_fraction=0.4):
    """Return ('table' or 'list', rows). Also returns the clustered rows for reuse.
    Rows that look like OCR noise (very low average confidence) are dropped."""
    rows = _cluster_rows(words)
    rows = [r for r in rows if not _row_is_noise(r)]
    if not rows:
        return "list", rows

    col_centres = _find_column_boundaries(rows)
    # Only count rows with at least 2 words - a single stray word (a page
    # number, a watermark fragment) shouldn't sway the decision.
    real_rows = [r for r in rows if len(r) >= 2]
    if not real_rows:
        return "list", rows

    multi = sum(1 for r in real_rows if _columns_touched(r, col_centres) >= min_columns_for_table)
    doc_type = "table" if multi / len(real_rows) >= table_row_fraction else "list"
    return doc_type, rows
