# -*- coding: utf-8 -*-
r"""从“前 10 章切片 + output/<书名>_分析/stats.json”复算 11 本对比的机读指标。

用法：
    py -3 tools\十一本书对比\metrics.py <切片目录> [--out output\十一本书对比\_data\metrics.json]

切片目录由 `tools\八本书文笔对比\extract_n.py <outdir> 10 .\novels\*.txt` 生成，
脚本读取 `<切片目录>/slices/*_前10章.txt`。
"""
import argparse
import glob
import json
import re
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEAD = re.compile(r"^[\s\u3000]*(?:={2,})?\s*第\s*[0-9零一二三四五六七八九十百千万两]+\s*[章节回]")
SENT = re.compile(r"[^。！？…]+[。！？…]*")
TAG = re.compile(r"【[^】]{1,24}】")
BUCKETS = [(1, 10), (11, 20), (21, 30), (31, 50), (51, 100), (101, 10 ** 9)]


def clen(s):
    return len(re.sub(r"\s", "", s))


def para_stats(paras):
    lens = [clen(p) for p in paras if clen(p) > 0]
    if not lens:
        return None
    mean = st.mean(lens)
    hist = [round(100.0 * sum(1 for x in lens if lo <= x <= hi) / len(lens), 1) for lo, hi in BUCKETS]
    bins = [x // 5 for x in lens]
    best = cur = 1
    for a, b in zip(bins, bins[1:]):
        cur = cur + 1 if a == b else 1
        best = max(best, cur)
    single = sum(1 for p in paras if len(SENT.findall(p)) <= 1)
    return dict(
        n=len(lens),
        mean=round(mean, 1),
        med=round(st.median(lens), 1),
        sd=round(st.pstdev(lens), 1) if len(lens) > 1 else 0,
        cv=round(st.pstdev(lens) / mean, 2) if len(lens) > 1 and mean else 0,
        hist=hist,
        single=round(100.0 * single / len(paras), 1),
        run=best,
    )


def canon_books():
    books = []
    for mp in glob.glob(str(ROOT / "output" / "*" / "manifest.json")):
        m = json.loads(Path(mp).read_text(encoding="utf-8"))
        books.append(m["book"])
    return books


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slices", help="切片目录（其下有 slices/*_前10章.txt）")
    ap.add_argument("--out", default=str(ROOT / "output" / "十一本书对比" / "_data" / "metrics.json"))
    args = ap.parse_args()
    slicedir = Path(args.slices) / "slices"
    if not slicedir.is_dir():
        raise SystemExit(f"找不到切片目录：{slicedir}")
    books = canon_books()
    data = {}
    for fp in sorted(slicedir.glob("*_前10章.txt")):
        book = next((b for b in books if b in fp.name), None)
        if not book:
            raise SystemExit(f"切片文件名匹配不到书目：{fp.name}")
        lines = fp.read_text(encoding="utf-8").splitlines()
        idx = [i for i, line in enumerate(lines) if HEAD.match(line)]
        if not idx:
            raise SystemExit(f"切片里没有章标题：{fp.name}")
        idx.append(len(lines))
        chs = []
        for k in range(len(idx) - 1):
            body = lines[idx[k] + 1: idx[k + 1]]
            paras = [p.strip().strip("\u3000").strip() for p in body]
            paras = [p for p in paras if p]
            text = "".join(paras)
            chars = clen(text)
            if chars >= 100:
                chs.append(dict(chars=chars, paras=paras, text=text))
        first10, first3 = chs[:10], chs[:3]
        allparas = [p for c in first10 for p in c["paras"]]
        ps = para_stats(allparas)
        sents = [clen(m.group(0)) for c in first10 for p in c["paras"] for m in SENT.finditer(p)]
        text10 = "".join(c["text"] for c in first10)
        tags = len(TAG.findall(text10))
        chars10 = sum(c["chars"] for c in first10)
        dial = 100.0 * sum(1 for p in allparas if p[0] in '“"「') / len(allparas) if allparas else 0
        longpct = 100.0 * sum(1 for x in sents if x > 40) / len(sents) if sents else 0
        p3 = para_stats([p for c in first3 for p in c["paras"]])
        smp = glob.glob(str(ROOT / "output" / f"{book}_分析" / "stats.json"))
        s = json.loads(Path(smp[0]).read_text(encoding="utf-8")) if smp else {}
        data[book] = dict(
            chapters10=len(first10),
            chars10=chars10,
            chap_mean=round(chars10 / len(first10), 1) if first10 else 0,
            para_mean=ps["mean"] if ps else 0,
            para_sd=ps["sd"] if ps else 0,
            para_cv=ps["cv"] if ps else 0,
            sent_mean=round(st.mean(sents), 1) if sents else 0,
            long_sent_pct=round(longpct, 1),
            dialogue_pct=round(dial, 1),
            tag_per_k=round(tags * 1000.0 / chars10, 2) if chars10 else 0,
            first3_para=p3,
            overall=dict(
                chapters=s.get("totals", {}).get("chapters"),
                mean=s.get("metrics", {}).get("chapter_len", {}).get("mean"),
                sd=s.get("metrics", {}).get("chapter_len", {}).get("stdev"),
                dialogue=s.get("metrics", {}).get("dialogue_para_pct"),
                short=s.get("metrics", {}).get("short_para_pct"),
                hook=s.get("metrics", {}).get("hook_pct"),
            ),
        )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{'书':<34}{'10章':>6}{'字数':>8}{'章均':>8}{'段均':>7}{'句均':>7}{'长句%':>7}{'对话%':>7}{'标签/k':>8}")
    for b, d in data.items():
        print(f"{b:<34}{d['chapters10']:>6}{d['chars10']:>8}{d['chap_mean']:>8}{d['para_mean']:>7}{d['sent_mean']:>7}{d['long_sent_pct']:>7}{d['dialogue_pct']:>7}{d['tag_per_k']:>8}")
    print(f"\n{len(data)} 本 → {out}")


if __name__ == "__main__":
    main()
