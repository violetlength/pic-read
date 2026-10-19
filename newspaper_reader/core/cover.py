from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .layout import Block


@dataclass
class IssueInfo:
    title: str = ""
    issue_no: str = ""
    date: str = ""
    edition: str = ""
    page_count: str = ""
    raw: str = ""
    is_cover: bool = False
    page_label: str = ""


_ISSUE_RE = re.compile(r"第\s*([0-9０-９]{1,6})\s*期")
_DATE_RE = re.compile(
    r"([0-9０-９]{2,4})\s*年\s*([0-9０-９]{1,2})\s*月\s*([0-9０-９]{1,2})\s*日?"
)
_DATE_YM_RE = re.compile(r"([0-9０-９]{2,4})\s*年\s*([0-9０-９]{1,2})\s*月")
_PAGES_RE = re.compile(r"本期\s*([0-9０-９]{1,3})\s*版")
_PAGE_LABEL_RE = re.compile(r"第\s*([0-9A-Za-z]{1,3})\s*版")
_CN_NUM = "零一二三四五六七八九"


def _norm_digits(s: str) -> str:
    tbl = str.maketrans("０１２３４５６７８９", "0123456789")
    return s.translate(tbl)


def _clean(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _word_join(words) -> str:
    """Cluster OCR words into text lines (baseline tolerant) and join them."""
    if not words:
        return ""
    ws = sorted(words, key=lambda w: ((w.y0 + w.y1) / 2.0, w.x0))
    heights = sorted(w.h for w in ws)
    tol = max(6.0, heights[len(heights) // 2] * 0.6)
    lines: List[dict] = []
    for w in ws:
        cy = (w.y0 + w.y1) / 2.0
        if lines and abs(cy - lines[-1]["cy"]) <= tol:
            lines[-1]["ws"].append(w)
            lines[-1]["cy"] = (lines[-1]["cy"] * lines[-1]["n"] + cy) / (lines[-1]["n"] + 1)
            lines[-1]["n"] += 1
        else:
            lines.append({"cy": cy, "ws": [w], "n": 1})
    out: List[str] = []
    for ln in lines:
        out.append("".join(w.text for w in sorted(ln["ws"], key=lambda w: w.x0)))
    return re.sub(r"\s+", "", "".join(out))


def parse_cover(blocks: List[Block], words=None) -> IssueInfo:
    info = IssueInfo()
    if not blocks:
        return info

    ordered = sorted(blocks, key=lambda b: (round(b.y0 / 24.0), b.x0))
    joined = "".join(b.text for b in ordered)
    joined_flat = re.sub(r"\s+", "", joined)
    # finer-grained fallback: blocks can split the date line in the wrong order
    alt = _word_join(words) if words else ""
    info.raw = joined_flat[:400]

    m = _ISSUE_RE.search(joined_flat)
    if not m:
        m = re.search(r"第?([0-9０-９]{3,6})\s*期", joined_flat)
    if not m and alt:
        m = _ISSUE_RE.search(alt) or re.search(r"第?([0-9０-９]{3,6})\s*期", alt)
    if m:
        info.issue_no = _norm_digits(m.group(1))

    m = _DATE_RE.search(joined_flat)
    if not m and alt:
        m = _DATE_RE.search(alt)
    if m:
        y, mo, d = _norm_digits(m.group(1)), _norm_digits(m.group(2)), _norm_digits(m.group(3))
        info.date = f"{y}-{int(mo):02d}-{int(d):02d}"
    else:
        m = _DATE_YM_RE.search(joined_flat)
        if not m and alt:
            m = _DATE_YM_RE.search(alt)
        if m:
            y, mo = _norm_digits(m.group(1)), _norm_digits(m.group(2))
            info.date = f"{y}-{int(mo):02d}"

    m = _PAGES_RE.search(joined_flat)
    if m:
        info.page_count = _norm_digits(m.group(1))

    m = _PAGE_LABEL_RE.search(joined_flat)
    if m:
        info.page_label = _norm_digits(m.group(1))

    cand = [b for b in blocks if b.size >= 18 or b.kind == "title"]
    cand.sort(key=lambda b: (-b.size, b.y0))

    max_size = max((b.size for b in blocks), default=0.0)
    page_h = max((b.y1 for b in blocks), default=100.0)
    top_h = max(30.0, page_h * 0.30)
    big_top = [b for b in blocks if b.y0 < top_h and b.size >= max(18.0, max_size * 0.75)]
    big_top.sort(key=lambda b: (-b.size, b.y0))
    title_src = big_top or cand
    for b in title_src:
        t = _clean(b.text)
        if len(t) < 2 or len(t) > 12:
            continue
        if re.fullmatch(r"[0-9A-Za-z\.\-·、，,]+", t):
            continue
        if _ISSUE_RE.fullmatch(t) or _DATE_RE.fullmatch(t):
            continue
        if any(k in t for k in ("国内统一", "邮发代号", "出版", "主办", "本期", "本报记者")):
            continue
        info.title = t
        break

    title_score = 0
    if info.title:
        title_score = 2
        if big_top and big_top[0].size >= max_size * 0.8 and max_size >= 24:
            title_score = 3

    score = title_score
    if info.issue_no:
        score += 3
    if info.date:
        score += 1
    if info.page_count:
        score += 1
    info.is_cover = score >= 4

    if not info.page_label:
        m = re.search(r"[A-Za-z]?\s*([0-9]{1,2})\s*$", _clean(joined_flat[:80]))
        if m:
            info.page_label = m.group(1)

    return info


def group_issues(pages: List[dict]) -> List[dict]:
    issues: List[dict] = []
    current: Optional[dict] = None

    for idx, pg in enumerate(pages):
        info: IssueInfo = pg.get("info") or IssueInfo()
        if info.is_cover or current is None:
            current = {
                "title": info.title or (issues[-1]["title"] if issues else ""),
                "issue_no": info.issue_no,
                "date": info.date,
                "edition": info.edition,
                "page_count": info.page_count,
                "pages": [],
            }
            issues.append(current)
        if info.is_cover:
            current["title"] = info.title or current["title"]
            current["issue_no"] = info.issue_no or current["issue_no"]
            current["date"] = info.date or current["date"]
            current["page_count"] = info.page_count or current["page_count"]
            current["edition"] = info.edition or current["edition"]
        current["pages"].append(idx)

    if not issues:
        issues = [{"title": "", "issue_no": "", "date": "", "edition": "", "page_count": "", "pages": list(range(len(pages)))}]
    return issues


def page_label_for(pg: dict, issue: dict, pos: int) -> str:
    info = pg.get("info") or IssueInfo()
    if info.page_label:
        return info.page_label
    return str(pos + 1)
