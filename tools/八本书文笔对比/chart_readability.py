#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画网文可看性四问堆叠图"""
import json, os
from PIL import Image, ImageDraw, ImageFont

rows = json.load(open(os.path.join(os.environ["TEMP"], "readability_rank.json"), encoding="utf-8"))
OUT = r"G:\txt\output\八本书可看性对比.png"

def font(size, bold=False):
    cands = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + [
        r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]
    for p in cands:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

W, H = 1680, 1000
img = Image.new("RGB", (W, H), (250, 250, 248))
d = ImageDraw.Draw(img)
f_t, f_s = font(40, True), font(21)
f_n, f_v, f_l = font(25), font(25, True), font(20)

d.text((60, 38), "八本网文 · 前三章 可看性四问", font=f_t, fill=(30, 30, 34))
d.text((60, 94), "加权：Q1进得去 30% ｜ Q2跟得上 25% ｜ Q3有看点 25% ｜ Q4想追 20%　（越靠左的段越长＝门槛越低）",
       font=f_s, fill=(110, 110, 118))

QCOL = {"q1": (74, 132, 190), "q2": (98, 168, 152), "q3": (214, 150, 58), "q4": (168, 118, 186)}
QLAB = {"q1": "Q1 进得去", "q2": "Q2 跟得上", "q3": "Q3 有看点", "q4": "Q4 想追"}
WTS = {"q1": 0.30, "q2": 0.25, "q3": 0.25, "q4": 0.20}

left, right = 450, W - 230
top, rowh = 190, 92
scale = (right - left) / 10.0

for t in range(0, 11):
    px = left + t * scale
    d.line([px, top - 10, px, top + rowh * len(rows) - 8], fill=(232, 232, 236), width=1)
    d.text((px - 6, top + rowh * len(rows) - 44), str(t), font=f_l, fill=(140, 140, 146))

for i, r in enumerate(rows):
    y = top + i * rowh
    name = r["name"] if len(r["name"]) <= 13 else r["name"][:13] + "…"
    d.text((56, y + 2), f"{i+1}. {name}", font=f_n, fill=(40, 40, 46))
    d.text((56, y + 36), r["hook"], font=f_l, fill=(135, 135, 142))

    x = left
    for q in ("q1", "q2", "q3", "q4"):
        seg = r[q] * WTS[q] * scale
        d.rectangle([x, y + 22, x + seg, y + 58], fill=QCOL[q])
        if seg > 34:
            d.text((x + 8, y + 26), str(r[q]), font=f_l, fill=(255, 255, 255))
        x += seg
    d.text((right + 16, y + 26), f"{r['T']:.2f}", font=f_v, fill=(35, 35, 40))

# 图例
lx, ly = 56, H - 54
for q in ("q1", "q2", "q3", "q4"):
    d.rectangle([lx, ly, lx + 22, ly + 22], fill=QCOL[q])
    d.text((lx + 30, ly - 1), QLAB[q], font=f_l, fill=(80, 80, 88))
    lx += 210
d.text((56, H - 30), "分数为四问人工判定 + 脚本加权；条越长越好，最短那一段就是这书的死穴。", font=f_l, fill=(140, 140, 146))

img.save(OUT)
print("saved", OUT)
