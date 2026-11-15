#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""十本章可看性图：堆叠四问 + 双权重名次"""
import json, os
from PIL import Image, ImageDraw, ImageFont

J = json.load(open(os.path.join(os.environ["TEMP"], "ten_rank.json"), encoding="utf-8"))
rows = J["A"]
rankB = {r["name"]: i + 1 for i, r in enumerate(J["B"])}
OUT = r"G:\txt\output\八本书_十本章可看性.png"

def font(size, bold=False):
    c = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]
    for p in c:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

W, H = 1680, 1020
img = Image.new("RGB", (W, H), (250, 250, 248))
d = ImageDraw.Draw(img)
f_t, f_s, f_n, f_v, f_l = font(40, True), font(21), font(21), font(24, True), font(19)

d.text((56, 34), "八本网文 · 前 10 章 可看性四问", font=f_t, fill=(30, 30, 34))
d.text((56, 90), "每本 2.1–4.7 万字　｜　左：均衡权重(30/25/25/20)　右：门槛优先(35/30/20/15)　｜　条最长的四项越靠左，门槛越低",
       font=f_s, fill=(110, 110, 118))

QCOL = {"q1": (74, 132, 190), "q2": (98, 168, 152), "q3": (214, 150, 58), "q4": (168, 118, 186)}
QLAB = {"q1": "Q1 进得去", "q2": "Q2 跟得上", "q3": "Q3 有看点", "q4": "Q4 想追"}
WTS = {"q1": 0.30, "q2": 0.25, "q3": 0.25, "q4": 0.20}

left, right = 430, W - 300
top, rowh = 180, 92
scale = (right - left) / 10.0

for t in range(0, 11):
    px = left + t * scale
    d.line([px, top - 12, px, top + rowh * len(rows) - 58], fill=(232, 232, 236), width=1)
    d.text((px - 6, top + rowh * len(rows) - 52), str(t), font=f_l, fill=(140, 140, 146))

for i, r in enumerate(rows):
    y = top + i * rowh
    d.text((56, y + 4), f"{i+1}. {r['name']}", font=f_n, fill=(40, 40, 46))
    d.text((56, y + 36), f"{r['chars']/10000:.1f}万字 / 10章", font=f_l, fill=(135, 135, 142))
    x = left
    for q in ("q1", "q2", "q3", "q4"):
        seg = r[q] * WTS[q] * scale
        d.rectangle([x, y + 14, x + seg, y + 50], fill=QCOL[q])
        if seg > 34:
            d.text((x + 7, y + 18), str(r[q]), font=f_l, fill=(255, 255, 255))
        x += seg
    d.text((right + 16, y + 14), f"{r['A']:.2f}", font=f_v, fill=(35, 35, 40))
    rb = rankB[r["name"]]
    arrow = "" if rb == i + 1 else ("  ↑" if rb < i + 1 else "  ↓")
    d.text((right + 110, y + 20), f"B名次 {rb}{arrow}", font=f_l, fill=(120, 120, 128))

lx, ly = left, H - 76
for q in ("q1", "q2", "q3", "q4"):
    d.rectangle([lx, ly, lx + 22, ly + 22], fill=QCOL[q])
    d.text((lx + 30, ly - 1), QLAB[q], font=f_l, fill=(80, 80, 88))
    lx += 200
d.text((56, H - 34), "B 名次＝把门槛权重调高后的名次；↑↓ 表示两套权重下位次变化。分数为四问人工判定 + 脚本加权。",
       font=f_l, fill=(140, 140, 146))

img.save(OUT)
print("saved", OUT)
