"""Turns the user's free-text WhatsApp replies into choices, and holds the message texts."""

FORMAT_MENU = {"1": "excel", "2": "word", "3": "pdf", "4": "csv", "5": "txt"}
FORMAT_NAMES = {"excel", "word", "pdf", "csv", "txt"}
FORMAT_ALIASES = {"xlsx": "excel", "xls": "excel", "docx": "word", "doc": "word", "text": "txt"}
FORMAT_LABEL = {"excel": "Excel", "word": "Word", "pdf": "PDF", "csv": "CSV", "txt": "TXT"}

EDIT_QUESTION = (
    "Got your photo! ✅\n\n"
    "Do you want to review and edit the text before you get your file?\n\n"
    "1. ✏️ Yes, let me edit\n"
    "2. \U0001f4c4 No, just send the file\n\n"
    "Reply 1 or 2."
)

MENU_TEXT = (
    "Which format do you want?\n\n"
    "1. Excel (.xlsx)\n"
    "2. Word (.docx)\n"
    "3. PDF\n"
    "4. CSV\n"
    "5. TXT\n\n"
    "Reply with a number (1-5) or the format name."
)

_YES = {"1", "yes", "y", "yeah", "yep", "ok", "okay", "edit", "haan", "ha", "han"}
_NO = {"2", "no", "n", "nope", "direct", "skip", "nahi", "nahin", "na"}


def _clean(text):
    return (text or "").strip().lower().strip(".!?, ")


def parse_format_reply(text):
    """Return 'excel' / 'word' / 'pdf' / 'csv' / 'txt', or None if not understood."""
    text = _clean(text)
    if text in FORMAT_MENU:
        return FORMAT_MENU[text]
    text = FORMAT_ALIASES.get(text, text)
    return text if text in FORMAT_NAMES else None


def parse_edit_reply(text):
    """Return 'edit', 'direct', or None if not understood."""
    text = _clean(text)
    if text in _YES:
        return "edit"
    if text in _NO:
        return "direct"
    return None


def parse_format_name(text):
    """Like parse_format_reply, but ignores 1-5 (those mean 'yes/no' on the edit question)."""
    return None if _clean(text) in FORMAT_MENU else parse_format_reply(text)
