"""
One-command check that Groq works with your key.

    python -m app.ocr.groq_check path\\to\\photo.jpg

Prints exactly what Groq answered (or the exact error), so you never have to
guess why the bot fell back to basic OCR.
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from app.ocr.groq_engine import read_with_groq          # noqa: E402
from app.utils import groq_client                        # noqa: E402


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m app.ocr.groq_check <photo.jpg>")
        return
    if not groq_client.groq_available():
        print("FAIL: GROQ_API_KEY not found. Add it to .env (no quotes, no spaces) and run again.")
        return
    print(f"Model: {groq_client._models_to_try()[0]}")
    result = read_with_groq(sys.argv[1])
    if result is None:
        print(f"FAIL: {groq_client.LAST_ERROR}")
        return
    print(f"OK: Groq read a {result['doc_type']} with {len(result['rows'])} rows\n")
    print(" | ".join(result["headers"]))
    print("-" * 40)
    for row in result["rows"]:
        print(" | ".join(row))


if __name__ == "__main__":
    main()
