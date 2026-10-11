from app.utils.spellcheck import correct_word, correct_text


def test_corrects_obvious_misspelling():
    assert correct_word("Ricee") == "Rice"


def test_leaves_units_and_numbers_alone():
    assert correct_word("kg") == "kg"
    assert correct_word("500") == "500"
    assert correct_word("2.5") == "2.5"


def test_leaves_real_words_alone():
    assert correct_word("Milk") == "Milk"


def test_correct_text_sentence():
    assert correct_text("2 kg Ricee") == "2 kg Rice"


def test_leaves_all_caps_words_alone():
    """ALL-CAPS tokens are codes/acronyms/brand names printed in caps on
    receipts (HSN, NESTLE, BALAJI) - a dictionary correction would silently
    replace a real term with a wrong one (e.g. HSN -> HEN)."""
    assert correct_word("HSN") == "HSN"
    assert correct_word("NESTLE") == "NESTLE"


def test_leaves_alphanumeric_codes_alone():
    """Tokens mixing letters and digits (product codes, weights) aren't
    misspellings and must be left exactly as OCR read them."""
    assert correct_word("SE-400g") == "SE-400g"
    assert correct_word("MUNCH-8.74") == "MUNCH-8.74"


def test_all_caps_words_are_never_corrected():
    """ALL-CAPS tokens are brand names / codes / abbreviations on real receipts
    (NESTLE, BALAJI, CGST, HSN) - a dictionary must never 'fix' these."""
    assert correct_word("BALAJI") == "BALAJI"
    assert correct_word("NESTLE") == "NESTLE"
    assert correct_word("CGST") == "CGST"
    assert correct_word("HSN") == "HSN"
