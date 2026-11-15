#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽出每本书的前三章（含章标题），供文笔对比。

用法：
    python extract_first3.py <outdir> <file1> <file2> ...
输出：
    <outdir>/<书名>_前三章.txt + 控制台汇总表
"""
import os
import re
import sys

HEAD = re.compile(r"^[\s\u3000]*(?:={2,})?\s*第\s*[0-9零一二三四五六七八九十百]+\s*[章节回]")
CJK = re.compile(r"[\u4e00-\u9fff]")


def read_text(path):
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read(), enc
        except (UnicodeDecodeError, LookupError):
            continue
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(), "utf-8(replace)"


def main():
    if len(sys.argv) < 3:
        sys.exit("用法: python extract_first3.py <outdir> <file...>")
    outdir, files = sys.argv[1], sys.argv[2:]
    os.makedirs(outdir, exist_ok=True)

    rows = []
    for path in files:
        text, enc = read_text(path)
        lines = text.splitlines()
        idx = [i for i, ln in enumerate(lines) if HEAD.match(ln)]
        if len(idx) < 3:
            rows.append((os.path.basename(path), "跳过（章标题不足3个）", 0, 0, enc))
            continue
        start, end = idx[0], (idx[3] if len(idx) > 3 else len(lines))
        body = lines[start:end]
        clean = "".join(body).replace(" ", "").replace("\u3000", "")
        name = os.path.splitext(os.path.basename(path))[0]
        name = re.sub(r"_第?一?部分$", "", name)
        name = re.sub(r"_第1卷.*$", "_卷1", name)
        out = os.path.join(outdir, f"{name}_前三章.txt")
        with open(out, "w", encoding="utf-8") as f:
            f.write("\n".join(body))
        titles = [lines[i].strip() for i in idx[:3]]
        rows.append((name, " / ".join(titles), len(clean), len(body), enc))

    print(f"{'书名':<26}{'前三章字数':>9}{'行数':>7}  编码")
    for name, titles, chars, nline, enc in rows:
        print(f"{name:<26}{chars:>9}{nline:>7}  {enc}")
        if chars:
            print(f"    {titles}")
    print(f"\n输出目录: {outdir}")


if __name__ == "__main__":
    main()
