# -*- coding: utf-8 -*-
"""覆盖校验：整理稿的每个情节点条目，是否都能在扩写产物里找到对应章节锚点。

用法：py -3 check_coverage.py <整理稿.md> <扩写目录> <输出报告.txt>
判定：取出条目里的「第N章」「第N—M章」「第N、M行」等引用，若扩写目录里所有文件都
      没出现其中任何一个引用，则该条目判为"疑似漏覆盖"，列出来人工确认。
"""
import re
import sys
from pathlib import Path

RE_ENTRY = re.compile(r"^-\s+\*\*(.+?)\*\*[：:]?(.*)$")
RE_CHAP = re.compile(r"第\s*([0-9]+)\s*章")
RE_RANGE = re.compile(r"第\s*([0-9]+)\s*[—\-~－]\s*([0-9]+)\s*章")
RE_LINE = re.compile(r"第\s*([0-9]{3,6})\s*[—\-~－]?\s*([0-9]{0,6})\s*行")


def chapters_in(text):
    """抽出文本里提到的所有章号，支持“第65—66章”这类区间写法。"""
    nums = set()
    for a, b in RE_RANGE.findall(text):
        a, b = int(a), int(b)
        if b - a <= 200:
            nums.update(range(a, b + 1))
    for n in RE_CHAP.findall(text):
        nums.add(int(n))
    return nums


def main(md_path, out_dir, report_path):
    md = Path(md_path).read_text(encoding="utf-8").splitlines()
    entries = []
    for i, line in enumerate(md, 1):
        m = RE_ENTRY.match(line.strip())
        if m:
            entries.append((i, m.group(1).strip(), m.group(2).strip()))

    out_files = sorted(Path(out_dir).glob("*.md"))
    body = {}
    for p in out_files:
        body[p.name] = p.read_text(encoding="utf-8")
    all_text = "\n".join(body.values())
    covered = chapters_in(all_text)

    rep = [f"整理稿: {md_path}", f"扩写目录: {out_dir}  文件数 {len(out_files)}",
           f"整理稿情节点条目数: {len(entries)}", ""]
    miss = []
    for ln, head, rest in entries:
        blob = head + " " + rest
        chaps = sorted(chapters_in(blob))
        lines = [int(x) for x in RE_LINE.findall(blob) for x in x if x]
        hit_ch = [c for c in chaps if c in covered]
        hit_ln = [x for x in lines if str(x) in all_text]
        status = "OK" if (hit_ch or hit_ln) else "MISS"
        if status == "MISS":
            miss.append((ln, head))
        rep.append(f"[{status}] 整理稿第{ln}行 章{chaps or '-'} 行号{lines or '-'}  {head[:60]}")
    rep.append("")
    rep.append(f"疑似漏覆盖: {len(miss)} / {len(entries)}")
    for ln, head in miss:
        rep.append(f"  !! 第{ln}行 {head}")
    Path(report_path).write_text("\n".join(rep), encoding="utf-8")
    return len(miss), len(entries)


if __name__ == "__main__":
    n, total = main(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"done: miss={n} total={total}")
