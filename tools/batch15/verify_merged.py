# -*- coding: utf-8 -*-
"""合并版回读体检：章号序列、缺章占位、边界、尾部、体量。"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("m", r"G:\txt\tools\batch15\merge_yinan.py")
m = importlib.util.module_from_spec(spec)
sys.modules["m"] = m
spec.loader.exec_module(m)

raw = m.DST.read_bytes().decode("utf-8")
lines = raw.split("\r\n")
heads = [(i + 1, m.parse_heading(l)) for i, l in enumerate(lines) if m.parse_heading(l)]

out = [f"文件: {m.DST}  字节 {m.DST.stat().st_size}  行 {len(lines)}"]
out.append(f"标题单元 {len(heads)}")
nums = [h[1][1] for h in heads if h[1][0] in ("cn", "ar")]
out.append(f"章数 {len(nums)}  首 {nums[0]}  末 {nums[-1]}  连续={nums == list(range(1, 1045))}")

out.append("\n=== 关键位置抽查（章节标题行号 + 标题） ===")
want = [1, 77, 328, 329, 330, 345, 346, 347, 360, 361, 367, 368, 374, 375, 476, 477, 478,
        580, 581, 582, 606, 607, 612, 613, 634, 635, 636, 735, 736, 737, 812, 813, 814,
        830, 831, 832, 906, 907, 912, 913, 920, 921, 940, 941, 959, 960, 961, 1004, 1005,
        1006, 1007, 1036, 1037, 1044]
d = {h[1][1]: (h[0], h[1][2]) for h in heads if h[1][0] in ("cn", "ar")}
for n in want:
    if n in d:
        out.append(f"  第{n}章 -> 行{d[n][0]:>6}  {d[n][1]}")
    else:
        out.append(f"  第{n}章 -> 缺失")

out.append("\n=== 序章/最终章 ===")
for ln, h in heads:
    if h[0] in ("prologue", "final"):
        out.append(f"  行{ln}: {h[2]}")

out.append("\n=== 缺章占位块原文（635 前后） ===")
for ln, h in heads:
    if h[1] == 635:
        for k in range(ln - 3, ln + 3):
            out.append(f"  {k+1}: {lines[k]}")
out.append("\n=== 头 20 行 ===")
for i in range(20):
    out.append(f"  {i+1}: {lines[i]}")
out.append("\n=== 尾 6 行 ===")
for i in range(len(lines) - 8, len(lines)):
    out.append(f"  {i+1}: {lines[i][:120]}")

# 每章净字数，找异常短章
out.append("\n=== 净字数 < 500 的章（可能是残章/占位） ===")
for k, (ln, h) in enumerate(heads):
    end = heads[k + 1][0] - 1 if k + 1 < len(heads) else len(lines)
    chars = sum(len(x.strip()) for x in lines[ln:end - 1])
    if chars < 500:
        out.append(f"  行{ln:>6} {h[2]} -> {chars} 字")

Path(r"G:\txt\tools\batch15\results\verify_merged.txt").write_text("\n".join(out), encoding="utf-8")
print(f"报告已写出：{len(out)} 行")
