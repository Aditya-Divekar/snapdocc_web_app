"""Image preprocessing with OpenCV: resize -> grayscale -> denoise -> deskew -> threshold."""
import cv2
import numpy as np


def load_image(path):
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Could not read image: {path}")
    return img


def resize_max(img, max_side=1600):
    """Phone photos are huge (4000px+). Shrinking keeps OCR fast without hurting accuracy."""
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale >= 1:
        return img
    return cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)


def blur_score(img):
    """Variance of the Laplacian: low value = blurry. (Used for error handling in Phase 4.)"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    return cv2.Laplacian(gray, cv2.CV_64F).var()


def is_blurry(img, threshold=100.0):
    return blur_score(img) < threshold


def _rotate(img, angle, fill):
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=fill)


def deskew(gray, max_angle=10.0, step=0.5):
    """Try small rotations; the best one is where text rows line up most sharply
    (largest variance of the row-wise ink sums). Simple and sign-proof."""
    scale = min(1.0, 600 / max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale)
    _, bw = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    best_angle, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step, step):
        score = np.var(_rotate(bw, angle, 0).sum(axis=1))
        if score > best_score:
            best_angle, best_score = angle, score
    if abs(best_angle) < 0.3:   # already straight enough
        return gray
    return _rotate(gray, best_angle, 255)


def preprocess(img, threshold=False):
    """Full pipeline. Returns a grayscale (or black & white) image ready for OCR.

    Tested on real receipts: hard black/white thresholding and strong denoising
    erase thin printed digits (e.g. the "1" in a Qty column), so by default we
    only upscale small photos and boost contrast (CLAHE). Set threshold=True
    for very faint/uneven-light scans."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Tesseract reads best when text is fairly large, so enlarge small photos
    if max(gray.shape) < 1600:
        gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    gray = deskew(gray)
    if threshold:  # adaptive threshold copes with uneven lighting
        gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY, 31, 15)
    return gray
