from __future__ import annotations

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path(__file__).resolve().parent / "pages"
OUT.mkdir(parents=True, exist_ok=True)

HEI = r"C:\Windows\Fonts\msyh.ttc"
HEI_BD = r"C:\Windows\Fonts\msyhbd.ttc"
SONG = r"C:\Windows\Fonts\simsun.ttc"
KAI = r"C:\Windows\Fonts\simkai.ttf"

W, H = 1400, 1980


def f(path, size):
    return ImageFont.truetype(path, size)


def draw_photo(im: ImageDraw.ImageDraw, box, seed: int, label: str = ""):
    x0, y0, x1, y1 = box
    rnd = random.Random(seed)
    base = (rnd.randint(70, 210), rnd.randint(70, 200), rnd.randint(70, 200))
    im.rectangle(box, fill=base)
    for _ in range(140):
        cx, cy = rnd.randint(x0, x1), rnd.randint(y0, y1)
        r = rnd.randint(4, max(6, (x1 - x0) // 8))
        col = (
            min(255, base[0] + rnd.randint(-60, 60)),
            min(255, base[1] + rnd.randint(-60, 60)),
            min(255, base[2] + rnd.randint(-60, 60)),
        )
        im.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
    im.rectangle(box, outline=(120, 110, 100), width=2)
    if label:
        im.text((x0 + 8, y0 + 6), label, font=f(KAI, 20), fill=(255, 255, 255))


def make_cover(path: Path, issue: int, date: str, title: str = "阳光少年报"):
    im = Image.new("RGB", (W, H), (252, 250, 244))
    d = ImageDraw.Draw(im)

    d.rectangle([0, 0, W, 170], fill=(246, 238, 222))
    d.text((60, 36), title, font=f(HEI_BD, 104), fill=(32, 118, 205))
    d.text((70, 145), "学做人 学立志 学创造", font=f(SONG, 26), fill=(90, 80, 66))
    d.line([0, 172, W, 172], fill=(30, 30, 30), width=5)

    d.text((60, 190), f"第{issue}期", font=f(HEI, 34), fill=(140, 47, 30))
    d.text((240, 190), date, font=f(HEI, 34), fill=(140, 47, 30))
    d.text((520, 196), "本期16版", font=f(SONG, 26), fill=(90, 80, 66))
    d.text((60, 240), "国内统一连续出版物号：CN41-0111  邮发代号：35-666", font=f(SONG, 22), fill=(110, 100, 88))

    draw_photo(d, (60, 300, 700, 900), seed=issue, label="配图1")
    draw_photo(d, (740, 300, 1340, 780), seed=issue + 1, label="配图2")

    d.rectangle([60, 930, 1340, 1130], fill=(255, 252, 240), outline=(30, 30, 30), width=3)
    d.text((90, 960), "亚运会赛场上，中国小将绽放光芒", font=f(HEI_BD, 58), fill=(20, 60, 120))
    d.text((90, 1040), "多名年轻选手摘金夺银，展现拼搏精神", font=f(KAI, 34), fill=(60, 55, 50))

    heads = [
        ("中国", "种草，也写进了国家规划？", "P04"),
        ("世界", "这场大赛，真是行行出状元", "P10"),
        ("文化", "云肩，古人肩膀上的时装秀", "P12"),
        ("科学", "霸王龙测体温竟然靠牙齿", "P14"),
    ]
    for i, (cat, head, pg) in enumerate(heads):
        x = 60 + (i % 2) * 650
        y = 1170 + (i // 2) * 220
        d.rectangle([x, y, x + 610, y + 190], fill=(248, 244, 232), outline=(200, 190, 170), width=2)
        d.rectangle([x + 16, y + 16, x + 110, y + 56], fill=(60, 140, 90))
        d.text((x + 30, y + 22), cat, font=f(HEI, 26), fill=(255, 255, 255))
        d.text((x + 500, y + 20), pg, font=f(SONG, 24), fill=(140, 47, 30))
        for j, part in enumerate([head[j * 11 : (j + 1) * 11] for j in range(2)]):
            if part:
                d.text((x + 24, y + 74 + j * 52), part, font=f(HEI, 42), fill=(30, 30, 30))

    d.text((60, H - 46), "主管：河南广播电视台  主办：河南大象客户端有限公司", font=f(SONG, 20), fill=(120, 110, 98))
    im.save(path)
    return path


def make_inner(path: Path, seed: int, page_no: str):
    random.seed(seed)
    im = Image.new("RGB", (W, H), (253, 252, 248))
    d = ImageDraw.Draw(im)

    d.text((60, 40), "阳光少年报", font=f(HEI, 34), fill=(32, 118, 205))
    d.text((1080, 46), f"第{page_no}版", font=f(SONG, 26), fill=(90, 80, 66))
    d.line([60, 92, W - 60, 92], fill=(30, 30, 30), width=3)

    title = [
        "科技馆新展亮相，孩子们亲手做实验",
        "校园足球联赛开幕，小球员斗志昂扬",
        "古寺里的千年银杏，秋天披上金甲",
        "机器人走进课堂，和同学一起上课",
        "少年气象员记录天气，坚持一整年",
    ][seed % 5]
    d.text((70, 112), title, font=f(HEI_BD, 54), fill=(25, 25, 25))
    d.text((70, 182), f"本报记者 报道  ·  摄影 视觉中心", font=f(SONG, 24), fill=(110, 100, 88))

    body = (
        "昨天上午，市科技馆新展区正式开放，许多同学一大早就来排队。展厅里摆着可以动手操作的装置，"
        "大家在讲解员的带领下完成了小实验，明白了声音是怎样传播的。带队老师说，这样的活动能激发同学们"
        "对科学的兴趣，希望大家回家后继续观察身边的现象，把发现记录在科学笔记上。"
        "下午的交流环节中，几位同学还分享了自己的小发明，现场气氛十分热烈。"
        "工作人员表示，新展将持续到年底，周末会增加场次，方便更多孩子前来参观体验。"
    )
    para = [body[i : i + 22] for i in range(0, len(body), 22)]

    photos = [(70, 240, 640, 640), (700, 240, 1330, 560)]
    for i, box in enumerate(photos):
        draw_photo(d, box, seed=seed * 10 + i, label=f"图{i + 1}")

    cols = 3
    col_w = 400
    gap = 30
    y_start = 700
    for c in range(cols):
        x = 70 + c * (col_w + gap)
        y = y_start
        random.seed(seed * 100 + c)
        lines = []
        for p in para:
            lines.extend([p[j : j + 15] for j in range(0, len(p), 15)])
        for ln in lines:
            if y > H - 90:
                break
            d.text((x, y), ln, font=f(SONG, 27), fill=(25, 25, 25))
            y += 38
        d.line([x, y_start - 16, x + col_w - 20, y_start - 16], fill=(210, 200, 180), width=1)

    side_head = "小知识：银杏为什么会变黄"
    d.rectangle([70, H - 250, W - 70, H - 70], fill=(246, 240, 226), outline=(190, 180, 160), width=2)
    d.text((90, H - 226), side_head, font=f(HEI, 34), fill=(140, 47, 30))
    txt = "秋天叶子变黄，是因为叶绿素分解后，原本被遮住的黄色色素显现了出来。"
    d.text((90, H - 176), txt[:24], font=f(KAI, 28), fill=(40, 38, 34))
    d.text((90, H - 136), txt[24:], font=f(KAI, 28), fill=(40, 38, 34))

    im.save(path)
    return path


if __name__ == "__main__":
    make_cover(OUT / "001_cover_379.png", 379, "2026年10月8日")
    for i, pno in enumerate(["2", "3", "4", "5"], start=1):
        make_inner(OUT / f"{i + 1:03d}_p{pno}.png", seed=i, page_no=pno)
    make_cover(OUT / "006_cover_380.png", 380, "2026年10月15日")
    make_inner(OUT / "007_p2.png", seed=7, page_no="2")
    print("generated", len(list(OUT.glob('*.png'))), "pages ->", OUT)
