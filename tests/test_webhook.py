"""
The WhatsApp conversation flow. Twilio sending and the photo reader are faked,
so nothing touches the network.
"""

from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import OUTPUT_DIR
from app.db.models import Base, engine, init_db, SessionLocal, EditJob, RequestLog
from app.main import app
from app.session import get_session, clear_session
from app.webhook import handle_message

PHONE = "whatsapp:+911234567890"
BOT = "whatsapp:+17372508034"
BASE = "https://demo.ngrok-free.dev"
AUTH = ("sid", "token")

READ_OK = {"headers": ["Items", "Qty"], "rows": [["Bag", "2"], ["Pen", "3"]],
           "confs": [[1.0, 1.0], [0.5, 1.0]], "doc_type": "table",
           "engine": "groq-qwen", "avg_conf": 0.9, "note": ""}


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    init_db()
    yield
    clear_session(PHONE)


@pytest.fixture
def sent():
    return []


@pytest.fixture
def photo(tmp_path):
    p = tmp_path / "photo.jpg"
    cv2.imwrite(str(p), (np.indices((200, 200)).sum(axis=0) % 2 * 255).astype("uint8"))
    return p


def _sender(sent):
    def send(to, from_, body, media_url=None):
        sent.append({"to": to, "from": from_, "body": body, "media_url": media_url})
    return send


def send_photo(photo_path):
    with patch("app.webhook._download_media", return_value=photo_path):
        return handle_message(PHONE, "", 1, "http://fake", AUTH, BASE, BOT)


def say(text, sent, **kw):
    return handle_message(PHONE, text, 0, None, AUTH, BASE, BOT, send=_sender(sent), **kw)


def test_text_without_session_gets_welcome(sent):
    assert "Send me a photo" in say("hello", sent)


def test_photo_asks_whether_to_edit(photo):
    twiml = send_photo(photo)
    assert "edit" in twiml.lower() and "1." in twiml and "2." in twiml
    assert get_session(PHONE).state == "awaiting_edit_choice"


def test_blurry_photo_is_accepted_first_time(tmp_path):
    """No 'please resend' - even a very blurry photo goes straight to the question."""
    flat = tmp_path / "blurry.jpg"
    cv2.imwrite(str(flat), np.full((200, 200), 128, dtype="uint8"))
    twiml = send_photo(flat)
    assert "blurry" not in twiml.lower()
    assert "edit" in twiml.lower()


def test_invalid_replies_ask_again(photo, sent):
    send_photo(photo)
    assert "didn't understand" in say("banana", sent)          # edit question
    say("no", sent)
    assert "didn't understand" in say("banana", sent)          # format menu
    assert get_session(PHONE).state == "awaiting_format"
    assert sent == []


def test_no_then_format_sends_file_directly(photo, sent):
    send_photo(photo)
    assert "which format" in say("no", sent).lower()
    with patch("app.webhook.extract_grid", return_value=READ_OK):
        twiml = say("csv", sent)
    assert "Reading your photo" in twiml

    assert len(sent) == 1
    msg = sent[0]
    assert msg["to"] == PHONE and msg["from"] == BOT        # replies from the number they chatted with
    assert msg["media_url"].startswith(f"{BASE}/files/") and msg["media_url"].endswith("/SnapDocc.csv")
    folder = msg["media_url"].split("/files/")[1].split("/")[0]
    text = (OUTPUT_DIR / folder / "SnapDocc.csv").read_text()
    assert "Bag,2" in text and "Pen,3" in text
    assert get_session(PHONE) is None                         # conversation finished
    assert not photo.exists()                                 # photo deleted after a direct job

    db = SessionLocal()
    log = db.query(RequestLog).one()
    db.close()
    assert log.status == "success" and log.ocr_engine == "groq-qwen" and log.fmt == "csv"


def test_yes_sends_edit_link_and_saves_job(photo, sent):
    send_photo(photo)
    with patch("app.webhook.extract_grid", return_value=READ_OK):
        twiml = say("1", sent)
    assert "edit link" in twiml.lower()

    assert len(sent) == 1 and sent[0]["from"] == BOT and sent[0]["media_url"] is None
    assert f"{BASE}/edit/" in sent[0]["body"]

    db = SessionLocal()
    job = db.query(EditJob).one()
    db.close()
    assert sent[0]["body"].count(job.token) == 1
    assert job.phone == PHONE and job.bot_number == BOT and job.engine == "groq-qwen"
    assert Path(job.image_path).exists()                      # photo kept for the edit page
    assert '"Bag"' in job.grid_json


def test_typing_a_format_name_skips_the_question(photo, sent):
    send_photo(photo)
    with patch("app.webhook.extract_grid", return_value=READ_OK):
        say("pdf", sent)
    assert sent[0]["media_url"].endswith("/SnapDocc.pdf")


def test_extra_messages_while_processing_are_ignored(photo, sent):
    send_photo(photo)
    say("1", sent, background=lambda *a, **k: None)           # job never runs
    assert get_session(PHONE).state == "processing"
    assert "Still reading" in say("1", sent)


def test_fallback_reason_is_shown_to_the_user(sent, tmp_path):
    """Real Tesseract path (Groq key is blank in tests): the user is told why it is basic OCR."""
    from PIL import Image, ImageDraw, ImageFont
    p = tmp_path / "list.jpg"
    im = Image.new("RGB", (800, 300), "white")
    try:
        font = ImageFont.load_default(size=60)
    except TypeError:
        font = ImageFont.load_default()
    ImageDraw.Draw(im).text((30, 40), "2 kg Rice", fill="black", font=font)
    ImageDraw.Draw(im).text((30, 150), "1 L Milk", fill="black", font=font)
    im.save(p)

    send_photo(p)
    say("csv", sent)
    assert len(sent) == 1 and "basic OCR" in sent[0]["body"]


def test_no_text_found_message(photo, sent):
    send_photo(photo)
    empty = {**READ_OK, "rows": [], "confs": []}
    with patch("app.webhook.extract_grid", return_value=empty):
        say("1", sent)
    assert "couldn't find any readable text" in sent[0]["body"] and sent[0]["media_url"] is None


def test_error_in_job_apologises_and_logs(photo, sent):
    send_photo(photo)
    with patch("app.webhook.extract_grid", side_effect=RuntimeError("boom")):
        say("1", sent)
    assert "Something went wrong" in sent[0]["body"]
    db = SessionLocal()
    assert db.query(RequestLog).one().status == "error:boom"
    db.close()
    assert get_session(PHONE) is None


def test_missing_public_url_is_reported(photo, sent):
    send_photo(photo)
    with patch("app.webhook.extract_grid", return_value=READ_OK):
        handle_message(PHONE, "1", 0, None, AUTH, "", BOT, send=_sender(sent))
    assert "PUBLIC_BASE_URL" in sent[0]["body"]


def test_too_large_and_invalid_images_are_rejected(tmp_path):
    with patch("app.webhook._download_media", side_effect=ValueError("file_too_large")):
        assert "too large" in handle_message(PHONE, "", 1, "http://x", AUTH, BASE, BOT).lower()
    junk = tmp_path / "junk.jpg"
    junk.write_text("not an image")
    with patch("app.webhook._download_media", return_value=junk):
        assert "doesn't look like a photo" in handle_message(PHONE, "", 1, "http://x", AUTH, BASE, BOT)
    assert get_session(PHONE) is None


def test_whole_flow_over_http_returns_file_in_one_reply(photo, monkeypatch):
    """Through the real /webhook route: background task runs, `To` becomes the sender."""
    monkeypatch.setenv("PUBLIC_BASE_URL", BASE)

    def post(**form):
        return client.post("/webhook", data={"From": PHONE, "To": BOT, **form}).text

    with TestClient(app) as client, \
         patch("app.webhook._download_media", return_value=photo), \
         patch("app.webhook.extract_grid", return_value=READ_OK), \
         patch("app.webhook.deliver") as fake_send:
        assert "edit" in post(Body="", NumMedia="1", MediaUrl0="http://x").lower()
        assert "which format" in post(Body="2", NumMedia="0").lower()
        reply = post(Body="excel", NumMedia="0")      # the file comes back as the reply itself

    assert "<Media>" in reply and reply.count("/SnapDocc.xlsx") == 1
    fake_send.assert_not_called()                      # no separate push needed


def test_sync_mode_returns_the_file_as_the_reply(photo):
    """One smooth flow: the file comes back in the webhook reply itself, no 'ok' needed."""
    send_photo(photo)
    handle_message(PHONE, "no", 0, None, AUTH, BASE, BOT)
    with patch("app.webhook.extract_grid", return_value=READ_OK):
        xml = handle_message(PHONE, "csv", 0, None, AUTH, BASE, BOT, sync=True)
    assert "Here's your CSV file" in xml and "/SnapDocc.csv" in xml and "<Media>" in xml


def test_sync_mode_slow_job_falls_back_to_delayed_send(photo, sent, monkeypatch):
    import time as _t
    monkeypatch.setattr("app.webhook.SYNC_WAIT_SECS", 0.05)
    send_photo(photo)
    handle_message(PHONE, "no", 0, None, AUTH, BASE, BOT)

    def slow(_):
        _t.sleep(0.3)
        return READ_OK
    with patch("app.webhook.extract_grid", side_effect=slow):
        xml = handle_message(PHONE, "csv", 0, None, AUTH, BASE, BOT, send=_sender(sent), sync=True)
        assert "Reading your photo" in xml
        _t.sleep(0.6)
    assert len(sent) == 1 and sent[0]["media_url"].endswith("/SnapDocc.csv")
