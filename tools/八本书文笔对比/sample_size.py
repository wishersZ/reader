#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""样本量与段落字数分布分析

A. 收敛分析：按章递增取样，看各指标何时稳定（判断"几章够用"）
B. 段落分布：段长分桶、变异、连续同长度游程（判断"每段字数"结构）

用法: python sample_size.py <outdir> <file...>
"""
import os
import re
import sys
import json
import statistics as st
from collections import Counter

HEAD = re.compile(r"^[\s\u3000]*(?:={2,})?\s*第\s*[0-9零一二三四五六七八九十百]+\s*[章节回]")
CJK = re.compile(r"[\u4e00-\u9fff]")
SENT = re.compile(r"[^。！？…]+[。！？…]*")
TAG = re.compile(r"【[^】]{1,24}】")
BUCKETS = [(1, 10), (11, 20), (21, 30), (31, 50), (51, 100), (101, 10**9)]
BUCKET_LAB = ["1-10", "11-20", "21-30", "31-50", "51-100", "100+"]


def read(path):
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return open(path, encoding=enc).read()
        except (UnicodeDecodeError, LookupError):
            pass
    return open(path, encoding="utf-8", errors="replace").read()


def clen(s):
    return len(re.sub(r"\s", "", s))


def split_chapters(text):
    lines = text.splitlines()
    idx = [i for i, l in enumerate(lines) if HEAD.match(l)]
    if not idx:
        return [("全文", lines)]
    idx.append(len(lines))
    return [(lines[idx[i]].strip(), lines[idx[i] + 1: idx[i + 1]]) for i in range(len(idx) - 1)]


def para_stats(paras):
    lens = [clen(p) for p in paras if clen(p) > 0]
    if not lens:
        return None
    mean = st.mean(lens)
    hist = []
    for lo, hi in BUCKETS:
        hist.append(round(100.0 * sum(1 for x in lens if lo <= x <= hi) / len(lens), 1))
    # 最长"同长度"游程（按 5 字分档）
    bins = [x // 5 for x in lens]
    best = cur = 1
    for a, b in zip(bins, bins[1:]):
        cur = cur + 1 if a == b else 1
        best = max(best, cur)
    single = sum(1 for p in paras if len(SENT.findall(p)) <= 1)
    return dict(n=len(lens), mean=round(mean, 1), med=round(st.median(lens), 1),
                sd=round(st.pstdev(lens), 1) if len(lens) > 1 else 0,
                cv=round(st.pstdev(lens) / mean, 2) if len(lens) > 1 and mean else 0,
                hist=hist, single=round(100.0 * single / len(paras), 1), run=best)


def ch_metrics(lines):
    paras = [l.strip().strip("\u3000").strip() for l in lines]
    paras = [p for p in paras if p]
    body = "".join(paras)
    chars = clen(body)
    if chars < 300:
        return None
    ps = para_stats(paras)
    sents = [len(m.group(0).strip()) for p in paras for m in SENT.finditer(p)]
    tags = len(TAG.findall(body))
    return dict(段均=ps["mean"], 句均=round(st.mean(sents), 1) if sents else 0,
                对话=round(100.0 * sum(1 for p in paras if p[0] in '“"「') / len(paras), 1),
                术语=round(tags * 1000.0 / chars, 2), 字数=chars)


def converge(seq, label, tol):
    """返回：达到 ±tol 相对误差所需章数（以最终均值为真值）"""
    if len(seq) < 5:
        return None
    final = st.mean(seq)
    if final == 0:
        return None
    need = None
    for n in range(1, len(seq) + 1):
        run = st.mean(seq[:n])
        if abs(run - final) / abs(final) <= tol:
            need = n
            break
    return need


def main():
    if len(sys.argv) < 3:
        sys.exit("用法: sample_size.py <outdir> <file...>")
    outdir, files = sys.argv[1], sys.argv[2:]
    os.makedirs(outdir, exist_ok=True)
    report = {}

    print("=" * 96)
    print("A. 收敛分析：几章才够（相对最终均值，误差 ±10% / ±5%）")
    print("=" * 96)
    print(f"{'书':<22}{'章数':>5}{'段均±10%':>10}{'句均±10%':>10}{'对话±10%':>10}{'术语±10%':>10}{'段均±5%':>9}{'句均±5%':>9}")
    for path in files:
        name = re.sub(r"_第?一?部分$|_第1卷.*$", "", os.path.splitext(os.path.basename(path))[0])
        chs = split_chapters(read(path))
        rows = [m for m in (ch_metrics(b) for _, b in chs) if m]
        if len(rows) < 6:
            print(f"{name:<22}{len(rows):>5}  章数不足")
            continue
        d = {k: [r[k] for r in rows] for k in ("段均", "句均", "对话", "术语")}
        n10 = {k: converge(v, k, 0.10) for k, v in d.items()}
        n05 = {k: converge(v, k, 0.05) for k, v in d.items()}
        print(f"{name:<22}{len(rows):>5}{n10['段均'] or '-':>10}{n10['句均'] or '-':>10}"
              f"{n10['对话'] or '-':>10}{n10['术语'] or '-':>10}{n05['段均'] or '-':>9}{n05['句均'] or '-':>9}")
        report[name] = dict(chapters=len(rows), converge10=n10, converge05=n05,
                            within_sd={k: round(st.pstdev(v), 2) for k, v in d.items()},
                            means={k: round(st.mean(v), 2) for k, v in d.items()})

    print()
    print("=" * 96)
    print("B. 段落字数分布（前三章；占比 %）")
    print("=" * 96)
    print(f"{'书':<22}{'段数':>5}{'段均':>6}{'中位':>6}{'SD':>6}{'CV':>6}"
          + "".join(f"{b:>8}" for b in BUCKET_LAB) + f"{'一句一段%':>9}{'同长游程':>8}")
    dist = {}
    for path in files:
        name = re.sub(r"_第?一?部分$|_第1卷.*$", "", os.path.splitext(os.path.basename(path))[0])
        chs = split_chapters(read(path))
        first3 = [b for _, b in chs[:3]]
        paras = [p.strip() for blk in first3 for p in blk if p.strip()]
        ps = para_stats(paras)
        if not ps:
            continue
        dist[name] = ps
        print(f"{name:<22}{ps['n']:>5}{ps['mean']:>6}{ps['med']:>6}{ps['sd']:>6}{ps['cv']:>6}"
              + "".join(f"{h:>8}" for h in ps["hist"]) + f"{ps['single']:>9}{ps['run']:>8}")

    json.dump(dict(converge=report, para=dist),
              open(os.path.join(outdir, "sample_para.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print(f"\nJSON: {os.path.join(outdir, 'sample_para.json')}")


if __name__ == "__main__":
    main()
