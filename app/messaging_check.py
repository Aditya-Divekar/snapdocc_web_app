"""Test Twilio sending on its own:  python -m app.messaging_check whatsapp:+91XXXXXXXXXX
Tries a plain text message from every sender number it can think of and prints
the exact result, so we can see which sender Twilio accepts."""
import os
import sys

from twilio.rest import Client

import app.config  # loads .env  # noqa: F401


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m app.messaging_check whatsapp:+91XXXXXXXXXX")
        return
    to = sys.argv[1]
    client = Client(os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"))
    senders = []
    for s in (os.getenv("TWILIO_WHATSAPP_NUMBER"), "whatsapp:+17372508034", "whatsapp:+14155238886"):
        if s and s not in senders:
            senders.append(s)
    for s in senders:
        try:
            m = client.messages.create(from_=s, to=to, body="SnapDocc test message")
            print(f"OK    from {s}  (sid {m.sid})")
        except Exception as e:
            print(f"FAIL  from {s}  ->  {str(e).splitlines()[-1] if str(e) else e}")
            print("      " + " ".join(str(e).split())[:300])


main()
