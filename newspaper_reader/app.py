from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel

from . import config
from .core import (
    cover as cover_mod,
    enhance as enhance_mod,
    fonts as fonts_mod,
    image_proc,
    layout as layout_mod,
    library as lib_mod,
    ocr as ocr_mod,
    render_pdf,
)

config.ensure_dirs()
fonts_mod.register_fonts()

app = FastAPI(title="图片文字阅读器", version="2.0.0")


@app.middleware("http")
async def _no_store_shell(request, call_next):
    """Local tool: never let the browser cache the page shell / API answers.

    A stale index.html+app.js pair after a restart would silently break the UI.
    """
    resp = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") or path in ("", "/") or Path(path).suffix.lower() in (".html", ".js", ".css"):
        resp.headers["Cache-Control"] = "no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
    return resp

JOBS: Dict[str, dict] = {}
LOCK = threading.Lock()


def _safe_name(name: str) -> str:
    name = Path(name or "page").name
    keep = "".join(ch for ch in name if ch.isalnum() or ch in "._- 一二三四五六七八九十")
    keep = keep.strip() or "page"
    if len(keep) > 80:
        keep = keep[:60] + "_" + uuid.uuid4().hex[:6]
    return keep


def _thumb(path: Path, max_side: int = 420) -> Optional[str]:
    try:
        from PIL import Image

        im = Image.open(path)
        im = image_proc.load_image(path)
        r = max_side / float(max(im.size))
        if r < 1.0:
            im = im.resize((max(1, int(im.size[0] * r)), max(1, int(im.size[1] * r))), Image.LANCZOS)
        out = PREVIEW_THUMBS / (path.stem + ".jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        im.save(out, format="JPEG", quality=80)
        return f"/preview/{out.name}"
    except Exception:
        return None


def _save_preview(im, stem: str, max_side: int) -> Optional[Path]:
    try:
        out = PREVIEW_THUMBS / (stem + ".jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        r = max_side / float(max(im.size))
        work = im.resize((max(1, int(im.size[0] * r)), max(1, int(im.size[1] * r))), Image.LANCZOS) if r < 1.0 else im
        if work.mode in ("1", "L"):
            work = work.convert("RGB")
        work.save(out, format="JPEG", quality=88, optimize=True)
        return out
    except Exception:
        return None


def _thumb_image(im, stem: str, max_side: int = 420) -> Optional[str]:
    p = _save_preview(im, stem, max_side)
    return f"/preview/{p.name}" if p else None


def _load_page_image(page: dict):
    """Load an uploaded page (EXIF applied) and bake in the user's manual rotation."""
    try:
        im = image_proc.load_image(Path(page["path"]))
    except Exception:
        return None
    angle = int(page.get("rotate") or 0) % 360
    if angle:
        im = im.rotate(-angle, expand=True)
    return im


def _page_of(job_id: str, page_id: str) -> Optional[dict]:
    job = JOBS.get(job_id)
    if not job:
        return None
    for p in job.get("pages", []):
        if p.get("id") == page_id:
            return p
    return None


PREVIEW_THUMBS = config.PREVIEW_DIR / "thumbs"
PREVIEW_THUMBS.mkdir(parents=True, exist_ok=True)


def _cleanup_old_jobs() -> None:
    now = time.time()
    with LOCK:
        dead = [k for k, v in JOBS.items() if now - v.get("created", now) > config.JOB_TTL_SECONDS]
        for k in dead:
            JOBS.pop(k, None)
    for d in (config.UPLOAD_DIR, config.OUTPUT_DIR):
        if not d.exists():
            continue
        for p in d.iterdir():
            try:
                if now - p.stat().st_mtime > config.JOB_TTL_SECONDS:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        p.unlink(missing_ok=True)
            except Exception:
                pass
    thumbs = config.PREVIEW_DIR / "thumbs"
    if thumbs.exists():
        for p in thumbs.iterdir():
            try:
                if now - p.stat().st_mtime > config.JOB_TTL_SECONDS:
                    p.unlink(missing_ok=True)
            except Exception:
                pass


def _clean_title(s: str) -> str:
    """Drop OCR junk (a stray latin letter plus one hanzi etc.) so names stay meaningful."""
    s = (s or "").strip()
    if not s or len(s) > 24:
        return ""
    if sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff") < 2:
        return ""
    return s


def _safe_filename(s: str, fallback: str = "文档") -> str:
    name = re_sub(s or fallback)
    return (name or fallback) + ".pdf"


def _doc_title(iss: dict, k: int = 0, total: int = 1) -> str:
    """Neutral document title: only mention issue/date when they were recognised."""
    no = (iss.get("issue_no") or "").strip()
    name = _clean_title(iss.get("title"))
    if name and no:
        return f"{name} · 第 {no} 期"
    if no:
        return f"第 {no} 期"
    if name:
        return name
    return "文档" if total <= 1 else f"文档 {k + 1}"


@app.get("/api/health")
def health() -> dict:
    return {
        "ok": True,
        "tesseract": Path(config.TESSERACT_CMD).exists(),
        "lang": config.OCR_LANG,
        "runtime": str(config.RUNTIME_DIR),
    }


@app.post("/api/upload")
async def upload(files: List[UploadFile] = File(...)) -> dict:
    _cleanup_old_jobs()
    job_id = uuid.uuid4().hex
    job_dir = config.UPLOAD_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    errors = []
    for f in files:
        ext = Path(f.filename or "p.jpg").suffix.lower()
        if ext not in config.ALLOWED_EXT:
            errors.append(f"{f.filename}: 不支持的格式 {ext}")
            continue
        raw = await f.read()
        if not raw:
            errors.append(f"{f.filename}: 空文件")
            continue
        dest = job_dir / f"{len(pages) + 1:03d}_{_safe_name(f.filename)}"
        dest.write_bytes(raw)
        pages.append(
            {
                "id": uuid.uuid4().hex[:8],
                "name": dest.name,
                "orig": f.filename,
                "path": str(dest),
                "thumb": _thumb(dest),
                "size": dest.stat().st_size,
            }
        )

    job = {
        "id": job_id,
        "created": time.time(),
        "status": "uploaded",
        "progress": 0,
        "stage": "已上传，等待转换",
        "pages": pages,
        "errors": errors,
        "issues": [],
        "results": [],
        "log": [],
    }
    with LOCK:
        JOBS[job_id] = job

    return {"job_id": job_id, "pages": pages, "errors": errors}


def _log(job: dict, msg: str) -> None:
    job["log"].append(f"[{time.strftime('%H:%M:%S')}] {msg}")
    if len(job["log"]) > 400:
        del job["log"][:200]


def _process(job_id: str, opts: dict) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["status"] = "processing"

    try:
        pages = job["pages"]
        total = max(1, len(pages))
        processed: List[dict] = []
        mode = str(opts.get("mode") or config.DEFAULT_OUTPUT_MODE)
        if mode not in ("scan", "rebuild"):
            mode = config.DEFAULT_OUTPUT_MODE
        scan_style = str(opts.get("scan_style") or config.DEFAULT_SCAN_STYLE)
        if scan_style not in enhance_mod.STYLES:
            scan_style = config.DEFAULT_SCAN_STYLE
        clarity = str(opts.get("clarity") or config.DEFAULT_CLARITY)
        if clarity not in enhance_mod.CLARITIES:
            clarity = config.DEFAULT_CLARITY

        for i, p in enumerate(pages):
            job["progress"] = int(8 + 70 * i / total)
            if mode == "scan":
                job["stage"] = f"扫描增强第 {i + 1}/{total} 页：{p['orig']}"
            else:
                job["stage"] = f"识别第 {i + 1}/{total} 页：{p['orig']}"
            _log(job, f"OCR {p['orig']}")

            prep = image_proc.prepare_page(p["path"])
            im = prep["image"]
            manual = int(p.get("rotate") or 0) % 360
            if manual:
                # the user set the orientation in step 2 -> honour it, skip auto-upright
                im = im.rotate(-manual, expand=True)
                rot = manual
            else:
                im, rot = ocr_mod.upright(im)
            used_style = ""
            if mode == "scan":
                im, used_style = enhance_mod.scan_page(im, scan_style, clarity)
            res = ocr_mod.run_ocr(im, auto_rotate=True)
            lay = layout_mod.analyze(im, res.words)
            info = cover_mod.parse_cover(lay.blocks, res.words)
            _log(job, f"{p['orig']}：{len(res.words)} 词 / {len(lay.blocks)} 块" + (f" / 旋转 {rot}°(手动)" if manual else (f" / 旋转 {rot}°" if rot else "")) + (f" / 风格 {used_style}" if used_style else ""))
            new_thumb = p.get("thumb", "")
            if mode != "scan":
                new_thumb = _thumb_image(im, f"{job_id}_{p['id']}") or new_thumb

            processed.append(
                {
                    "id": p["id"],
                    "name": p["name"],
                    "orig": p["orig"],
                    "path": p["path"],
                    "thumb": new_thumb,
                    "image": im,
                    "layout": lay,
                    "info": info,
                    # layout coordinates are already relative to the cropped page
                    "ox": 0,
                    "oy": 0,
                    "words": len(res.words),
                    "ocr_words": res.words,
                    "style": used_style,
                    "rotate": rot,
                    "manual_rotate": manual,
                    "blocks": len(lay.blocks),
                    "photos": len(lay.photos),
                    "deskew": prep.get("deskew_angle", 0.0),
                }
            )

        job["progress"] = 82
        job["stage"] = "识别文档分组"
        issues = cover_mod.group_issues(processed)
        for iss in issues:
            for pos, pi in enumerate(iss["pages"]):
                processed[pi]["page_label"] = cover_mod.page_label_for(processed[pi], iss, pos)

        out_dir = config.OUTPUT_DIR / job_id
        out_dir.mkdir(parents=True, exist_ok=True)
        results = []
        pdf_paths: List[Path] = []
        opacity = float(opts.get("bg_opacity", config.DEFAULT_BG_OPACITY))
        build_preview = bool(opts.get("preview", True))

        if mode == "scan":
            job["progress"] = 90
            job["stage"] = "页面增强并合并为一个 PDF"
            iss0 = issues[0] if issues else {}
            # a scanned document is named by its scan time - OCR often mangles cover titles
            stamp = time.strftime("%Y%m%d_%H%M")
            head = "扫描件 " + time.strftime("%Y-%m-%d %H:%M")
            pdf_path = out_dir / f"扫描件_{stamp}.pdf"
            meta = render_pdf.render_scan_pdf(processed, pdf_path, title=head, clarity=clarity)
            pdf_paths.append(pdf_path)

            results.append(
                {
                    "mode": "scan",
                    "style": scan_style,
                    "clarity": clarity,
                    "title": head,
                    "issue_no": (iss0.get("issue_no") or "").strip(),
                    "date": iss0.get("date", ""),
                    "page_count": str(len(processed)),
                    "pages": len(processed),
                    "pdf": f"/api/download/{job_id}/{pdf_path.name}",
                    "preview": "",
                    "size": meta["size"],
                    "page_labels": [pg.get("page_label", "") for pg in processed],
                }
            )
        else:
            total_iss = max(1, len(issues))
            for k, iss in enumerate(issues):
                job["progress"] = int(85 + 12 * (k + 1) / max(1, len(issues)))
                job["stage"] = f"重建版式并生成 PDF（第 {k + 1}/{len(issues)} 份）"
                sub = [processed[i] for i in iss["pages"]]
                title = _doc_title(iss, k, total_iss)
                label = (iss.get("issue_no") or "").strip() or (title if title != "文档" else f"文档{k + 1}")
                safe = re_sub(label)
                pdf_path = out_dir / f"{k + 1:02d}_{safe}.pdf"
                meta = render_pdf.render_issue_pdf(sub, pdf_path, bg_opacity=opacity, title=title)
                pdf_paths.append(pdf_path)

                preview_name = ""
                if build_preview and meta.get("meta"):
                    preview_name = f"{job_id}_{k}.json"
                    shutil.copyfile(meta["meta"], config.PREVIEW_DIR / preview_name)

                results.append(
                    {
                        "mode": "rebuild",
                        "title": title,
                        "issue_no": (iss.get("issue_no") or "").strip(),
                        "date": iss["date"],
                        "page_count": iss["page_count"],
                        "pages": len(sub),
                        "pdf": f"/api/download/{job_id}/{pdf_path.name}",
                        "preview": f"/api/preview/{preview_name}" if preview_name else "",
                        "size": meta["size"],
                        "page_labels": [processed[i].get("page_label", "") for i in iss["pages"]],
                    }
                )

        zip_path = out_dir / "all_issues.zip"
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
                for r in results:
                    name = Path(r["pdf"]).name
                    f = out_dir / name
                    if f.exists():
                        z.write(f, arcname=name)
        except Exception:
            pass

        for r, path in zip(results, pdf_paths):
            try:
                saved = lib_mod.add_document(
                    path,
                    title=r.get("title") or "文档",
                    mode=r.get("mode", ""),
                    source=job_id,
                    page_labels=r.get("page_labels"),
                )
                r["doc_id"] = saved["id"]
                r["doc_pages"] = saved["pages"]
            except Exception as e:
                r["doc_id"] = ""
                r["doc_pages"] = r.get("pages", 0)
                _log(job, f"加入阅读历史失败：{e}")

        job["issues"] = [
            {
                "title": i["title"],
                "issue_no": i["issue_no"],
                "date": i["date"],
                "page_count": i["page_count"],
                "pages": len(i["pages"]),
            }
            for i in issues
        ]
        job["results"] = results
        for p in processed:
            p["info"] = {
                "title": p["info"].title,
                "issue_no": p["info"].issue_no,
                "date": p["info"].date,
                "is_cover": p["info"].is_cover,
            }
            p["blocks_preview"] = [
                {
                    "t": b.text,
                    "x": b.x0,
                    "y": b.y0,
                    "w": b.w,
                    "h": b.h,
                    "s": b.size,
                    "v": 1 if b.vertical else 0,
                }
                for b in p["layout"].blocks[:400]
            ]
            p["image"] = None
            p["ocr_words"] = None
            p["layout"] = None
        job["mode"] = mode
        job["pages"] = [
            {
                "id": x.get("id", ""),
                "name": x.get("name", ""),
                "orig": x.get("orig", ""),
                "path": x.get("path", ""),
                "thumb": x.get("thumb", ""),
                "size": x.get("size", 0),
                "words": x.get("words", 0),
                "blocks": x.get("blocks", 0),
                "photos": x.get("photos", 0),
                "rotate": int(x.get("manual_rotate") or 0) % 360,
                "issue_no": x.get("info", {}).get("issue_no", ""),
                "is_cover": x.get("info", {}).get("is_cover", False),
                "blocks_preview": x.get("blocks_preview", []),
            }
            for x in processed
        ]
        job["progress"] = 100
        job["stage"] = "完成"
        job["status"] = "done"
        _log(job, f"转换完成，共 {len(results)} 份文档")
    except Exception as e:
        import traceback

        job["status"] = "error"
        job["stage"] = f"失败：{e}"
        _log(job, traceback.format_exc())


def re_sub(s: str) -> str:
    import re

    s = re.sub(r"[^\w一-鿿\-]+", "_", s or "issue")
    return s[:40] or "issue"


class ConvertOptions(BaseModel):
    bg_opacity: Optional[float] = config.DEFAULT_BG_OPACITY
    preview: Optional[bool] = True
    mode: Optional[str] = config.DEFAULT_OUTPUT_MODE
    scan_style: Optional[str] = config.DEFAULT_SCAN_STYLE
    clarity: Optional[str] = config.DEFAULT_CLARITY


class RotateOptions(BaseModel):
    angle: int = 0


class OrderOptions(BaseModel):
    ids: List[str] = []


@app.post("/api/convert/{job_id}")
def convert(job_id: str, opts: Optional[ConvertOptions] = None) -> dict:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在，请重新上传")
        if job["status"] == "processing":
            raise HTTPException(409, "正在转换中")
        if not job["pages"]:
            raise HTTPException(400, "没有可转换的图片")
    o = (opts or ConvertOptions()).model_dump()
    threading.Thread(target=_process, args=(job_id, o), daemon=True).start()
    return {"ok": True, "job_id": job_id}


@app.get("/api/job/{job_id}")
def job_status(job_id: str) -> dict:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在")
        return json.loads(json.dumps(job, ensure_ascii=False, default=str))


@app.delete("/api/job/{job_id}")
def delete_job(job_id: str) -> dict:
    with LOCK:
        JOBS.pop(job_id, None)
    shutil.rmtree(config.UPLOAD_DIR / job_id, ignore_errors=True)
    shutil.rmtree(config.OUTPUT_DIR / job_id, ignore_errors=True)
    return {"ok": True}


def _page_guard(job_id: str, page_id: str) -> dict:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在，请重新上传")
    if job.get("status") == "processing":
        raise HTTPException(409, "正在转换中，请稍后再试")
    page = _page_of(job_id, page_id)
    if not page:
        raise HTTPException(404, "图片不存在")
    return page


@app.post("/api/job/{job_id}/page/{page_id}/rotate")
def rotate_page(job_id: str, page_id: str, opts: Optional[RotateOptions] = None) -> dict:
    angle = int((opts or RotateOptions()).angle) % 360
    if angle % 90:
        raise HTTPException(400, "旋转角度必须是 90 的倍数")
    with LOCK:
        page = _page_guard(job_id, page_id)
        page["rotate"] = angle
    im = _load_page_image(page)
    thumb = _thumb_image(im, f"{job_id}_{page_id}_r{angle}", 520) if im is not None else None
    return {
        "ok": True,
        "rotate": angle,
        "thumb": thumb or page.get("thumb", ""),
        "img": f"/api/job/{job_id}/pageimg/{page_id}",
    }


@app.get("/api/job/{job_id}/pageimg/{page_id}")
def job_page_image(job_id: str, page_id: str, w: int = 1600) -> FileResponse:
    with LOCK:
        page = _page_of(job_id, page_id)
        if not page:
            raise HTTPException(404, "图片不存在")
        angle = int(page.get("rotate") or 0) % 360
    width = max(480, min(int(w), 2400))
    stem = f"big_{job_id}_{page_id}_r{angle}_w{width}"
    out = PREVIEW_THUMBS / (stem + ".jpg")
    if not out.exists():
        im = _load_page_image(page)
        if im is None:
            raise HTTPException(404, "图片读取失败")
        saved = _save_preview(im, stem, width)
        if not saved:
            raise HTTPException(500, "预览生成失败")
        out = saved
    return FileResponse(out, media_type="image/jpeg")


@app.post("/api/job/{job_id}/order")
def reorder_pages(job_id: str, opts: Optional[OrderOptions] = None) -> dict:
    ids = list((opts or OrderOptions()).ids or [])
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在，请重新上传")
        if job.get("status") == "processing":
            raise HTTPException(409, "正在转换中，请稍后再试")
        pages = job.get("pages") or []
        by_id = {p.get("id"): p for p in pages}
        wanted = [i for i in ids if i in by_id]
        if len(wanted) != len(pages) or len(set(wanted)) != len(pages):
            raise HTTPException(400, "顺序参数与图片数量不一致")
        job["pages"] = [by_id[i] for i in wanted]
        return {"ok": True, "order": wanted}


@app.get("/api/download/{job_id}/{name}")
def download(job_id: str, name: str) -> FileResponse:
    safe = Path(name).name
    path = (config.OUTPUT_DIR / job_id / safe).resolve()
    root = config.OUTPUT_DIR.resolve()
    if not str(path).startswith(str(root)) or not path.exists():
        raise HTTPException(404, "文件不存在")
    return FileResponse(path, filename=safe, media_type="application/pdf")


@app.get("/api/zip/{job_id}")
def download_zip(job_id: str) -> FileResponse:
    path = config.OUTPUT_DIR / job_id / "all_issues.zip"
    if not path.exists():
        raise HTTPException(404, "压缩包不存在")
    return FileResponse(path, filename=f"newspapers_{job_id[:6]}.zip", media_type="application/zip")


@app.get("/api/preview/{name}")
def preview_meta(name: str) -> JSONResponse:
    safe = Path(name).name
    path = (config.PREVIEW_DIR / safe).resolve()
    root = config.PREVIEW_DIR.resolve()
    if not str(path).startswith(str(root)) or not path.exists():
        raise HTTPException(404, "预览不存在")
    return JSONResponse(json.loads(path.read_text(encoding="utf-8")))


# ---------- reading history ----------


@app.get("/api/library")
def library_index() -> dict:
    return {"docs": lib_mod.list_documents()}


@app.get("/api/library/{doc_id}/page/{page_no}")
def library_page(doc_id: str, page_no: int, w: int = config.PAGE_RENDER_WIDTH) -> FileResponse:
    path = lib_mod.page_path(doc_id, page_no, w)
    if not path:
        raise HTTPException(404, "页面不存在")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/library/{doc_id}/thumb.jpg")
def library_thumb(doc_id: str) -> FileResponse:
    path = lib_mod.thumb_path(doc_id)
    if not path:
        raise HTTPException(404, "缩略图不存在")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/library/{doc_id}/pdf")
def library_pdf(doc_id: str) -> FileResponse:
    path = lib_mod.pdf_path(doc_id)
    meta = lib_mod.get_document(doc_id)
    if not path or not meta:
        raise HTTPException(404, "文档不存在")
    return FileResponse(path, filename=_safe_filename(meta.get("title")), media_type="application/pdf")


@app.delete("/api/library/{doc_id}")
def library_delete(doc_id: str) -> dict:
    if not lib_mod.delete_document(doc_id):
        raise HTTPException(404, "文档不存在")
    return {"ok": True}


@app.delete("/api/library")
def library_clear() -> dict:
    return {"ok": True, "deleted": lib_mod.clear()}


app.mount("/preview", StaticFiles(directory=str(PREVIEW_THUMBS)), name="thumbs")
app.mount("/", StaticFiles(directory=str(config.STATIC_DIR), html=True), name="static")
