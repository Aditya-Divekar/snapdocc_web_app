"""
Delete old data: uploaded photos, generated files and expired edit links.
Good for privacy (documents can contain personal info) and disk space.
Runs at startup and after every processed photo.
"""

import shutil
import time
from datetime import datetime, timedelta

from app.config import UPLOAD_DIR, OUTPUT_DIR, DOWNLOAD_DIR
from app.db.models import SessionLocal, EditJob, Session, PendingDelivery, EDIT_LINK_HOURS

MAX_AGE_HOURS = EDIT_LINK_HOURS + 1   # one hour longer than a link is valid


def run_housekeeping():
    cutoff = time.time() - MAX_AGE_HOURS * 3600
    for folder in (UPLOAD_DIR, OUTPUT_DIR, DOWNLOAD_DIR):
        for item in folder.iterdir():
            try:
                if item.stat().st_mtime < cutoff:
                    shutil.rmtree(item) if item.is_dir() else item.unlink()
            except OSError:
                pass   # in use or already gone - next run will retry

    old = datetime.utcnow() - timedelta(hours=MAX_AGE_HOURS)
    db = SessionLocal()
    try:
        db.query(EditJob).filter(EditJob.created_at < old).delete()
        db.query(Session).filter(Session.created_at < old).delete()
        db.query(PendingDelivery).filter(PendingDelivery.created_at < old).delete()
        db.commit()
    finally:
        db.close()
