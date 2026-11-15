#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""八本书前三章 · 文笔打分与排序（分数由人判，算术由脚本算）"""
import io, json, os

# 八维打分：S1句负荷 S2段负荷 S3信息密度 | S4画面 S5感官 S6节奏 S7人声 S8质地
DATA = [
    # 书名, S1, S2, S3, S4, S5, S6, S7, S8, 平台/频道
    ("从纯血龙族开始不做人", 7.5, 7.5, 8.0, 8.5, 8.0, 8.0, 8.5, 8.5, "同人·龙族/柯南"),
    ("这个巫师他就不科学",   9.2, 8.8, 7.5, 7.0, 7.0, 7.5, 7.5, 7.3, "巫师流·番茄向"),
    ("混沌冠冕",             6.0, 6.5, 6.0, 8.5, 8.5, 8.5, 6.5, 7.5, "西幻·起点向"),
    ("我在东京教剑道",       6.5, 7.0, 6.5, 7.5, 7.5, 7.5, 7.5, 8.0, "东京流·起点向"),
    ("带着火影重生日本东京", 6.5, 6.5, 6.5, 7.5, 7.5, 7.5, 7.0, 7.0, "同人·东京流"),
    ("反派少爷只想过佛系生活", 8.0, 8.0, 5.5, 6.0, 5.0, 7.5, 6.5, 6.5, "日轻·反派流"),
    ("从全面战争开始爆兵反清", 5.5, 6.0, 6.0, 7.0, 7.0, 5.5, 5.5, 6.5, "军事·历史穿越"),
    ("带着写轮眼降临东京",   6.5, 7.0, 5.5, 5.0, 6.0, 6.5, 6.0, 5.5, "同人·早期作"),
]

rows = []
for name, s1, s2, s3, s4, s5, s6, s7, s8, plat in DATA:
    R = 0.40 * s1 + 0.35 * s2 + 0.25 * s3
    A = 0.30 * s4 + 0.15 * s5 + 0.25 * s6 + 0.20 * s7 + 0.10 * s8
    P = 0.40 * R + 0.60 * A
    if R < 4.0 or A < 4.0:
        P = min(P, 6.0)
    rows.append(dict(name=name, S1=s1, S2=s2, S3=s3, S4=s4, S5=s5, S6=s6, S7=s7, S8=s8,
                     R=round(R, 2), A=round(A, 2), P=round(P, 2), plat=plat))

rows.sort(key=lambda r: (-r["P"], -r["A"]))

out = io.StringIO()
out.write(f"{'名次':<5}{'书名':<26}{'P':>6}{'R':>6}{'A':>6}   {'短板维度'}\n")
dims = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
for i, r in enumerate(rows, 1):
    worst = min(dims, key=lambda d: r[d])
    out.write(f"{i:<5}{r['name']:<26}{r['P']:>6}{r['R']:>6}{r['A']:>6}   {worst}={r[worst]}\n")

out.write("\n--- 八维明细（按总分排序）---\n")
hdr = f"{'书名':<26}" + "".join(f"{d:>6}" for d in dims)
out.write(hdr + "\n")
for r in rows:
    out.write(f"{r['name']:<26}" + "".join(f"{r[d]:>6}" for d in dims) + "\n")

out.write("\n--- 判档 ---\n")
def band(p):
    if p >= 8.5: return "有个人风格"
    if p >= 7.0: return "成熟商业文笔"
    if p >= 5.5: return "合格但平"
    if p >= 4.0: return "有明显毛病"
    return "影响签约"
for r in rows:
    out.write(f"{r['name']:<26}{r['P']:>6}  {band(r['P'])}\n")

print(out.getvalue())
with open(os.path.join(os.environ["TEMP"], "prose_rank.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, ensure_ascii=False, indent=2)
