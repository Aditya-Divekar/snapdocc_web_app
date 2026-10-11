"""
Light spelling correction for OCR output.

OCR often mis-reads letters (e.g. "R1ce" instead of "Rice"). This module
runs each *word* item through a dictionary-based spell checker and swaps
in the most likely correct word - but only when it's fairly confident,
so it doesn't "fix" names, brands, or numbers into nonsense.

We deliberately do NOT touch:
  - numbers / quantities (e.g. "500", "2.5")
  - units (kg, ml, pcs, ...) - these are domain words, not dictionary words
  - very short tokens (1-2 letters) - too easy to "correct" wrongly
"""

from spellchecker import SpellChecker

_checker = SpellChecker()          # loads English dictionary once
_SKIP_UNITS = {
    "kg", "g", "mg", "l", "ml", "lb", "lbs", "oz", "pcs", "pc", "pack",
    "pkt", "dozen", "doz", "nos", "no", "unit", "units", "box", "bag",
    "bottle", "btl",
}


def _looks_numeric(token):
    return any(ch.isdigit() for ch in token)


def correct_word(token):
    """Correct a single word if the dictionary is confident; else leave it unchanged."""
    if not token or len(token) <= 2 or _looks_numeric(token):
        return token
    if any(ch.isdigit() for ch in token):
        # Mixed alphanumeric tokens (product codes, weights like "SE-400g")
        # aren't misspellings - leave them exactly as OCR read them.
        return token
    if token.lower() in _SKIP_UNITS:
        return token
    if token.isupper():
        # ALL-CAPS tokens are almost always codes, acronyms, or intentionally
        # capitalized brand/item names (receipts print items like "NESTLE",
        # "HSN" this way). A dictionary won't know these - "correcting" them
        # (e.g. HSN -> HEN) replaces a real term with a wrong one. Safer to
        # leave them exactly as OCR read them.
        return token

    # Keep original casing style (Title Case, lower) after correcting
    lower = token.lower()
    if lower in _checker:                # already a real word - leave it alone
        return token

    suggestion = _checker.correction(lower)
    if not suggestion or suggestion == lower:
        return token

    if token[0].isupper():
        return suggestion.capitalize()
    return suggestion


def correct_text(text):
    """Correct every word in a space-separated string, keep punctuation attached."""
    return " ".join(correct_word(w) for w in text.split())


def correct_structured(structured):
    """
    Apply spelling correction to a structured dict from app.structuring.pipeline,
    IN PLACE, and also return it. Works for both 'list' and 'table' types.
    """
    if structured["type"] == "list":
        for row in structured["data"]:
            row["item"] = correct_text(row["item"])
    else:  # table
        for row in structured["data"]:
            row["cells"] = [correct_text(c) for c in row["cells"]]
    return structured
