"""
Spelling + grammar auto-correct for the edit page.

1. If GROQ_API_KEY is set: ask the LLM to fix spelling, grammar and
   capitalisation (keeps numbers, units, codes and brand names).
2. Otherwise (or if that fails): free local spell-checker + capitalise.
"""

import json

from app.utils.grid import normalize_grid
from app.utils.groq_client import groq_available, groq_chat, extract_json
from app.utils.spellcheck import correct_text

PROMPT = """Fix spelling, grammar and capitalisation in this table. Return ONLY JSON in exactly the same shape and size: {"headers": [...], "rows": [[...]]}.
Rules: never change numbers, prices, codes, units or brand names. Do not add, remove or reorder rows or cells. Keep empty cells empty.

"""


def _local(grid):
    def fix(cell):
        cell = correct_text(cell)
        return cell[:1].upper() + cell[1:] if cell[:1].isalpha() else cell
    return {"headers": [fix(h) for h in grid["headers"]],
            "rows": [[fix(c) for c in row] for row in grid["rows"]]}


def autocorrect_grid(headers, rows):
    """Returns (grid, method) where method is 'groq' or 'local'."""
    grid = normalize_grid(headers, rows)
    if groq_available():
        reply = groq_chat([{"role": "user", "content": PROMPT + json.dumps(grid)}])
        data = extract_json(reply)
        if data and isinstance(data.get("rows"), list):
            fixed = normalize_grid(data.get("headers"), data["rows"])
            # Only trust it if the shape is unchanged
            if (len(fixed["rows"]) == len(grid["rows"])
                    and len(fixed["headers"]) == len(grid["headers"])):
                return fixed, "groq"
    return _local(grid), "local"
