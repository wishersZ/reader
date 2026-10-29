# -*- coding: utf-8 -*-
"""《幽暗主宰.txt》合并去重 -> 《幽暗主宰_合并版.txt》

源文件是两套东西拼在一起的：
  第1-43109行   干净校对版：书籍信息/声明/正文卷 + 序章 + 第一~九百二十章
  第43110-57991行 劣质拼凑版：第1~156章（阿拉伯数字）+ 一批残片
                  （581、742-747、855-856、461-462、705-706、730-739、814-821、
                    921-940、941-1044、最终章），960/1005/1006/1037 有重复块

已实测确认的问题及处理：
  1. 干净版里插了一“补丁块”（第18755-19091行），内容错位：
       - 第三百四十六章 转化之刻 被插在 374 和 375 之间 -> 归位到 345 之后
       - 第三百六十一~三百六十七章 被重下一份更干净的拷贝插在 374 之后
         -> 用干净拷贝替换前面那份脏拷贝（半角标点/人名错字）
  2. 干净版里有 4 处章号贴错（都是补丁块带来的），按上下文归位：
       第229章 黑暗深渊（I）  -> 第329章（夹在328与330之间）
       第77章  从天而降的怒火 -> 第477章（夹在476与478之间）
       第381章 霜之哀伤       -> 第831章（夹在830与832之间）
       第607~612章 终曲(XI)~新世界 -> 第907~912章（夹在906与913之间）
  3. 局部前后颠倒（841/842、859/860）-> 统一按章号排序
  4. 干净版缺第581章 海岸之战（V）-> 从拼凑版补入
  5. 拼凑版 921~1044 有重复块（960、1005、1006、1037）-> 去重
  6. 全书真正缺章：635、736、813、895（源文件里两套都没有）
     -> 输出里插一行明确的缺章占位，保证章号连续

输出：书籍信息 + 序章 + 第1~1044章（其中4章为占位）+ 最终章
"""
import re
import sys
from pathlib import Path

SRC = Path(r"G:\txt\novels\幽暗主宰.txt")
DST = Path(r"G:\txt\novels\幽暗主宰_合并版.txt")

A_END = 43109          # 干净版最后一行（1-based）
PROLOGUE_LINE = 17     # 序章所在行（1-based）

CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
             "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}

# 补丁块里的错号 -> 正确章号（键为源文件 1-based 行号）
FIX_NUM = {
    16803: 329,
    24133: 477,
    40144: 831,
    42683: 907, 42702: 908, 42737: 909, 42768: 910, 42805: 911, 42829: 912,
}
# 脏拷贝（前半段那份 361~367），行号 -> 丢弃
DROP_LINES = {18131, 18174, 18220, 18258, 18296, 18334, 18377}
# 拼凑版里补回来的一章（1-based 起始行）
BORROW_LINES = {581: 51389}
MISSING = [635, 736, 813, 895]


def cn2int(s: str) -> int:
    total = section = number = 0
    for ch in s:
        if ch in CN_DIGITS:
            number = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit = CN_UNITS[ch]
            if number == 0:
                number = 1
            section += number * unit
            number = 0
        else:
            raise ValueError(f"无法解析的中文数字: {s!r}")
    return total + section + number


RE_CN = re.compile(r"^第\s*([一二三四五六七八九十百千零两]+)\s*章")
RE_AR = re.compile(r"^第\s*([0-9]+)\s*章")
RE_FINAL = re.compile(r"^最终章")

_CN_D = "零一二三四五六七八九"
_CN_U = ["", "十", "百", "千"]


def int2cn(n: int) -> str:
    """int -> 中文数字（1~9999），风格与源文件一致：一千零四十四 / 九百零七 / 一十。"""
    s = str(n)
    res, zero = "", False
    for i, ch in enumerate(s):
        d = int(ch)
        pos = len(s) - i - 1
        if d == 0:
            zero = True
            continue
        if zero and res:
            res += "零"
        zero = False
        if not (d == 1 and pos == 1 and res == ""):
            res += _CN_D[d]
        res += _CN_U[pos]
    return res


def parse_heading(line: str):
    """标题行一律顶格；带缩进的一律当正文（防“　　第八百五十九章…”误判）。"""
    if not line or line[0].isspace():
        return None
    s = line.strip()
    if not s:
        return None
    m = RE_CN.match(s)
    if m:
        return ("cn", cn2int(m.group(1)), s)
    m = RE_AR.match(s)
    if m:
        return ("ar", int(m.group(1)), s)
    if RE_FINAL.match(s):
        return ("final", None, s)
    if s == "序章" or s.startswith("序章 "):
        return ("prologue", None, s)
    return None


def segments(lines, offset=0):
    """把一段文本按标题切成 [(起始行1based, head, [正文行...]), ...]"""
    idx = [i for i, l in enumerate(lines) if parse_heading(l)]
    out = []
    for k, i in enumerate(idx):
        end = idx[k + 1] if k + 1 < len(idx) else len(lines)
        out.append((i + 1 + offset, parse_heading(lines[i]), lines[i + 1:end]))
    return out


def clean_body(seg):
    body = list(seg)
    while body and body[-1] == "":
        body.pop()
    return body


def main() -> int:
    raw = SRC.read_bytes().decode("utf-8").lstrip("\ufeff")
    lines = raw.split("\r\n")
    while lines and lines[-1] == "":
        lines.pop()
    part_a = lines[:A_END]
    part_b = lines[A_END:]

    front = [l for l in part_a[:PROLOGUE_LINE - 1]]
    while front and front[-1] == "":
        front.pop()

    a_units = {}
    a_prologue = None
    log = []
    for start, head, body in segments(part_a):
        if head[0] == "prologue":
            a_prologue = clean_body(body)
            continue
        num = FIX_NUM.get(start, head[1])
        if start in DROP_LINES:
            log.append(f"丢弃脏拷贝: 行{start} {head[2]}")
            continue
        if num in a_units:
            raise SystemExit(f"章号仍然冲突: {num} 行{start} {head[2]}")
        title = head[2]
        if num != head[1]:
            # 把标题行里的章号一起改成正确编号（保留原标题文字）
            rest = re.sub(r"^第\s*[一二三四五六七八九十百千零两0-9]+\s*章", "", title).lstrip()
            title = f"第{int2cn(num)}章" + (f" {rest}" if rest else "")
            log.append(f"章号归位: 行{start} {head[2]} -> {title}")
        a_units[num] = (title, clean_body(body))

    missing_a = [n for n in range(1, 921) if n not in a_units]
    log.append(f"干净版缺号: {missing_a}")

    b_units = {}
    b_final = None
    for start, head, body in segments(part_b, offset=A_END):
        if head[0] in ("cn", "ar") and head[1] is not None:
            if 921 <= head[1] <= 1044 and head[1] not in b_units:
                b_units[head[1]] = (head[2], clean_body(body))
        elif head[0] == "final" and b_final is None:
            b_final = (head[2], body)
    assert len(b_units) == 124, f"拼凑版 921-1044 不全: {len(b_units)}"
    assert b_final is not None

    for num, start_line in BORROW_LINES.items():
        seg = [s for s in segments(part_b, offset=A_END) if s[0] == start_line]
        assert seg, f"找不到补入章 行{start_line}"
        a_units[num] = (seg[0][1][2], clean_body(seg[0][2]))
        log.append(f"从拼凑版补入: 行{start_line} {seg[0][1][2]}")

    # ---- 拼装 ----
    out = list(front)
    out += ["", ""]
    out.append("序章 幽域深处")
    out += a_prologue

    for num in range(1, 1045):
        out += ["", ""]
        if num in a_units:
            title, body = a_units[num]
            out.append(title)
            out += body
        elif num in b_units:
            title, body = b_units[num]
            out.append(title)
            out += body
        elif num in MISSING:
            out.append(f"第{int2cn(num)}章 【缺章：源文件的两套版本都没有收录这一章】")
            out.append("　　本章内容在源 TXT 中确实缺失，此处仅保留章号占位，以便章节编号连续。")
        else:
            raise SystemExit(f"第{num}章既不在干净版也不在拼凑版")

    out += ["", ""]
    out.append(b_final[0])
    out += b_final[1]
    while out and out[-1] == "":
        out.pop()

    text = "\r\n".join(out) + "\r\n"
    DST.write_bytes(text.encode("utf-8"))

    # ---- 回读校验 ----
    back = DST.read_bytes().decode("utf-8").split("\r\n")
    heads = [parse_heading(l) for l in back if parse_heading(l)]
    nums = [h[1] for h in heads if h[0] in ("cn", "ar")]
    assert nums == list(range(1, 1045)), "输出章号不连续！"
    chars = sum(len(l.strip()) for l in back)

    print("\n".join(log))
    print(f"\n输出: {DST}")
    print(f"  字节 {DST.stat().st_size} / 行 {len(back)} / 净字 {chars}")
    print(f"  标题单元 {len(heads)} = 序章1 + 章{len(nums)} + 最终章{sum(1 for h in heads if h[0]=='final')}")
    print(f"  章号连续性: OK 1-1044；其中占位缺章 {MISSING}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
