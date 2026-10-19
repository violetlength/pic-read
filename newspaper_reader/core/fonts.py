from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List, Optional

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

_CANDIDATES = {
    "hei": [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\Deng.ttf",
        r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf",
    ],
    "hei-bold": [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\Dengb.ttf",
        r"C:\Windows\Fonts\Noto Sans SC Bold (TrueType).otf",
        r"C:\Windows\Fonts\simhei.ttf",
    ],
    "song": [
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\Noto Serif SC (TrueType).otf",
        r"C:\Windows\Fonts\Deng.ttf",
    ],
    "kai": [
        r"C:\Windows\Fonts\simkai.ttf",
        r"C:\Windows\Fonts\STKAITI.TTF",
        r"C:\Windows\Fonts\simfang.ttf",
    ],
}

_PIL_FONT: Dict[str, "object"] = {}
_PDF_NAME: Dict[str, Optional[str]] = {}
_PDF_OBJ: Dict[str, Optional[object]] = {}
_PIL_PATH: Dict[str, Optional[str]] = {}
_REF_PX = 1000
_WIDTH_CACHE: Dict[str, Dict[str, float]] = {}


def _pil_load(style: str, px: int):
    from PIL import ImageFont

    if style not in _PIL_FONT or getattr(_PIL_FONT[style], "size", 0) != px:
        path = _PIL_PATH.get(style)
        if path is None:
            _PIL_FONT[style] = ImageFont.load_default()
            return _PIL_FONT[style]
        try:
            _PIL_FONT[style] = ImageFont.truetype(path, px)
        except Exception:
            _PIL_FONT[style] = ImageFont.load_default()
    return _PIL_FONT[style]


def register_fonts() -> Dict[str, str]:
    for style, paths in _CANDIDATES.items():
        chosen = None
        obj = None
        for p in paths:
            if not p or not Path(p).exists():
                continue
            name = f"NSR_{style}"
            try:
                obj = TTFont(name, p, subfontIndex=0)
            except Exception:
                try:
                    obj = TTFont(name, p)
                except Exception:
                    continue
            pdfmetrics.registerFont(obj)
            chosen = name
            _PIL_PATH[style] = p
            break
        if chosen is None:
            _PIL_PATH[style] = None
        _PDF_NAME[style] = chosen
        _PDF_OBJ[style] = obj

    if _PDF_NAME.get("song") is None:
        try:
            pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
            _PDF_NAME["song"] = "STSong-Light"
            _PDF_OBJ["song"] = "STSong-Light"
        except Exception:
            _PDF_NAME["song"] = "Helvetica"

    for style in _CANDIDATES:
        _PDF_NAME.setdefault(style, _PDF_NAME.get("song") or "Helvetica")
        _PIL_PATH.setdefault(style, None)
        _WIDTH_CACHE.setdefault(style, {})

    return {k: (v or "") for k, v in _PDF_NAME.items()}


def pdf_font_name(style: str) -> str:
    return _PDF_NAME.get(style) or _PDF_NAME.get("song") or "Helvetica"


def font_available(style: str) -> bool:
    return bool(_PDF_NAME.get(style))


def measure_width(text: str, style: str, pt: float) -> float:
    if not text:
        return 0.0
    cache = _WIDTH_CACHE.setdefault(style, {})
    ref = cache.get(text)
    if ref is None:
        font = _pil_load(style, _REF_PX)
        try:
            ref = float(font.getlength(text)) / _REF_PX
        except Exception:
            ref = sum(1.0 if ord(c) > 0x2E80 else 0.5 for c in text)
        if len(cache) < 8000:
            cache[text] = ref
    return ref * float(pt)


def fit_font_size(
    text: str,
    style: str,
    box_w: float,
    box_h: float,
    hi_pt: float,
    lo_pt: float = 4.0,
) -> float:
    text = text.replace("\n", " ").strip()
    if not text or box_w <= 0 or box_h <= 0:
        return max(lo_pt, min(hi_pt, box_h * 0.85 if box_h > 0 else lo_pt))

    lo = max(lo_pt, box_h * 0.55)
    hi = max(lo, min(hi_pt, box_h * 0.98))
    best = lo
    for _ in range(12):
        if hi - lo < 0.05:
            break
        mid = (lo + hi) / 2
        if measure_width(text, style, mid) <= box_w:
            best = mid
            lo = mid
        else:
            hi = mid
    return round(best, 2)
