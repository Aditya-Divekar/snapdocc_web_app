"""The web edit page: load, photo, auto-correct, send to WhatsApp, download fallback."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import OUTPUT_DIR
from app.db.models import Base, engine, init_db, SessionLocal, EditJob
from app.main import app

BASE = "https://demo.ngrok-free.dev"
GRID = {"headers": ["Items", "Qty"], "rows": [["Bag", "2"], ["Pen", "3"]],
        "confs": [[1.0, 1.0], [0.5, 1.0]]}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)
    Base.metadata.drop_all(engine)
    init_db()
    with TestClient(app) as c:
        yield c


def _job(token="abc123", fmt="excel", age_hours=0, engine_name="groq-qwen", image_path=None, grid=GRID):
    db = SessionLocal()
    db.add(EditJob(token=token, phone="whatsapp:+911", bot_number="whatsapp:+1737", fmt=fmt,
                   engine=engine_name, image_path=image_path, grid_json=json.dumps(grid),
                   created_at=datetime.utcnow() - timedelta(hours=age_hours)))
    db.commit()
    db.close()
    return token


def test_page_has_send_button_and_data(client):
    html = client.get(f"/edit/{_job()}").text
    assert "Send to my WhatsApp" in html and "Bag" in html
    assert "Download file" not in html                        # no download button any more
    assert "Read by AI" in html
    assert '"flags": [[false, false], [true, false]]' in html  # the 0.5 cell is flagged yellow
    assert "Yellow cells" in html


def test_basic_ocr_badge_warns(client):
    html = client.get(f"/edit/{_job(engine_name='tesseract')}").text
    assert "basic OCR" in html


def test_photo_route(client, tmp_path):
    p = tmp_path / "p.jpg"
    cv2.imwrite(str(p), np.full((50, 50, 3), 200, dtype="uint8"))
    r = client.get(f"/edit/{_job(image_path=str(p))}/photo")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert "if (true)" in client.get("/edit/abc123").text      # page shows the photo section
    assert client.get(f"/edit/{_job('nophoto')}/photo").status_code == 404
    assert "if (false)" in client.get("/edit/nophoto").text


def test_unknown_and_expired_links_404(client):
    old = _job("old", age_hours=25)
    for path in ("/edit/nope", f"/edit/{old}", "/edit/nope/photo"):
        assert client.get(path).status_code == 404
    form = {"payload": json.dumps(GRID), "fmt": "csv"}
    assert client.post(f"/edit/{old}/send", data=form).status_code == 404
    assert client.post(f"/edit/{old}/download", data=form).status_code == 404
    assert client.post(f"/edit/{old}/autocorrect", json=GRID).status_code == 404


def test_script_injection_is_escaped(client):
    evil = {"headers": ["A"], "rows": [["</script><script>alert(1)</script>"]]}
    _job("evil", grid=evil)
    assert "</script><script>alert" not in client.get("/edit/evil").text


def test_autocorrect_endpoint(client):
    r = client.post(f"/edit/{_job()}/autocorrect", json={"headers": ["items"], "rows": [["ricee", "2"]]})
    assert r.status_code == 200
    assert r.json()["rows"] == [["Rice", "2"]] and r.json()["method"] == "local"


def test_send_uses_edited_content_and_sends_to_whatsapp(client):
    token = _job()
    edited = {"headers": ["Items", "Qty"], "rows": [["Bag", "2"], ["Notebook", "9"]]}
    with patch("app.web.deliver") as fake:
        r = client.post(f"/edit/{token}/send", data={"payload": json.dumps(edited), "fmt": "csv"})
    assert r.status_code == 200 and r.json()["ok"] is True

    to, from_, body, media_url = fake.call_args.args
    assert to == "whatsapp:+911" and from_ == "whatsapp:+1737"
    assert media_url.startswith(f"{BASE}/files/") and media_url.endswith("/SnapDocc.csv")
    # the file really is reachable at that public path, with the edited text
    served = client.get(media_url.replace(BASE, ""))
    assert served.status_code == 200 and "Notebook,9" in served.text


@pytest.mark.parametrize("fmt,ext", [("excel", "xlsx"), ("word", "docx"), ("pdf", "pdf"), ("txt", "txt")])
def test_send_all_formats(client, fmt, ext):
    with patch("app.web.deliver") as fake:
        r = client.post(f"/edit/{_job()}/send", data={"payload": json.dumps(GRID), "fmt": fmt})
    assert r.status_code == 200
    assert fake.call_args.args[3].endswith(f"/SnapDocc.{ext}")


def test_send_failure_returns_reason_and_page_offers_download(client):
    class TwilioLike(Exception):
        msg = "Unable to create record: sandbox session expired"
    with patch("app.web.deliver", side_effect=TwilioLike("long technical text")):
        r = client.post(f"/edit/{_job()}/send", data={"payload": json.dumps(GRID), "fmt": "csv"})
    assert r.status_code == 502 and r.json()["ok"] is False
    assert "sandbox session expired" in r.json()["error"]


def test_send_without_public_url_or_with_bad_input(client, monkeypatch):
    token = _job()
    good = {"payload": json.dumps(GRID), "fmt": "csv"}
    assert client.post(f"/edit/{token}/send", data={**good, "fmt": "exe"}).status_code == 400
    assert client.post(f"/edit/{token}/send", data={**good, "payload": "not json"}).status_code == 400
    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    assert client.post(f"/edit/{token}/send", data=good).status_code == 500


def test_download_fallback_still_works(client):
    r = client.post(f"/edit/{_job()}/download", data={"payload": json.dumps(GRID), "fmt": "csv"})
    assert r.status_code == 200 and "Bag,2" in r.text
    assert "attachment" in r.headers["content-disposition"]
