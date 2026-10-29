# -*- coding: utf-8 -*-
"""诊断《幽暗主宰》干净版(前半段)的章号重复/跳号到底是排版错还是内容重复。"""
import importlib.util
import re
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
units = []
for k, i in enumerate(idx):
    end = idx[k + 1] if k + 1 < len(idx) else len(part_a)
    head = m.parse_heading(part_a[i])
    body = part_a[i + 1:end]
    text = "".join(x.strip() for x in body)
    units.append({"i": i, "head": head, "title": head[2], "num": head[1],
                  "lines": end - i, "chars": len(text), "fp": text[:120], "tail": text[-60:]})

REPORT = Path(r"G:\txt\tools\batch15\results\diag_partA.txt")
_rl = []
_out = print


def print(*a, **kw):  # noqa: A001  —— 同时写报告文件
    s = " ".join(str(x) for x in a)
    _rl.append(s)
    _out(s, **kw)


print(f"干净版单元数: {len(units)}")
print("\n=== 340-380 章号序列 ===")
for u in units:
    if u["num"] and 340 <= u["num"] <= 380:
        print(f'  行{u["i"]+1:>6} #{u["num"]:<4} 行数{u["lines"]:>4} 字{u["chars"]:>6}  {u["title"]}')

print("\n=== 重复章号的内容指纹对比 ===")
seen = {}
for u in units:
    if u["num"] is None:
        continue
    seen.setdefault(u["num"], []).append(u)
for num, us in sorted(seen.items()):
    if len(us) > 1:
        print(f'#{num} {len(us)}块:')
        for u in us:
            print(f'   行{u["i"]+1:>6} 行数{u["lines"]:>4} 字{u["chars"]:>6} {u["title"]}')
            print(f'      头: {u["fp"][:60]}')
            print(f'      尾: {u["tail"]}')

print("\n=== 跳号处的相邻单元 ===")
missing = [n for n in range(1, 921) if n not in seen]
for n in missing:
    prev = [u for u in units if u["num"] == n - 1]
    nxt = [u for u in units if u["num"] == n + 1]
    print(f'缺 {n}: 前={prev[0]["title"] if prev else "无"} | 后={nxt[0]["title"] if nxt else "无"}')

# 全文内容级重复检测（跨所有单元）
print("\n=== 内容级重复（前120字+字数 相同） ===")
byfp = {}
for u in units:
    byfp.setdefault((u["fp"], u["chars"]), []).append(u)
for key, us in byfp.items():
    if len(us) > 1:
        print("  " + " | ".join(f'行{u["i"]+1} #{u["num"]} {u["title"]}' for u in us))

REPORT.write_text("\n".join(_rl), encoding="utf-8")
