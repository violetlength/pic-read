# -*- coding: utf-8 -*-
"""HTTP level test of the step-2 editing APIs: big preview, manual rotate, drag reorder."""
from __future__ import annotations

import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
from PIL import Image

BASE = "http://127.0.0.1:8765"
SRC = Path(__file__).resolve().parent / "pages"


def lib_ids() -> set:
    return {d["id"] for d in requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]}


def img_size(url: str) -> tuple:
    r = requests.get(BASE + url, timeout=60)
    assert r.status_code == 200, (r.status_code, url, r.text[:200])
    im = Image.open(io.BytesIO(r.content))
    return im.size


def wait_done(job: str, timeout: float = 600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = requests.get(f"{BASE}/api/job/{job}", timeout=30).json()
        if j.get("status") in ("done", "error"):
            return j
        time.sleep(2)
    raise AssertionError("conversion timeout")


def main() -> int:
    before = lib_ids()
    job = None
    try:
        files = sorted(SRC.glob("*.png"))[:3]
        assert len(files) == 3, files
        with requests.post(
            f"{BASE}/api/upload",
            files=[("files", (p.name, p.read_bytes(), "image/png")) for p in files],
            timeout=120,
        ) as r:
            assert r.status_code == 200, r.text[:300]
            j = r.json()
        job = j["job_id"]
        pages = j["pages"]
        assert len(pages) == 3, pages
        print("uploaded", [p["orig"] for p in pages])

        # --- big preview + manual rotate ---
        pid = pages[0]["id"]
        base_url = f"/api/job/{job}/pageimg/{pid}?w=800"
        w0, h0 = img_size(base_url)
        print("preview size:", w0, "x", h0)

        r = requests.post(f"{BASE}/api/job/{job}/page/{pid}/rotate", json={"angle": 90}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        rot = r.json()
        assert rot["rotate"] == 90, rot
        assert rot["thumb"].startswith("/preview/") and "_r90" in rot["thumb"], rot
        w1, h1 = img_size(rot["img"] + "?w=800")
        assert (w1, h1) == (h0, w0), f"rotate 90 should swap size: {(w0, h0)} -> {(w1, h1)}"
        print("rotate 90 ok ->", w1, "x", h1, "| thumb", rot["thumb"])

        r = requests.post(f"{BASE}/api/job/{job}/page/{pid}/rotate", json={"angle": 45}, timeout=60)
        assert r.status_code == 400, r.status_code
        r = requests.post(f"{BASE}/api/job/{job}/page/{pid}/rotate", json={"angle": 0}, timeout=60)
        assert r.status_code == 200 and r.json()["rotate"] == 0
        w2, h2 = img_size(base_url + "&v=0")
        assert (w2, h2) == (w0, h0), (w2, h2)
        print("rotate back to 0 ok")
        assert requests.get(f"{BASE}/api/job/{job}/pageimg/nope", timeout=30).status_code == 404

        # --- reorder ---
        names = [p["name"] for p in pages]
        rev = list(reversed([p["id"] for p in pages]))
        r = requests.post(f"{BASE}/api/job/{job}/order", json={"ids": rev}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        got = [p["name"] for p in requests.get(f"{BASE}/api/job/{job}", timeout=30).json()["pages"]]
        assert got == list(reversed(names)), (names, got)
        print("reorder ok:", got)
        assert requests.post(f"{BASE}/api/job/{job}/order", json={"ids": rev[:2]}, timeout=30).status_code == 400

        # --- conversion follows the edited order ---
        r = requests.post(f"{BASE}/api/convert/{job}", json={"mode": "rebuild"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        j = wait_done(job)
        assert j["status"] == "done", j.get("stage")
        assert requests.get(f"{BASE}/api/job/{job}", timeout=30).json()["pages"][0]["name"] == names[-1], "order lost after convert"
        docs = [d for d in requests.get(f"{BASE}/api/library", timeout=30).json()["docs"] if d["id"] not in before]
        assert docs, "no document archived"
        print("convert ok, archived:", [(d["title"], d["pages"]) for d in docs])
    finally:
        if job:
            try:
                requests.delete(f"{BASE}/api/job/{job}", timeout=30)
            except Exception:
                pass
        for d in lib_ids() - before:
            requests.delete(f"{BASE}/api/library/{d}", timeout=30)
        print("history left:", len(lib_ids()))
    print("EDIT E2E DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
