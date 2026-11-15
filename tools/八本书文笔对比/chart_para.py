#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""段落字数分布图（堆叠条形）"""
import json, os
from PIL import Image, ImageDraw, ImageFont

J = json.load(open(os.path.join(os.environ["TEMP"], "sample_out", "sample_para.json"), encoding="utf-8"))
dist = J["para"]
rows = sorted(dist.items(), key=lambda kv: kv[1]["mean"])
OUT = r"G:\txt\output\八本书_每段字数分布.png"

LAB = ["1-10字", "11-20", "21-30", "31-50", "51-100", "100+"]
COL = [(150, 196, 226), (120, 178, 216), (98, 160, 200), (222, 176, 106), (214, 140, 76), (188, 102, 66)]

def font(size, bold=False):
    c = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]
    for p in c:
        if os.path.exists(p):
            try: return ImageFont.truetype(p, size)
            except Exception: pass
    return ImageFont.load_default()

W, H = 1680, 1010
img = Image.new("RGB", (W, H), (250, 250, 248))
d = ImageDraw.Draw(img)
f_t, f_s, f_n, f_v, f_l = font(40, True), font(21), font(21), font(22, True), font(19)

d.text((56, 36), "每段字数分布（前三章）", font=f_t, fill=(30, 30, 34))
d.text((56, 92), "手机竖屏一屏约 5–7 行 × 18–22 字；11–50 字是舒适区，>100 字要滚动。按段均从短到长排序。",
       font=f_s, fill=(110, 110, 118))

left, right = 410, W - 320
top, rowh = 185, 88
scale = (right - left) / 100.0

for i, (name, s) in enumerate(rows):
    y = top + i * rowh
    nm = name if len(name) <= 12 else name[:12] + "…"
    d.text((56, y + 12), nm, font=f_n, fill=(40, 40, 46))
    d.text((56, y + 44), f"段均 {s['mean']}", font=f_l, fill=(130, 130, 138))
    x = left
    for pct, col in zip(s["hist"], COL):
        seg = pct * scale
        if seg > 0:
            d.rectangle([x, y + 8, x + seg, y + 62], fill=col)
            if seg > 42:
                d.text((x + 7, y + 24), f"{pct:.0f}", font=f_l, fill=(255, 255, 255))
        x += seg
    d.text((right + 14, y + 12), f"CV {s['cv']:.2f}", font=f_l, fill=(90, 90, 98))
    d.text((right + 14, y + 40), f"单句段 {s['single']:.0f}%", font=f_l, fill=(90, 90, 98))

# 舒适区参考线（11-50 字累计位置因书而异，这里只画 0/100 轴）
d.line([left, top + rowh * len(rows) - 6, right, top + rowh * len(rows) - 6], fill=(200, 200, 206), width=2)
for t in (0, 25, 50, 75, 100):
    px = left + t * scale
    d.text((px - 8, top + rowh * len(rows) + 2), f"{t}%", font=f_l, fill=(140, 140, 146))

lx, ly = left, H - 78
for lab, col in zip(LAB, COL):
    d.rectangle([lx, ly, lx + 20, ly + 20], fill=col)
    d.text((lx + 26, ly - 2), lab, font=f_l, fill=(80, 80, 88))
    lx += 152
d.text((56, H - 34), "同长游程＝连续几段字数落在同一 5 字档；越大越单调（反派少爷 7 段，最高）。",
       font=f_l, fill=(140, 140, 146))

img.save(OUT)
print("saved", OUT)
