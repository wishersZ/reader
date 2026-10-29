# -*- coding: utf-8 -*-
"""锚点校验 v2：核实每个节点"回查锚点"声称的原文摘引是否真在它引用的批次文件里。

相比 v1 的三点改进：
  1. 支持省略号摘引（"科顿·布莱克已经在幽暗地域里……战死"）——按片段分别匹配；
  2. 支持只写"第NNN批"的引用（按批次号解析成实际文件名）；
  3. 在引用文件里找不到时，**再全目录搜一遍**（因为弗雷尔卓德那批文件名与内容错位），
     全目录能找到记为 MISNAMED（文件名引错，内容真实），全找不到才是 BAD。

用法：py -3 verify_anchors.py <扩写目录> <批次目录> <报告.txt>
"""
import collections
import re
import sys
from pathlib import Path

RE_FULLFILE = re.compile(r"第(\d{3})批_第\d{4}-\d{4}章\.txt")
RE_BATCHNO = re.compile(r"第\s*(\d{1,3})\s*批")
RE_LINE = re.compile(r"第\s*(\d{1,5})\s*行")
RE_SECTION = re.compile(r"(回查锚点|原文摘引|摘句)")
QUOTES = re.compile(r"[“\"「]([^”\"」]{6,60})[”\"」]")
ELLIPSIS = re.compile(r"…+|\.{2,}|．{2,}")


def load_batches(bdir):
    return {p.name: p.read_bytes().decode("utf-8", "replace").splitlines()
            for p in Path(bdir).glob("*.txt")}


def fragments(q):
    parts = [s.strip("… .。，,、！!？?；;") for s in ELLIPSIS.split(q)]
    return [s for s in parts if len(s) >= 4]


def find_frag(lines, frag):
    return [i + 1 for i, t in enumerate(lines) if frag in t]


def main(out_dir, batch_dir, report_path):
    batches = load_batches(batch_dir)
    by_no = {}
    for name in batches:
        m = RE_FULLFILE.match(name)
        if m:
            by_no.setdefault(int(m.group(1)), name)
    all_lines = [(name, ls) for name, ls in batches.items()]

    rep = [f"扩写目录: {out_dir}", f"批次目录: {batch_dir}（{len(batches)} 个文件）", ""]
    stats = collections.Counter()
    rows = collections.defaultdict(list)

    for p in sorted(Path(out_dir).glob("*.md")):
        for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not RE_SECTION.search(line):
                continue
            quotes = [q for q in QUOTES.findall(line) if len(q) >= 6]
            if not quotes:
                continue
            names = [m.group(0) for m in RE_FULLFILE.finditer(line)]
            if not names:
                names = [by_no[n] for n in (int(x) for x in RE_BATCHNO.findall(line)) if n in by_no]
            nums = [int(x) for x in RE_LINE.findall(line)]

            for q in quotes:
                frags = fragments(q)
                if not frags:
                    continue
                verdict = "BAD"
                where = ""
                for scope_name, scope in (("cited", [(n, batches[n]) for n in names if n in batches]),
                                          ("all", all_lines)):
                    if not scope:
                        continue
                    ok_all, near_all = True, False
                    for f in frags:
                        hits = []
                        for _, ls in scope:
                            hits += find_frag(ls, f)
                        if not hits:
                            ok_all = False
                            break
                        if nums and any(abs(h - n) <= 80 for h in hits for n in nums):
                            near_all = True
                    if ok_all:
                        if scope_name == "cited":
                            verdict, where = ("OK" if (near_all or not nums) else "FAR"), "cited"
                        else:
                            verdict, where = "MISNAMED", "whole-dir"
                        break
                stats[verdict] += 1
                rows[verdict].append((p.name, ln, q[:40], ",".join(names) or "-", nums, where))

    rep.append("  ".join(f"{k}={v}" for k, v in sorted(stats.items())))
    for k in ("BAD", "MISNAMED", "FAR"):
        rep.append("")
        rep.append(f"=== {k} ({len(rows[k])}) ===")
        for r in rows[k][:80]:
            rep.append("  " + " | ".join(str(x) for x in r[:5]))
    Path(report_path).write_text("\n".join(rep), encoding="utf-8")
    return stats


if __name__ == "__main__":
    s = main(sys.argv[1], sys.argv[2], sys.argv[3])
    print("done: " + "  ".join(f"{k}={v}" for k, v in sorted(s.items())))
