from app.generators.sanitize import sanitize_cell


def test_leaves_normal_text_alone():
    assert sanitize_cell("Rice") == "Rice"
    assert sanitize_cell("") == ""


def test_defuses_formula_looking_values():
    assert sanitize_cell("=Qty:") == " =Qty:"
    assert sanitize_cell("+91234") == " +91234"
    assert sanitize_cell("-5") == " -5"
    assert sanitize_cell("@user") == " @user"


def test_non_string_values_untouched():
    assert sanitize_cell(5) == 5
    assert sanitize_cell(None) is None
