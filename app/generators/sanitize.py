"""
Guard against spreadsheet "formula injection": if a cell's text starts with
=, +, -, or @, Excel (and some other spreadsheet tools) may try to interpret
it as a formula instead of showing the actual text - which is what caused
"#NAME?" errors when OCR noise happened to start a cell with "=".

We defuse this by prefixing a harmless space, which keeps the text visible
and correct while stopping it from being read as a formula.
"""

_FORMULA_TRIGGERS = ("=", "+", "-", "@")


def sanitize_cell(value):
    """Return value unchanged, unless it looks like it could be mistaken
    for a spreadsheet formula - in which case prefix a space."""
    if isinstance(value, str) and value.startswith(_FORMULA_TRIGGERS):
        return " " + value
    return value
