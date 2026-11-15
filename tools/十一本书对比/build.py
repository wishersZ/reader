# -*- coding: utf-8 -*-
r"""从 scores.json + metrics.json 生成 11 本对比的 SVG 图表与 Markdown 数据表。

用法：
    py -3 tools\十一本书对比\build.py

输入：
    tools\十一本书对比\scores.json          （11 本四问评分，人工维护）
    output\十一本书对比\_data\metrics.json   （由前 10 章切片与 stats.json 复算）
输出：
    output\十一本书对比\_data\scores.json
    output\十一本书对比\_data\tables.md
    output\十一本书对比\十一本书_可看性对比.svg
    output\十一本书对比\十一本书_十本章可看性.svg
    output\十一本书对比\十一本书_每段字数分布.svg
"""
import html
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
OUT = ROOT / "output" / "十一本书对比"
DATA = OUT / "_data"
WA = (0.30, 0.25, 0.25, 0.20)
WB = (0.35, 0.30, 0.20, 0.15)
QCOL = {"q1": "#4a84be", "q2": "#62a898", "q3": "#d6963a", "q4": "#a876ba"}
QLAB = {"q1": "Q1 进得去", "q2": "Q2 跟得上", "q3": "Q3 有看点", "q4": "Q4 想追"}
WTS = {"q1": WA[0], "q2": WA[1], "q3": WA[2], "q4": WA[3]}


def esc(s):
    return html.escape(str(s))


def short(n, limit=13):
    return n if len(n) <= limit else n[:limit] + "…"


def load():
    scores = json.loads((TOOL / "scores.json").read_text(encoding="utf-8"))
    mpath = DATA / "metrics.json"
    if not mpath.exists():
        raise SystemExit(f"缺少 {mpath}；请先用前 10 章切片复算 metrics.json")
    metrics = json.loads(mpath.read_text(encoding="utf-8"))
    three, ten = scores["three_ch"], scores["ten_ch"]
    for r in three:
        r["T"] = round(r["q1"] * WA[0] + r["q2"] * WA[1] + r["q3"] * WA[2] + r["q4"] * WA[3], 2)
    for r in ten:
        r["A"] = round(r["q1"] * WA[0] + r["q2"] * WA[1] + r["q3"] * WA[2] + r["q4"] * WA[3], 2)
        r["B"] = round(r["q1"] * WB[0] + r["q2"] * WB[1] + r["q3"] * WB[2] + r["q4"] * WB[3], 2)
        r["chars10"] = metrics.get(r["name"], {}).get("chars10")
    three.sort(key=lambda x: (-x["T"], -x["q3"]))
    ten.sort(key=lambda x: (-x["A"], -x["q3"]))
    by_b = sorted(ten, key=lambda x: (-x["B"], -x["q3"]))
    rank_b = {r["name"]: i + 1 for i, r in enumerate(by_b)}
    for i, r in enumerate(three, 1):
        r["rank"] = i
    for i, r in enumerate(ten, 1):
        r["rank"] = i
        r["rankB"] = rank_b[r["name"]]
    return scores, three, ten, metrics


def svg_readability(rows, path, title, subtitle, show_chars=False, show_brank=False):
    rowh, top, W = 92, 190, 1680
    H = top + rowh * len(rows) + 100
    left = 500
    right = 1680 - (330 if show_brank else 250)
    scale = (right - left) / 10.0
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="#fafaf8"/>',
        f'<text x="56" y="66" font-family="Microsoft YaHei, sans-serif" font-size="40" font-weight="bold" fill="#1e1e22">{esc(title)}</text>',
        f'<text x="56" y="110" font-family="Microsoft YaHei, sans-serif" font-size="21" fill="#6e6e76">{esc(subtitle)}</text>',
    ]
    for t in range(11):
        x = left + t * scale
        out.append(f'<line x1="{x:.1f}" y1="{top - 12}" x2="{x:.1f}" y2="{top + rowh * len(rows) - 60}" stroke="#e8e8ec" stroke-width="1"/>')
        out.append(f'<text x="{x - 6:.1f}" y="{top + rowh * len(rows) - 44}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#8c8c92">{t}</text>')
    for i, r in enumerate(rows):
        y = top + i * rowh
        out.append(f'<text x="56" y="{y + 10}" font-family="Microsoft YaHei, sans-serif" font-size="22" fill="#28282e">{i + 1}. {esc(short(r["name"]))}</text>')
        sub = r.get("hook") or r.get("evidence", "")
        out.append(f'<text x="56" y="{y + 44}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#87878e">{esc(sub[:32] + ("…" if len(sub) > 32 else ""))}</text>')
        x = left
        for q in ("q1", "q2", "q3", "q4"):
            seg = r[q] * WTS[q] * scale
            out.append(f'<rect x="{x:.1f}" y="{y + 20}" width="{seg:.1f}" height="36" fill="{QCOL[q]}"/>')
            if seg > 34:
                out.append(f'<text x="{x + 8:.1f}" y="{y + 44}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#ffffff">{r[q]}</text>')
            x += seg
        out.append(f'<text x="{right + 16}" y="{y + 46}" font-family="Microsoft YaHei, sans-serif" font-size="25" font-weight="bold" fill="#232328">{r.get("T", r.get("A")):.2f}</text>')
        if show_chars and r.get("chars10"):
            out.append(f'<text x="{right + 92}" y="{y + 46}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#787880">{r["chars10"] / 10000:.1f}万字</text>')
        if show_brank:
            rb = r["rankB"]
            arrow = "" if rb == i + 1 else (" ↑" if rb < i + 1 else " ↓")
            out.append(f'<text x="{right + 205}" y="{y + 46}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#787880">B名次 {rb}{arrow}</text>')
    lx, ly = left, H - 64
    for q in ("q1", "q2", "q3", "q4"):
        out.append(f'<rect x="{lx}" y="{ly}" width="22" height="22" fill="{QCOL[q]}"/>')
        out.append(f'<text x="{lx + 30}" y="{ly + 18}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#505058">{esc(QLAB[q])}</text>')
        lx += 200
    out.append(f'<text x="56" y="{H - 30}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#8c8c92">分数为四问人工判定 + 脚本加权；条最短的一段就是这书的死穴。</text>')
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")


def svg_para(metrics, path):
    rows = sorted(metrics.items(), key=lambda kv: kv[1]["first3_para"]["mean"] if kv[1]["first3_para"] else 0)
    col = ["#96c4e2", "#78b2d8", "#62a0c8", "#deb06a", "#d68c4c", "#bc6642"]
    lab = ["1-10字", "11-20", "21-30", "31-50", "51-100", "100+"]
    rowh, top, W = 88, 185, 1680
    H = top + rowh * len(rows) + 110
    left, right = 500, W - 330
    scale = (right - left) / 100.0
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
        f'<rect width="{W}" height="{H}" fill="#fafaf8"/>',
        f'<text x="56" y="66" font-family="Microsoft YaHei, sans-serif" font-size="40" font-weight="bold" fill="#1e1e22">每段字数分布（前三章）</text>',
        f'<text x="56" y="110" font-family="Microsoft YaHei, sans-serif" font-size="21" fill="#6e6e76">11 本按段均从短到长排序　｜　11–50 字是手机屏舒适区，&gt;100 字要滚动　｜　条内数字为占比%</text>',
    ]
    for i, (name, v) in enumerate(rows):
        p, y = v["first3_para"], top + i * rowh
        out.append(f'<text x="56" y="{y + 18}" font-family="Microsoft YaHei, sans-serif" font-size="21" fill="#28282e">{esc(short(name))}</text>')
        out.append(f'<text x="56" y="{y + 50}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#82828a">段均 {p["mean"]} / CV {p["cv"]}</text>')
        x = left
        for pct, c in zip(p["hist"], col):
            seg = pct * scale
            if seg > 0:
                out.append(f'<rect x="{x:.1f}" y="{y + 8}" width="{seg:.1f}" height="54" fill="{c}"/>')
                if seg > 42:
                    out.append(f'<text x="{x + 7:.1f}" y="{y + 43}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#ffffff">{pct:.0f}</text>')
            x += seg
        out.append(f'<text x="{right + 14}" y="{y + 24}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#5a5a62">单句段 {p["single"]:.0f}%</text>')
        out.append(f'<text x="{right + 14}" y="{y + 52}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#5a5a62">同长游程 {p["run"]}</text>')
    lx, ly = left, H - 78
    for l, c in zip(lab, col):
        out.append(f'<rect x="{lx}" y="{ly}" width="20" height="20" fill="{c}"/>')
        out.append(f'<text x="{lx + 26}" y="{ly + 17}" font-family="Microsoft YaHei, sans-serif" font-size="19" fill="#505058">{l}</text>')
        lx += 152
    out.append("</svg>")
    path.write_text("\n".join(out), encoding="utf-8")


def tables(three, ten, metrics):
    L = []

    def w(s=""):
        L.append(s)

    w("## 3章排名")
    w("| # | 书 | 总分 | Q1 | Q2 | Q3 | Q4 | 卡点 |")
    w("|---|---|---:|---:|---:|---:|---:|---|")
    for r in three:
        weak = min([("Q1", r["q1"]), ("Q2", r["q2"]), ("Q3", r["q3"]), ("Q4", r["q4"])], key=lambda x: x[1])[0]
        w(f"| {r['rank']} | {r['name']} | **{r['T']:.2f}** | {r['q1']} | {r['q2']} | {r['q3']} | {r['q4']} | {weak} |")
    w()
    w("## 10章排名A")
    w("| # | 书 | 总分A | Q1 | Q2 | Q3 | Q4 | 10章字数 | 一句话证据 |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---|")
    for r in ten:
        w(f"| {r['rank']} | {r['name']} | **{r['A']:.2f}** | {r['q1']} | {r['q2']} | {r['q3']} | {r['q4']} | {r['chars10']:,} | {r['evidence']} |")
    w()
    w("## 10章排名B")
    w("| # | 书 | 总分B | B名次 |")
    w("|---|---|---:|---:|")
    for i, r in enumerate(sorted(ten, key=lambda x: (-x["B"], -x["q3"])), 1):
        w(f"| {i} | {r['name']} | {r['B']:.2f} | {r['rankB']} |")
    w()
    w("## 10章机读指标")
    w("| 书 | 10章字数 | 章均 | 段均 | 句均 | 长句率 | 对话段% | 【】标签/千字 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in ten:
        m = metrics[r["name"]]
        w(f"| {r['name']} | {m['chars10']:,} | {m['chap_mean']} | {m['para_mean']} | {m['sent_mean']} | {m['long_sent_pct']}% | {m['dialogue_pct']}% | {m['tag_per_k']} |")
    w()
    w("## 全书统计")
    w("| 书 | 章数 | 章均 | 章长SD | CV | 对话占比 | 短段率 | 章末钩前二 |")
    w("|---|---:|---:|---:|---:|---:|---:|---|")
    for r in ten:
        m = metrics[r["name"]]["overall"]
        cv = round(m["sd"] / m["mean"], 2) if m["mean"] else 0
        hooks = sorted([(k, v) for k, v in m["hook"].items() if not k.startswith("无")], key=lambda x: -x[1])[:2]
        hs = " / ".join(f"{k.split()[0]} {v:.1f}%" for k, v in hooks)
        w(f"| {r['name']} | {m['chapters']:,} | {m['mean']:.1f} | {m['sd']:.1f} | {cv} | {m['dialogue']:.2f}% | {m['short']:.2f}% | {hs} |")
    w()
    w("## 前三章段落分布（按段均升序）")
    w("| 书 | 段数 | 段均 | 中位 | SD | CV | 1-10 | 11-20 | 21-30 | 31-50 | 51-100 | 100+ | 单句段% | 同长游程 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for name, v in sorted(metrics.items(), key=lambda kv: kv[1]["first3_para"]["mean"]):
        p = v["first3_para"]
        w(f"| {name} | {p['n']} | {p['mean']} | {p['med']} | {p['sd']} | {p['cv']} | " + " | ".join(str(x) for x in p["hist"]) + f" | {p['single']} | {p['run']} |")
    w()
    w("## 3章→10章名次变化")
    w("| 书 | 3章名次 | 10章名次 | 变化 |")
    w("|---|---:|---:|---|")
    tr = {r["name"]: r["rank"] for r in three}
    for r in ten:
        a, b = tr[r["name"]], r["rank"]
        delta = b - a
        arrow = "—" if delta == 0 else ("↑" + str(-delta) if delta < 0 else "↓" + str(delta))
        w(f"| {r['name']} | {a} | {b} | {arrow} |")
    (DATA / "tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    DATA.mkdir(parents=True, exist_ok=True)
    scores, three, ten, metrics = load()
    (DATA / "scores.json").write_text(json.dumps(scores, ensure_ascii=False, indent=2), encoding="utf-8")
    svg_readability(three, OUT / "十一本书_可看性对比.svg",
                    "十一本书 · 前3章 可看性四问",
                    "均衡权重 Q1 30% / Q2 25% / Q3 25% / Q4 20%　｜　按总分排序")
    svg_readability(ten, OUT / "十一本书_十本章可看性.svg",
                    "十一本书 · 前10章 可看性四问",
                    "均衡权重 30/25/25/20　｜　右为门槛优先(35/30/20/15)名次　｜　按总分排序",
                    show_chars=True, show_brank=True)
    svg_para(metrics, OUT / "十一本书_每段字数分布.svg")
    tables(three, ten, metrics)
    print("OK")
    print("3章前五:", " / ".join(f"{r['name']} {r['T']:.2f}" for r in three[:5]))
    print("10章前五:", " / ".join(f"{r['name']} {r['A']:.2f}" for r in ten[:5]))
    print("输出:", OUT)


if __name__ == "__main__":
    main()
