"""Groq engine, grid helpers and auto-correct - all with Groq mocked (no network, no key)."""
from unittest.mock import patch

import cv2
import numpy as np

from app.ocr.groq_engine import read_with_groq
from app.utils.autocorrect import autocorrect_grid
from app.utils.grid import normalize_grid, grid_to_structured, structured_to_grid
from app.utils.groq_client import extract_json


def _img(tmp_path):
    p = tmp_path / "x.jpg"
    cv2.imwrite(str(p), np.full((100, 100, 3), 255, dtype="uint8"))
    return p


def test_extract_json_handles_fences_and_think_blocks():
    text = '<think>hmm</think>\n```json\n{"rows": [["a"]]}\n```'
    assert extract_json(text) == {"rows": [["a"]]}
    assert extract_json("no json here") is None
    assert extract_json(None) is None


def test_groq_engine_parses_reply(tmp_path):
    reply = '{"type":"table","headers":["Items","Qty"],"rows":[["Bag","2"],["Pen","3"],["",""]]}'
    with patch("app.ocr.groq_engine.groq_chat", return_value=reply):
        out = read_with_groq(_img(tmp_path))
    assert out["headers"] == ["Items", "Qty"]
    assert out["rows"] == [["Bag", "2"], ["Pen", "3"]]   # empty row dropped
    assert out["doc_type"] == "table"


def test_groq_engine_returns_none_on_failure(tmp_path):
    with patch("app.ocr.groq_engine.groq_chat", return_value=None):
        assert read_with_groq(_img(tmp_path)) is None
    with patch("app.ocr.groq_engine.groq_chat", return_value="sorry, can't"):
        assert read_with_groq(_img(tmp_path)) is None


def test_normalize_grid_pads_and_names_headers():
    g = normalize_grid(["A"], [["1", "2", "3"], ["4"]])
    assert g["headers"] == ["A", "Column 2", "Column 3"]
    assert g["rows"] == [["1", "2", "3"], ["4", "", ""]]


def test_grid_structured_roundtrip():
    grid = {"headers": ["Item", "Qty"], "rows": [["Bag", "2"]]}
    s = grid_to_structured(grid)
    assert s["type"] == "table" and s["data"][0]["cells"] == ["Bag", "2"]
    back = structured_to_grid(s)
    assert back["headers"] == grid["headers"] and back["rows"] == grid["rows"]
    assert back["confs"] == [[1.0, 1.0]]


def test_autocorrect_local_fallback_without_groq_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    grid, method = autocorrect_grid(["items"], [["ricee", "2"], ["mobile", "1"]])
    assert method == "local"
    assert grid["rows"][0] == ["Rice", "2"]       # spelling fixed
    assert grid["rows"][1][0] == "Mobile"         # capitalised


def test_autocorrect_uses_groq_when_shape_is_unchanged(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test")
    good = '{"headers":["Items"],"rows":[["Rice","2"]]}'
    with patch("app.utils.autocorrect.groq_chat", return_value=good):
        grid, method = autocorrect_grid(["items"], [["ricee", "2"]])
    assert method == "groq" and grid["rows"] == [["Rice", "2"]]
    # LLM changed the number of rows -> not trusted, local fallback used
    bad = '{"headers":["Items"],"rows":[["Rice","2"],["extra","1"]]}'
    with patch("app.utils.autocorrect.groq_chat", return_value=bad):
        _, method = autocorrect_grid(["items"], [["ricee", "2"]])
    assert method == "local"


def test_uncertain_cells_get_low_confidence(tmp_path):
    reply = '{"type":"table","headers":["Items","Qty"],"rows":[["Bag","2"],["Pen","3"]],"uncertain":[[1,0],[9,9]]}'
    with patch("app.ocr.groq_engine.groq_chat", return_value=reply):
        out = read_with_groq(_img(tmp_path))
    assert out["confs"] == [[1.0, 1.0], [0.5, 1.0]]      # bad position [9,9] ignored


def test_normalize_keeps_confs_aligned_when_empty_rows_dropped():
    g = normalize_grid(["A"], [["x"], [""], ["y"]], [[1.0], [1.0], [0.5]])
    assert g["rows"] == [["x"], ["y"]] and g["confs"] == [[1.0], [0.5]]


def test_extract_grid_falls_back_with_a_reason(tmp_path):
    from app.ocr.extract import extract_grid
    with patch("app.ocr.extract.read_with_groq", return_value=None):
        out = extract_grid(_img(tmp_path))
    assert out["engine"] != "groq-qwen" and "basic OCR" in out["note"]
