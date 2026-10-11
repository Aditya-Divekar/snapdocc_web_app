"""Confirm the log viewer script runs without errors against real logged data."""

import subprocess
import sys
from pathlib import Path


def test_view_logs_runs_after_a_request(tmp_path, monkeypatch):
    # Ensure at least one log row exists by importing and calling _log directly
    from app.db.models import init_db, SessionLocal, RequestLog

    init_db()
    db = SessionLocal()
    db.add(RequestLog(phone="whatsapp:+911111111111", doc_type="list", fmt="csv",
                      ocr_engine="tesseract", avg_confidence=0.9,
                      processing_secs=0.5, status="success"))
    db.commit()
    db.close()

    result = subprocess.run([sys.executable, "-m", "app.db.view_logs"],
                            capture_output=True, text=True, cwd=Path(__file__).parent.parent)
    assert result.returncode == 0
    assert "Total requests logged" in result.stdout
