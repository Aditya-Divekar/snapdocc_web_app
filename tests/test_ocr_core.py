from app.ocr.base import Word, words_to_text
from app.utils.metrics import cer, wer, edit_distance


def test_edit_distance():
    assert edit_distance("kitten", "sitting") == 3


def test_cer_wer():
    assert cer("abc", "abc") == 0.0
    assert abs(cer("abc", "abd") - 1 / 3) < 1e-9
    assert wer("2 kg rice", "2 kg rise") == 1 / 3
    assert cer("Hello  World", "hello world") == 0.0   # case/spacing ignored


def test_words_to_text_orders_lines():
    words = [Word("kg", (60, 12, 90, 40), .9), Word("2", (10, 10, 30, 40), .9),
             Word("Rice", (100, 11, 160, 41), .9), Word("Milk", (10, 80, 70, 110), .9)]
    assert words_to_text(words) == "2 kg Rice\nMilk"
