"""Unit tests for the structuring module. No images needed - we build fake Word objects."""

from app.ocr.base import Word
from app.structuring.detector import detect_type
from app.structuring.list_parser import parse_list, _is_number
from app.structuring.table_parser import parse_table


def make_word(text, x1, y1, x2, y2, conf=0.9):
    return Word(text, (x1, y1, x2, y2), conf)


# --- detector ---

def test_detect_list():
    # Words stacked vertically, no big horizontal gaps -> list
    words = [
        make_word("2", 10, 0, 30, 20),
        make_word("kg", 35, 0, 70, 20),
        make_word("Rice", 75, 0, 140, 20),
        make_word("1", 10, 30, 30, 50),
        make_word("L", 35, 30, 50, 50),
        make_word("Milk", 55, 30, 110, 50),
    ]
    t, rows = detect_type(words)
    assert t == "list"
    assert len(rows) == 2


def test_detect_table():
    # Each row has 3 aligned column clusters (name / qty / price) - this is
    # what reliably distinguishes a table from a list; a 2-column layout is
    # genuinely ambiguous with a list row like "2 kg Rice".
    words = [
        make_word("Item", 10, 0, 60, 20),   make_word("Qty", 250, 0, 290, 20),   make_word("Price", 400, 0, 460, 20),
        make_word("Pen", 10, 30, 50, 50),   make_word("10", 250, 30, 270, 50),   make_word("5.00", 400, 30, 450, 50),
        make_word("Book", 10, 60, 55, 80),  make_word("3", 250, 60, 265, 80),    make_word("120.00", 400, 60, 480, 80),
    ]
    t, rows = detect_type(words)
    assert t == "table"


# --- list parser ---

def test_is_number():
    assert _is_number("5")
    assert _is_number("2.5")
    assert not _is_number("kg")
    assert not _is_number("Rice")


def test_list_parser_full():
    rows = [
        [make_word("2", 10, 0, 30, 20), make_word("kg", 35, 0, 70, 20), make_word("Rice", 75, 0, 140, 20)],
        [make_word("Soap", 10, 30, 60, 50)],
        [make_word("6", 10, 60, 30, 80), make_word("Eggs", 35, 60, 90, 80)],
    ]
    records = parse_list(rows)
    assert records[0] == {"qty": "2", "unit": "kg", "item": "Rice", "conf": 0.9}
    assert records[1] == {"qty": "", "unit": "", "item": "Soap", "conf": 0.9}
    assert records[2] == {"qty": "6", "unit": "", "item": "Eggs", "conf": 0.9}


# --- table parser ---

def test_table_parser():
    rows = [
        [make_word("Name", 10, 0, 80, 20), make_word("Qty", 300, 0, 340, 20),  make_word("Price", 500, 0, 560, 20)],
        [make_word("Pen", 10, 30, 50, 50), make_word("10", 300, 30, 330, 50),  make_word("5.00", 500, 30, 540, 50)],
        [make_word("Book", 10, 60, 60, 80),make_word("3", 300, 60, 320, 80),   make_word("120.00", 500, 60, 570, 80)],
    ]
    grid, centres = parse_table(rows)
    assert len(grid) == 3
    assert grid[0]["cells"][0] == "Name"
    assert grid[1]["cells"][1] == "10"
    assert grid[2]["cells"][2] == "120.00"


# --- regression: tight-column receipts and noisy rows (real photo bugs) ---

def test_detect_type_handles_tight_columns():
    """A receipt-style row where columns are close together (not one big
    gap) must still be detected as a table using the global column layout,
    not a single per-row gap check."""
    words = [
        make_word("HSN", 10, 0, 50, 20), make_word("Particulars", 60, 0, 160, 20),
        make_word("Qty", 250, 0, 280, 20), make_word("Rate", 320, 0, 360, 20), make_word("Value", 400, 0, 450, 20),
        make_word("190532", 10, 30, 70, 50), make_word("NESTLE", 80, 30, 140, 50),
        make_word("1", 255, 30, 270, 50), make_word("4.65", 325, 30, 365, 50), make_word("4.65", 405, 30, 445, 50),
        make_word("210690", 10, 60, 70, 80), make_word("BALAJI", 80, 60, 140, 80),
        make_word("1", 255, 60, 270, 80), make_word("72.00", 325, 60, 375, 80), make_word("72.00", 405, 60, 455, 80),
    ]
    t, _ = detect_type(words)
    assert t == "table"


def test_detect_type_drops_low_confidence_noise_row():
    """A row that's entirely low-confidence garbage (e.g. OCR misreading a
    dashed divider line) should be dropped, not counted as real data."""
    good_row_words = [
        make_word("Item", 10, 0, 60, 20, conf=0.9), make_word("Qty", 250, 0, 280, 20, conf=0.9),
        make_word("Price", 400, 0, 450, 20, conf=0.9),
        make_word("Pen", 10, 30, 50, 50, conf=0.9), make_word("2", 255, 30, 270, 50, conf=0.9),
        make_word("5.00", 405, 30, 445, 50, conf=0.9),
    ]
    noise_row = [
        make_word("ee", 10, 60, 30, 80, conf=0.1), make_word("ee", 40, 60, 60, 80, conf=0.05),
        make_word("waoueanaw", 80, 60, 160, 80, conf=0.0),
    ]
    t, rows = detect_type(good_row_words + noise_row)
    assert len(rows) == 2   # the noise row was dropped
    assert all("ee" not in [w.text for w in r] for r in rows)


def test_low_confidence_and_junk_words_are_filtered():
    """Very low confidence tokens, and repeated-single-letter junk like 'ee'
    (a common Tesseract misread of ruled lines), should never reach the
    structured output."""
    from app.structuring.pipeline import structure
    from app.ocr.base import OCRResult

    words = [
        make_word("Rice", 10, 0, 60, 20, conf=0.90),
        make_word("ee", 70, 0, 120, 20, conf=0.10),     # junk pattern, low conf
        make_word("eeeee", 10, 30, 100, 50, conf=0.05),  # junk pattern, very low conf
        make_word("Milk", 10, 60, 60, 80, conf=0.85),
    ]
    result = OCRResult(engine="tesseract", words=words, text="", avg_conf=0.5, seconds=0.1)
    out = structure(result)
    all_text = " ".join(r["item"] for r in out["data"])
    assert "ee" not in all_text.split()
    assert "Rice" in all_text
    assert "Milk" in all_text
