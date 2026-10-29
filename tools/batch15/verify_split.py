# -*- coding: utf-8 -*-
"""独立校验「每15章拆分」产物（不信任外包方的自检，自己重算一遍）。

用法：py -3 verify_split.py <源文件> <输出目录> <每批章数>
校验项：
  1. 文件名格式 第NNN批_第XXXX-XXXX章.txt，批次号连续，章号区间首尾相接且覆盖 1..总章数
  2. 每份文件首/末章标题的章号 == 文件名区间；批内章数 <= 每批章数（首尾批允许额外的前置/最终章）
  3. 每份文件 UTF-8 无 BOM、行尾 CRLF
  4. 零丢失：按文件名顺序拼接所有文件 == 源文件逐字节相同（sha256）
"""
import hashlib
import re
import sys
from pathlib import Path

RE_NAME = re.compile(r"^第(\d{3})批_第(\d{4})-(\d{4})章\.txt$")
RE_CN = re.compile(r"^第\s*([一二三四五六七八九十百千零两]+)\s*章")
RE_AR = re.compile(r"^第\s*([0-9]+)\s*章")
RE_FINAL = re.compile(r"^最终章")
CN_D = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
        "六": 6, "七": 7, "八": 8, "九": 9}
CN_U = {"十": 10, "百": 100, "千": 1000}


def cn2int(s):
    total = section = number = 0
    for ch in s:
        if ch in CN_D:
            number = CN_D[ch]
        elif ch in CN_U:
            u = CN_U[ch]
            if number == 0:
                number = 1
            section += number * u
            number = 0
    return total + section + number


def heading(line):
    if not line or line[0].isspace():
        return None
    s = line.strip()
    m = RE_CN.match(s)
    if m:
        return cn2int(m.group(1))
    m = RE_AR.match(s)
    if m:
        return int(m.group(1))
    if RE_FINAL.match(s):
        return "最终章"
    if s == "序章" or s.startswith("序章 "):
        return "序章"
    return None


def main(src, outdir, per):
    per = int(per)
    src_p = Path(src)
    src_bytes = src_p.read_bytes()
    src_text = src_bytes.decode("utf-8")
    src_lines = src_text.split("\r\n")
    src_hashes = hashlib.sha256(src_bytes).hexdigest()

    rep = [f"源文件: {src_p}  字节 {len(src_bytes)}  行 {len(src_lines)}"]
    rep.append(f"源文件 sha256: {src_hashes}")

    files = sorted(p for p in Path(outdir).iterdir() if p.is_file())
    rep.append(f"输出目录: {outdir}")
    rep.append(f"文件数: {len(files)}")

    errs = []
    cat = bytearray()
    expect_start = 1
    total_ch = 0
    for k, p in enumerate(files, 1):
        m = RE_NAME.match(p.name)
        if not m:
            errs.append(f"文件名不合规: {p.name}")
            continue
        bn, lo, hi = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if bn != k:
            errs.append(f"批次号不连续: {p.name}（应为第{k:03d}批）")
        if lo != expect_start:
            errs.append(f"章号区间不接续: {p.name} 起始 {lo}，应为 {expect_start}")
        expect_start = hi + 1

        raw = p.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            errs.append(f"{p.name}: 带 BOM")
        if b"\n" in raw.replace(b"\r\n", b""):
            errs.append(f"{p.name}: 存在裸 LF")
        text = raw.decode("utf-8")
        lines = text.split("\r\n")
        heads = [(i, heading(l)) for i, l in enumerate(lines) if heading(l)]
        nums = [h for _, h in heads if isinstance(h, int)]
        total_ch += len(nums)
        if nums:
            if nums[0] != lo:
                errs.append(f"{p.name}: 首章 {nums[0]} != 区间起点 {lo}")
            if nums[-1] != hi:
                errs.append(f"{p.name}: 末章 {nums[-1]} != 区间终点 {hi}")
        if len(nums) > per:
            errs.append(f"{p.name}: 批内章数 {len(nums)} > {per}")
        extras = [h for _, h in heads if not isinstance(h, int)]
        cat += raw

    if expect_start - 1 != total_ch:
        errs.append(f"章号覆盖到 {expect_start-1}，但实际章数 {total_ch}")

    cat_hash = hashlib.sha256(bytes(cat)).hexdigest()
    rep.append(f"拼接结果 sha256: {cat_hash}")
    rep.append(f"零丢失校验: {'通过（与源文件逐字节一致）' if cat_hash == src_hashes else '失败！'}")
    rep.append(f"章号覆盖: 1..{expect_start-1}（共 {total_ch} 章）")
    rep.append(f"首文件: {files[0].name if files else '无'}")
    rep.append(f"末文件: {files[-1].name if files else '无'}")
    rep.append(f"错误数: {len(errs)}")
    for e in errs[:40]:
        rep.append(f"  !! {e}")
    return "\n".join(rep), not errs and cat_hash == src_hashes


if __name__ == "__main__":
    report, ok = main(sys.argv[1], sys.argv[2], sys.argv[3])
    rp = Path(r"G:\txt\tools\batch15\results") / f"verify_split_{Path(sys.argv[1]).stem}.txt"
    rp.write_text(report, encoding="utf-8")
    sys.stdout.write(("OK\n" if ok else "FAIL\n") + f"报告 {len(report)} 字符\n")
