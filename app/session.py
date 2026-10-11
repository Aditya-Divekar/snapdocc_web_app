"""
Thin helper layer over the Session table: create / fetch / update / clear,
so webhook.py never touches SQLAlchemy directly.
"""

from datetime import datetime

from app.db.models import Session, SessionLocal


def get_session(phone):
    """Return the active Session row for this phone number, or None.
    Automatically deletes and ignores an expired session."""
    db = SessionLocal()
    try:
        s = db.query(Session).filter_by(phone=phone).first()
        if s and s.is_expired():
            db.delete(s)
            db.commit()
            return None
        return s
    finally:
        db.close()


def start_session(phone, image_path, state="awaiting_edit_choice"):
    """Create (or replace) a session: user just sent a photo, we now wait for their answer."""
    db = SessionLocal()
    try:
        existing = db.query(Session).filter_by(phone=phone).first()
        if existing:
            db.delete(existing)
            db.commit()
        s = Session(phone=phone, image_path=image_path, state=state)
        db.add(s)
        db.commit()
        return s
    finally:
        db.close()


def set_state(phone, state):
    """Move the conversation to its next step (and restart the expiry timer)."""
    db = SessionLocal()
    try:
        s = db.query(Session).filter_by(phone=phone).first()
        if s:
            s.state = state
            s.created_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def clear_session(phone):
    db = SessionLocal()
    try:
        s = db.query(Session).filter_by(phone=phone).first()
        if s:
            db.delete(s)
            db.commit()
    finally:
        db.close()
