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

files = [("files", (p.name, p.read_bytes(), "image/png")) for p in sorted(SRC.glob("*.png"))]
print("uploading", len(files))
job = requests.post(f"{BASE}/api/upload", files=files, timeout=120).json()["job_id"]
print("job", job)

created = []
for mode in ("rebuild", "scan", "rebuild"):
    r = requests.post(f"{BASE}/api/convert/{job}", json={"mode": mode, "scan_style": "bw"}, timeout=30)
    print(mode, "->", r.status_code, r.text[:120])
    t0 = time.time()
    st = {}
    while time.time() - t0 < 900:
        st = requests.get(f"{BASE}/api/job/{job}", timeout=30).json()
        if st.get("status") in ("done", "error"):
            break
        time.sleep(2)
    print("  status:", st.get("status"))
    if st.get("status") != "done":
        print("  " + "\n  ".join(st.get("log", [])[-12:]))
        continue
    import pymupdf

    for i, x in enumerate(st["results"]):
        rr = requests.get(BASE + x["pdf"], timeout=120)
        d = pymupdf.open(stream=rr.content, filetype="pdf")
        n = d.page_count
        c = sum(len(p.get_text().strip()) for p in d)
        if mode == "rebuild":
            d[0].get_pixmap(dpi=100).save(str(OUT / f"_regr_{i}_p1.png"))
        d.close()
        print(f"  {mode} doc[{i}] title={x['title']!r} pages={n} chars={c} bytes={len(rr.content)}")
        assert x.get("doc_id"), "result missing doc_id"
        created.append(x["doc_id"])
        pg = requests.get(f"{BASE}/api/library/{x['doc_id']}/page/1?w=800", timeout=60)
        assert pg.status_code == 200, "library page image failed"
    if mode == "scan":
        (OUT / "_regr_scan.pdf").write_bytes(rr.content)

# keep the device reading history clean after the test run
for cid in dict.fromkeys([c for c in created if c]):
    requests.delete(f"{BASE}/api/library/{cid}", timeout=30)
print("history left:", len(requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]))
print("DONE")
