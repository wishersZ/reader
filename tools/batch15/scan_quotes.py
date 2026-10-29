# -*- coding: utf-8 -*-
"""审计"自造台词"：v2 口径只允许两类引用——原文逐字摘引（≤40字，需标注）与要点转述。

本脚本抓出每个文件里**长度 ≥8 字且未被标注为原文摘引的引号内文本**，
即疑似代理自己写的对白，供人工回查原文确认。

用法：py -3 scan_quotes.py <目录> <报告.txt>
"""
import re
import sys
from pathlib import Path

QUOTE = re.compile(r"[“\"「]([^”\"」]{8,})[”\"」]")
MARKERS = ("原文摘引", "摘句", "摘引", "原文行", "原文：", "原文:", "旁白写着", "原文写着",
           "原文第", "批次原文", "整理稿第", "原句", "节选自", "原文中", "原文里")


def main(out_dir, report_path):
    files = sorted(Path(out_dir).glob("*.md"))
    rep = [f"目录: {out_dir}  文件数 {len(files)}", ""]
    total = 0
    for p in files:
        hits = []
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in QUOTE.finditer(line):
                s = m.group(1)
                ctx = line
                if any(k in ctx for k in MARKERS):
                    continue  # 已标注为原文摘引
                hits.append((i, s, line.strip()[:60]))
        if hits:
            rep.append(f"## {p.name}  疑似自造/未标注引用 {len(hits)} 处")
            for i, s, ctx in hits[:40]:
                rep.append(f"  L{i}: 「{s}」")
                rep.append(f"      行内上下文: {ctx}")
            total += len(hits)
        else:
            rep.append(f"## {p.name}  ✔ 无未标注引号台词")
    rep.append("")
    rep.append(f"合计疑似未标注引用: {total}")
    Path(report_path).write_text("\n".join(rep), encoding="utf-8")
    return total


if __name__ == "__main__":
    n = main(sys.argv[1], sys.argv[2])
    print(f"done: unmarked_quotes={n}")
