"""Regression test for the '#NAME?' bug: cell text starting with '=' must
never be interpreted as a formula by Excel."""

from pathlib import Path
import shutil
import openpyxl
from app.generators.convert import convert

SAMPLE = {
    "type": "table",
    "headers": ["HSN", "Particulars"],
    "data": [
        {"cells": ["190532", "= Qty: noise"], "confs": [0.9, 0.2]},
    ],
    "confs": [[0.9, 0.2]],
}

OUT = Path("data/test_output_formula")


def test_excel_cell_starting_with_equals_is_not_a_formula():
    path = convert(SAMPLE, "excel", OUT)
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    cell = ws.cell(2, 2)   # the "= Qty: noise" cell
    assert cell.data_type != "f"          # must NOT be stored as a formula
    assert cell.value.strip() == "= Qty: noise"
    shutil.rmtree(OUT)
