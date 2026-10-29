# -*- coding: utf-8 -*-
"""为《弗雷尔卓德的孤狼完结》整理稿里的每个行号引用，算出「章节标题 / 批次文件 / 批次内行号」。

背景：该书整理稿只给源 TXT 的物理行号，不给章号；三个扩写代理需要反复手工换算。
本脚本一次性生成映射表，代理直接查表 + read 即可。

用法：py -3 locate_lines.py [整理稿.md ...]
输出：G:\\txt\\tools\\batch15\\results\\_archive_freljord\\freljord_行号映射.tsv（源书已不在工作区，本脚本仅存档）
"""
import importlib.util
import re
import sys
from pathlib import Path

SRC = Path(r"G:\txt\novels\弗雷尔卓德的孤狼完结.txt")
SPLIT_DIR = Path(r"G:\txt\novels\弗雷尔卓德的孤狼完结_每15章拆分")
OUT = Path(r"G:\txt\tools\batch15\results\_archive_freljord\freljord_行号映射.tsv")
PER = 15

spec = importlib.util.spec_from_file_location("m", r"G:\txt\tools\batch15\merge_yinan.py")
m = importlib.util.module_from_spec(spec)
sys.modules["m"] = m
spec.loader.exec_module(m)
parse_heading = m.parse_heading

RE_REF = re.compile(r"(\d{2,6})\s*[—\-~－]\s*(\d{2,6})")
RE_REF1 = re.compile(r"第(\d{2,6})行")


def main(mds):
    raw = SRC.read_bytes().decode("utf-8").lstrip("\ufeff")
    lines = raw.split("\r\n")

    heads = []  # (行号1based, 章号, 标题)
    for i, l in enumerate(lines):
        h = parse_heading(l)
        if h and h[0] in ("cn", "ar") and h[1]:
            heads.append((i + 1, h[1], h[2]))

    # 注意：本项目 弗雷尔卓德 的拆分文件夹是上一轮会话生成的，**文件名里的章号区间与内容错位**，
    # 因此这里完全按"文件内容里实际出现的章标题"建表，不信任文件名。
    chap2file = {}   # 章号 -> (文件名, 该章标题在文件内的行号)
    for p in sorted(SPLIT_DIR.glob("*.txt")):
        # 注意：这批文件是 LF 换行（不是 CRLF），必须用 splitlines() 而不是 split("\r\n")
        for i, l in enumerate(p.read_bytes().decode("utf-8", "replace").splitlines(), 1):
            h = parse_heading(l)
            if h and h[0] in ("cn", "ar") and h[1]:
                chap2file.setdefault(h[1], (p.name, i))
    total_ch = max(chap2file) if chap2file else 0

    starts = [h[0] for h in heads]
    head_line = {ch: ln for ln, ch, _ in heads}

    def locate(ref_line):
        import bisect
        k = bisect.bisect_right(starts, ref_line) - 1
        if k < 0:
            return None
        hl, ch, title = heads[k]
        hit = chap2file.get(ch)
        if not hit:
            return None
        fname, in_file_head = hit
        return (ch, title, fname, ref_line - hl + in_file_head)

    refs = set()
    for md in mds:
        txt = Path(md).read_text(encoding="utf-8")
        for mm in RE_REF.finditer(txt):
            for g in mm.groups():
                v = int(g)
                if 1 <= v <= len(lines):
                    refs.add(v)
        for mm in RE_REF1.finditer(txt):
            v = int(mm.group(1))
            if 1 <= v <= len(lines):
                refs.add(v)

    rows = ["源行号\t章号\t章节标题\t批次文件(按内容)\t批次内行号\t该行内容首40字"]
    ok = 0
    for r in sorted(refs):
        loc = locate(r)
        if not loc:
            rows.append(f"{r}\t-\t未定位\t-\t-\t{lines[r-1][:40]}")
            continue
        ch, title, name, inb = loc
        ok += 1
        rows.append(f"{r}\t{ch}\t{title}\t{name}\t{inb}\t{lines[r-1].strip()[:40]}")
    OUT.write_text("\n".join(rows), encoding="utf-8")
    print(f"源文件 {len(lines)} 行 / {total_ch} 章；整理稿引用行号 {len(refs)} 个，定位成功 {ok} -> {OUT}")


if __name__ == "__main__":
    mds = sys.argv[1:] or [r"G:\txt\novels\弗雷尔卓德的孤狼完结_暧昧与后宫情节点整理.md"]
    main(mds)
