"""
FastAPI app: the /webhook route that Twilio calls for every WhatsApp message,
the web edit page (app/web.py), and the public /files folder for finished files.

Run with:  uvicorn app.main:app --reload
"""

import mimetypes
import os

from fastapi import BackgroundTasks, FastAPI, Form
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.config import OUTPUT_DIR, public_base_url
from app.db.models import init_db
from app.housekeeping import run_housekeeping
from app.web import router as web_router
from app.webhook import handle_message

# The slim Docker image has no system MIME table, so .docx/.xlsx would be served as
# "application/octet-stream" and WhatsApp rejects the file (Twilio error 63019).
# Register the types ourselves so the right Content-Type is always sent.
for _ext, _type in {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".txt": "text/plain",
}.items():
    mimetypes.add_type(_type, _ext)

app = FastAPI(title="SnapDocc")
app.include_router(web_router)   # /edit/<token> pages

# Finished files are served at /files/<random-folder>/<name> so Twilio can
# fetch and attach them. Folder names are random, so links can't be guessed.
app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")


@app.on_event("startup")
def on_startup():
    init_db()            # creates the database and tables if they don't exist yet
    run_housekeeping()   # delete old photos / files / expired links


@app.api_route("/", methods=["GET", "HEAD"])   # HEAD too: uptime monitors use it
def health_check():
    """Simple page so you can confirm the server is running by visiting it in a browser."""
    return {"status": "SnapDocc is running"}


@app.post("/webhook")
def whatsapp_webhook(
    background_tasks: BackgroundTasks,
    Body: str = Form(""),
    From: str = Form(...),
    To: str = Form(""),
    NumMedia: str = Form("0"),
    MediaUrl0: str = Form(None),
):
    """
    Twilio POSTs form data here (not JSON) for every incoming WhatsApp message.
    Field names (Body, From, To, NumMedia, MediaUrl0) are fixed by Twilio - see
    https://www.twilio.com/docs/messaging/guides/webhook-request
    `To` is the Twilio number the user chatted with; we reply from that same number.
    """
    twiml = handle_message(
        phone=From,
        body=Body,
        num_media=int(NumMedia or 0),
        media_url=MediaUrl0,
        twilio_auth=(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN")),
        public_base_url=public_base_url(),
        bot_number=To,
        background=background_tasks.add_task,
        sync=True,   # wait a few seconds so the file/link comes back as the reply itself
    )
    return Response(content=twiml, media_type="text/xml")
