"""Format parsing, DB migration, housekeeping, Twilio sender."""
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import text

from app.utils.formats import parse_edit_reply, parse_format_reply, parse_format_name


def test_parse_edit_reply():
    assert parse_edit_reply("1") == "edit" and parse_edit_reply("Yes") == "edit"
    assert parse_edit_reply("2") == "direct" and parse_edit_reply("no") == "direct"
    assert parse_edit_reply("banana") is None


def test_parse_format_reply():
    assert parse_format_reply("1") == "excel" and parse_format_reply("PDF") == "pdf"
    assert parse_format_reply("xlsx") == "excel" and parse_format_reply("9") is None


def test_parse_format_name_ignores_digits():
    assert parse_format_name("1") is None and parse_format_name("csv") == "csv"


def test_old_edit_jobs_table_is_migrated():
    from app.db.models import engine, Base, init_db
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.execute(text("CREATE TABLE edit_jobs (token VARCHAR PRIMARY KEY, phone VARCHAR)"))
    init_db()
    with engine.begin() as c:
        cols = {r[1] for r in c.execute(text("PRAGMA table_info(edit_jobs)"))}
    assert {"bot_number", "engine", "grid_json", "created_at"} <= cols


def test_housekeeping_removes_only_old_things():
    from app.config import UPLOAD_DIR
    from app.housekeeping import run_housekeeping
    old, new = UPLOAD_DIR / "old.jpg", UPLOAD_DIR / "new.jpg"
    old.write_bytes(b"x"); new.write_bytes(b"x")
    t = time.time() - 3 * 24 * 3600
    os.utime(old, (t, t))
    run_housekeeping()
    assert not old.exists() and new.exists()
    new.unlink()


def test_send_whatsapp_uses_twilio_client(monkeypatch):
    from app import messaging
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "tok")
    with patch("app.messaging.Client") as C:
        messaging.send_whatsapp("whatsapp:+911", "whatsapp:+1415", "hi", "https://x/f.csv")
    kw = C.return_value.messages.create.call_args.kwargs
    assert kw["to"] == "whatsapp:+911" and kw["from_"] == "whatsapp:+1415"
    assert kw["media_url"] == ["https://x/f.csv"]


def test_send_whatsapp_without_credentials_raises(monkeypatch):
    from app import messaging
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    with pytest.raises(RuntimeError):
        messaging.send_whatsapp("a", "b", "hi")


def test_deliver_queues_when_twilio_refuses_and_next_reply_gets_it(monkeypatch):
    from app import messaging
    from app.db.models import Base, engine, init_db
    Base.metadata.drop_all(engine); init_db()
    with patch("app.messaging.send_whatsapp", side_effect=RuntimeError("ContentSid Required")):
        assert messaging.deliver("whatsapp:+911", "whatsapp:+1415", "hi", "https://x/f.csv") == "queued"
    assert messaging.pop_pending("whatsapp:+999") is None
    assert messaging.pop_pending("whatsapp:+911") == ("hi", "https://x/f.csv")
    assert messaging.pop_pending("whatsapp:+911") is None          # delivered once only


def test_webhook_hands_over_queued_file_with_media():
    from app import messaging
    from app.db.models import Base, engine, init_db
    from app.webhook import handle_message
    Base.metadata.drop_all(engine); init_db()
    with patch("app.messaging.send_whatsapp", side_effect=RuntimeError("nope")):
        messaging.deliver("whatsapp:+911", "b", "Here you go", "https://x/SnapDocc.xlsx")
    xml = handle_message("whatsapp:+911", "ok", 0, None, ("a", "b"))
    assert "Here you go" in xml and "https://x/SnapDocc.xlsx" in xml
