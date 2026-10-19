from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import numpy as np
from PIL import Image

from .. import config


@dataclass
class Word:
    text: str
    conf: float
    x0: int
    y0: int
    x1: int
    y1: int

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def h(self) -> float:
        return max(1, self.y1 - self.y0)

    @property
    def w(self) -> float:
        return max(1, self.x1 - self.x0)


@dataclass
class OcrResult:
    words: List[Word] = field(default_factory=list)
    engine: str = "tesseract"
    lang: str = config.OCR_LANG
    ok: bool = True
    error: str = ""


def _pil_to_gray(im: Image.Image) -> np.ndarray:
    return np.array(im.convert("L"))


def _upscale_if_small(im: Image.Image, target: int = 2600) -> tuple[Image.Image, float]:
    w, h = im.size
    if max(w, h) >= target:
        return im, 1.0
    r = min(3.0, target / float(max(w, h)))
    return im.resize((max(1, int(w * r)), max(1, int(h * r))), Image.LANCZOS), r


def _score_rotation(im: Image.Image) -> float:
    import cv2

    gray = _pil_to_gray(im)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    binimg = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 15
    )
    lines = cv2.HoughLinesP(
        binimg, 1, np.pi / 180, threshold=120, minLineLength=max(80, gray.shape[1] // 8), maxLineGap=12
    )
    if lines is None:
        return -1.0
    hor = 0.0
    vert = 0.0
    for x1, y1, x2, y2 in lines[:, 0]:
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dy < dx * 0.25:
            hor += dx
        elif dx < dy * 0.25:
            vert += dy
    return hor - vert * 0.85


def _detect_orientation(im: Image.Image) -> int:
    try:
        sm_side = 1400
        r = sm_side / float(max(im.size))
        small = im if r >= 1.0 else im.resize((max(1, int(im.size[0] * r)), max(1, int(im.size[1] * r))), Image.LANCZOS)
        scores = []
        for k in range(4):
            cand = small.rotate(-90 * k, expand=True) if k else small
            scores.append(_score_rotation(cand))
        best = int(np.argmax(scores))
        ordered = sorted(scores, reverse=True)
        # only trust a rotation when it clearly beats the upright orientation
        if best == 0:
            return 0
        if ordered[0] <= 1500 or ordered[0] < ordered[1] * 1.25:
            return 0
        return 90 * best
    except Exception:
        return 0


def detect_orientation(im: Image.Image) -> int:
    """Return rotation (0/90/180/270) that makes the page upright, or 0 when unsure."""
    return _detect_orientation(im)


def _ocr_score(im: Image.Image) -> float:
    """How much readable text an orientation candidate contains (upright >> sideways)."""
    try:
        sm = im
        if max(sm.size) > 1400:
            r = 1400.0 / max(sm.size)
            sm = sm.resize((max(1, int(sm.size[0] * r)), max(1, int(sm.size[1] * r))), Image.LANCZOS)
        words = _tesseract_words(sm)
        good = [w for w in words if w.conf >= 60]
        if not good:
            return 0.0
        return float(sum(min(w.conf, 99.0) for w in good)) + 12.0 * sum(
            1 for w in good if len(w.text) >= 2
        )
    except Exception:
        return 0.0


def _resolve_orientation(im: Image.Image) -> int:
    """Line-dominance first, then OCR to tell 90 from 270 (they look alike to Hough)."""
    try:
        sm_side = 1400
        r = sm_side / float(max(im.size))
        small = im if r >= 1.0 else im.resize((max(1, int(im.size[0] * r)), max(1, int(im.size[1] * r))), Image.LANCZOS)
        scores = []
        for k in range(4):
            cand = small.rotate(-90 * k, expand=True) if k else small
            scores.append(_score_rotation(cand))

        cross = max(scores[1], scores[3])
        straight = max(scores[0], scores[2])
        # sideways page needs a quarter turn; otherwise keep the frame as is
        if cross <= 1500 or cross < straight * 1.15:
            return 0
        # newspaper pages are portrait: never turn an upright frame sideways
        if im.size[1] >= im.size[0]:
            return 0

        cands = [k for k in (1, 3) if scores[k] > 0] or [1, 3]
        best_k = max(cands, key=lambda k: _ocr_score(small.rotate(-90 * k, expand=True)))
        return 90 * int(best_k)
    except Exception:
        return 0


def upright(im: Image.Image) -> tuple[Image.Image, int]:
    """Rotate the page upright. Portrait pages are never turned landscape."""
    try:
        angle = _resolve_orientation(im)
        if angle:
            return rotate_for_ocr(im, angle), int(angle)
    except Exception:
        pass
    return im, 0


def rotate_for_ocr(im: Image.Image, angle: int = 0) -> Image.Image:
    angle = int(angle) % 360
    if angle == 90:
        return im.transpose(Image.ROTATE_270)
    if angle == 180:
        return im.transpose(Image.ROTATE_180)
    if angle == 270:
        return im.transpose(Image.ROTATE_90)
    return im


def _rescale_words(words: List[Word], ratio: float) -> List[Word]:
    if abs(ratio - 1.0) < 1e-6 or not words:
        return words
    out: List[Word] = []
    for wd in words:
        out.append(
            Word(
                wd.text,
                wd.conf,
                int(round(wd.x0 / ratio)),
                int(round(wd.y0 / ratio)),
                int(round(wd.x1 / ratio)),
                int(round(wd.y1 / ratio)),
            )
        )
    return out


def rotate_words(words: List[Word], angle: int, size_before: tuple[int, int]) -> List[Word]:
    angle = int(angle) % 360
    w, h = size_before
    if angle == 0:
        return words
    out: List[Word] = []
    for wd in words:
        x0, y0, x1, y1 = wd.x0, wd.y0, wd.x1, wd.y1
        if angle == 90:
            nx0, ny0, nx1, ny1 = h - y1, x0, h - y0, x1
        elif angle == 180:
            nx0, ny0, nx1, ny1 = w - x1, h - y1, w - x0, h - y0
        else:
            nx0, ny0, nx1, ny1 = y0, w - x1, y1, w - x0
        out.append(Word(wd.text, wd.conf, int(nx0), int(ny0), int(nx1), int(ny1)))
    return out


def _tesseract_words(im: Image.Image) -> List[Word]:
    import cv2
    import pytesseract

    if Path(config.TESSERACT_CMD).exists():
        pytesseract.pytesseract.tesseract_cmd = config.TESSERACT_CMD

    arr = np.array(im)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    scale = 2.0 if max(gray.shape) < 1400 else 1.0
    if scale > 1.0:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

    langs = [config.OCR_LANG]
    if config.OCR_LANG != "eng" and Path(config.TESSDATA_DIR).exists():
        if (Path(config.TESSDATA_DIR) / "eng.traineddata").exists():
            langs.append("eng")
    psm = os.environ.get("OCR_PSM", "6")
    cfg = f"--psm {psm} --oem 1 -c tessedit_create_tsv=1"
    data = pytesseract.image_to_data(
        Image.fromarray(gray),
        lang="+".join(langs),
        config=cfg,
        output_type=pytesseract.Output.DICT,
    )

    words: List[Word] = []
    n = len(data.get("text", []))
    W, H = im.size
    for i in range(n):
        txt = (data["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0
        if conf < config.MIN_TEXT_CONF:
            continue
        x, y, w, h = int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i])
        if w <= 1 or h <= 1:
            continue
        if scale > 1.0:
            x, y, w, h = int(x / scale), int(y / scale), int(w / scale), int(h / scale)
        x0, y0, x1, y1 = x, y, x + w, y + h
        # clamp to image bounds, drop words that fall completely outside
        cx0, cy0 = max(0, x0), max(0, y0)
        cx1, cy1 = min(W, x1), min(H, y1)
        if cx1 - cx0 < 2 or cy1 - cy0 < 2:
            continue
        if (x1 - x0) > 0 and (cx1 - cx0) / float(x1 - x0) < 0.55:
            continue
        if (y1 - y0) > 0 and (cy1 - cy0) / float(y1 - y0) < 0.55:
            continue
        txt = txt.replace("\n", " ").replace("\x0c", "")
        words.append(Word(txt, conf, cx0, cy0, cx1, cy1))

    words = _dedup_words(words)
    return words


def _dedup_words(words: List[Word]) -> List[Word]:
    if len(words) < 2:
        return words
    words = sorted(words, key=lambda w: (-w.conf, w.y0, w.x0))
    kept: List[Word] = []
    for w in words:
        dup = False
        for k in kept:
            if k.text != w.text:
                continue
            dx = abs(k.cx - w.cx)
            dy = abs(k.cy - w.cy)
            if dx < max(30, w.w * 0.9) and dy < max(14, w.h * 0.7):
                dup = True
                break
        if not dup:
            kept.append(w)
    return kept


def _sort_reading_order(words: List[Word]) -> List[Word]:
    if not words:
        return words
    xs = np.array([w.cx for w in words], dtype=np.float64)
    ys = np.array([w.cy for w in words], dtype=np.float64)
    hx = np.histogram(xs, bins=min(60, max(6, len(words) // 8)), range=(xs.min(), xs.max() + 1))[0]
    hy = np.histogram(ys, bins=min(60, max(6, len(words) // 8)), range=(ys.min(), ys.max() + 1))[0]
    vx = float(np.median(hx)) if len(hx) else 0.0
    vy = float(np.median(hy)) if len(hy) else 0.0
    key = (vx, vy)
    if vy == 0 or (vx > 0 and vx >= vy):
        key = (ys.mean(), xs.mean())
    return sorted(words, key=lambda w: (w.cy // 40 if False else w.cy, w.x0))


def run_ocr(im: Image.Image, auto_rotate: bool = True) -> OcrResult:
    try:
        work, ratio = _upscale_if_small(im)
        angle = 0
        if auto_rotate:
            angle = _detect_orientation(work)
            if angle:
                before = work.size
                work = rotate_for_ocr(work, angle)
                words = _tesseract_words(work)
                words = _rescale_words(words, ratio)
                words = rotate_words(words, angle, before)
                return OcrResult(words=words, engine="tesseract", lang=config.OCR_LANG, ok=True)
        words = _tesseract_words(work)
        words = _rescale_words(words, ratio)
        return OcrResult(words=words, engine="tesseract", lang=config.OCR_LANG, ok=True)
    except Exception as e:
        return OcrResult(words=[], engine="tesseract", lang=config.OCR_LANG, ok=False, error=str(e))
