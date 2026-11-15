#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""十本章可看性打分 + 双权重敏感性分析

Q1 进得去 / Q2 跟得上 / Q3 有看点 / Q4 想追
权重A（均衡）: 30/25/25/20
权重B（门槛优先）: 35/30/20/15
"""
import io, json, os

DATA = [
    # 书名, Q1, Q2, Q3, Q4, 十字章字数(实测), 一句话证据
    ("我在东京教剑道", 8, 7, 7, 7, 34688, "极道→三流氓→锦山平太→妹妹，唯一有完整对手链"),
    ("带着火影重生日本东京", 8, 7, 6, 6, 23166, "打脸集中在2/4章，6-10章转日常恋爱"),
    ("反派少爷只想过佛系生活", 7, 6, 6, 6, 21777, "十章一个'指标管理'循环，无外部对手"),
    ("从纯血龙族开始不做人", 4, 5, 8, 7, 21102, "柯南线有实质内容，跳转只发生一次"),
    ("从全面战争开始爆兵反清", 7, 6, 3, 5, 20806, "来复枪碾压后无升级对手，8-9章转伦理说教"),
    ("带着写轮眼降临东京", 7, 6, 3, 4, 26826, "十章全练功日常，第5章末还混进求票"),
    ("混沌冠冕", 5, 5, 4, 5, 46839, "单章4400-5600字，十场无一场对抗胜利"),
    ("这个巫师他就不科学", 2, 4, 5, 5, 23860, "开篇术语墙依旧；但1-6章连续越级击杀"),
]
WA = (0.30, 0.25, 0.25, 0.20)
WB = (0.35, 0.30, 0.20, 0.15)

rows = []
for name, q1, q2, q3, q4, chars, ev in DATA:
    a = q1 * WA[0] + q2 * WA[1] + q3 * WA[2] + q4 * WA[3]
    b = q1 * WB[0] + q2 * WB[1] + q3 * WB[2] + q4 * WB[3]
    rows.append(dict(name=name, q1=q1, q2=q2, q3=q3, q4=q4, chars=chars, ev=ev,
                     A=round(a, 2), B=round(b, 2)))

byA = sorted(rows, key=lambda r: -r["A"])
byB = sorted(rows, key=lambda r: -r["B"])
rankB = {r["name"]: i + 1 for i, r in enumerate(byB)}

buf = io.StringIO()
buf.write(f"{'#':<3}{'书名':<24}{'Q1':>4}{'Q2':>4}{'Q3':>4}{'Q4':>4}{'总分A':>7}{'总分B':>7}{'B名次':>7}\n")
for i, r in enumerate(byA, 1):
    buf.write(f"{i:<3}{r['name']:<24}{r['q1']:>4}{r['q2']:>4}{r['q3']:>4}{r['q4']:>4}"
              f"{r['A']:>7}{r['B']:>7}{rankB[r['name']]:>7}\n")
print(buf.getvalue())
print("--- 门槛优先（权重B）排序 ---")
for i, r in enumerate(byB, 1):
    print(f"{i}. {r['name']:<24}{r['B']}")
json.dump(dict(A=byA, B=byB), open(os.path.join(os.environ["TEMP"], "ten_rank.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
