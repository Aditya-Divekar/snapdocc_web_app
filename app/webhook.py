"""
The WhatsApp conversation logic, called by main.py for every incoming message.

Flow:
  photo  ->  "Do you want to edit it first?"
     1 / yes  ->  read the photo (in the background)  ->  send a link to the
                  web edit page; the page sends the finished file back here
     2 / no   ->  "Which format?"  ->  read the photo (background)  ->
                  send the file straight to this chat

We never ask for a photo to be re-sent: every photo is read on the first go.

Reading a photo can take a few seconds, but Twilio only waits ~15 seconds
for a webhook reply. So the webhook answers immediately ("reading your
photo...") and the real result is sent afterwards with the Twilio REST API
(see messaging.py). `background` and `send` are parameters so the tests can
run everything instantly without a network.
"""

import json
import threading
import time
import uuid
from pathlib import Path

import requests
from twilio.twiml.messaging_response import MessagingResponse

from app.config import UPLOAD_DIR, OUTPUT_DIR
from app.db.models import SessionLocal, RequestLog, EditJob
from app.generators.convert import convert
from app.housekeeping import run_housekeeping
from app.messaging import deliver, pop_pending
from app.ocr.extract import extract_grid
from app.ocr.preprocess import load_image
from app.session import get_session, start_session, set_state, clear_session
from app.utils.formats import (EDIT_QUESTION, MENU_TEXT, FORMAT_LABEL, parse_edit_reply,
                               parse_format_reply, parse_format_name)
from app.utils.grid import grid_to_structured

MAX_IMAGE_BYTES = 5 * 1024 * 1024   # 5 MB limit (requirement #7)


def _reply(text):
    """Build a TwiML response containing one text message."""
    r = MessagingResponse()
    r.message(text)
    return str(r)


def _reply_with_media(text, media_url=None):
    r = MessagingResponse()
    m = r.message(text)
    if media_url:
        m.media(media_url)
    return str(r)


def _download_media(media_url, phone, auth):
    """Download the photo Twilio is hosting and save it locally.
    Twilio media URLs require your Twilio credentials (HTTP basic auth) to fetch."""
    resp = requests.get(media_url, auth=auth, timeout=20)
    resp.raise_for_status()
    if len(resp.content) > MAX_IMAGE_BYTES:
        raise ValueError("file_too_large")
    path = UPLOAD_DIR / f"{uuid.uuid4().hex}.jpg"
    path.write_bytes(resp.content)
    return path


def _log(phone, doc_type, fmt, engine, conf, secs, status):
    db = SessionLocal()
    try:
        db.add(RequestLog(phone=phone, doc_type=doc_type, fmt=fmt, ocr_engine=engine,
                          avg_confidence=conf, processing_secs=secs, status=status))
        db.commit()
    finally:
        db.close()


def _save_edit_job(phone, bot_number, image_path, result):
    """Store the extracted table so the web edit page can load it.
    The random token in the link is what keeps it private."""
    token = uuid.uuid4().hex
    grid = {"headers": result["headers"], "rows": result["rows"], "confs": result.get("confs")}
    db = SessionLocal()
    try:
        db.add(EditJob(token=token, phone=phone, bot_number=bot_number, fmt="excel",
                       engine=result["engine"], image_path=str(image_path),
                       grid_json=json.dumps(grid)))
        db.commit()
    finally:
        db.close()
    return token


def _run_now(func, *args, **kwargs):
    """Default `background`: just run it. (main.py passes FastAPI's background tasks.)"""
    func(*args, **kwargs)


SYNC_WAIT_SECS = 12     # Twilio gives up on a webhook after ~15 s


class _Box:
    """Catches the job's result so it can be returned as the webhook reply (one smooth flow).
    If the job takes too long, it is abandoned here and the result goes out the normal way."""

    def __init__(self, late_send):
        self.late_send, self.item = late_send, None
        self.done, self.lock, self.abandoned = threading.Event(), threading.Lock(), False

    def send(self, to, from_, body, media_url=None):
        with self.lock:
            if not self.abandoned:
                self.item = (body, media_url)
                self.done.set()
                return
        self.late_send(to, from_, body, media_url)


def _launch(background, send, sync, immediate_text, args):
    """Start the slow job. Normally the answer is sent later (background). With sync=True
    we wait a few seconds so the answer can be the reply itself - no extra message needed."""
    if not sync:
        background(_run_job, *args, send)
        return _reply(immediate_text)
    box = _Box(send)
    threading.Thread(target=_run_job, args=(*args, box.send), daemon=True).start()
    box.done.wait(SYNC_WAIT_SECS)
    with box.lock:
        box.abandoned = not box.done.is_set()
    if box.item:
        return _reply_with_media(*box.item)
    return _reply(immediate_text)


def handle_message(phone, body, num_media, media_url, twilio_auth,
                   public_base_url="", bot_number="", background=None, send=None, sync=False):
    """
    phone           : WhatsApp sender, e.g. "whatsapp:+91xxxxxxxxxx"
    body            : text of the message (may be empty)
    num_media       : how many media items are attached
    media_url       : URL of the first media item, if any
    twilio_auth     : (account_sid, auth_token), needed to download media
    public_base_url : your public https URL (ngrok / Render), used for links
    bot_number      : the number the user chatted with (Twilio's `To`); replies go out from it
    background      : function(func, *args) that runs slow work after we have replied
    send            : function(to, from_, body, media_url=None) that sends a WhatsApp message
    Returns         : TwiML XML string with the immediate reply
    """
    background = background or _run_now
    send = send or deliver
    session = get_session(phone)

    # --- A photo arrived: save it, ask whether to edit. No blur gate, no re-send requests. ---
    if num_media and num_media > 0:
        if not media_url:
            return _reply("Sorry, I couldn't read that image. Please try sending it again.")
        try:
            path = _download_media(media_url, phone, twilio_auth)
        except ValueError:
            return _reply("That image is too large (max 5 MB). Please send a smaller photo.")
        except Exception:
            return _reply("Sorry, I couldn't download that image. Please try again.")
        try:
            load_image(path)    # make sure it really is an image
        except Exception:
            path.unlink(missing_ok=True)
            return _reply("Sorry, that doesn't look like a photo. Please send a picture of your document.")

        start_session(phone, str(path), "awaiting_edit_choice")
        return _reply(EDIT_QUESTION)

    # --- Something is waiting for this user (Twilio refused to push it): hand it over now ---
    pending = pop_pending(phone)
    if pending:
        return _reply_with_media(*pending)

    # --- Text, but we are not waiting for anything ---
    if session is None:
        return _reply("Hi! Send me a photo of a shopping list, receipt, table or handwritten "
                      "note and I'll turn it into a file for you.")

    # --- Question 1: edit first? ---
    if session.state == "awaiting_edit_choice":
        fmt = parse_format_name(body)          # typed a format name -> skip the question
        choice = "direct" if fmt else parse_edit_reply(body)

        if choice == "edit":
            set_state(phone, "processing")
            return _launch(background, send, sync,
                           "\U0001f44d Reading your photo... I'll send you the edit link in a few seconds.\n(If nothing arrives in about 20 seconds, reply \"ok\".)",
                           (phone, bot_number, session.image_path, "edit", "excel", public_base_url))
        if choice == "direct" and fmt:
            set_state(phone, "processing")
            return _launch(background, send, sync,
                           f"\U0001f44d Reading your photo... your {FORMAT_LABEL[fmt]} file will arrive in a few seconds.\n(If nothing arrives in about 20 seconds, reply \"ok\".)",
                           (phone, bot_number, session.image_path, "direct", fmt, public_base_url))
        if choice == "direct":
            set_state(phone, "awaiting_format")
            return _reply(MENU_TEXT)
        return _reply("I didn't understand that.\n\n" + EDIT_QUESTION)

    # --- Question 2 (only if they chose not to edit): which format? ---
    if session.state == "awaiting_format":
        fmt = parse_format_reply(body)
        if fmt is None:
            return _reply("I didn't understand that.\n\n" + MENU_TEXT)
        set_state(phone, "processing")
        return _launch(background, send, sync,
                       f"\U0001f44d Reading your photo... your {FORMAT_LABEL[fmt]} file will arrive in a few seconds.\n(If nothing arrives in about 20 seconds, reply \"ok\".)",
                       (phone, bot_number, session.image_path, "direct", fmt, public_base_url))

    if session.state == "processing":
        return _reply("⏳ Still reading your photo, one moment...")

    # Unknown state (e.g. left over from an older version): start the questions again.
    set_state(phone, "awaiting_edit_choice")
    return _reply(EDIT_QUESTION)


def _safe_send(send, to, from_, body, media_url=None):
    """Send, but never let a Twilio problem crash the background job."""
    try:
        send(to, from_, body, media_url)
    except Exception as e:
        print(f"[webhook] could not send WhatsApp message: {e}")


def _run_job(phone, bot_number, image_path, mode, fmt, public_base_url, send):
    """The slow part, run in the background: read the photo, then send either
    the edit link (mode='edit') or the finished file (mode='direct')."""
    start = time.time()
    engine, doc_type = "unknown", "unknown"
    try:
        result = extract_grid(image_path)    # Groq (Qwen) if it works, else Tesseract
        engine, doc_type = result["engine"], result["doc_type"]
        note = f"\n\n⚠️ {result['note']}" if result.get("note") else ""

        if not result["rows"]:
            _log(phone, doc_type, fmt, engine, 0.0, time.time() - start, "no_text_found")
            send(phone, bot_number, "I couldn't find any readable text in that photo." + note)
            return

        if not public_base_url:
            _log(phone, doc_type, fmt, engine, result["avg_conf"], time.time() - start,
                 "error:PUBLIC_BASE_URL not set")
            send(phone, bot_number, "Server setup problem: PUBLIC_BASE_URL is not set in .env, "
                                    "so I can't send links or files.")
            return

        if mode == "edit":
            token = _save_edit_job(phone, bot_number, image_path, result)
            send(phone, bot_number,
                 f"✅ I've read your {doc_type}.\n\n"
                 f"✏️ Review and fix anything here:\n{public_base_url}/edit/{token}\n\n"
                 f"Tap \"Send to my WhatsApp\" on that page and your file comes back to this chat. "
                 f"(Link valid for 24 hours.)" + note)
        else:
            out_dir = OUTPUT_DIR / uuid.uuid4().hex     # random folder = unguessable link
            out_path = convert(grid_to_structured(result), fmt, out_dir, stem="SnapDocc")
            send(phone, bot_number, f"✅ Here's your {FORMAT_LABEL[fmt]} file." + note,
                 f"{public_base_url}/files/{out_dir.name}/{out_path.name}")

        _log(phone, doc_type, fmt, engine, result["avg_conf"], time.time() - start, "success")

    except Exception as e:
        _log(phone, doc_type, fmt, engine, 0.0, time.time() - start, f"error:{e}")
        _safe_send(send, phone, bot_number,
                   "Something went wrong while processing your photo. Please send it again.")
    finally:
        clear_session(phone)
        if mode == "direct":       # nothing needs the photo any more (privacy)
            try:
                Path(image_path).unlink(missing_ok=True)
            except OSError:
                pass
        run_housekeeping()
