"""
Parse list rows into structured records: {qty, unit, item}.

Strategy:
  Most shopping lists / receipts look like:
      2 kg   Rice
      1 L    Milk
      500 g  Sugar
      Soap          <- no qty/unit
      3      Eggs   <- qty, no unit

  We scan each row left-to-right:
  - First token that is a number (int or float)        -> qty
  - Next token that matches a known unit abbreviation  -> unit
  - Everything else                                    -> item
"""

import re

# Common unit abbreviations (expand if you like)
UNITS = {
    "kg", "g", "mg", "l", "ml", "litre", "litres", "liter", "liters",
    "lb", "lbs", "oz", "pcs", "pc", "pack", "pkt", "dozen", "doz",
    "nos", "no", "unit", "units", "box", "bag", "bottle", "btl",
}

_NUM = re.compile(r"^\d+([.,]\d+)?$")


def _is_number(tok):
    return bool(_NUM.match(tok.replace(",", ".")))


def parse_list(rows):
    """
    Return a list of dicts: [{qty, unit, item, conf}, ...]
    conf = minimum word confidence in the row.
    """
    records = []
    for row in rows:
        tokens = [w.text for w in row]
        conf = min(w.conf for w in row) if row else 1.0
        qty = unit = ""
        remaining = list(tokens)

        # Try to grab qty from the first token
        if remaining and _is_number(remaining[0]):
            qty = remaining.pop(0)

        # Try to grab unit from what's now the first token
        if remaining and remaining[0].lower().rstrip(".") in UNITS:
            unit = remaining.pop(0)

        item = " ".join(remaining)
        records.append({"qty": qty, "unit": unit, "item": item, "conf": conf})

    return records
