from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
from PIL import Image, ImageFilter

STYLES = ("auto", "color", "gray", "bw")
CLARITIES = ("high", "std")


def _illumination_field(plane: np.ndarray, k: int) -> np.ndarray:
    kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    return cv2.morphologyEx(plane, cv2.MORPH_CLOSE, kern)


def _background(rgb: np.ndarray, kernel: int = 31) -> np.ndarray:
    h, w = rgb.shape[:2]
    small = rgb
    max_side = 900
    if max(h, w) > max_side:
        r = max_side / float(max(h, w))
        small = cv2.resize(rgb, (max(1, int(w * r)), max(1, int(h * r))), interpolation=cv2.INTER_AREA)
    if small.ndim == 2:
        bg = _illumination_field(small, kernel)
    else:
        bg = np.dstack([_illumination_field(small[:, :, c], kernel) for c in range(3)])
    if small.shape[0] != h or small.shape[1] != w:
        bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR)
    return bg.astype(np.float32)


def remove_shadows(rgb: np.ndarray, max_gain: float = 1.55) -> np.ndarray:
    """Lift uneven lighting / drop shadows while keeping artwork and photos intact."""
    arr = rgb.astype(np.float32)
    bg = _background(rgb, 31)
    target = np.percentile(bg, 93, axis=(0, 1))
    gain = target / np.maximum(bg, 1.0)
    gain = np.clip(gain, 1.0, max_gain)

    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    sat = hsv[:, :, 1] / 255.0
    val = hsv[:, :, 2] / 255.0
    protect_color = np.clip((sat - 0.25) / 0.30, 0, 1) * np.clip((0.60 - val) / 0.30, 0, 1)

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    mu = cv2.blur(gray, (15, 15))
    mu2 = cv2.blur(gray * gray, (15, 15))
    std = np.sqrt(np.maximum(mu2 - mu * mu, 0.0))
    protect_tex = np.clip((std - 16.0) / 24.0, 0, 1)

    keep = np.clip(1.0 - protect_color - 0.8 * protect_tex, 0.0, 1.0)[:, :, None]
    gain = 1.0 + (gain - 1.0) * keep
    return np.clip(arr * gain, 0, 255)


def _white_balance(rgb: np.ndarray, target: float = 250.0) -> np.ndarray:
    pts = np.percentile(rgb.reshape(-1, 3), 98, axis=0)
    pts = np.maximum(pts, 1.0)
    scale = np.clip(target / pts, 0.92, 1.60)
    return np.clip(rgb * scale, 0, 255)


def _contrast(rgb: np.ndarray, amount: float = 1.07) -> np.ndarray:
    return np.clip(128.0 + (rgb - 128.0) * amount, 0, 255)


def _sharpen(im: Image.Image, percent: int = 70, radius: float = 1.4, threshold: int = 3) -> Image.Image:
    return im.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=threshold))


def _fit_resolution(im: Image.Image, clarity: str) -> Image.Image:
    """Keep every embedded page around 200-300 DPI - below that text turns mushy."""
    if clarity not in CLARITIES:
        clarity = "high"
    target = 3000 if clarity == "high" else 2400
    longest = max(im.size)
    if longest >= target:
        return im
    r = target / float(longest)
    if r <= 1.03:
        return im
    r = min(r, 2.4)
    w, h = im.size
    return im.resize((int(round(w * r)), int(round(h * r))), Image.LANCZOS)


def _denoise(im: Image.Image) -> Image.Image:
    """Light luma-only denoise so the sharpening pass does not amplify grain."""
    try:
        arr = np.array(im.convert("RGB"))
        ycc = cv2.cvtColor(arr, cv2.COLOR_RGB2YCrCb)
        ycc[:, :, 0] = cv2.bilateralFilter(ycc[:, :, 0], 5, 16, 6)
        return Image.fromarray(cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB))
    except Exception:
        return im


def _sharpen_adaptive(im: Image.Image, clarity: str = "high") -> Image.Image:
    """Two-pass unsharp (fine + mid) with radii scaled to the pixel resolution."""
    if clarity not in CLARITIES:
        clarity = "high"
    strength = 1.0 if clarity == "high" else 0.8
    longest = max(im.size)
    sc = float(np.sqrt(max(900.0, longest) / 2400.0))
    sc = max(0.75, min(2.2, sc))
    fine = int(round(95 * strength))
    mid = int(round(45 * strength))
    im = _sharpen(im, percent=fine, radius=round(0.85 * sc, 2), threshold=2)
    return _sharpen(im, percent=mid, radius=round(2.6 * sc, 2), threshold=3)


def _binarize_page(gray: np.ndarray) -> np.ndarray:
    g = cv2.GaussianBlur(gray, (3, 3), 0)
    longest = max(gray.shape[:2])
    block = int(round(41 * max(1.0, longest / 2400.0)))
    block = max(21, block + 1 if block % 2 == 0 else block)
    c = max(6, int(round(12 * max(1.0, longest / 2400.0))))
    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, c)
    return cv2.medianBlur(th, 3)


def pick_style(im: Image.Image) -> str:
    """`auto`: keep colour whenever the page carries real colour content, else B&W."""
    try:
        arr = np.array(im.convert("RGB"))
        if arr.size == 0:
            return "color"
        hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
        sat = hsv[:, :, 1]
        colorful = float((sat > 40).mean())
        white_ratio = float((hsv[:, :, 2] > 205).mean())
        if colorful < 0.04 and white_ratio > 0.45:
            return "bw"
        return "color"
    except Exception:
        return "color"


def scan_page(
    im: Image.Image, style: str = "auto", clarity: str = "high"
) -> tuple[Image.Image, str]:
    """Scanner-app style enhancement: shadow removal, whitening, contrast, sharpening."""
    style = (style or "auto").lower()
    if style not in STYLES:
        style = "auto"
    if clarity not in CLARITIES:
        clarity = "high"
    if style == "auto":
        style = pick_style(im)

    src = _fit_resolution(im.convert("RGB"), clarity)
    try:
        arr = remove_shadows(np.array(src))
        if style == "bw":
            gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            out = Image.fromarray(_binarize_page(gray)).convert("RGB")
            return out, "bw"

        if style == "gray":
            gray = cv2.cvtColor(arr.astype(np.uint8), cv2.COLOR_RGB2GRAY)
            gray = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(gray)
            arr = np.dstack([gray, gray, gray]).astype(np.float32)
            arr = _white_balance(arr, 252.0)
            arr = _contrast(arr, 1.10)
            res = Image.fromarray(arr.astype(np.uint8))
            if clarity == "high":
                res = _denoise(res)
            return _sharpen_adaptive(res, clarity), "gray"

        arr = _white_balance(arr, 250.0)
        arr = _contrast(arr, 1.06)
        res = Image.fromarray(arr.astype(np.uint8))
        if clarity == "high":
            res = _denoise(res)
        return _sharpen_adaptive(res, clarity), "color"
    except Exception:
        return src, style


def save_preview(im: Image.Image, path, max_side: int = 1400, quality: int = 84) -> Optional[str]:
    try:
        out = im.copy()
        if max(out.size) > max_side:
            r = max_side / float(max(out.size))
            out = out.resize((max(1, int(out.size[0] * r)), max(1, int(out.size[1] * r))), Image.LANCZOS)
        if out.mode == "1":
            out = out.convert("L")
        out.save(path, format="JPEG", quality=quality, optimize=True)
        return str(path)
    except Exception:
        return None
