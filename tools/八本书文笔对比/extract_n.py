#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽取每本书前 N 章 + 生成章节骨架（每章前2行/后3行），供人工判断节拍。

用法:
    python extract_n.py <outdir> <N> <file...>
产出:
    <outdir>/slices/<书名>_前N章.txt      —— 用于 prose_metrics 实测
    <outdir>/skeleton.txt                —— 8 本书的章节骨架，供阅读
"""
import os
import re
import sys

HEAD = re.compile(r"^[\s\u3000]*(?:={2,})?\s*第\s*[0-9零一二三四五六七八九十百]+\s*[章节回]")
CJK = re.compile(r"[\u4e00-\u9fff]")


def read(path):
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return open(path, encoding=enc).read()
        except (UnicodeDecodeError, LookupError):
            pass
    return open(path, encoding="utf-8", errors="replace").read()


def clean_name(p):
    n = os.path.splitext(os.path.basename(p))[0]
    n = re.sub(r"_第?一?部分$", "", n)
    n = re.sub(r"_第1卷.*$", "_卷1", n)
    return n


def main():
    if len(sys.argv) < 4:
        sys.exit("用法: extract_n.py <outdir> <N> <file...>")
    outdir, N = sys.argv[1], int(sys.argv[2])
    files = sys.argv[3:]
    slicedir = os.path.join(outdir, "slices")
    os.makedirs(slicedir, exist_ok=True)

    skel = []
    print(f"{'书':<24}{'章数':>5}{'总字数':>9}{'覆盖到':>22}")
    for path in files:
        name = clean_name(path)
        lines = read(path).splitlines()
        idx = [i for i, l in enumerate(lines) if HEAD.match(l)]
        if not idx:
            print(f"{name:<24}   无章标题")
            continue
        take = idx[:N]
        end = idx[N] if len(idx) > N else len(lines)
        body = lines[take[0]:end]
        chars = len(re.sub(r"\s", "", "".join(body)))
        with open(os.path.join(slicedir, f"{name}_前{N}章.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(body))
        print(f"{name:<24}{len(take):>5}{chars:>9}   {lines[take[0]].strip()[:20]}")

        skel.append(f"\n{'='*74}\n### {name}（前 {len(take)} 章）\n{'='*74}")
        for k, st in enumerate(take):
            en = take[k + 1] if k + 1 < len(take) else end
            block = [l.strip() for l in lines[st:en] if l.strip()]
            if len(block) < 6:
                continue
            head = block[0]
            cjk = len(re.sub(r"\s", "", "".join(block)))
            skel.append(f"\n[{k+1}] {head}  ({cjk}字)")
            for l in block[1:3]:
                skel.append("    开头| " + l[:60])
            for l in block[-3:]:
                skel.append("    章末| " + l[:60])

    with open(os.path.join(outdir, "skeleton.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(skel))
    print(f"\n骨架: {os.path.join(outdir, 'skeleton.txt')}")
    print(f"切片: {slicedir}")


if __name__ == "__main__":
    main()
