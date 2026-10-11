"""
Send a WhatsApp message (optionally with a file) using the Twilio REST API.

The webhook can only answer one message per incoming message, and quickly.
Anything slow (reading the photo) or later (the web page sending the final
file) is sent from here instead.
"""

import os

from twilio.rest import Client


def send_whatsapp(to, from_, body, media_url=None):
    """to / from_ look like 'whatsapp:+9199...'. media_url must be a public https URL.
    from_ should be the number the user chatted with (Twilio sends it as the
    webhook's `To` field); TWILIO_WHATSAPP_NUMBER in .env is only a fallback."""
    sid = os.getenv("TWILIO_ACCOUNT_SID")
    token = os.getenv("TWILIO_AUTH_TOKEN")
    from_ = from_ or os.getenv("TWILIO_WHATSAPP_NUMBER")
    if not (sid and token and from_):
        raise RuntimeError("Twilio credentials or sender number are missing in .env")

    kwargs = {"from_": from_, "to": to, "body": body}
    if media_url:
        kwargs["media_url"] = [media_url]
    return Client(sid, token).messages.create(**kwargs).sid


def deliver(to, from_, body, media_url=None):
    """Send with the REST API; if Twilio refuses (some accounts do), keep the message
    and give it to the user as the reply to their next WhatsApp message instead.
    Returns "sent" or "queued"."""
    try:
        send_whatsapp(to, from_, body, media_url)
        return "sent"
    except Exception as e:
        print(f"[messaging] REST send failed, queued for the next reply: {' '.join(str(e).split())[:200]}")
        from app.db.models import SessionLocal, PendingDelivery
        db = SessionLocal()
        try:
            db.add(PendingDelivery(phone=to, body=body, media_url=media_url))
            db.commit()
        finally:
            db.close()
        return "queued"


def pop_pending(phone):
    """Oldest queued message for this phone (and delete it), or None."""
    from app.db.models import SessionLocal, PendingDelivery
    db = SessionLocal()
    try:
        row = (db.query(PendingDelivery).filter(PendingDelivery.phone == phone)
               .order_by(PendingDelivery.id).first())
        if row is None:
            return None
        out = (row.body, row.media_url)
        db.delete(row)
        db.commit()
        return out
    finally:
        db.close()
