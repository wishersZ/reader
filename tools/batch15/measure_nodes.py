# -*- coding: utf-8 -*-
"""实测每个节点第4节（节点详述／扩写正文）的去空白字符数，客观核对 v2.1 门槛。

用法：py -3 measure_nodes.py <扩写目录> <报告.txt>
输出：每文件 节点数 / 第4节 min·中位·max，并统计达标情况（普通≥800，关键≥1800由人工认定）。
"""
import re
import statistics
import sys
from pathlib import Path

RE_NODE = re.compile(r"^###\s*节点", re.M)
RE_S4 = re.compile(r"^\s*4\.\s*\*\*(节点详述|扩写正文)\*\*", re.M)
RE_S5 = re.compile(r"^\s*5\.\s*\*\*", re.M)


def measure(text):
    nodes = []
    marks = [m.start() for m in RE_NODE.finditer(text)]
    for i, start in enumerate(marks):
        end = marks[i + 1] if i + 1 < len(marks) else len(text)
        chunk = text[start:end]
        m4 = RE_S4.search(chunk)
        if not m4:
            nodes.append(None)
            continue
        m5 = RE_S5.search(chunk, m4.end())
        body = chunk[m4.end(): m5.start() if m5 else len(chunk)]
        nodes.append(len(re.sub(r"\s", "", body)))
    return nodes


def main(out_dir, report_path):
    rep = [f"目录: {out_dir}", ""]
    rep.append("文件\t节点数\tmin\t中位\tmax\t<800的节点数")
    allv = []
    for p in sorted(Path(out_dir).glob("*.md")):
        if p.name.startswith(("_", "00_")):
            continue
        vals = [v for v in measure(p.read_text(encoding="utf-8")) if v is not None]
        if not vals:
            rep.append(f"{p.name}\t0\t-\t-\t-\t-")
            continue
        allv += vals
        rep.append(f"{p.name}\t{len(vals)}\t{min(vals)}\t{int(statistics.median(vals))}\t{max(vals)}\t"
                   f"{sum(1 for v in vals if v < 800)}")
    if allv:
        rep.append("")
        rep.append(f"合计节点 {len(allv)}；中位 {int(statistics.median(allv))}；"
                   f"≥800 的 {sum(1 for v in allv if v >= 800)} 个；"
                   f"≥1800 的 {sum(1 for v in allv if v >= 1800)} 个；"
                   f"<800 的 {sum(1 for v in allv if v < 800)} 个")
    Path(report_path).write_text("\n".join(rep), encoding="utf-8")
    return allv


if __name__ == "__main__":
    v = main(sys.argv[1], sys.argv[2])
    print(f"done: nodes={len(v)} median={int(statistics.median(v)) if v else 0} "
          f"below800={sum(1 for x in v if x < 800)}")
