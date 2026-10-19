from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from newspaper_reader.core import cover as cover_mod
from newspaper_reader.core import fonts as fonts_mod
from newspaper_reader.core import image_proc, layout as layout_mod, ocr as ocr_mod, render_pdf

fonts_mod.register_fonts()

SRC = Path(__file__).resolve().parent / "pages"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

paths = sorted(SRC.glob("*.png"))
print("pages:", len(paths))

pages = []
t_all = time.time()
for i, p in enumerate(paths):
    t0 = time.time()
    prep = image_proc.prepare_page(p)
    im = prep["image"]
    box = prep["box"]
    res = ocr_mod.run_ocr(im)
    lay = layout_mod.analyze(im, res.words)
    info = cover_mod.parse_cover(lay.blocks)
    pages.append(
        {
            "name": p.name,
            "image": im,
            "layout": lay,
            "info": info,
            "ox": 0,
            "oy": 0,
        }
    )
    print(
        f"[{i + 1}/{len(paths)}] {p.name} size={im.size} box={box} words={len(res.words)} "
        f"blocks={len(lay.blocks)} photos={len(lay.photos)} cover={info.is_cover} "
        f"issue={info.issue_no} date={info.date} title={info.title!r} ({time.time() - t0:.1f}s)"
    )

issues = cover_mod.group_issues(pages)
print("\n== issues ==")
for k, iss in enumerate(issues):
    print(k, iss)

for k, iss in enumerate(issues):
    sub = [pages[i] for i in iss["pages"]]
    out = OUT / f"issue_{k + 1}_{iss['issue_no']}.pdf"
    meta = render_pdf.render_issue_pdf(sub, out, bg_opacity=0.06, title=iss["title"])
    print("pdf ->", meta)

# dump text of first page for sanity check
lay0 = pages[0]["layout"]
sample = [{"t": b.text, "s": b.size, "k": b.kind, "v": b.vertical, "b": [b.x0, b.y0, b.x1, b.y1]} for b in lay0.blocks[:25]]
(OUT / "page1_blocks.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
print("total %.1fs" % (time.time() - t_all))
