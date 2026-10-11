"""Shared data structures for the OCR module."""
import time
from dataclasses import dataclass, field
from statistics import median


@dataclass
class Word:
    text: str
    bbox: tuple   # (x1, y1, x2, y2) in pixels
    conf: float   # confidence from 0.0 to 1.0


@dataclass
class OCRResult:
    engine: str
    words: list = field(default_factory=list)
    text: str = ""
    avg_conf: float = 0.0
    seconds: float = 0.0


def words_to_text(words):
    """Rebuild readable text: group words into lines by height, then sort left -> right.
    Both engines use this, so the comparison between them is fair."""
    if not words:
        return ""
    line_tol = 0.6 * median(w.bbox[3] - w.bbox[1] for w in words)
    lines = []  # each entry is a list of words on the same line
    for w in sorted(words, key=lambda w: (w.bbox[1] + w.bbox[3]) / 2):
        cy = (w.bbox[1] + w.bbox[3]) / 2
        if lines:
            avg_cy = sum((x.bbox[1] + x.bbox[3]) / 2 for x in lines[-1]) / len(lines[-1])
            if abs(cy - avg_cy) <= line_tol:
                lines[-1].append(w)
                continue
        lines.append([w])
    return "\n".join(" ".join(w.text for w in sorted(ln, key=lambda w: w.bbox[0])) for ln in lines)


def make_result(engine, words, start_time):
    """Bundle words + text + average confidence + timing into one OCRResult."""
    avg = sum(w.conf for w in words) / len(words) if words else 0.0
    return OCRResult(engine, words, words_to_text(words), avg, time.time() - start_time)
