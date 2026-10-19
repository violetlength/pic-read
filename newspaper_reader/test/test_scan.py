from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from newspaper_reader.core import cover as cover_mod
from newspaper_reader.core import enhance, fonts as fonts_mod, image_proc, layout as layout_mod, ocr as ocr_mod, render_pdf

fonts_mod.register_fonts()

SRC = Path(__file__).resolve().parent / "pages"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

paths = sorted(SRC.glob("*.png"))
clarity = (sys.argv[1] if len(sys.argv) > 1 else "high").strip()
if clarity not in ("high", "std"):
    clarity = "high"
print("pages:", len(paths), "clarity:", clarity)

pages = []
t_all = time.time()
for i, p in enumerate(paths):
    t0 = time.time()
    prep = image_proc.prepare_page(p)
    im, rot = ocr_mod.upright(prep["image"])
    im, style = enhance.scan_page(im, "auto", clarity)
    res = ocr_mod.run_ocr(im)
    lay = layout_mod.analyze(im, res.words)
    info = cover_mod.parse_cover(lay.blocks, res.words)
    pages.append(
        {
            "image": im,
            "words": res.words,
            "layout": lay,
            "info": info,
            "page_label": "",
            "style": style,
        }
    )
    print(
        f"[{i + 1}/{len(paths)}] {p.name} size={im.size} style={style} rot={rot} "
        f"words={len(res.words)} cover={info.is_cover} issue={info.issue_no} date={info.date} "
        f"title={info.title!r} ({time.time() - t0:.1f}s)"
    )

issues = cover_mod.group_issues(pages)
for k, iss in enumerate(issues):
    for pos, pi in enumerate(iss["pages"]):
        pages[pi]["page_label"] = cover_mod.page_label_for(pages[pi], iss, pos)
    print("issue", k, iss["title"], iss["issue_no"], iss["date"], iss["pages"])

out = OUT / f"scan_merged_{clarity}.pdf"
meta = render_pdf.render_scan_pdf(pages, out, title="扫描测试", clarity=clarity)
print("pdf ->", meta)

import fitz  # noqa: E402

doc = fitz.open(str(out))
print("pages:", doc.page_count)
total = 0
for i, page in enumerate(doc):
    txt = page.get_text().strip()
    total += len(txt)
    if i == 0:
        print("page0 text sample:", txt[:120].replace("\n", " "))
        pix = page.get_pixmap(dpi=110)
        pix.save(str(OUT / f"_scan_p1_{clarity}.png"))
        print("images on page0:", len(page.get_images(full=True)))
print("extracted chars:", total)
doc.close()

print("total %.1fs" % (time.time() - t_all))
