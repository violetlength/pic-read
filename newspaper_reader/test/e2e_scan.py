# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests

BASE = "http://127.0.0.1:8765"
SRC = Path(__file__).resolve().parent / "pages"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

REF = Path(
    r"G:\xwechat_files\violetlength_e7f5\temp\RWTemp\2026-10"
    r"\9e20f478899dc29eb19741386f9343c8\2e404beca4732135016aae7e79e64e1a.jpg"
)

files = [("files", (p.name, p.read_bytes(), "image/png")) for p in sorted(SRC.glob("*.png"))]
if REF.exists():
    files.append(("files", ("ref_cover_sideways.jpg", REF.read_bytes(), "image/jpeg")))
print("uploading", len(files), "files")

r = requests.post(f"{BASE}/api/upload", files=files, timeout=120)
r.raise_for_status()
job = r.json()["job_id"]
print("job", job)

r = requests.post(
    f"{BASE}/api/convert/{job}",
    json={"mode": "scan", "scan_style": "auto", "clarity": "high", "bg_opacity": 0.055},
    timeout=30,
)
print("convert ->", r.status_code, r.text[:200])


def wait_done(job_id: str, limit: float = 900.0) -> dict:
    t0 = time.time()
    state = {}
    while time.time() - t0 < limit:
        state = requests.get(f"{BASE}/api/job/{job_id}", timeout=30).json()
        print(f"[{state.get('progress')}] {state.get('stage')}")
        if state.get("status") in ("done", "error"):
            break
        time.sleep(2)
    return state


state = wait_done(job)
if state.get("status") != "done":
    print("STATUS:", state.get("status"))
    print("\n".join(state.get("log", [])[-25:]))
    sys.exit(1)

print("issues:", state.get("issues"))
res = state["results"][0]
print("result:", res)
assert res.get("doc_id"), "result is missing doc_id (not archived to reading history)"
doc_id = res["doc_id"]

pdf = requests.get(BASE + res["pdf"], timeout=120)
pdf_path = OUT / "_e2e_scan.pdf"
pdf_path.write_bytes(pdf.content)
print("pdf bytes", len(pdf.content))

import pymupdf

doc = pymupdf.open(str(pdf_path))
print("pages:", doc.page_count)
chars = sum(len(p.get_text().strip()) for p in doc)
print("searchable chars:", chars)
for i in (0, doc.page_count - 1):
    doc[i].get_pixmap(dpi=100).save(str(OUT / f"_e2e_p{i + 1}.png"))
doc.close()

# reading history: list / page image / thumb / pdf
lib = requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]
print("library docs:", [(d["id"], d["title"], d["pages"]) for d in lib])
assert any(d["id"] == doc_id for d in lib), "converted document not in reading history"

page = requests.get(f"{BASE}/api/library/{doc_id}/page/1?w=1200", timeout=60)
print("page1:", page.status_code, page.headers.get("content-type"), len(page.content))
assert page.status_code == 200 and page.content[:2] == b"\xff\xd8", "page image not served as jpeg"
thumb = requests.get(f"{BASE}/api/library/{doc_id}/thumb.jpg", timeout=60)
print("thumb:", thumb.status_code, len(thumb.content))
assert thumb.status_code == 200
lpdf = requests.get(f"{BASE}/api/library/{doc_id}/pdf", timeout=120)
print("library pdf:", lpdf.status_code, len(lpdf.content), lpdf.headers.get("content-disposition"))
assert lpdf.status_code == 200
bad = requests.get(f"{BASE}/api/library/{doc_id}/page/9999", timeout=30)
print("bad page ->", bad.status_code)
assert bad.status_code == 404
bad_doc = requests.get(f"{BASE}/api/library/../../etc/page/1", timeout=30)
print("bad id ->", bad_doc.status_code)
assert bad_doc.status_code in (404, 400)

(OUT / "_e2e_page1.jpg").write_bytes(page.content)

# regression: rebuild mode on the same job
r = requests.post(
    f"{BASE}/api/convert/{job}",
    json={"mode": "rebuild", "bg_opacity": 0.055},
    timeout=30,
)
print("rebuild convert ->", r.status_code, r.text[:120])
state = wait_done(job)
print("rebuild status:", state.get("status"))
created = [doc_id]
if state.get("status") == "done":
    for i, x in enumerate(state["results"]):
        rr = requests.get(BASE + x["pdf"], timeout=120)
        d = pymupdf.open(stream=rr.content, filetype="pdf")
        n = d.page_count
        c = sum(len(p.get_text().strip()) for p in d)
        d.close()
        print(f"  rebuild doc[{i}] title={x['title']!r} issue={x['issue_no']!r} pages={n} chars={c} bytes={len(rr.content)}")
        (OUT / f"_e2e_rebuild_{i}.pdf").write_bytes(rr.content)
        assert x.get("doc_id"), "rebuild result missing doc_id"
        created.append(x["doc_id"])
        pp = requests.get(f"{BASE}/api/library/{x['doc_id']}/page/1?w=1000", timeout=60)
        assert pp.status_code == 200, "rebuild page image failed"
else:
    print("\n".join(state.get("log", [])[-25:]))
    sys.exit(1)

# keep the device reading history clean after the test run
for cid in created:
    requests.delete(f"{BASE}/api/library/{cid}", timeout=30)
left = requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]
print("history after cleanup:", [(d["id"], d["title"]) for d in left])

print("E2E DONE")
