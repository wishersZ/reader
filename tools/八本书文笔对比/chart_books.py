#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画文笔总分对比图（PIL）"""
import json, os
from PIL import Image, ImageDraw, ImageFont

rows = json.load(open(os.path.join(os.environ["TEMP"], "prose_rank.json"), encoding="utf-8"))
out_png = os.path.join(r"D:\_tmp_chart.png") if os.path.isdir("D:\\") else "chart.png"

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\SimSun.ttc",
]
def font(size, bold=False):
    order = ([r"C:\Windows\Fonts\msyhbd.ttc"] if bold else []) + FONT_CANDIDATES
    for p in order:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()

W, H = 1680, 980
BG = (250, 250, 248)
img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

f_title = font(40, True)
f_sub = font(22)
f_name = font(25)
f_val = font(26, True)
f_small = font(20)

d.text((60, 40), "八本书 · 前三章 文笔总分对比", font=f_title, fill=(30, 30, 34))
d.text((60, 96), "P = 0.4×可读性R + 0.6×吸引力A　｜　满分 10　｜　竖虚线为分档线：5.5 合格 / 7.0 成熟 / 8.5 有风格", font=f_sub, fill=(110, 110, 118))

left, right = 430, W - 300
top, rowh = 175, 92
scale = (right - left) / 10.0

# 分档背景
bands = [(0, 5.5, (246, 240, 240)), (5.5, 7.0, (248, 246, 238)), (7.0, 8.5, (240, 246, 240)), (8.5, 10, (232, 244, 236))]
for lo, hi, col in bands:
    d.rectangle([left + lo * scale, top - 34, left + hi * scale, top + rowh * len(rows) - 18], fill=col)
for x in (5.5, 7.0, 8.5):
    px = left + x * scale
    for yy in range(top - 34, top + rowh * len(rows) - 18, 12):
        d.line([px, yy, px, yy + 6], fill=(190, 190, 196), width=2)

# 刻度
for t in range(0, 11):
    px = left + t * scale
    d.line([px, top + rowh * len(rows) - 18, px, top + rowh * len(rows) - 6], fill=(150, 150, 156), width=2)
    d.text((px - 8, top + rowh * len(rows) - 2), str(t), font=f_small, fill=(120, 120, 126))

def color_for(p):
    if p >= 8.5: return (52, 140, 92)
    if p >= 7.0: return (74, 132, 190)
    if p >= 5.5: return (214, 150, 58)
    return (196, 92, 92)

for i, r in enumerate(rows):
    y = top + i * rowh
    name = r["name"]
    if len(name) > 12:
        name = name[:12] + "…"
    d.text((60, y + 6), f"{i+1}. {name}", font=f_name, fill=(40, 40, 46))
    d.text((60, y + 40), r["plat"], font=f_small, fill=(130, 130, 138))

    bar_h = 34
    w = max(r["P"] * scale, 3)
    d.rounded_rectangle([left, y + 8, left + w, y + 8 + bar_h], radius=6, fill=color_for(r["P"]))
    d.text((left + w + 12, y + 10), f"{r['P']:.2f}", font=f_val, fill=(40, 40, 46))
    d.text((right + 74, y + 14), f"R {r['R']:.1f}", font=f_small, fill=(90, 90, 98))
    d.text((right + 74, y + 40), f"A {r['A']:.1f}", font=f_small, fill=(90, 90, 98))

d.text((60, H - 58), "注：分数为八维人工判定后按公式合成；R/A 由脚本计算，避免手算误差。文笔分≠好看程度。", font=f_small, fill=(140, 140, 146))

img.save(out_png, quality=95)
print("saved:", out_png, img.size)
