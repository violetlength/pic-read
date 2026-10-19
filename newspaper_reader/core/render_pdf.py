from __future__ import annotations

import io
import json
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .. import config
from .fonts import fit_font_size, measure_width, pdf_font_name
from .layout import Block, LayoutResult, PhotoBlock


def _page_size_for(w: int, h: int) -> Tuple[float, float]:
    scale = config.PDF_TARGET_HEIGHT / float(h)
    pw = w * scale
    if pw > config.PDF_MAX_WIDTH:
        scale = config.PDF_MAX_WIDTH / float(w)
    pw = max(120.0, w * scale)
    ph = max(120.0, h * scale)
    return pw, ph


def _clip_region(im: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
    x0, y0, x1, y1 = box
    x0 = max(0, min(im.size[0] - 1, int(x0)))
    y0 = max(0, min(im.size[1] - 1, int(y0)))
    x1 = max(x0 + 1, min(im.size[0], int(x1)))
    y1 = max(y0 + 1, min(im.size[1], int(y1)))
    return im.crop((x0, y0, x1, y1))


def _draw_photo(c: canvas.Canvas, im: Image.Image, p: PhotoBlock, scale: float, ox: int, oy: int, min_side: int = 24) -> Optional[dict]:
    px0, py0 = p.x0 - ox, p.y0 - oy
    px1, py1 = p.x1 - ox, p.y1 - oy
    pw, ph = px1 - px0, py1 - py0
    if pw < min_side or ph < min_side:
        return None
    if pw * scale < 8 or ph * scale < 8:
        return None

    crop = _clip_region(im, (p.x0, p.y0, p.x1, p.y1))
    if crop.size[0] < 2 or crop.size[1] < 2:
        return None

    max_px = 1500
    if max(crop.size) > max_px:
        r = max_px / float(max(crop.size))
        crop = crop.resize((max(1, int(crop.size[0] * r)), max(1, int(crop.size[1] * r))), Image.LANCZOS)

    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=88, optimize=True, progressive=True)
    buf.seek(0)

    x = px0 * scale
    y = config.PDF_TARGET_HEIGHT - py1 * scale
    w = pw * scale
    h = ph * scale
    c.drawImage(ImageReader(buf), x, y, width=w, height=w * crop.size[1] / crop.size[0], mask="auto")
    return {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)}


def _draw_background(c: canvas.Canvas, im: Image.Image, scale: float, opacity: float) -> None:
    if opacity <= 0.001:
        return
    try:
        bg = im.copy()
        if max(bg.size) > 1500:
            r = 1500.0 / max(bg.size)
            bg = bg.resize((max(1, int(bg.size[0] * r)), max(1, int(bg.size[1] * r))), Image.LANCZOS)
        buf = io.BytesIO()
        bg.save(buf, format="JPEG", quality=70, optimize=True)
        buf.seek(0)
        c.saveState()
        c.setFillAlpha(float(opacity))
        c.drawImage(ImageReader(buf), 0, 0, width=bg.size[0] * scale, height=bg.size[1] * scale, mask="auto")
        c.restoreState()
    except Exception:
        pass


def _draw_block(
    c: canvas.Canvas, b: Block, scale: float, ox: int, oy: int, layout_w: int, layout_h: int
) -> Optional[dict]:
    text = b.text.strip()
    if not text:
        return None
    x0, y0 = b.x0 - ox, b.y0 - oy
    x1, y1 = b.x1 - ox, b.y1 - oy
    if x1 <= 0 or y1 <= 0 or x0 >= layout_w or y0 >= layout_h:
        return None
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(layout_w, x1)
    y1 = min(layout_h, y1)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    pw = max(1.0, x1 - x0) * scale
    ph = max(1.0, y1 - y0) * scale
    font = pdf_font_name(b.style)
    size = float(b.size)

    if b.vertical:
        chars = [ch for ch in text if ch.strip()]
        if not chars:
            return None
        cell = ph / len(chars)
        fs = max(config.MIN_FONT_PT, min(size * scale, cell * 0.94, pw * 0.98))
        top = config.PDF_TARGET_HEIGHT - y0 * scale
        c.setFont(font, fs)
        c.setFillAlpha(0.97)
        for i, ch in enumerate(chars):
            try:
                c.drawCentredString(x0 * scale + pw / 2.0, top - (i + 1) * cell + (cell - fs) * 0.55, ch)
            except Exception:
                continue
        c.setFillAlpha(1.0)
        return {
            "text": text,
            "x": round(x0 * scale, 2),
            "y": round(top - ph, 2),
            "w": round(pw, 2),
            "h": round(ph, 2),
            "size": round(fs, 2),
            "font": b.style,
            "vertical": True,
        }

    hi = max(config.MIN_FONT_PT, min(size * scale, ph * 0.98))
    lo = max(config.MIN_FONT_PT, hi * 0.55)
    fs = fit_font_size(text, b.style, pw, ph, hi, lo)
    if fs <= 0:
        fs = max(config.MIN_FONT_PT, min(hi, ph * 0.85))

    natural = measure_width(text, b.style, fs)
    if natural <= 0:
        return None
    if natural <= pw:
        hscale = 1.0
    else:
        # keep the original glyph height, compress horizontally to fit the box
        hscale = max(0.52, pw / natural)

    baseline = config.PDF_TARGET_HEIGHT - (y0 * scale + fs * 0.86)

    try:
        c.setFont(font, fs)
        c.setFillAlpha(0.97)
        if hscale < 0.995:
            c.saveState()
            c.translate(x0 * scale, baseline)
            c.scale(hscale, 1.0)
            c.drawString(0, 0, text)
            c.restoreState()
        else:
            c.drawString(x0 * scale, baseline, text)
        c.setFillAlpha(1.0)
    except Exception:
        c.setFont("Helvetica", max(config.MIN_FONT_PT, fs))
        try:
            c.drawString(x0 * scale, baseline, text.encode("ascii", "ignore").decode("ascii"))
        except Exception:
            return None

    return {
        "text": text,
        "x": round(x0 * scale, 2),
        "y": round(config.PDF_TARGET_HEIGHT - (y0 * scale + ph), 2),
        "w": round(pw, 2),
        "h": round(ph, 2),
        "size": round(fs, 2),
        "hscale": round(hscale, 3),
        "font": b.style,
        "vertical": False,
    }


def render_issue_pdf(
    pages: List[dict],
    out_path: str | Path,
    bg_opacity: float = config.DEFAULT_BG_OPACITY,
    title: str = "",
) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    page_infos = []
    first = pages[0] if pages else None
    pw, ph = (600.0, 841.9)
    if first is not None:
        pw, ph = _page_size_for(first["layout"].page_w, first["layout"].page_h)

    c = canvas.Canvas(str(out_path), pagesize=(pw, ph))
    c.setTitle(title or out_path.stem)
    c.setCreator("Newspaper Reader")

    for idx, pg in enumerate(pages):
        im: Image.Image = pg["image"]
        layout: LayoutResult = pg["layout"]
        ox, oy = pg.get("ox", 0), pg.get("oy", 0)
        w, h = layout.page_w, layout.page_h
        pw, ph = _page_size_for(w, h)
        c.setPageSize((pw, ph))
        scale = pw / float(w)

        _draw_background(c, im, scale, bg_opacity)

        text_payload = []
        for b in layout.blocks:
            info = _draw_block(c, b, scale, ox, oy, layout.page_w, layout.page_h)
            if info:
                text_payload.append(info)

        photo_payload = []
        for p in layout.photos:
            info = _draw_photo(c, im, p, scale, ox, oy)
            if info:
                photo_payload.append(info)

        page_infos.append(
            {
                "index": idx,
                "w": round(pw, 2),
                "h": round(ph, 2),
                "text": text_payload,
                "photos": photo_payload,
                "page_label": pg.get("page_label", ""),
            }
        )
        c.showPage()

    c.save()

    meta_path = out_path.with_suffix(".json")
    try:
        meta_path.write_text(
            json.dumps({"pages": page_infos, "title": title}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    return {
        "pdf": str(out_path),
        "meta": str(meta_path),
        "pages": len(pages),
        "size": out_path.stat().st_size if out_path.exists() else 0,
    }


def _encode_page(
    im: Image.Image,
    bw: bool = False,
    quality: int = config.SCAN_JPEG_QUALITY,
    subsampling: int = config.SCAN_JPEG_SUBSAMPLING,
) -> io.BytesIO:
    buf = io.BytesIO()
    if bw:
        if im.mode not in ("1", "L"):
            im = im.convert("L")
        im.save(buf, format="PNG", optimize=True)
    elif im.mode in ("1", "L"):
        im.convert("RGB").save(
            buf, format="JPEG", quality=quality, subsampling=subsampling, optimize=True
        )
    else:
        im.save(
            buf,
            format="JPEG",
            quality=quality,
            subsampling=subsampling,
            optimize=True,
            progressive=True,
        )
    buf.seek(0)
    return buf


def _draw_invisible_text(c: canvas.Canvas, words, scale: float, page_h_pt: float) -> List[dict]:
    if not words:
        return []
    payload: List[dict] = []
    c.saveState()
    try:
        c._code.append("3 Tr")  # text render mode 3 = invisible (keeps the page searchable)
        font = pdf_font_name("hei")
        last = None
        for wd in words:
            txt = (wd.text or "").strip()
            if not txt:
                continue
            box_h = max(1, wd.y1 - wd.y0) * scale
            fs = max(config.MIN_FONT_PT, min(config.MAX_FONT_PT, box_h * 0.92))
            if fs <= 0:
                continue
            x = wd.x0 * scale
            y = page_h_pt - wd.y1 * scale + fs * 0.18
            if x < -2 or y < -2 or x > config.PDF_MAX_WIDTH + 2:
                continue
            try:
                if last != font:
                    c.setFont(font, fs)
                    last = font
                elif c._fontsize != fs:
                    c.setFont(font, fs)
                c.drawString(x, y, txt)
            except Exception:
                continue
            payload.append({"text": txt, "x": round(x, 2), "y": round(y, 2), "size": round(fs, 2)})
        c._code.append("0 Tr")
    finally:
        c.restoreState()
    return payload


def render_scan_pdf(
    pages: List[dict],
    out_path: str | Path,
    title: str = "",
    clarity: str = "high",
) -> dict:
    """Merge enhanced page images into one PDF (searchable via an invisible text layer)."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 4:4:4 keeps colour fringes on text; PSNR 95/4:4:4 ≈ 47dB, 92/4:4:4 ≈ 43dB
    quality = 95 if clarity == "high" else 92

    page_infos = []
    c = None
    for idx, pg in enumerate(pages):
        im: Image.Image = pg["image"]
        w, h = im.size
        pw, ph = _page_size_for(w, h)
        if c is None:
            c = canvas.Canvas(str(out_path), pagesize=(pw, ph))
            c.setTitle(title or out_path.stem)
            c.setCreator("Newspaper Reader")
        c.setPageSize((pw, ph))
        scale = pw / float(w)
        ph = h * scale

        buf = _encode_page(
            im,
            bw=pg.get("style", "") == "bw" or im.mode == "1",
            quality=quality,
            subsampling=config.SCAN_JPEG_SUBSAMPLING,
        )
        c.drawImage(ImageReader(buf), 0, 0, width=pw, height=ph, mask="auto")

        wl = pg.get("ocr_words")
        if wl is None:
            wl = pg.get("words") or []
        if not isinstance(wl, list):
            wl = []
        text_payload = _draw_invisible_text(c, wl, scale, ph)

        page_infos.append(
            {
                "index": idx,
                "w": round(pw, 2),
                "h": round(ph, 2),
                "text": text_payload,
                "photos": [],
                "page_label": pg.get("page_label", ""),
            }
        )
        c.showPage()

    if c is None:
        c = canvas.Canvas(str(out_path), pagesize=(600.0, 841.9))
    c.save()

    meta_path = out_path.with_suffix(".json")
    try:
        meta_path.write_text(
            json.dumps({"pages": page_infos, "title": title}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass

    return {
        "pdf": str(out_path),
        "meta": str(meta_path),
        "pages": len(pages),
        "size": out_path.stat().st_size if out_path.exists() else 0,
    }
