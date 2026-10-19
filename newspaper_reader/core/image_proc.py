from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageOps

from .. import config

Image.MAX_IMAGE_PIXELS = 400_000_000


def load_image(path: str | Path) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGB")
    elif im.mode != "RGB":
        im = im.convert("RGB")
    return im


def scale_image(im: Image.Image, max_side: int | None = None) -> Image.Image:
    max_side = max_side or config.MAX_IMAGE_SIDE
    w, h = im.size
    longest = max(w, h)
    if longest > max_side:
        r = max_side / float(longest)
        im = im.resize((max(1, int(w * r)), max(1, int(h * r))), Image.LANCZOS)
    elif longest < config.MIN_IMAGE_SIDE:
        r = min(4.0, config.MIN_IMAGE_SIDE / float(longest))
        im = im.resize((int(w * r), int(h * r)), Image.LANCZOS)
    return im


def _order_corners(pts: np.ndarray) -> np.ndarray:
    pts = pts.reshape(4, 2).astype("float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).reshape(-1)
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype="float32",
    )


def _wrap_perspective(
    im: Image.Image, quad: np.ndarray
) -> Tuple[Image.Image, Tuple[int, int, int, int], str]:
    (tl, tr, br, bl) = quad
    width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if width < 100 or height < 100:
        return im, (0, 0, im.size[0], im.size[1]), "none"

    ratio = max(im.size) / float(min(width, height))
    if ratio > 6.0:
        return im, (0, 0, im.size[0], im.size[1]), "none"

    dst = np.array(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32"
    )
    m = cv2.getPerspectiveTransform(quad, dst)
    arr = cv2.warpPerspective(np.array(im), m, (width, height), flags=cv2.INTER_CUBIC)
    out = Image.fromarray(arr)
    return out, (0, 0, width, height), "quad"


def _margin_ok(box: Tuple[int, int, int, int], w: int, h: int, min_ratio: float = 0.05) -> bool:
    x0, y0, x1, y1 = box
    if (x1 - x0) < w * 0.5 or (y1 - y0) < h * 0.5:
        return False
    return (
        x0 <= w * min_ratio
        and y0 <= h * min_ratio
        and (w - x1) <= w * min_ratio
        and (h - y1) <= h * min_ratio
    )


def straighten_paper(im: Image.Image) -> Tuple[Image.Image, Tuple[int, int, int, int], str]:
    w, h = im.size
    full = (0, 0, w, h)
    try:
        sm_side = 1300
        r = sm_side / float(max(w, h))
        if r < 1.0:
            small = im.resize((max(1, int(w * r)), max(1, int(h * r))), Image.LANCZOS)
        else:
            small = im
        gray = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(gray, 50, 150)
        edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=2)
        contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:15]
        sw, sh = small.size
        img_area = float(sw * sh)
        best_quad = None
        for c in contours:
            area = cv2.contourArea(c)
            if area < img_area * 0.30:
                break
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.035 * peri, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                quad = _order_corners(approx.reshape(4, 2))
                best_quad = quad
                break
        if best_quad is not None:
            quad = best_quad * (max(w, h) / float(sm_side))
            xs, ys = quad[:, 0], quad[:, 1]
            box = (
                int(max(0, xs.min())),
                int(max(0, ys.min())),
                int(min(w, xs.max())),
                int(min(h, ys.max())),
            )
            if _margin_ok(box, w, h, 0.06) or (box[2] - box[0]) * (box[3] - box[1]) > img_area * (w * h) * 0.55 / (sw * sh):
                out, outbox, how = _wrap_perspective(im, quad)
                if _margin_ok(outbox, out.size[0], out.size[1], 0.35):
                    return out, outbox, how
    except Exception:
        pass
    return im, full, "none"


def content_box(im: Image.Image, pad: int = 10) -> Tuple[int, int, int, int]:
    w, h = im.size
    full = (0, 0, w, h)
    try:
        sm = 1600
        r = sm / float(max(w, h))
        if r < 1.0:
            small = im.resize((max(1, int(w * r)), max(1, int(h * r))), Image.LANCZOS)
        else:
            small = im
        gray = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2GRAY)
        th = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 18
        )
        th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8), iterations=2)
        th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        coords = cv2.findNonZero(th)
        if coords is None:
            return full
        x, y, bw, bh = cv2.boundingRect(coords)
        sw, sh = small.size
        if bw < sw * 0.4 or bh < sh * 0.4:
            return full
        sx, sy = w / float(sw), h / float(sh)
        box = (
            max(0, int(x * sx) - pad),
            max(0, int(y * sy) - pad),
            min(w, int((x + bw) * sx) + pad),
            min(h, int((y + bh) * sy) + pad),
        )
        # never crop away a significant part of the page (photos can be pale)
        if (box[2] - box[0]) < w * 0.82 or (box[3] - box[1]) < h * 0.82:
            return full
        return box
    except Exception:
        return full


def deskew(im: Image.Image, max_angle: float = 6.0) -> Tuple[Image.Image, float]:
    try:
        sm = 1500
        r = sm / float(max(im.size))
        small = im if r >= 1.0 else im.resize((max(1, int(im.size[0] * r)), max(1, int(im.size[1] * r))), Image.LANCZOS)
        gray = cv2.cvtColor(np.array(small), cv2.COLOR_RGB2GRAY)
        th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = cv2.findNonZero(th)
        if coords is None or len(coords) < 50:
            return im, 0.0
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.15 or abs(angle) > max_angle:
            return im, 0.0
        return im.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(255, 255, 255)), float(angle)
    except Exception:
        return im, 0.0


def prepare_page(path: str | Path) -> dict:
    im = load_image(path)
    im = scale_image(im)
    original_size = im.size

    im, quad_box, how = straighten_paper(im)
    box = content_box(im)
    im = im.crop(box)

    angle = 0.0
    im, angle = deskew(im)

    return {
        "image": im,
        "box": box,
        "original_size": original_size,
        "deskew_angle": round(angle, 3),
        "straighten": how,
    }


def binarize(im: Image.Image) -> np.ndarray:
    gray = cv2.cvtColor(np.array(im), cv2.COLOR_RGB2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 15
    )
