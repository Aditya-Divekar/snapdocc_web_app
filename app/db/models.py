"""
SQLAlchemy models.

Session      - one row per WhatsApp conversation-in-progress. `state` says what
               we are waiting for: awaiting_edit_choice -> awaiting_format ->
               processing.
RequestLog   - one row per completed request, used for Phase 5 logging
               and the CER/WER-style stats dashboard later.
EditJob      - the extracted table waiting on the web edit page. The random
               token in the link is what keeps each job private.
"""

from datetime import datetime, timedelta
from sqlalchemy import create_engine, inspect, text, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATA_DIR

Base = declarative_base()

SESSION_TIMEOUT_MINUTES = 10   # a session expires if the user goes quiet this long


class Session(Base):
    __tablename__ = "sessions"

    id          = Column(Integer, primary_key=True)
    phone       = Column(String, unique=True, index=True)   # WhatsApp "from" number
    image_path  = Column(String)                             # saved photo, waiting on format choice
    state       = Column(String, default="awaiting_edit_choice")  # simple state machine
    created_at  = Column(DateTime, default=datetime.utcnow)

    def is_expired(self):
        return datetime.utcnow() - self.created_at > timedelta(minutes=SESSION_TIMEOUT_MINUTES)


class RequestLog(Base):
    __tablename__ = "request_logs"

    id              = Column(Integer, primary_key=True)
    timestamp       = Column(DateTime, default=datetime.utcnow)
    phone           = Column(String)
    doc_type        = Column(String)     # "list" or "table"
    fmt             = Column(String)     # "xlsx", "docx", ...
    ocr_engine      = Column(String)
    avg_confidence  = Column(Float)
    processing_secs = Column(Float)
    status          = Column(String)     # "success" or an error reason


EDIT_LINK_HOURS = 24   # edit links stop working after this long


class EditJob(Base):
    __tablename__ = "edit_jobs"

    token      = Column(String, primary_key=True)   # random, unguessable
    phone      = Column(String)                     # who to send the finished file to
    bot_number = Column(String)                     # the number the user chatted with (our "from")
    fmt        = Column(String)                     # format pre-selected on the page
    engine     = Column(String)                     # which reader produced the text
    image_path = Column(String)                     # the photo, shown on the page for comparison
    grid_json  = Column(Text)                       # {"headers": [...], "rows": [[...]], "confs": [[...]]}
    created_at = Column(DateTime, default=datetime.utcnow)

    def is_expired(self):
        return datetime.utcnow() - self.created_at > timedelta(hours=EDIT_LINK_HOURS)


# --- engine / session factory, created once and reused everywhere ---
engine = create_engine(f"sqlite:///{(DATA_DIR / 'snapdocc.db').as_posix()}",
                       connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)


class PendingDelivery(Base):
    """A message we could not push through Twilio's REST API. It is handed over as the
    reply to the user's next WhatsApp message instead (that kind of reply always works)."""
    __tablename__ = "pending_deliveries"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    phone      = Column(String, index=True)
    body       = Column(Text)
    media_url  = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def _add_missing_columns(table, columns):
    """create_all() never adds columns to a table that already exists, so a
    database created by an older version would break. This adds them."""
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return
    have = {c["name"] for c in inspector.get_columns(table)}
    with engine.begin() as conn:
        for name, sql_type in columns.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {sql_type}"))


def init_db():
    Base.metadata.create_all(engine)
    _add_missing_columns("edit_jobs", {"bot_number": "VARCHAR", "engine": "VARCHAR",
                                       "image_path": "VARCHAR", "fmt": "VARCHAR",
                                       "grid_json": "TEXT", "created_at": "DATETIME"})
    with engine.begin() as conn:   # rows from an old version have no date: treat them as new
        conn.execute(text("UPDATE edit_jobs SET created_at = :now WHERE created_at IS NULL"),
                     {"now": datetime.utcnow()})
