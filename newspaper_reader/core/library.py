from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from .. import config

_LOCK = threading.Lock()
_DOC_ID_RE = re.compile(r"^[0-9a-f]{8,32}$")


def _dir_of(doc_id: str) -> Optional[Path]:
    if not _DOC_ID_RE.match(doc_id or ""):
        return None
    d = config.LIBRARY_DIR / doc_id
    return d if d.is_dir() else None


def _clamp_width(width) -> int:
    try:
        w = int(width)
    except Exception:
        w = config.PAGE_RENDER_WIDTH
    return max(config.PAGE_RENDER_MIN, min(w, config.PAGE_RENDER_MAX))


def render_page(pdf_path: Path, page_no: int, width, cache_dir: Path) -> Path:
    """Render one PDF page to a JPEG (cached on disk) for the reader."""
    import pymupdf
    from PIL import Image

    width = _clamp_width(width)
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"p{page_no:04d}_w{width}.jpg"
    if out.exists() and out.stat().st_size > 0:
        return out

    doc = pymupdf.open(str(pdf_path))
    try:
        if page_no < 1 or page_no > doc.page_count:
            raise IndexError(f"page {page_no} out of range 1..{doc.page_count}")
        page = doc[page_no - 1]
        zoom = width / float(page.rect.width or 1.0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    finally:
        doc.close()

    im.save(out, format="JPEG", quality=92, subsampling=0, optimize=True)
    return out


def _page_count(pdf: Path) -> int:
    try:
        import pymupdf

        doc = pymupdf.open(str(pdf))
        n = doc.page_count
        doc.close()
        return int(n)
    except Exception:
        return 0


def _with_urls(meta: Dict) -> Dict:
    doc_id = meta.get("id", "")
    meta["pdf"] = f"/api/library/{doc_id}/pdf"
    meta["thumb"] = f"/api/library/{doc_id}/thumb.jpg"
    meta["page_url"] = f"/api/library/{doc_id}/page/{{n}}"
    return meta


def add_document(
    pdf_path: Path,
    *,
    title: str = "",
    mode: str = "",
    source: str = "",
    page_labels=None,
) -> Dict:
    """Copy a finished PDF into the reading history (one doc = one PDF)."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(str(pdf_path))

    with _LOCK:
        doc_id = uuid.uuid4().hex[:12]
        d = config.LIBRARY_DIR / doc_id
        d.mkdir(parents=True, exist_ok=True)
        dest = d / "doc.pdf"
        shutil.copyfile(pdf_path, dest)
        meta = {
            "id": doc_id,
            "title": (title or "").strip() or "文档",
            "mode": mode,
            "source": source,
            "created": time.time(),
            "pages": _page_count(dest),
            "size": dest.stat().st_size,
            "page_labels": list(page_labels or []),
        }
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            render_page(dest, 1, 480, d / "pages")
        except Exception:
            pass
        _prune_locked()
        return _with_urls(dict(meta))


def _prune_locked() -> None:
    """Keep the history within LIBRARY_MAX_DOCS: drop the oldest entries."""
    root = config.LIBRARY_DIR
    if not root.exists():
        return
    entries = []
    for d in root.iterdir():
        if not d.is_dir() or not (d / "doc.pdf").exists():
            continue
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
            created = float(meta.get("created", d.stat().st_mtime))
        except Exception:
            created = d.stat().st_mtime
        entries.append((created, d.name))
    entries.sort()
    overflow = len(entries) - max(1, config.LIBRARY_MAX_DOCS)
    for _, name in entries[:overflow]:
        shutil.rmtree(root / name, ignore_errors=True)


def list_documents() -> List[Dict]:
    out: List[Dict] = []
    root = config.LIBRARY_DIR
    if not root.exists():
        return out
    for d in root.iterdir():
        if not d.is_dir() or not (d / "doc.pdf").exists():
            continue
        try:
            meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        meta["size"] = meta.get("size") or (d / "doc.pdf").stat().st_size
        out.append(_with_urls(meta))
    out.sort(key=lambda m: -float(m.get("created", 0)))
    return out


def get_document(doc_id: str) -> Optional[Dict]:
    d = _dir_of(doc_id)
    if not d:
        return None
    try:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    except Exception:
        meta = {"id": doc_id, "title": "文档", "created": d.stat().st_mtime}
    meta["size"] = meta.get("size") or (d / "doc.pdf").stat().st_size
    return _with_urls(meta)


def pdf_path(doc_id: str) -> Optional[Path]:
    d = _dir_of(doc_id)
    if not d:
        return None
    p = d / "doc.pdf"
    return p if p.exists() else None


def thumb_path(doc_id: str) -> Optional[Path]:
    d = _dir_of(doc_id)
    if not d:
        return None
    p = d / "pages" / "p0001_w480.jpg"
    if p.exists():
        return p
    pdf = d / "doc.pdf"
    if not pdf.exists():
        return None
    try:
        return render_page(pdf, 1, 480, d / "pages")
    except Exception:
        return None


def page_path(doc_id: str, page_no: int, width) -> Optional[Path]:
    d = _dir_of(doc_id)
    if not d:
        return None
    pdf = d / "doc.pdf"
    if not pdf.exists():
        return None
    try:
        return render_page(pdf, int(page_no), width, d / "pages")
    except IndexError:
        return None
    except Exception:
        return None


def delete_document(doc_id: str) -> bool:
    d = _dir_of(doc_id)
    if not d:
        return False
    shutil.rmtree(d, ignore_errors=True)
    return True


def clear() -> int:
    root = config.LIBRARY_DIR
    if not root.exists():
        return 0
    n = 0
    for d in root.iterdir():
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            n += 1
    return n
