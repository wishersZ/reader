# -*- coding: utf-8 -*-
"""导出《幽暗主宰》干净版(前半段)全部章节单元清单，用于人工核对章号异常。"""
import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("m", r"G:\txt\tools\batch15\merge_yinan.py")
m = importlib.util.module_from_spec(spec)
sys.modules["m"] = m
spec.loader.exec_module(m)

raw = m.SRC.read_bytes().decode("utf-8")
lines = raw.split("\r\n")
part_a = lines[: m.A_END]

idx = [i for i, l in enumerate(part_a) if m.parse_heading(l)]
rows = []
for k, i in enumerate(idx):
    end = idx[k + 1] if k + 1 < len(idx) else len(part_a)
    head = m.parse_heading(part_a[i])
    text = "".join(x.strip() for x in part_a[i + 1:end])
    rows.append((k + 1, i + 1, head[1], head[2], end - i, len(text), text[:80]))

out = ["序号\t行号\t章号\t标题\t行数\t净字数\t正文头80字"]
for r in rows:
    out.append("\t".join("" if x is None else str(x) for x in r))
Path(r"G:\txt\tools\batch15\results\partA_units.tsv").write_text("\n".join(out), encoding="utf-8")
print(f"写出 {len(rows)} 个单元 -> partA_units.tsv")

# 尾部 880 号之后的所有单元（含错位块）
print("\n=== 章号 >= 880 的单元（按文件顺序） ===")
for r in rows:
    if r[2] is not None and r[2] >= 880:
        print(f'{r[0]:>4} 行{r[1]:>6} #{r[2]:<4} {r[3]}')
print("\n=== 76-80 / 227-231 / 327-331 / 379-383 附近 ===")
for lo, hi in ((75, 81), (226, 232), (326, 332), (378, 384), (475, 479), (579, 583), (633, 637), (734, 738), (811, 815), (829, 833), (893, 897)):
    print(f"-- {lo}-{hi} --")
    for r in rows:
        if r[2] is not None and lo <= r[2] <= hi:
            print(f'{r[0]:>4} 行{r[1]:>6} #{r[2]:<4} {r[3]}')
