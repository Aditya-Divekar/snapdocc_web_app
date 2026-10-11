"""Error metrics for OCR: CER (character error rate) and WER (word error rate).
Both = edit distance / length of the reference. 0.0 is perfect; lower is better."""


def edit_distance(a, b):
    """Levenshtein distance between two sequences (works for strings and word lists)."""
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1,            # deletion
                           cur[j - 1] + 1,         # insertion
                           prev[j - 1] + (x != y)))  # substitution
        prev = cur
    return prev[-1]


def normalize(text):
    """Ignore case and extra spaces/newlines so we only measure real reading mistakes."""
    return " ".join(text.lower().split())


def cer(reference, hypothesis):
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def wer(reference, hypothesis):
    ref, hyp = normalize(reference).split(), normalize(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)
