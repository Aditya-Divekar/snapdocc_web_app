"""
Test setup - runs before any test module is imported.

* All data (database, photos, generated files) goes to a throw-away temp
  folder, so `pytest` never touches your real data/ folder or request logs.
* The real Groq / Twilio credentials from your .env are blanked, so tests
  can never call the real APIs or send real WhatsApp messages.
"""

import atexit
import os
import shutil
import tempfile

_tmp = tempfile.mkdtemp(prefix="snapdocc_test_")
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)

os.environ["SNAPDOCC_DATA_DIR"] = _tmp
for _name in ("GROQ_API_KEY", "GROQ_MODEL", "PUBLIC_BASE_URL",
              "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_NUMBER"):
    os.environ[_name] = ""    # set (not removed) so load_dotenv() won't fill them from .env
