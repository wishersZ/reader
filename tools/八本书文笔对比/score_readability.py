#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网文可看性四问打分（Q1 进得去 / Q2 跟得上 / Q3 有看点 / Q4 想追）"""
import io, json, os

# Q1 进得去(30%) Q2 跟得上(25%) Q3 有看点(25%) Q4 想追(20%)
DATA = [
    ("带着火影重生日本东京",   8, 7, 7, 7, "霸凌/割腕原主，忍术反击"),
    ("反派少爷只想过佛系生活", 7, 6, 8, 8, "我是注定惨死的反派，得苟住"),
    ("我在东京教剑道",         8, 7, 6, 6, "卖道场换钱 vs 妹妹不让"),
    ("混沌冠冕",               7, 6, 6, 5, "杀人有快感，四神选中他"),
    ("带着写轮眼降临东京",     7, 6, 4, 5, "穿越带写轮眼，关不掉"),
    ("从全面战争开始爆兵反清", 7, 6, 3, 5, "40把来复枪打冷兵器清兵"),
    ("从纯血龙族开始不做人",   4, 3, 7, 5, "三章换三个世界，未交代"),
    ("这个巫师他就不科学",     2, 4, 3, 3, "术语开场，目标只有'变强'"),
]
W = (0.30, 0.25, 0.25, 0.20)

rows = []
for name, q1, q2, q3, q4, hook in DATA:
    total = q1 * W[0] + q2 * W[1] + q3 * W[2] + q4 * W[3]
    rows.append(dict(name=name, q1=q1, q2=q2, q3=q3, q4=q4, T=round(total, 2), hook=hook,
                     weak=min([("Q1", q1), ("Q2", q2), ("Q3", q3), ("Q4", q4)], key=lambda x: x[1])[0]))
rows.sort(key=lambda r: -r["T"])

buf = io.StringIO()
buf.write(f"{'#':<3}{'书名':<24}{'可看性':>7}{'Q1':>4}{'Q2':>4}{'Q3':>4}{'Q4':>4}  卡在哪\n")
for i, r in enumerate(rows, 1):
    buf.write(f"{i:<3}{r['name']:<24}{r['T']:>7}{r['q1']:>4}{r['q2']:>4}{r['q3']:>4}{r['q4']:>4}  {r['weak']}\n")
print(buf.getvalue())
json.dump(rows, open(os.path.join(os.environ["TEMP"], "readability_rank.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
