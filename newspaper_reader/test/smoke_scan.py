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

files = [("files", (p.name, p.read_bytes(), "image/png")) for p in sorted(SRC.glob("*.png"))]
before = {d["id"] for d in requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]}
job = requests.post(f"{BASE}/api/upload", files=files, timeout=120).json()["job_id"]
print("job", job)
r = requests.post(
    f"{BASE}/api/convert/{job}",
    json={"mode": "scan", "scan_style": "auto", "clarity": "high"},
    timeout=30,
)
print("convert", r.status_code)

t0 = time.time()
st = {}
while time.time() - t0 < 600:
    st = requests.get(f"{BASE}/api/job/{job}", timeout=30).json()
    if st.get("status") in ("done", "error"):
        break
    time.sleep(2)
print("status", st.get("status"))
if st.get("status") != "done":
    print("\n".join(st.get("log", [])[-12:]))
    sys.exit(1)

res = st["results"][0]
print("clarity", res.get("clarity"), "pages", res["pages"], "size", res["size"], "doc", res.get("doc_id"))
assert res.get("doc_id"), "result not archived to reading history"
print("groups", [(i["issue_no"], i["date"]) for i in st.get("issues", [])])
content = requests.get(BASE + res["pdf"], timeout=180).content
(OUT / "_smoke_scan.pdf").write_bytes(content)

import pymupdf

d = pymupdf.open(str(OUT / "_smoke_scan.pdf"))
chars = sum(len(p.get_text().strip()) for p in d)
imgs = [len(p.get_images(full=True)) for p in d]
print("pdf pages", d.page_count, "chars", chars, "imgs/page", imgs, "bytes", len(content))
d[0].get_pixmap(dpi=150).save(str(OUT / "_smoke_p1.png"))
d.close()

page = requests.get(f"{BASE}/api/library/{res['doc_id']}/page/1?w=800", timeout=60)
print("library page1:", page.status_code, len(page.content))
assert page.status_code == 200

# keep the reading history clean after the test run
requests.delete(f"{BASE}/api/job/{job}", timeout=30)
for x in requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]:
    if x["id"] not in before:
        requests.delete(f"{BASE}/api/library/{x['id']}", timeout=30)
print("history left:", len(requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]))
print("SMOKE OK")
