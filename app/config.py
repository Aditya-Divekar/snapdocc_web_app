"""
Paths and settings shared across the app.

SNAPDOCC_DATA_DIR lets the tests use a throw-away folder, so running
`pytest` never touches your real database or files in data/.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()   # read .env (does not override variables that are already set)

DATA_DIR = Path(os.getenv("SNAPDOCC_DATA_DIR") or "data")
UPLOAD_DIR = DATA_DIR / "uploads"       # photos received from WhatsApp
OUTPUT_DIR = DATA_DIR / "output"        # generated files, served at /files/<random>/<name>
DOWNLOAD_DIR = DATA_DIR / "downloads"   # temp files for the "download instead" fallback

for _folder in (UPLOAD_DIR, OUTPUT_DIR, DOWNLOAD_DIR):
    _folder.mkdir(parents=True, exist_ok=True)


def public_base_url():
    """Your public https address (ngrok / Render), without a trailing slash.
    Read at call time so a changed .env works after a restart."""
    return (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
