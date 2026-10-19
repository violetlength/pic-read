from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image

from .. import config
from .ocr import Word

CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿]")
PUNCT_ONLY_RE = re.compile(r"^[\s\.,:;!?\|·、。，；：！？\-—_~～\-()\[\]【】《》“”‘’'\"/\\]+$")


@dataclass
class Block:
    text: str
    x0: int
    y0: int
    x1: int
    y1: int
    size: float
    style: str = "song"
    vertical: bool = False
    conf: float = 90.0
    align: str = "left"
    kind: str = "body"

    @property
    def w(self) -> float:
        return max(1, self.x1 - self.x0)

    @property
    def h(self) -> float:
        return max(1, self.y1 - self.y0)


@dataclass
class PhotoBlock:
    x0: int
    y0: int
    x1: int
    y1: int


@dataclass
class LayoutResult:
    blocks: List[Block] = field(default_factory=list)
    photos: List[PhotoBlock] = field(default_factory=list)
    page_w: int = 0
    page_h: int = 0


def _is_cjk(ch: str) -> bool:
    return bool(CJK_RE.match(ch))


def _drop_noise(words: List[Word]) -> List[Word]:
    if not words:
        return []
    hs = sorted(float(w.h) for w in words)
    med_h = hs[len(hs) // 2] if hs else 10.0
    kept: List[Word] = []
    for w in words:
        t = w.text.strip()
        if not t:
            continue
        if PUNCT_ONLY_RE.match(t):
            continue
        cjk = sum(1 for c in t if _is_cjk(c))
        if cjk == 0 and not re.search(r"[0-9A-Za-z]", t):
            continue
        if w.h < med_h * 0.28 and len(t) <= 1:
            continue
        kept.append(w)
    return kept


def cluster_lines(words: List[Word]) -> List[dict]:
    if not words:
        return []

    segments: List[dict] = []
    for w in sorted(words, key=lambda w: (w.y0, w.x0)):
        merged = False
        for seg in segments:
            hmin = max(6.0, min(seg["hmax"], float(w.h)))
            ov = min(seg["y1"], w.y1) - max(seg["y0"], w.y0)
            if ov <= 0:
                continue
            if ov < hmin * 0.30:
                continue
            if float(w.h) > seg["hmax"] * 1.45 or seg["hmax"] > float(w.h) * 1.45:
                continue
            gap = max(0, max(seg["x0"], w.x0) - min(seg["x1"], w.x1))
            if gap <= max(16.0, seg["hmax"] * 0.60):
                seg["words"].append(w)
                seg["x0"] = min(seg["x0"], w.x0)
                seg["y0"] = min(seg["y0"], w.y0)
                seg["x1"] = max(seg["x1"], w.x1)
                seg["y1"] = max(seg["y1"], w.y1)
                seg["hmax"] = max(seg["hmax"], float(w.h))
                merged = True
                break
        if not merged:
            segments.append(
                {
                    "words": [w],
                    "x0": w.x0,
                    "y0": w.y0,
                    "x1": w.x1,
                    "y1": w.y1,
                    "hmax": float(w.h),
                }
            )

    for seg in segments:
        ws = sorted(seg["words"], key=lambda x: x.x0)
        seg["words"] = ws
        seg["text"] = "".join(x.text for x in ws)
        seg["conf"] = float(np.mean([x.conf for x in ws])) if ws else 0.0

    segments = _merge_aligned(segments)

    for seg in segments:
        ws = seg["words"]
        heights = [float(x.h) for x in ws] or [float(seg["y1"] - seg["y0"])]
        base_h = max(seg["y1"] - seg["y0"], float(np.median(heights)))
        if ws:
            right = max(float(x.x1) for x in ws)
            left = min(float(x.x0) for x in ws)
            bottom = max(float(x.y1) for x in ws)
            top = min(float(x.y0) for x in ws)
            span = max(right - left, bottom - top)
            needed = span / max(2.0, float(len(seg["text"])))
            seg["hmax"] = max(float(np.median(heights)), needed)
            seg["x0"], seg["y0"] = int(left), int(top)
            seg["x1"], seg["y1"] = int(right), int(bottom)
        else:
            seg["hmax"] = base_h

    segments.sort(key=lambda s: (round(s["y0"] / 20.0), s["x0"]))
    return segments


def _split_spanning(segments: List[dict]) -> List[dict]:
    if len(segments) < 2:
        return segments
    W = max(s["x1"] for s in segments)
    hist = np.zeros(W + 1, dtype=np.float32)
    for s in segments:
        hist[s["x0"] : s["x1"]] += float(s["hmax"])
    k = max(3, int(W * 0.010) | 1)
    smooth = np.convolve(hist, np.ones(k, dtype=np.float32) / k, mode="same")
    thr = max(0.5, float(np.percentile(smooth, 60)) * 0.10)
    low = smooth <= thr

    cuts: List[Tuple[int, int]] = []
    x = 0
    while x < len(low):
        if not low[x]:
            x += 1
            continue
        start = x
        while x < len(low) and low[x]:
            x += 1
        if x - start >= max(6, W * 0.005):
            cuts.append((start, x))
    if not cuts:
        return segments

    out: List[dict] = []
    for seg in segments:
        spans = [(seg["x0"], seg["x1"])]
        for cs, ce in cuts:
            nxt = []
            hit = False
            for a, b in spans:
                if ce <= a or cs >= b:
                    nxt.append((a, b))
                    continue
                hit = True
                if cs > a:
                    nxt.append((a, cs))
                if ce < b:
                    nxt.append((ce, b))
            spans = nxt
            if not hit:
                break
        if len(spans) <= 1:
            out.append(seg)
            continue
        spans.sort()
        for a, b in spans:
            ws = [w for w in seg["words"] if a <= w.cx < b] or [
                w for w in seg["words"] if min(b, w.x1) - max(a, w.x0) > 0
            ]
            if not ws:
                continue
            out.append(
                {
                    "words": ws,
                    "x0": int(min(w.x0 for w in ws)),
                    "y0": int(min(w.y0 for w in ws)),
                    "x1": int(max(w.x1 for w in ws)),
                    "y1": int(max(w.y1 for w in ws)),
                    "hmax": float(max(w.h for w in ws)),
                    "text": "".join(w.text for w in sorted(ws, key=lambda x: x.x0)),
                    "conf": float(np.mean([w.conf for w in ws])),
                }
            )
    return out


def _merge_aligned(segments: List[dict]) -> List[dict]:
    if len(segments) < 2:
        return segments
    segs = sorted(segments, key=lambda s: (s["x0"], s["y0"]))
    used = [False] * len(segs)
    out: List[dict] = []
    for i, s in enumerate(segs):
        if used[i]:
            continue
        base = float((s["y0"] + s["y1"]) / 2.0)
        grp = [s]
        used[i] = True
        for j in range(i + 1, len(segs)):
            if used[j]:
                continue
            t = segs[j]
            tbase = float((t["y0"] + t["y1"]) / 2.0)
            if abs(tbase - base) > max(8.0, min(s["hmax"], t["hmax"]) * 0.45):
                continue
            if t["hmax"] > s["hmax"] * 1.6 or s["hmax"] > t["hmax"] * 1.6:
                continue
            gap = t["x0"] - s["x1"]
            if gap < -4 or gap > max(20.0, s["hmax"] * 1.0):
                continue
            grp.append(t)
            used[j] = True
        if len(grp) == 1:
            out.append(s)
            continue
        grp.sort(key=lambda g: g["x0"])
        ws: List[Word] = []
        for g in grp:
            ws.extend(g["words"])
        out.append(
            {
                "words": sorted(ws, key=lambda x: x.x0),
                "x0": int(min(g["x0"] for g in grp)),
                "y0": int(min(g["y0"] for g in grp)),
                "x1": int(max(g["x1"] for g in grp)),
                "y1": int(max(g["y1"] for g in grp)),
                "hmax": float(max(g["hmax"] for g in grp)),
                "text": "".join(g["text"] for g in grp),
                "conf": float(np.mean([g["conf"] for g in grp])),
            }
        )
    out.sort(key=lambda s: (round(s["y0"] / 20.0), s["x0"]))
    return out


def _looks_vertical(line: dict) -> bool:
    text = line["text"].strip()
    ws = line["words"]
    if len(text) < 2 or len(ws) < 2:
        return False
    # punctuation/quote boxes from OCR are often tall and narrow: ignore them
    ink = [w for w in ws if any(_is_cjk(c) or c.isalnum() for c in w.text)]
    if len(ink) < 2:
        return False
    hs = [float(w.h) for w in ink]
    widths = [float(w.w) for w in ink]
    med_h = float(np.median(hs))
    med_w = float(np.median(widths))
    if med_h <= 0 or med_w <= 0:
        return False
    cjk = sum(1 for c in text if _is_cjk(c))
    if cjk < max(2, len(text) * 0.6):
        return False
    # the whole line must be taller than wide, otherwise it is horizontal text
    line_w = float(line["x1"] - line["x0"])
    line_h = float(line["y1"] - line["y0"])
    if line_w <= 0 or line_h <= 0:
        return False
    if line_h < line_w * 1.15:
        return False
    if med_h >= med_w * 1.8:
        ys = [w.cy for w in ink]
        xs = [w.cx for w in ink]
        span_y = max(ys) - min(ys) + med_h
        span_x = max(xs) - min(xs) + med_w
        if span_y >= span_x * 1.6:
            return True
    if med_h >= med_w * 1.5 and med_w <= med_h * 0.60:
        return True
    return False


def _band_columns(lines: List[dict]) -> List[Tuple[int, int]]:
    valid = [l for l in lines if (l["x1"] - l["x0"]) > 0]
    if not valid:
        return []
    W = max(l["x1"] for l in valid)
    hist = np.zeros(W + 1, dtype=np.float32)
    for l in valid:
        hist[l["x0"] : l["x1"]] += 1.0
    k = max(3, int(W * 0.012) | 1)
    ker = np.ones(k, dtype=np.float32) / k
    smooth = np.convolve(hist, ker, mode="same")
    thr = float(np.percentile(smooth, 62)) * 0.12
    low = smooth <= max(0.6, thr)

    bands: List[Tuple[int, int]] = []
    x = 0
    Wm = len(low)
    while x < Wm:
        if not low[x]:
            x += 1
            continue
        start = x
        while x < Wm and low[x]:
            x += 1
        if x - start >= max(6, W * 0.004):
            bands.append((start, x))
    if not bands:
        return []

    cols: List[Tuple[int, int]] = []
    prev = 0
    for s, e in bands:
        if s > prev:
            cols.append((prev, s))
        prev = e
    if prev < W:
        cols.append((prev, W))

    merged: List[Tuple[int, int]] = []
    for c in cols:
        if not merged:
            merged.append(c)
            continue
        ps, pe = merged[-1]
        if c[1] - c[0] < W * 0.02 and (c[0] - pe) < W * 0.006:
            merged[-1] = (ps, c[1])
        else:
            merged.append(c)
    return [c for c in merged if c[1] - c[0] > W * 0.02]


def _group_bands(lines: List[dict], cols: List[Tuple[int, int]]) -> List[List[dict]]:
    if not cols:
        return [sorted(lines, key=lambda l: (l["y0"], l["x0"]))]
    groups: List[List[dict]] = [[] for _ in cols]
    for ln in lines:
        ws = ln.get("words") or []
        if not ws:
            groups[0].append(ln)
            continue
        buckets: dict[int, List[Word]] = {}
        for w in ws:
            best_i, best_ov = 0, -1.0
            for i, (s, e) in enumerate(cols):
                ov = min(e, w.x1) - max(s, w.x0)
                if ov > best_ov:
                    best_ov, best_i = ov, i
            if best_ov <= 0:
                cx = w.cx
                for i, (s, e) in enumerate(cols):
                    if s <= cx <= e:
                        best_i = i
                        break
            buckets.setdefault(best_i, []).append(w)

        for i, wlist in buckets.items():
            if not wlist:
                continue
            wlist = sorted(wlist, key=lambda x: x.x0)
            groups[i].append(
                {
                    "words": wlist,
                    "x0": int(min(w.x0 for w in wlist)),
                    "y0": int(min(w.y0 for w in wlist)),
                    "x1": int(max(w.x1 for w in wlist)),
                    "y1": int(max(w.y1 for w in wlist)),
                    "hmax": float(max(w.h for w in wlist)),
                    "text": "".join(w.text for w in wlist),
                    "conf": float(np.mean([w.conf for w in wlist])),
                }
            )

    for g in groups:
        g.sort(key=lambda l: l["y0"])
    merged_groups: List[List[dict]] = []
    for g in groups:
        if g:
            merged_groups.append(g)
    return merged_groups or [sorted(lines, key=lambda l: (l["y0"], l["x0"]))]


def _median_size(lines: List[dict]) -> float:
    hs = [float(l["y1"] - l["y0"]) for l in lines if len(l["text"].strip()) >= 4]
    if not hs:
        hs = [float(l["y1"] - l["y0"]) for l in lines]
    return float(np.median(hs)) if hs else 12.0


def detect_photos(im: Image.Image, words: List[Word]) -> List[PhotoBlock]:
    arr = np.array(im)
    h, w = arr.shape[:2]
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    mean = cv2.blur(blur, (9, 9))
    sq = cv2.blur(blur.astype(np.float32) ** 2, (9, 9))
    var = np.clip(sq - mean.astype(np.float32) ** 2, 0, None)
    std = np.sqrt(var)

    hsv = cv2.cvtColor(arr, cv2.COLOR_RGB2HSV)
    sat = hsv[:, :, 1].astype(np.float32)
    sat = cv2.GaussianBlur(sat, (9, 9), 0)

    thr_std = max(22.0, float(np.percentile(std, 78)))
    thr_sat = max(55.0, float(np.percentile(sat, 85)))
    mask = ((std > thr_std) | (sat > thr_sat)).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8), iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8), iterations=1)

    min_area = max(2500, int(w * h * config.PHOTO_MIN_AREA_RATIO))
    min_side = max(28, config.PHOTO_MIN_SIDE * min(2.5, max(w, h) / 1500.0))
    max_area = int(w * h * 0.40)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    text_mask = np.zeros((h, w), dtype=np.uint8)
    for wd in words:
        x0, y0 = max(0, wd.x0), max(0, wd.y0)
        x1, y1 = min(w, wd.x1), min(h, wd.y1)
        if x1 > x0 and y1 > y0:
            cv2.rectangle(text_mask, (x0, y0), (x1, y1), 255, -1)

    out: List[PhotoBlock] = []
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        if area < min_area or area > max_area or bw < min_side or bh < min_side:
            continue
        if bw > w * 0.98 and bh > h * 0.98:
            continue
        if bw * bh > max_area * 1.6:
            continue
        fill = area / float(max(1, bw * bh))
        if fill < 0.35:
            continue
        roi = labels[y : y + bh, x : x + bw] == i
        if roi.mean() < 0.4:
            continue
        box = np.zeros((h, w), dtype=np.uint8)
        cv2.rectangle(box, (x, y), (x + bw, y + bh), 255, -1)
        inter = int(np.count_nonzero(cv2.bitwise_and(box, text_mask)))
        if inter / float(max(1, bw * bh)) > config.PHOTO_TEXT_OVERLAP:
            continue
        out.append(PhotoBlock(int(x), int(y), int(x + bw), int(y + bh)))

    out.sort(key=lambda p: (p.y0, p.x0))
    kept: List[PhotoBlock] = []
    for p in out:
        merged = False
        for q in kept:
            ix = max(0, min(p.x1, q.x1) - max(p.x0, q.x0))
            iy = max(0, min(p.y1, q.y1) - max(p.y0, q.y0))
            inter = ix * iy
            a1 = (p.x1 - p.x0) * (p.y1 - p.y0)
            a2 = (q.x1 - q.x0) * (q.y1 - q.y0)
            if inter > 0.45 * min(a1, a2):
                q.x0, q.y0 = min(q.x0, p.x0), min(q.y0, p.y0)
                q.x1, q.y1 = max(q.x1, p.x1), max(q.y1, p.y1)
                merged = True
                break
        if not merged:
            kept.append(p)
    return kept


def _line_to_block(line: dict, med: float, vertical: bool = False) -> Optional[Block]:
    text = line["text"].strip()
    if not text:
        return None
    if len(text) < config.MIN_LINE_CHARS and not re.search(r"[0-9A-Za-z぀-ヿ]", text):
        return None
    x0, y0, x1, y1 = line["x0"], line["y0"], line["x1"], line["y1"]
    hs = [float(w.h) for w in line.get("words", [])] or [float(y1 - y0)]
    ch = max(1.0, max(y1 - y0, line.get("hmax", 0.0) or 0.0, float(np.median(hs))))
    cw = max(1.0, float(x1 - x0))
    if vertical:
        chars = [c for c in text if c.strip()]
        n = max(1, len(chars))
        ink = [w for w in line.get("words", []) if any(_is_cjk(c) or c.isalnum() for c in w.text)]
        if ink:
            med_w = float(np.median([w.w for w in ink]))
            med_h = float(np.median([w.h for w in ink]))
            size = float(np.median([med_w * 1.02, med_h * 0.92]))
        else:
            size = ch * 0.9
        size = max(4.0, min(size, config.MAX_FONT_PT))
        style = "hei" if size > med * 1.7 else "song"
        return Block(
            text=text,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            size=round(size, 2),
            style=style,
            vertical=True,
            conf=float(line.get("conf", 90.0)),
            kind="title" if size > med * 1.7 else "body",
        )

    n = max(1, len(text))
    size = ch * 0.92
    if n >= 6:
        avg_w = cw / n
        cjk_n = sum(1 for c in text if _is_cjk(c))
        if cjk_n >= n * 0.6:
            size = min(size, avg_w * 1.12)
    size = max(config.MIN_FONT_PT, min(size, config.MAX_FONT_PT))

    style = "song"
    kind = "body"
    ratio = size / max(1.0, med)
    if ratio >= 1.75:
        style = "hei"
        kind = "title"
    elif ratio >= 1.3:
        style = "hei"
        kind = "subtitle"

    return Block(
        text=text,
        x0=x0,
        y0=y0,
        x1=x1,
        y1=y1,
        size=round(size, 2),
        style=style,
        vertical=False,
        conf=float(line.get("conf", 90.0)),
        kind=kind,
    )


def analyze(im: Image.Image, words: List[Word]) -> LayoutResult:
    w, h = im.size
    words = _drop_noise(words)
    lines = cluster_lines(words)
    if not lines:
        return LayoutResult(blocks=[], photos=detect_photos(im, []), page_w=w, page_h=h)

    med = _median_size(lines)

    vertical_lines = [l for l in lines if _looks_vertical(l)]
    normal_lines = [l for l in lines if l not in vertical_lines]

    blocks: List[Block] = []
    for ln in vertical_lines:
        b = _line_to_block(ln, med, vertical=True)
        if b:
            blocks.append(b)

    cols = _band_columns(normal_lines)
    groups = _group_bands(normal_lines, cols)
    for g in groups:
        for ln in g:
            b = _line_to_block(ln, med, vertical=False)
            if b:
                blocks.append(b)

    photos = detect_photos(im, words)
    for p in photos:
        cut = False
        for b in blocks:
            ix = max(0, min(p.x1, b.x1) - max(p.x0, b.x0))
            iy = max(0, min(p.y1, b.y1) - max(p.y0, b.y0))
            if ix * iy > 0.6 * b.w * b.h:
                cut = True
                break
        if cut:
            continue

    blocks.sort(key=lambda b: (b.y0, b.x0))
    return LayoutResult(blocks=blocks, photos=photos, page_w=w, page_h=h)
