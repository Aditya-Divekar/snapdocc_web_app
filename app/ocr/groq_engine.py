"""
Vision-LLM "OCR" using Qwen on Groq.

Unlike Tesseract/EasyOCR (which match character shapes), a vision language
model reads the way a person does - it uses context to understand messy
handwriting. It also returns the table structure directly, so no bounding-box
grouping is needed. Costs one API call per photo (Groq has a free tier).
"""

import base64

import cv2

from app.ocr.preprocess import load_image, resize_max
from app.utils.grid import normalize_grid
from app.utils import groq_client
from app.utils.groq_client import groq_chat, extract_json

PROMPT = """You are an expert OCR engine for photos taken on a phone. The photo may be a handwritten note, a shopping list, a printed receipt or a table. Read every line carefully (including messy or cursive handwriting) and return ONLY one JSON object:
{"type": "list" or "table", "headers": ["..."], "rows": [["..."], ["..."]], "uncertain": [[0, 1]]}

Rules:
- Copy the text exactly as written. Fix only obvious spelling mistakes in plain words.
- Never change numbers, prices, codes, units or brand names. Keep decimals exactly (4.65 stays 4.65).
- One row per line of the document, top to bottom. Every row must have the same number of cells; use "" for an empty cell.
- Use the document's own column headings if it has them (e.g. Items | Qty). Otherwise invent short ones (e.g. Qty, Item).
- Put each value under its own column: quantities in the quantity column, prices in the price column, never merged into the item name.
- Totals or footer lines (e.g. "Items: 3  Qty: 3  Total 166.65") are their own rows.
- Handwriting: letters of one word may be split by a gap or touched by a letter from the line above (e.g. "Boo k" is "Book", a long "g" from the line above is not part of the next word). Pick the most likely real word from context.
- Ignore pen marks, circles, underlines, ruled lines and faint text bleeding through from the other side of the page.
- A crossed-out value is still read as written.
- "uncertain" lists the [row, column] positions (0-based, counted in "rows") of cells you are NOT sure you read correctly. Use [] if you are sure of everything.
- If you truly cannot read anything, return {"type": "list", "headers": [], "rows": [], "uncertain": []}."""


def read_with_groq(image_path):
    """Return {'doc_type', 'headers', 'rows'} or None if Groq is unavailable/failed."""
    img = resize_max(load_image(image_path), max_side=1600)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        return None
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()

    reply = groq_chat([{
        "role": "user",
        "content": [
            {"type": "text", "text": PROMPT},
            {"type": "image_url", "image_url": {"url": data_url}},
        ],
    }])
    data = extract_json(reply)
    if not data or not isinstance(data.get("rows"), list):
        if reply is not None:
            groq_client.LAST_ERROR = "Groq replied, but not in the expected JSON format"
        return None

    # Cells the model was unsure about get a low confidence (0.5) so they are
    # highlighted for a human to double-check; everything else counts as 1.0.
    confs = [[1.0] * len(r) if isinstance(r, (list, tuple)) else [] for r in data["rows"]]
    for pos in data.get("uncertain") or []:
        try:
            confs[int(pos[0])][int(pos[1])] = 0.5
        except (TypeError, ValueError, IndexError, KeyError):
            pass   # model gave a bad position - ignore it

    grid = normalize_grid(data.get("headers"), data["rows"], confs)
    doc_type = data.get("type") if data.get("type") in ("list", "table") else "table"
    return {"doc_type": doc_type, **grid}
