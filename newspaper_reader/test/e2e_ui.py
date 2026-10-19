# -*- coding: utf-8 -*-
"""Browser level test of the 上传 → 转换 → 阅读/下载 flow (Playwright/Chromium)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
SRC = Path(__file__).resolve().parent / "pages"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(parents=True, exist_ok=True)

shots = [OUT / "_ui_step1.png", OUT / "_ui_step3.png", OUT / "_ui_history.png", OUT / "_ui_viewer.png"]
errors: list[str] = []


def snapshot_ids() -> set:
    try:
        docs = requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]
        return {d["id"] for d in docs}
    except Exception:
        return set()


def cleanup(job_id, before: set) -> None:
    if job_id:
        try:
            requests.delete(f"{BASE}/api/job/{job_id}", timeout=30)
        except Exception:
            pass
    try:
        docs = requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]
        for d in docs:
            if d["id"] not in before:
                requests.delete(f"{BASE}/api/library/{d['id']}", timeout=30)
        left = requests.get(f"{BASE}/api/library", timeout=30).json()["docs"]
        print("history after cleanup:", len(left))
    except Exception as e:
        print("cleanup failed:", e)


def goto_step(page, n: int) -> None:
    """Navigate via the stepper when it has buttons, otherwise call setStep directly."""
    if page.query_selector_all(".step"):
        page.click(f".step[data-step='{n}']")
    else:
        page.evaluate(f"setStep({n})")
    page.wait_for_selector(("#pagesPanel" if n == 2 else "#resultPanel" if n == 3 else "#dropPanel") + ":not(.hidden)", timeout=10_000)


def run(pw) -> str | None:
    files = sorted(str(p) for p in SRC.glob("*.png"))[:3]
    assert files, "no sample pages"

    browser = pw.chromium.launch()
    page = browser.new_page(viewport={"width": 1360, "height": 980})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE, wait_until="networkidle")
    assert "图片文字阅读器" in page.inner_text("h1"), page.inner_text("h1")
    steps = page.query_selector_all(".step")
    if steps:
        assert len(steps) == 3, f"stepper expected 3, got {len(steps)}"
        assert page.is_disabled(".step[data-step='2']"), "step2 must start disabled"
        assert page.is_disabled(".step[data-step='3']"), "step3 must start disabled"
    else:
        assert page.inner_text("#steps").strip(), "flow hint missing"
    assert page.is_visible("#dropPanel")
    assert not page.is_visible("#pagesPanel")
    page.screenshot(path=str(shots[0]), full_page=True)
    print("step1 ok")

    # upload -> step2
    page.set_input_files("#fileInput", files)
    page.wait_for_selector("#pagesPanel:not(.hidden)", timeout=60_000)
    page.wait_for_function("document.querySelectorAll('#grid .card').length === 3", timeout=60_000)
    if page.query_selector_all(".step"):
        assert not page.is_disabled(".step[data-step='2']"), "step2 should be enabled after upload"
    print("upload -> step2 ok, cards:", page.eval_on_selector_all("#grid .card", "els => els.length"))

    # convert -> step3
    page.click("#convertBtn")
    page.wait_for_selector("#resultPanel:not(.hidden)", timeout=300_000)
    job_id = page.evaluate("state.jobId")
    print("convert -> step3 ok, job", job_id)
    title = page.inner_text("#readTitle")
    sub = page.inner_text("#readMeta")
    print("reader title:", title, "| meta:", sub)
    assert title.strip(), "reader title empty"
    assert "页" in sub, sub

    # reader: page image loads and paging works
    page.wait_for_function(
        "() => { const i = document.getElementById('readerImg'); return i && i.complete && i.naturalWidth > 200; }",
        timeout=60_000,
    )
    src1 = page.get_attribute("#readerImg", "src")
    print("page1 src:", src1)
    assert "/page/1?" in src1, src1
    total = page.inner_text("#pageTotal")
    print("total:", total)
    assert total.strip().startswith("/"), total

    page.click("#nextBtn")
    page.wait_for_function("() => document.getElementById('pageInput').value === '2'", timeout=30_000)
    page.wait_for_function(
        "() => { const i = document.getElementById('readerImg'); return i && i.complete && i.naturalWidth > 200 && i.src.includes('/page/2?'); }",
        timeout=60_000,
    )
    print("next page ok")
    page.click("#prevBtn")
    page.wait_for_function("() => document.getElementById('pageInput').value === '1'", timeout=30_000)
    print("prev page ok")

    # keyboard paging
    page.click("#readerStage")
    page.keyboard.press("ArrowRight")
    page.wait_for_function("() => document.getElementById('pageInput').value === '2'", timeout=30_000)
    page.keyboard.press("ArrowLeft")
    page.wait_for_function("() => document.getElementById('pageInput').value === '1'", timeout=30_000)
    print("keyboard paging ok")

    # jump via input
    page.fill("#pageInput", "3")
    page.press("#pageInput", "Enter")
    page.wait_for_function("() => document.getElementById('pageInput').value === '3'", timeout=30_000)
    print("page jump ok")

    # fit toggle
    page.click("#fitPBtn")
    assert page.get_attribute("#readerStage", "data-fit") == "p"
    page.click("#fitWBtn")
    assert page.get_attribute("#readerStage", "data-fit") == "w"
    print("fit toggle ok")

    page.screenshot(path=str(shots[1]), full_page=True)

    # step navigation back and forth
    goto_step(page, 2)
    goto_step(page, 3)
    print("step navigation ok")

    # reading history
    page.click("#libBtn")
    page.wait_for_selector("#libModal:not(.hidden)", timeout=10_000)
    page.wait_for_selector(".lib-item", timeout=20_000)
    n_items = page.eval_on_selector_all(".lib-item", "els => els.length")
    print("history items:", n_items)
    assert n_items >= 1, "history list empty after conversion"
    page.screenshot(path=str(shots[2]), full_page=True)
    page.click(".lib-item [data-read]")
    page.wait_for_selector("#resultPanel:not(.hidden)", timeout=10_000)
    page.wait_for_function(
        "() => { const i = document.getElementById('readerImg'); return i && i.complete && i.naturalWidth > 200; }",
        timeout=60_000,
    )
    print("read from history ok")

    # download link resolves
    href = page.get_attribute("#dlPdf", "href")
    if href and href.startswith("/"):
        r = requests.get(BASE + href, timeout=60)
        print("download pdf:", r.status_code, len(r.content))
        assert r.status_code == 200 and r.content[:4] == b"%PDF"

    # --- step 2 editing: preview / rotate / drag reorder (run last, they invalidate results) ---
    goto_step(page, 2)
    first_id = page.eval_on_selector("#grid .card:first-child", "el => el.dataset.id")
    # a real click always jitters a few px: it must still open the preview, not start a drag
    box = page.query_selector("#grid .card:first-child .thumb").bounding_box()
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    page.mouse.down()
    page.mouse.move(cx + 4, cy + 3)
    page.mouse.up()
    page.wait_for_selector("#viewModal:not(.hidden)", timeout=10_000)
    page.wait_for_function(
        "() => { const i = document.getElementById('viewImg'); return i && i.complete && i.naturalWidth > 300; }",
        timeout=60_000,
    )
    assert page.inner_text("#viewSub").startswith("第 1 / 3 张"), page.inner_text("#viewSub")
    page.screenshot(path=str(shots[3]), full_page=True)
    print("viewer opened:", page.inner_text("#viewSub"))

    page.click("#viewNext")
    page.wait_for_function("() => document.getElementById('viewSub').textContent.indexOf('第 2 / 3 张') === 0", timeout=10_000)
    page.click("#viewPrev")
    page.wait_for_function("() => document.getElementById('viewSub').textContent.indexOf('第 1 / 3 张') === 0", timeout=10_000)
    page.click("#rotCw")
    page.wait_for_function("() => document.getElementById('viewSub').textContent.indexOf('已旋转 90') > 0", timeout=30_000)
    assert "_r90" in page.get_attribute("#grid .card:first-child img", "src"), "grid thumb not refreshed"
    page.keyboard.press("Escape")
    page.wait_for_selector("#viewModal.hidden", state="attached", timeout=10_000)
    print("rotate + arrows + esc ok")

    ids_before = page.eval_on_selector_all("#grid .card", "els => els.map(e => e.dataset.id)")
    box = page.query_selector("#grid .card:nth-child(3) .grip").bounding_box()
    tgt = page.query_selector("#grid .card:first-child").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + 20, box["y"] + 20, steps=5)
    page.mouse.move(tgt["x"] + tgt["width"] / 2, tgt["y"] + tgt["height"] / 2, steps=15)
    page.mouse.up()
    page.wait_for_function(
        "ids => document.querySelector('#grid .card').dataset.id === ids", arg=ids_before[2], timeout=10_000
    )
    ids_after = page.eval_on_selector_all("#grid .card", "els => els.map(e => e.dataset.id)")
    assert ids_after == [ids_before[2], ids_before[0], ids_before[1]], (ids_before, ids_after)
    print("drag reorder ok:", ids_after)

    j = requests.get(f"{BASE}/api/job/{job_id}", timeout=30).json()
    assert [p["rotate"] for p in j["pages"]] == [0, 90, 0], [p.get("rotate") for p in j["pages"]]
    assert [p["id"] for p in j["pages"]] == ids_after, "server order not saved"
    print("server state after edit ok")

    browser.close()
    return job_id


def main() -> int:
    before = snapshot_ids()
    job_id = None
    try:
        with sync_playwright() as pw:
            job_id = run(pw)
    finally:
        cleanup(job_id, before)

    real_errors = [e for e in errors if "favicon" not in e]
    if real_errors:
        print("CONSOLE ERRORS:")
        for e in real_errors:
            print("  -", e)
        return 1
    print("UI E2E DONE")
    return 0


if __name__ == "__main__":
    rc = main()
    print("rc", rc)
    sys.exit(rc)
