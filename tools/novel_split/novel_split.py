#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
novel_split.py —— 长篇小说「编码统一 → 规范化 → 章节排序 → 分卷/分部分」工具

四个子命令（全部支持 --json / --quiet，便于 AI 或脚本调用）：

    probe    只探测编码/换行/BOM/可解码候选，不写盘          ← 先跑这个看文件底细
    encode   把 TXT 无损统一到指定编码（默认 UTF-8）          ← 解决编码混乱
    analyze  只分析卷/章结构，输出 Markdown 报告
    split    规范化 + 排序 + 切分输出多份 TXT
    all      一条命令跑完 probe → encode(可选) → analyze → split

退出码（AI 可直接据此判断）：
    0 = 全部成功      1 = 部分文件失败
    2 = 没有找到输入  3 = 校验失败 / 严格模式下编码无法无损表示

编码统一（encode）：
    - 默认**就地改写源文件**，并自动留一份 `.bak`（已存在则不覆盖，保住最早的原件）
    - 想不动源文件就加 `--out-dir DIR` 写副本
    - 严格无损：目标编码无法表示某个字符时直接报错，而不是静默替换成 `?`
    - 幂等：文件已是目标编码与换行时跳过，不产生多余写入
    - 源文件被误判时用 `--from gbk` 之类强制指定解码编码

拆分（split）的两种策略（--mode auto 自动选择）：
    1) 小说自带卷/部（「第一卷 化龙」）→ 每卷一个文件：《书名》_第一卷 化龙.txt
    2) 小说没有卷 → 按自定义数量均分：《书名》_第一部分.txt ...

每本书的输出目录内附带：
    00_目录索引.md     每份的章节范围、字数、异常汇总
    01_章节清单.tsv    全部章节的序号/卷/章号/标题/净字数
    manifest.json      机器可读清单
    _已删除行.txt      被当作广告/水印删掉的行（可复核；--keep-ads 可关闭清理）

仅用 Python 标准库，无需 pip install。

示例：
    py -3 novel_split.py probe  "G:\\txt"
    py -3 novel_split.py encode "G:\\txt" --to utf-8 --eol crlf
    py -3 novel_split.py analyze "G:\\txt" --json
    py -3 novel_split.py split   "G:\\txt" --parts 5 --json
    py -3 novel_split.py all     "G:\\txt" --encode --json      ← 一条命令跑完
    py -3 novel_split.py split   "G:\\txt\\混沌冠冕.txt" --mode volume --full
"""

from __future__ import annotations

import argparse
import codecs
import glob as globmod
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

# ------------------------------------------------------------------ 常量

CN_CHARS = "零〇○一二三四五六七八九十百千万两"
NUM_PAT = rf"[0-9０-９{CN_CHARS}]+"

CHAPTER_UNITS = "章回节話话"
VOLUME_UNITS = "卷部"
AMBIGUOUS_UNITS = "篇集"           # 不同小说里含义不同，按上下文自适应

# 注意：- 必须放最后或转义，否则会构成反向字符区间导致 re.error
DECOR_CHARS = r"=＝\-—–―*＊·・#＃_﹏~～ \t\u3000\u00a0"
DECOR_CLASS = f"[{DECOR_CHARS}]"
WRAPPERS = (("【", "】"), ("［", "］"), ("[", "]"), ("《", "》"),
            ("（", "）"), ("(", ")"), ("『", "』"), ("「", "」"))

SPECIAL_HEAD_RE = re.compile(
    r"^(序章|序言|序|楔子|引子|前言|卷首语|开篇|登场人物|人物介绍)\s*[：:、.，,\-—]?\s*(.*)$")
SPECIAL_TAIL_RE = re.compile(
    r"^(终章|尾声|后记|完本感言|完结感言|作者的话|番外篇|番外|特别篇|外传|附录)"
    r"\s*[：:、.，,\-—]?\s*(.*)$")

# 广告 / 水印特征：仅当“独立成行 + 足够短 + 不像正文”时才删
AD_PATTERNS = [re.compile(p, re.IGNORECASE) for p in (
    r"https?://", r"www\.", r"\.com\b", r"\.net\b", r"\.org\b", r"\.cc\b",
    r"搜书吧", r"笔趣", r"顶点小说", r"奇书网", r"书包网", r"燃文", r"飞卢",
    r"全本小说", r"无弹窗", r"手机阅读", r"手机版阅读", r"免费阅读", r"全文阅读",
    r"更新最快", r"最快更新", r"最新网址", r"备用地址", r"请记住本站", r"记住本站",
    r"本站域名", r"下载自", r"本书下载", r"txt下载", r"TXT下载", r"电子书下载",
    r"QQ群", r"书友群", r"微信公众号", r"本章未完", r"点击下一页", r"加入书架",
    r"投推荐票", r"求收藏", r"求月票", r"求订阅", r"求推荐", r"跪求", r"打赏",
    r"^\s*[（(]?本章完[)）]?\s*$",
    r"^\s*[（(]?未完待续[)）]?\s*$",
    r"^\s*[（(]?全文完[)）]?\s*$",
)]
SEPARATOR_RE = re.compile(r"^[\s\-—–―=＝*＊·・#＃_﹏~～.]{3,}$")

# 标题行里“单位字”后面若紧跟这些字，说明该单位是复合词的一部分，不是章节标记。
# 仅在“单位字后没有分隔符”时才启用，因此不会误杀「第10章重新开场抽取」这类真标题，
# 却能拦住「第二回合补卡两张。」「第543章之前好不容易过了」这类正文。
COMPOUND_BLOCK = {
    "回": "合来到去想过事声应答忆顾头家身",
    "节": "目奏约省能制假气日",
    "话": "题说语音",
    "章": "之节回程",
    "集": "合团中",
    "篇": "章幅目",
    "卷": "之起土子",
    "部": "",                 # 保留「第一部分」这类真正的分卷写法
}
# 卷标题里出现这些词说明它不是卷，而是卷末附言
VOLUME_TITLE_BLOCK = re.compile(r"本卷完|卷后语|卷末|本卷结束|卷尾|感言|后记|公告|请假|上架")
SEP_START_RE = re.compile(r"^[：:、.，,\-—～~・\s\u3000]")

HEADING_MAX_LEN = 60        # 标题行整行长度上限，超过即视为正文
HEADING_PUNCT_LEN = 30      # 含句号且超过此长度即视为正文
TOC_MIN_RUN = 5             # 连续密集标题达到此数量即判定为“目录/面板列表”并忽略
TOC_MAX_GAP = 2             # 密集块内相邻标题的行距上限
# 这些“短关键词”只有当后面不再紧跟序数时才可能是真标题（避免把「序九：血脉」当序章）
SHORT_SPECIAL = {"序", "引子", "前言", "楔子", "开篇"}
ORDINAL_HEAD = re.compile(r"^[0-9０-９零〇○一二三四五六七八九十百千万两]")
AI_CHUNK_CHARS = 100_000    # 未指定 --parts 时，每份的目标净字数（留出上下文余量）


# ------------------------------------------------------------------ 小工具

def cn_to_int(s: Optional[str]) -> Optional[int]:
    """中文/全角/阿拉伯数字转 int。支持 一 / 十 / 十一 / 一百零三 / 两。"""
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    digits = {"零": 0, "〇": 0, "○": 0, "一": 1, "壹": 1, "二": 2, "两": 2, "贰": 2,
              "三": 3, "叁": 3, "四": 4, "肆": 4, "五": 5, "伍": 5, "六": 6, "陆": 6,
              "七": 7, "柒": 7, "八": 8, "捌": 8, "九": 9, "玖": 9}
    units = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000,
             "万": 10000, "亿": 100000000}
    total = section = number = 0
    for ch in s:
        if ch in digits:
            number = digits[ch]
        elif ch in units:
            unit = units[ch]
            if unit >= 10000:
                section = (section + number) * unit
                total += section
                section = number = 0
            else:
                section += (number or 1) * unit
                number = 0
        else:
            return None
    return total + section + number


def cn_index(n: int) -> str:
    """1 -> 一, 11 -> 十一, 21 -> 二十一；>99 直接用阿拉伯数字。"""
    d = "零一二三四五六七八九"
    if n < 1:
        return str(n)
    if n < 10:
        return d[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + d[n % 10]
    if n < 100:
        return d[n // 10] + "十" + (d[n % 10] if n % 10 else "")
    return str(n)


ILLEGAL_FS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


def sanitize(name: str, limit: int = 80) -> str:
    name = unicodedata.normalize("NFC", name)
    name = ILLEGAL_FS.sub("_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if len(name) > limit:
        name = name[:limit].rstrip()
    return name or "untitled"


def strip_decorations(line: str) -> str:
    """去掉标题行两侧的 === / 括号 / 空白等装饰，仅用于识别，不用于输出。"""
    s = line.strip()
    prev = None
    while prev != s:
        prev = s
        s = re.sub(rf"^{DECOR_CLASS}+", "", s)
        s = re.sub(rf"{DECOR_CLASS}+$", "", s)
        for a, b in WRAPPERS:
            if len(s) > len(a) + len(b) and s.startswith(a) and s.endswith(b):
                s = s[len(a):-len(b)].strip()
    return s


def readable_book_name(stem: str) -> str:
    """从乱文件名里提取干净书名：《书名》（...）作者：x.txt -> 书名"""
    s = unicodedata.normalize("NFC", stem)
    m = re.search(r"《([^》]{1,60})》", s)
    if m:
        return sanitize(m.group(1).strip(), 60)
    s = re.split(r"作者[：:]", s)[0]
    s = re.sub(r"[（(【\[].*?[)）】\]]", "", s)
    s = re.split(r"[（(]", s)[0]
    return sanitize(s.strip() or stem, 60)


def net_chars(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def detect_and_decode(raw: bytes) -> tuple[str, str, bool]:
    """BOM → 严格 UTF-8 → GB18030/Big5。返回 (文本, 编码名, 是否无损)。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig").lstrip("\ufeff"), "utf-8 (BOM)", True
        except UnicodeDecodeError:
            pass
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16").lstrip("\ufeff"), "utf-16", True
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("utf-8").lstrip("\ufeff"), "utf-8", True
    except UnicodeDecodeError:
        pass
    for enc in ("gb18030", "big5"):
        try:
            return raw.decode(enc).lstrip("\ufeff"), enc, True
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace"), "utf-8 (有替换字符)", False


def strip_stray_bom(text: str) -> tuple[str, int]:
    """去掉正文里残留的零宽 U+FEFF（多 BOM 拼接的文件很常见，会污染正文）。

    返回 (清理后的文本, 清除个数)。
    """
    n = text.count("\ufeff")
    return (text.replace("\ufeff", ""), n) if n else (text, 0)


# ---------------------------------------------------------------- 编码统一

# 允许 --to / --from 指定的编码名 → Python 编解码器名
ENCODING_ALIASES = {
    "utf-8": "utf-8", "utf8": "utf-8",
    "utf-8-sig": "utf-8-sig", "utf8-sig": "utf-8-sig", "utf-8-bom": "utf-8-sig",
    "utf-16": "utf-16", "utf16": "utf-16",
    "utf-16-le": "utf-16-le", "utf-16-be": "utf-16-be",
    "gb18030": "gb18030", "gbk": "gbk", "gb2312": "gb2312", "cp936": "gbk",
    "big5": "big5", "big5hkscs": "big5hkscs",
    "ascii": "ascii", "latin-1": "latin-1",
}


def resolve_encoding(name: str) -> str:
    """把用户写的编码名解析成可用的 Python 编解码器名，并验证其存在。"""
    key = (name or "").strip().lower()
    cand = ENCODING_ALIASES.get(key, key)
    try:
        codecs.lookup(cand)
    except LookupError as e:
        raise ValueError(f"未知编码 {name!r}；支持：{', '.join(sorted(ENCODING_ALIASES))}") from e
    return cand


def eol_name(raw: bytes) -> str:
    if b"\r\n" in raw:
        return "crlf"
    if b"\r" in raw:
        return "cr"
    return "lf"


def bom_name(raw: bytes) -> Optional[str]:
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8"
    if raw.startswith(codecs.BOM_UTF16_LE):
        return "utf-16-le"
    if raw.startswith(codecs.BOM_UTF16_BE):
        return "utf-16-be"
    return None


def apply_eol(text: str, mode: str) -> str:
    """把换行统一成 crlf / lf；mode='keep' 时原样返回。"""
    if mode == "keep":
        return text
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    return t.replace("\n", "\r\n") if mode == "crlf" else t


def try_encode(text: str, target: str) -> tuple[bool, Optional[str], bytes]:
    """尝试无损编码：必须能严格编码，且回读后与原文完全一致。"""
    try:
        data = text.encode(target)
    except UnicodeEncodeError as e:
        bad = text[e.start:e.end]
        return False, (f"{target} 无法表示字符 {bad!r}（第 {e.start} 字符处）"), b""
    except LookupError as e:
        return False, str(e), b""
    if data.decode(target) != text:
        return False, f"{target} 编码后回读与原文不一致", data
    return True, None, data


def decode_with(raw: bytes, forced: Optional[str]) -> tuple[Optional[str], str, bool, Optional[str]]:
    """解码。forced 为 None 时自动探测。返回 (文本, 编码名, 是否无损, 错误)。"""
    if forced:
        enc = resolve_encoding(forced)
        try:
            return raw.decode(enc), f"{enc}（强制指定）", True, None
        except UnicodeDecodeError as e:
            return None, enc, False, f"按指定编码 {enc} 解码失败：{e}"
    text, enc, lossless = detect_and_decode(raw)
    return text, enc, lossless, None


def probe_file(path: Path, forced: Optional[str] = None) -> dict:
    """探测一个文件的编码/换行/BOM/可解码候选，供 AI 决策。不写盘。"""
    raw = path.read_bytes()
    text, enc, lossless, err = decode_with(raw, forced)
    info: dict = {
        "path": str(path), "name": path.name, "bytes": len(raw),
        "bom": bom_name(raw), "eol": eol_name(raw),
        "detected": enc, "decoded": text is not None, "lossless": lossless,
    }
    if err:
        info["error"] = err
    # 能无损解码该文件的候选编码（gb18030 几乎总能通过，故只作为参考）
    ok_candidates = []
    for cand in ("utf-8", "gb18030", "big5", "utf-16"):
        try:
            raw.decode(cand)
            ok_candidates.append(cand)
        except (UnicodeDecodeError, LookupError):
            pass
    info["decodable_as"] = ok_candidates
    info["ambiguous"] = len([c for c in ok_candidates if c != "utf-16"]) > 1
    if text is not None:
        info["chars"] = len(text)
        info["lines"] = text.count("\n") + (0 if text.endswith("\n") else 1)
        info["has_replacement_char"] = "\ufffd" in text
        info["stray_bom_chars"] = text.count("\ufeff")
    return info


def encode_file(path: Path, args, log) -> dict:
    """把一个文件统一到指定编码。默认就地改写并留 .bak 备份；已符合则跳过。"""
    raw = path.read_bytes()
    target = resolve_encoding(args.to)
    text, enc, lossless, err = decode_with(raw, args.from_enc)
    res: dict = {"path": str(path), "name": path.name, "from": enc, "to": target,
                 "bytes_in": len(raw), "ok": False, "action": "", "lossless": False}
    if err or text is None:
        res["error"] = err or "解码失败"
        return res
    if not lossless and args.strict:
        res["error"] = "源文件解码时产生了替换字符（可能有损坏字节）；加 --lenient 可强行继续"
        return res

    text, stray = strip_stray_bom(text)
    if stray:
        res["stray_bom_chars"] = stray
        log.say(f"    ℹ️ {path.name}: 清除正文内残留的零宽 BOM 字符 {stray} 个")

    new_text = apply_eol(text, args.eol)
    ok, why, data = try_encode(new_text, target)
    if not ok:
        res["error"] = why
        if args.strict:
            res["hint"] = ("该编码无法无损表示全文；改用 --to gb18030 或 --to utf-8，"
                           "或加 --lenient 允许有损替换")
            return res
        data = new_text.encode(target, errors="replace")
        res["lossy"] = True
        log.say(f"    ! {path.name}: {why} —— 已按 --lenient 有损替换")

    res["bytes_out"] = len(data)
    res["eol"] = args.eol

    # 目标：默认就地改写（留 .bak 备份）；给了 --out-dir 则写副本、不动源文件
    in_place = not args.out_dir
    dest = path if in_place else Path(args.out_dir) / path.name
    res["dest"] = str(dest)
    res["in_place"] = in_place

    # 已经就是目标编码 + 目标换行 → 幂等跳过，不产生多余写入
    if raw == data:
        res.update(ok=True, action="skip", lossless=True,
                   message="已是目标编码与换行，无需改动")
        return res
    if args.dry_run:
        res.update(ok=True, action="dry-run", lossless=not res.get("lossy"),
                   message="仅预演，未写盘")
        return res

    backup = None
    if in_place and not args.no_backup:
        backup = path.with_name(path.name + ".bak")
        if backup.exists():
            res["backup_kept"] = f"{backup.name} 已存在，保留最早的原始备份未覆盖"
        else:
            backup.write_bytes(raw)
    if not in_place:
        dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)

    # 写后回读校验：字节一致 + 能用目标编码解回同一文本
    back_raw = dest.read_bytes()
    verified = back_raw == data and back_raw.decode(target) == new_text
    res.update(ok=verified, action="written", lossless=not res.get("lossy"),
               verified=verified, backup=(backup.name if backup else None))
    if not verified:
        res["error"] = "写盘后回读校验失败，请检查磁盘/杀软干扰"
    return res


# ------------------------------------------------------------------ 数据结构

@dataclass
class Marker:
    kind: str                 # volume | chapter | special-head | special-tail
    unit: str
    num: Optional[int]
    title: str
    raw: str
    line_idx: int
    volume_idx: int = -1
    order: int = 0
    seg: int = 0
    chars: int = 0            # 正文净字数（不含标题行）

    @property
    def is_head_special(self) -> bool:
        return self.kind == "special-head"

    @property
    def is_chapter_like(self) -> bool:
        return self.kind in ("chapter", "special-head", "special-tail")


@dataclass
class Book:
    path: Path
    book: str
    encoding: str = ""
    lossless: bool = True
    raw_lines: list[str] = field(default_factory=list)
    norm_lines: list[str] = field(default_factory=list)
    removed: list[tuple[int, str]] = field(default_factory=list)
    mapping: dict[int, int] = field(default_factory=dict)
    volumes: list[Marker] = field(default_factory=list)
    chapters: list[Marker] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    preamble_lines: int = 0


# ------------------------------------------------------------------ 解析器

class Parser:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.chapter_re = re.compile(
            rf"^(?:正文\s*)?第\s*(?P<num>{NUM_PAT})\s*(?P<unit>[{CHAPTER_UNITS}])\s*(?P<rest>.*)$")
        self.volume_re = re.compile(
            rf"^(?:正文\s*)?第\s*(?P<num>{NUM_PAT})\s*(?P<unit>[{VOLUME_UNITS}])\s*(?P<rest>.*)$")
        self.volume_bare_re = re.compile(
            rf"^(?P<unit>[{VOLUME_UNITS}])\s*(?P<num>{NUM_PAT})\s*(?P<rest>.*)$")
        self.ambiguous_re = re.compile(
            rf"^(?:正文\s*)?第\s*(?P<num>{NUM_PAT})\s*(?P<unit>[{AMBIGUOUS_UNITS}])\s*(?P<rest>.*)$")
        if args.chapter_regex:
            self.chapter_re = re.compile(args.chapter_regex)
        if args.volume_regex:
            self.volume_re = re.compile(args.volume_regex)

    @staticmethod
    def _clean_title(rest: str) -> str:
        t = re.sub(rf"^[：:、.，,。\-—～~・\s]+", "", rest.strip())
        return re.sub(r"[：:、\s]+$", "", t).strip()

    @staticmethod
    def _looks_like_prose(line: str) -> bool:
        if len(line) > HEADING_MAX_LEN:
            return True
        if "。" in line and len(line) > HEADING_PUNCT_LEN:
            return True
        return False

    @staticmethod
    def _accept(unit: str, rest: str) -> bool:
        """单位字后没有分隔符时，用复合词黑名单否决（拦「回合」「章之前」这类正文）。"""
        if not rest or SEP_START_RE.match(rest):
            return True
        return rest[0] not in COMPOUND_BLOCK.get(unit, "")

    def scan(self, text: str, path: Path) -> Book:
        raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        bs = Book(path=path, book=readable_book_name(path.stem), raw_lines=raw_lines)

        # ---- 1) 逐行寻找候选标题 ----
        found: list[tuple[str, str, Optional[int], str, str, int]] = []
        ambiguous: list[tuple[str, Optional[int], str, str, int]] = []
        for i, raw in enumerate(raw_lines):
            s = strip_decorations(raw)
            if not s or self._looks_like_prose(s):
                continue
            m = self.volume_re.match(s) or self.volume_bare_re.match(s)
            if m and self._accept(m.group("unit"), m.group("rest")):
                title = self._clean_title(m.group("rest"))
                if not VOLUME_TITLE_BLOCK.search(title):
                    found.append(("volume", m.group("unit"), cn_to_int(m.group("num")),
                                  title, raw, i))
                    continue
            m = self.chapter_re.match(s)
            if m and self._accept(m.group("unit"), m.group("rest")):
                found.append(("chapter", m.group("unit"), cn_to_int(m.group("num")),
                              self._clean_title(m.group("rest")), raw, i))
                continue
            m = self.ambiguous_re.match(s)
            if m and self._accept(m.group("unit"), m.group("rest")):
                ambiguous.append((m.group("unit"), cn_to_int(m.group("num")),
                                  self._clean_title(m.group("rest")), raw, i))
                continue
            for rx, kind in ((SPECIAL_HEAD_RE, "special-head"), (SPECIAL_TAIL_RE, "special-tail")):
                m = rx.match(s)
                if m:
                    title = self._clean_title(m.group(2))
                    # 「序」「引子」这类短词后面直接跟序数，通常是正文里的列表项
                    if kind == "special-head" and m.group(1) in SHORT_SPECIAL and ORDINAL_HEAD.match(title):
                        break
                    found.append((kind, m.group(1), None, title, raw, i))
                    break

        # ---- 2) 目录/面板列表过滤：连续密集标题 ----
        found = self._drop_toc(found, bs)

        # ---- 3) 判定「篇/集」是卷还是章 ----
        vol_like = sum(1 for f in found if f[0] == "volume")
        chap_like = sum(1 for f in found if f[0] == "chapter")
        if ambiguous:
            as_volume = vol_like < 2 and chap_like == 0
            target = "volume" if as_volume else "chapter"
            bs.notes.append(
                f"把 {len(ambiguous)} 个「{'/'.join(AMBIGUOUS_UNITS)}」标记当作"
                f"{'卷' if as_volume else '章'}处理（卷标记 {vol_like} 个、章标记 {chap_like} 个）。")
            found.extend((target, u, n, t, r, i) for u, n, t, r, i in ambiguous)
            found = self._drop_toc(found, bs, label="篇/集")

        markers = [Marker(kind=k, unit=u, num=n, title=t, raw=r, line_idx=i, order=o)
                   for o, (k, u, n, t, r, i) in enumerate(found)]
        markers.sort(key=lambda m: m.line_idx)
        for o, m in enumerate(markers):
            m.order = o

        if self.args.dump_markers:
            out = path.with_suffix(".markers.tsv")
            with out.open("w", encoding="utf-8", newline="") as f:
                f.write("line\tkind\tunit\tnum\ttitle\n")
                for m in markers:
                    f.write(f"{m.line_idx + 1}\t{m.kind}\t{m.unit}\t{m.num}\t{m.title}\n")
            print(f"    [dump] {out.name}", file=sys.stderr if LOG.json_mode else sys.stdout)

        bs.volumes = [m for m in markers if m.kind == "volume"]
        bs.chapters = [m for m in markers if m.is_chapter_like]

        # ---- 4) 章节归属到卷 ----
        vols = sorted(bs.volumes, key=lambda m: m.line_idx)
        cursor = 0
        vi = -1
        for m in markers:
            while cursor < len(vols) and vols[cursor].line_idx < m.line_idx:
                cursor += 1
                vi = cursor - 1
            m.volume_idx = vi
        for k, v in enumerate(vols):
            v.volume_idx = k
        bs.preamble_lines = (bs.chapters[0].line_idx if bs.chapters
                             else (vols[0].line_idx if vols else 0))

        # ---- 5) 章节净字数 ----
        self._fill_chars(bs, raw_lines)

        # ---- 6) 剔除空壳重复标题（同卷同号、无标题/同标题、正文极短） ----
        dropped = self._drop_duplicate_shells(bs)
        if dropped:
            bs.notes.append(f"剔除 {dropped} 个空壳重复标题（同卷同章号、标题为空或与兄弟相同、"
                            f"正文 < 50 字），其行文已并入前一章，未丢失内容。")
            self._fill_chars(bs, raw_lines)
        return bs

    @staticmethod
    def _fill_chars(bs: Book, raw_lines: list[str]) -> None:
        for k, m in enumerate(bs.chapters):
            nxt = bs.chapters[k + 1].line_idx if k + 1 < len(bs.chapters) else len(raw_lines)
            m.chars = sum(net_chars(ln) for ln in raw_lines[m.line_idx + 1:nxt])

    @staticmethod
    def _drop_duplicate_shells(bs: Book) -> int:
        groups: dict[tuple[int, Optional[int]], list[Marker]] = {}
        for m in bs.chapters:
            if m.kind == "chapter" and m.num is not None:
                groups.setdefault((m.volume_idx, m.num), []).append(m)
        doomed: set[int] = set()
        for items in groups.values():
            if len(items) < 2:
                continue
            keep = max(items, key=lambda m: (bool(m.title), m.chars, -m.line_idx))
            for m in items:
                if m is keep:
                    continue
                if m.chars < 50 and (not m.title or m.title == keep.title):
                    doomed.add(id(m))
        if not doomed:
            return 0
        bs.chapters = [m for m in bs.chapters if id(m) not in doomed]
        return len(doomed)

    def _drop_toc(self, found, bs: Book, label: str = "") -> list:
        """剔除“目录页/面板列表”式的密集标题（连续 >= TOC_MIN_RUN 且行距 <= TOC_MAX_GAP）。

        真实章节之间必有正文，因此连续多行标题几乎不可能是真章节。
        """
        idxs = [k for k, f in enumerate(found) if f[0] != "volume"]
        run: list[int] = []
        toc: list[int] = []
        for k in idxs:
            if run and found[k][5] - found[run[-1]][5] <= TOC_MAX_GAP:
                run.append(k)
            else:
                if len(run) >= TOC_MIN_RUN:
                    toc.extend(run)
                run = [k]
        if len(run) >= TOC_MIN_RUN:
            toc.extend(run)
        if not toc:
            return found
        hits = sorted(found[k][5] for k in toc)
        bs.notes.append(f"疑似目录/列表{label}：第 {hits[0] + 1}–{hits[-1] + 1} 行"
                        f"共 {len(toc)} 个密集标题已忽略。")
        drop = set(toc)
        return [f for k, f in enumerate(found) if k not in drop]


# ------------------------------------------------------------------ 规范化

class Normalizer:
    def __init__(self, args: argparse.Namespace):
        self.args = args

    def _clean(self, line: str) -> tuple[Optional[str], bool]:
        if self.args.keep_ads:
            return line.rstrip(), False
        s = line.strip()
        if not s:
            return "", False
        if SEPARATOR_RE.match(s):
            return "", False
        if len(s) <= 80 and not s.startswith(("“", "「", "『", "\"")):
            for rx in AD_PATTERNS:
                if rx.search(s):
                    return None, True
        return line.rstrip(), False

    def run(self, bs: Book) -> None:
        args = self.args
        headings = {m.line_idx for m in bs.volumes + bs.chapters}
        indent = "\u3000" * args.indent if args.indent > 0 else ""
        out: list[str] = []
        removed: list[tuple[int, str]] = []
        mapping: dict[int, int] = {}
        blanks = 0

        for i, raw in enumerate(bs.raw_lines):
            kept, is_ad = self._clean(raw)
            if kept is None:
                removed.append((i + 1, raw.strip()))
                continue
            if i in headings:
                blanks = 0
                text = raw.strip() if args.heading_style == "keep" else strip_decorations(raw)
            elif kept == "":
                blanks += 1
                if blanks > args.max_blank:
                    continue
                text = ""
            else:
                blanks = 0
                body = re.sub(r"^[\s\u3000\u00a0]+", "", kept).rstrip()
                # 正文之前的前置内容（书名/作者/简介）不缩进
                if i < bs.preamble_lines:
                    text = body
                else:
                    text = indent + body
            out.append(text)
            mapping[i] = len(out) - 1

        bs.norm_lines, bs.removed, bs.mapping = out, removed, mapping
        bs.notes.append(f"规范化：{len(bs.raw_lines):,} 行 → {len(out):,} 行，"
                        f"清理疑似广告/分隔线 {len(removed)} 行。")

        if args.heading_style == "normalize":
            for m in bs.volumes + bs.chapters:
                if m.num is None:
                    continue
                idx = mapping.get(m.line_idx)
                if idx is not None:
                    title = f" {m.title}" if m.title else ""
                    bs.norm_lines[idx] = f"第{m.num}{m.unit}{title}"


# ------------------------------------------------------------------ 排序

def sort_chapters(chapters: Sequence[Marker], args):
    """按卷分组，组内按章号排序；自动识别章号重置并分段。

    --sort off   保持原始顺序
    --sort auto  （默认）识别章号重置后分段排序；文件本来有序时不动任何一章
    --sort force 忽略章号重置，整卷按章号一次性排序（用于确实被打乱的文件）

    返回 (有序章节, 说明, 位置调整审计)。
    """
    mode = "off" if getattr(args, "no_sort", False) else getattr(args, "sort", "auto")
    notes: list[str] = []
    moves: list[tuple[Marker, int, int]] = []
    groups: dict[int, list[Marker]] = {}
    for c in chapters:
        groups.setdefault(c.volume_idx, []).append(c)

    ordered: list[Marker] = []
    for vi in sorted(groups):
        items = groups[vi]
        numbered = [c for c in items if c.kind == "chapter" and c.num is not None]
        nums = [c.num for c in numbered]
        inversions = sum(1 for a, b in zip(nums, nums[1:]) if a > b)
        if mode == "off" or not inversions:
            ordered.extend(items)          # 本来就顺：一个字都不动
            continue

        seg = 0
        if mode == "auto":
            for prev, cur in zip(numbered, numbered[1:]):
                if cur.num is not None and prev.num is not None and cur.num <= prev.num:
                    seg += 1
                cur.seg = seg
        # 未编号的特殊章（序章/番外/后记）不做首尾归拢，而是锚定到它前面那一章之后，
        # 这样只有真正乱序的章节才会移动，避免“抬到开头”造成全书索引整体位移。
        anchor: dict[int, tuple[int, int]] = {}
        last = (-1, 0)
        for c in items:
            if c.kind == "chapter" and c.num is not None:
                last = (c.seg if mode == "auto" else 0, c.num)
            anchor[id(c)] = last
        result = sorted(
            items, key=lambda c: (*anchor[id(c)], 0 if c.kind == "chapter" else 1, c.order))

        before = {id(c): k for k, c in enumerate(items)}
        local = 0
        for k, c in enumerate(result):
            if before[id(c)] != k:
                moves.append((c, before[id(c)], k))
                local += 1
        ordered.extend(result)
        label = f"卷{vi + 1}" if vi >= 0 else "卷前内容"
        if local:
            notes.append(f"{label}：发现 {inversions} 处章号逆序，已重排 {len(numbered)} 章"
                         f"（分 {seg + 1} 段，疑似章号重置），实际移动 {local} 章，"
                         f"明细见 _排序调整.tsv。")
        else:
            notes.append(f"{label}：发现 {inversions} 处章号逆序（疑似章号重置或原书笔误），"
                         f"但分段排序后无需移动任何一章，已保持原始顺序；"
                         f"若确认原书被打乱请加 --sort force。")
    return ordered, notes, moves


# ------------------------------------------------------------------ 切分策略

def split_by_volumes(ordered: Sequence[Marker], volumes: Sequence[Marker]):
    groups: dict[int, list[Marker]] = {}
    for c in ordered:
        groups.setdefault(max(c.volume_idx, 0), []).append(c)
    parts = []
    for k, v in enumerate(sorted(volumes, key=lambda m: m.line_idx)):
        marker = f"第{v.num}{v.unit}" if v.num is not None else v.unit
        name = f"{marker} {v.title}".strip() if v.title else marker
        parts.append((name, [v] + groups.get(k, [])))
    return parts


def split_by_parts(ordered: Sequence[Marker], n: int):
    items = list(ordered)
    n = max(1, min(n, len(items)))
    target = (sum(c.chars for c in items) or 1) / n
    parts, cur, acc, remaining = [], [], 0, n
    for i, c in enumerate(items):
        cur.append(c)
        acc += c.chars
        if remaining - 1 > 0 and acc >= target and len(items) - i - 1 >= remaining - 1:
            parts.append(cur)
            cur, acc = [], 0
            remaining -= 1
    if cur:
        parts.append(cur)
    return [(f"第{cn_index(i + 1)}部分", p) for i, p in enumerate(parts)]


def split_by_maxchars(ordered: Sequence[Marker], max_chars: int):
    parts, cur, acc = [], [], 0
    for c in ordered:
        if cur and acc + c.chars > max_chars:
            parts.append(cur)
            cur, acc = [], 0
        cur.append(c)
        acc += c.chars
    if cur:
        parts.append(cur)
    return [(f"第{cn_index(i + 1)}部分", p) for i, p in enumerate(parts)]


def build_spans(bs: Book, parts) -> list[tuple[str, list[Marker], int, int]]:
    """把各份映射成规范化文本中的 [start, end) 行区间；首份从 0 开始以纳入前置内容。"""
    rows = []
    for name, ms in parts:
        idxs = [bs.mapping[m.line_idx] for m in ms if m.line_idx in bs.mapping]
        if idxs:
            rows.append([name, ms, min(idxs)])
    if not rows:
        return []
    rows.sort(key=lambda r: r[2])
    rows[0][2] = 0
    spans = []
    for k, (name, ms, st) in enumerate(rows):
        en = rows[k + 1][2] if k + 1 < len(rows) else len(bs.norm_lines)
        spans.append((name, ms, st, max(st, en)))
    return spans


# ------------------------------------------------------------------ 写盘

def write_book(bs: Book, ordered: list[Marker], parts, args, moves=(), mode: str = "") -> dict:
    outdir = Path(args.out) / sanitize(bs.book, 60)
    if not args.dry_run:
        outdir.mkdir(parents=True, exist_ok=True)
    eol = "\r\n" if args.eol == "crlf" else "\n"
    enc = "utf-8-sig" if args.bom else "utf-8"
    chapters_n = sum(1 for m in ordered if m.kind == "chapter")
    specials_n = sum(1 for m in ordered if m.kind.startswith("special"))

    spans = build_spans(bs, parts)
    files, total = [], 0
    for name, ms, st, en in spans:
        body = bs.norm_lines[st:en]
        chars = sum(net_chars(l) for l in body)
        total += chars
        fname = f"{sanitize(bs.book, 60)}_{sanitize(name, 60)}.txt"
        text = eol.join(body) + (eol if body else "")
        if not args.dry_run:
            (outdir / fname).write_text(text, encoding=enc, newline="")
        chapters = [m for m in ms if m.is_chapter_like]
        files.append({
            "file": fname,
            "part": name,
            "chapters": len(chapters),
            "chars": chars,
            "lines": len(body),
            "line_range": [st, en],
            "first_chapter": (chapters[0].raw.strip() if chapters else (ms[0].raw.strip() if ms else "")),
            "last_chapter": (chapters[-1].raw.strip() if chapters else ""),
        })

    if args.full and not args.dry_run:
        fname = f"{sanitize(bs.book, 60)}_全本_规范化.txt"
        (outdir / fname).write_text(eol.join(bs.norm_lines) + eol, encoding=enc, newline="")

    # 完整性回读校验
    verified, mismatch = 0, []
    if not args.dry_run:
        for f in files:
            p = outdir / f["file"]
            got = net_chars(p.read_text(encoding=enc)) if p.exists() else -1
            if got == f["chars"]:
                verified += 1
            else:
                mismatch.append((f["file"], f["chars"], got))

    vol_of = {id(v): f"第{v.num}{v.unit}" if v.num is not None else v.unit
              for k, v in enumerate(sorted(bs.volumes, key=lambda m: m.line_idx))}

    if not args.dry_run:
        # ---- 目录索引：给 AI（或人）看的“哪份文件装了什么” ----
        idx = [f"# 《{bs.book}》拆分索引", "",
               f"- 源文件：`{bs.path.name}`",
               f"- 编码：{bs.encoding} → 输出 UTF-8"
               f"{' (BOM)' if args.bom else ''}，换行 {args.eol.upper()}",
               f"- 行数：{len(bs.raw_lines):,} → 规范化后 {len(bs.norm_lines):,}"
               f"（清理广告/分隔线 {len(bs.removed)} 行）",
               f"- 全文净字数：{total:,}",
               f"- 结构：卷 {len(bs.volumes)} 个 / 章 {chapters_n} 章 / 特殊章 {specials_n} 个",
               f"- 切分方式：{mode}，共 {len(files)} 份，**净字数零丢失**"
               f"（{verified}/{len(files)} 份回读校验一致）",
               f"- 正文段首缩进：{args.indent} 个全角空格",
               ""]
        if moves:
            idx.append(f"> 章节排序移动了 {len(moves)} 章，明细见 `_排序调整.tsv`；"
                       f"如需保持原始顺序请用 `--sort off` 重跑。")
            idx.append("")
        idx += ["## 文件清单", "",
                "| # | 文件 | 章数 | 净字数 | 起 | 止 |", "|---|---|---|---|---|---|"]
        for k, f in enumerate(files, 1):
            idx.append(f"| {k} | `{f['file']}` | {f['chapters']} | {f['chars']:,} | "
                       f"{f['first_chapter'][:34]} | {f['last_chapter'][:34]} |")
        idx += ["", "## 全部章节", "",
                "章节号/标题/净字数/所在份的完整清单见 `01_章节清单.tsv`。", ""]
        if bs.notes:
            idx += ["## 处理提示", ""]
            idx += [f"- {n}" for n in bs.notes]
            idx.append("")
        if bs.removed:
            idx += [f"> 被删掉的 {len(bs.removed)} 行疑似广告/水印已存档在 `_已删除行.txt`，"
                    f"如误删正文请加 `--keep-ads` 重跑。", ""]
        (outdir / "00_目录索引.md").write_text("\n".join(idx), encoding="utf-8")

        # 章节清单
        with (outdir / "01_章节清单.tsv").open("w", encoding="utf-8", newline="") as f:
            f.write("序号\t类型\t卷\t章号\t标题\t原行号\t净字数\n")
            vols = sorted(bs.volumes, key=lambda m: m.line_idx)
            for i, m in enumerate(ordered, 1):
                vol = vol_of.get(id(vols[m.volume_idx]), "") if 0 <= m.volume_idx < len(vols) else ""
                f.write(f"{i}\t{m.kind}\t{vol}\t{m.num if m.num is not None else ''}\t"
                        f"{m.title or m.raw.strip()}\t{m.line_idx + 1}\t{m.chars}\n")
        # 删除行审计
        if bs.removed:
            with (outdir / "_已删除行.txt").open("w", encoding="utf-8", newline="") as f:
                f.write(f"# 被判定为广告/水印/分隔线而删除的行，共 {len(bs.removed)} 行\n")
                f.write("# 若误删正文，请加 --keep-ads 重新运行\n\n")
                for ln, txt in bs.removed:
                    f.write(f"{ln}\t{txt}\n")
        # 排序调整审计：哪一章被搬动了
        if moves:
            with (outdir / "_排序调整.tsv").open("w", encoding="utf-8", newline="") as f:
                f.write("# 章节排序时发生位置变动的记录（原位置 -> 新位置）\n")
                f.write("# 若发现搬动不合理，请用 --no-sort 重跑以保持原始顺序\n\n")
                f.write("章号\t标题\t卷\t原行号\t原位置\t新位置\n")
                vols = sorted(bs.volumes, key=lambda m: m.line_idx)
                for m, old, new in moves:
                    vol = vol_of.get(id(vols[m.volume_idx]), "") if 0 <= m.volume_idx < len(vols) else ""
                    f.write(f"{m.num if m.num is not None else ''}\t{m.title or m.raw.strip()}\t"
                            f"{vol}\t{m.line_idx + 1}\t{old + 1}\t{new + 1}\n")
        manifest = {
            "book": bs.book, "source": str(bs.path), "encoding": bs.encoding,
            "lossless_decode": bs.lossless,
            "raw_lines": len(bs.raw_lines), "norm_lines": len(bs.norm_lines),
            "removed_lines": len(bs.removed), "volumes": len(bs.volumes),
            "preamble_lines": bs.preamble_lines,
            "chapters": sum(1 for m in ordered if m.kind == "chapter"),
            "specials": sum(1 for m in ordered if m.kind.startswith("special")),
            "total_chars": total, "files": files,
            "verify": {"checked": verified, "mismatch": mismatch},
            "notes": bs.notes,
        }
        (outdir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"outdir": outdir, "files": files, "total": total,
            "verified": verified, "mismatch": mismatch,
            "norm_total": sum(net_chars(l) for l in bs.norm_lines)}


# ------------------------------------------------------------------ 单本流程

def process(path: Path, args) -> dict:
    raw = path.read_bytes()
    text, enc, lossless = detect_and_decode(raw)
    text, stray = strip_stray_bom(text)
    bs = Parser(args).scan(text, path)
    bs.encoding, bs.lossless = enc, lossless
    if stray:
        bs.notes.append(f"清除正文内残留的零宽 BOM 字符 {stray} 个。")
    Normalizer(args).run(bs)

    ordered, sort_notes, moves = sort_chapters(bs.chapters, args)
    bs.notes.extend(sort_notes)
    if not ordered:
        return {"error": "未识别到任何章节", "bs": bs, "path": path}

    total_chars = sum(c.chars for c in ordered)
    # --parts 未指定时按“AI 友好的单份体量”自动推荐份数
    if args.parts and args.parts > 0:
        auto_parts = False
        n_parts = args.parts
    else:
        auto_parts = True
        n_parts = max(1, -(-total_chars // AI_CHUNK_CHARS))

    use_volume = (args.mode == "volume"
                  or (args.mode == "auto" and len(bs.volumes) >= args.min_volumes))
    if use_volume and bs.volumes:
        parts, chosen = split_by_volumes(ordered, bs.volumes), "按卷"
    elif use_volume:
        bs.notes.append("未发现卷标记，回退为按数量均分。")
        if auto_parts:
            bs.notes.append(f"未指定 --parts，按每份约 {AI_CHUNK_CHARS // 1000}K 字自动切为 "
                            f"{n_parts} 份（可用 --parts N 覆盖）。")
        parts, chosen = split_by_parts(ordered, n_parts), "按数量(回退)"
    elif args.mode == "chars" or (args.mode == "auto" and args.max_chars):
        budget = args.max_chars or AI_CHUNK_CHARS
        parts, chosen = split_by_maxchars(ordered, budget), f"按字数≤{budget:,}"
    else:
        if auto_parts:
            bs.notes.append(f"未指定 --parts，按每份约 {AI_CHUNK_CHARS // 1000}K 字自动切为 "
                            f"{n_parts} 份（可用 --parts N 覆盖）。")
        parts, chosen = split_by_parts(ordered, n_parts), f"按数量{n_parts}份"
    stats_mode = chosen + ("（自动份数）" if auto_parts and "数量" in chosen else "")

    stats = {
        "book": bs.book, "path": str(path), "encoding": enc, "lossless": lossless,
        "raw_lines": len(bs.raw_lines), "norm_lines": len(bs.norm_lines),
        "removed": len(bs.removed), "volumes": len(bs.volumes),
        "chapters": sum(1 for m in ordered if m.kind == "chapter"),
        "specials": sum(1 for m in ordered if m.kind.startswith("special")),
        "mode": stats_mode,
        "parts": len(parts), "notes": list(bs.notes), "moves": len(moves),
    }
    out = {"path": path, "book": bs.book, "bs": bs, "ordered": ordered,
           "parts": parts, "stats": stats, "mode": chosen, "moves": moves}

    if args.analyze_only:
        return out

    w = write_book(bs, ordered, parts, args, moves, chosen)
    stats.update({
        "outdir": str(w["outdir"]), "out_chars": w["total"], "norm_chars": w["norm_total"],
        "loss": w["total"] - w["norm_total"], "verified": w["verified"],
        "mismatch": w["mismatch"], "files": [f["file"] for f in w["files"]],
    })
    out["written"] = w
    return out


# ------------------------------------------------------------------ 输出/退出码

EXIT_OK = 0          # 全部成功
EXIT_PARTIAL = 1     # 部分文件失败
EXIT_NO_INPUT = 2    # 没有找到可处理的输入
EXIT_LOSS = 3        # 校验失败 / 严格模式下编码无法无损表示


class Reporter:
    """统一输出：开启 --json 时，人类可读信息走 stderr，stdout 只保留纯 JSON。"""

    def __init__(self, json_mode: bool = False, quiet: bool = False):
        self.json_mode = json_mode
        self.quiet = quiet

    def say(self, msg: str = "") -> None:
        if self.json_mode:
            print(msg, file=sys.stderr)
        elif not self.quiet:
            print(msg)

    def emit(self, payload: dict) -> None:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


LOG = Reporter()


def err_exit(message: str, code: int = EXIT_PARTIAL) -> int:
    LOG.say(f"错误：{message}")
    if LOG.json_mode:
        LOG.emit({"ok": False, "error": message})
    return code


# ------------------------------------------------------------------ 报告

def collect_inputs(items: Sequence[str]) -> list[Path]:
    files: list[Path] = []
    for it in items:
        p = Path(it)
        if p.is_dir():
            files.extend(sorted(x for x in p.glob("*.txt") if x.is_file()))
        elif p.is_file():
            files.append(p)
        else:
            try:
                files.extend(sorted(Path(m) for m in globmod.glob(it, recursive=True)
                                    if Path(m).is_file()))
            except (ValueError, OSError) as e:
                LOG.say(f"  ! 无法展开通配符 {it!r}：{e}")
    seen, uniq = set(), []
    for f in files:
        r = f.resolve()
        if r not in seen:
            seen.add(r)
            uniq.append(f)
    return uniq


def book_report(res: dict) -> str:
    s = res["stats"]
    bs: Book = res["bs"]
    ordered: list[Marker] = res["ordered"]
    L = [f"### {s['book']}", "",
         f"- 源文件：`{Path(s['path']).name}`",
         f"- 编码：{s['encoding']} → 输出 UTF-8（解码{'无损' if s['lossless'] else '有替换字符'}）",
         f"- 行数：{s['raw_lines']:,} → {s['norm_lines']:,}（清理广告/分隔线 {s['removed']} 行）",
         f"- 结构：**卷 {s['volumes']} 个 / 章 {s['chapters']} 章 / 特殊章 {s['specials']} 个**"]

    if "out_chars" in s:
        flag = "✅ 零丢失" if s["loss"] == 0 else f"⚠️ 差异 {s['loss']:+}"
        L.append(f"- 切分：{s['mode']} → {len(s['files'])} 个文件，"
                 f"净字数 {s['out_chars']:,} / 全文 {s['norm_chars']:,}，{flag}"
                 f"（回读校验 {s['verified']}/{len(s['files'])} 个文件一致）")
    else:
        L.append(f"- 切分方式：{s['mode']} → 预计 {s['parts']} 份")
    if s.get("moves"):
        L.append(f"- 章节排序共调整 {s['moves']} 处位置，明细见 `_排序调整.tsv`"
                 f"（不满意可用 `--no-sort` 保持原顺序）")
    for n in s["notes"]:
        L.append(f"- ℹ️ {n}")

    vols = sorted(bs.volumes, key=lambda m: m.line_idx)
    if vols:
        counts: dict[int, int] = {}
        for c in bs.chapters:
            counts[c.volume_idx] = counts.get(c.volume_idx, 0) + 1
        L += ["", "| # | 卷 | 卷名 | 起始行 | 章数 |", "|---|---|---|---|---|"]
        if -1 in counts:
            L.append(f"| — | （卷前内容） | 书名/作者/简介 | 1 | {counts[-1]} |")
        for k, v in enumerate(vols):
            L.append(f"| {k + 1} | 第{v.num}{v.unit} | {v.title or '—'} | "
                     f"{v.line_idx + 1:,} | {counts.get(k, 0)} |")

    ch = [c for c in ordered if c.kind == "chapter" and c.num is not None]
    if ch:
        nums = [c.num for c in ch]
        seen, dup = set(), []
        for n in nums:
            if n in seen and n not in dup:
                dup.append(n)
            seen.add(n)
        miss = sorted(set(range(min(nums), max(nums) + 1)) - seen)
        L += ["", f"- 章号范围 {min(nums)}–{max(nums)}；重复号 {len(dup)} 个"
                  f"{'：' + '、'.join(map(str, sorted(dup)[:15])) if dup else ''}；"
                  f"缺号 {len(miss)} 个{'：' + '、'.join(map(str, miss[:15])) if miss else ''}"]
        thin = [c for c in ch if c.chars < 100]
        if thin:
            L.append(f"- ⚠️ 净字数 < 100 的疑似误判章节 {len(thin)} 个，例如："
                     + "；".join(f"第{c.line_idx + 1}行「{c.raw.strip()[:22]}」({c.chars}字)"
                                 for c in thin[:5]))
    L.append("")
    return "\n".join(L)


# ------------------------------------------------------------------ CLI

VERSION = "1.0"


def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("inputs", nargs="*", help="txt 文件 / 目录 / glob，可多个")
    p.add_argument("--out", default="output", help="输出根目录（默认 ./output）")
    p.add_argument("--mode", choices=["auto", "volume", "parts", "chars"], default="auto",
                   help="auto=有卷按卷、无卷按数量（默认）；chars=按字数上限")
    p.add_argument("--parts", type=int, default=0,
                   help=f"无卷时均分为几份；不指定则按每份约 {AI_CHUNK_CHARS // 1000}K 字自动决定")
    p.add_argument("--max-chars", type=int, default=0, help="每份净字数上限")
    p.add_argument("--min-volumes", type=int, default=2, help="auto 下至少几个卷才按卷切（默认 2）")
    p.add_argument("--indent", type=int, default=2, help="正文缩进的全角空格数（默认 2，0=不缩进）")
    p.add_argument("--max-blank", type=int, default=1, help="连续空行最多保留几行（默认 1）")
    p.add_argument("--eol", choices=["crlf", "lf"], default="crlf", help="换行符（默认 crlf）")
    p.add_argument("--bom", action="store_true", help="输出带 UTF-8 BOM")
    p.add_argument("--keep-ads", action="store_true", help="不清理广告/水印行")
    p.add_argument("--heading-style", choices=["keep", "normalize"], default="keep",
                   help="normalize=统一为「第N章 标题」阿拉伯数字样式")
    p.add_argument("--sort", choices=["auto", "force", "off"], default="auto",
                   help="auto=识别章号重置后分段排序（默认）；force=整卷按章号重排；off=保持原顺序")
    p.add_argument("--no-sort", action="store_true", help="等价于 --sort off")
    p.add_argument("--chapter-regex", default=None, help="自定义章节正则（num/unit/rest 命名组）")
    p.add_argument("--volume-regex", default=None, help="自定义卷正则")
    p.add_argument("--dump-markers", action="store_true", help="输出识别到的标题行清单 tsv")
    p.add_argument("--dry-run", action="store_true", help="只统计不写文件")
    add_output_flags(p)


def add_output_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true",
                   help="stdout 只输出机器可读 JSON（人类信息转 stderr），便于 AI/脚本调用")
    p.add_argument("--quiet", action="store_true", help="不打印过程信息")


def gather(args) -> list[Path]:
    """收集待处理的 txt，跳过临时文件与输出目录里的产物。"""
    items = getattr(args, "inputs", None) or ["."]
    outs = set()
    for attr in ("out", "out_dir"):
        v = getattr(args, attr, None)
        if v:
            try:
                outs.add(Path(v).resolve())
            except OSError:
                pass
    files = []
    for f in collect_inputs(items):
        if f.suffix.lower() != ".txt" or f.name.startswith("_"):
            continue
        try:
            if f.resolve().parent in outs:
                continue
        except OSError:
            pass
        files.append(f)
    return files


def result_json(res: dict, cmd: str) -> dict:
    """把内部结果整理成稳定的 JSON 结构（AI 消费用）。"""
    s = res.get("stats", {})
    payload: dict = {
        "command": cmd,
        "ok": not res.get("error"),
        "book": res.get("book"),
        "source": s.get("path"),
        "encoding": s.get("encoding"),
        "decode_lossless": s.get("lossless"),
        "volumes": s.get("volumes"),
        "chapters": s.get("chapters"),
        "specials": s.get("specials"),
        "removed_lines": s.get("removed"),
        "mode": s.get("mode"),
        "moves": s.get("moves", 0),
        "notes": s.get("notes", []),
    }
    if res.get("error"):
        payload["error"] = res["error"]
    if "out_chars" in s:
        payload.update({
            "out_dir": s.get("outdir"),
            "total_chars": s.get("out_chars"),
            "normalized_chars": s.get("norm_chars"),
            "loss": s.get("loss"),
            "verified_files": s.get("verified"),
            "file_count": len(s.get("files", [])),
            "files": res.get("written", {}).get("files", []),
        })
    else:
        payload["planned_parts"] = s.get("parts")
    return payload


def run_split_like(args) -> int:
    files = gather(args)
    if not files:
        return err_exit("没有找到可处理的 txt 文件。", EXIT_NO_INPUT)

    LOG.say(f"待处理 {len(files)} 个文件 | 模式={args.mode} | 输出={Path(args.out).resolve()}")
    reports, payloads, ok, loss = [], [], 0, 0
    for f in files:
        LOG.say(f"\n>>> {f.name}")
        try:
            res = process(f, args)
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            reports.append(f"### {f.name}\n\n- ❌ 处理失败：{e}\n")
            payloads.append({"command": args.cmd, "ok": False,
                             "source": str(f), "error": str(e)})
            continue
        if res.get("error"):
            LOG.say(f"    ✗ {res['error']}")
            reports.append(f"### {f.name}\n\n- ❌ {res['error']}\n")
            payloads.append(result_json(res, args.cmd))
            continue
        ok += 1
        s = res["stats"]
        LOG.say(f"    编码={s['encoding']} 卷={s['volumes']} 章={s['chapters']} "
                f"特殊={s['specials']} 清理={s['removed']}行 方式={s['mode']}")
        if "out_chars" in s:
            flag = "✅" if s["loss"] == 0 else "⚠️"
            if s["loss"]:
                loss += 1
            LOG.say(f"    {len(s['files'])} 个文件 | 净字数 {s['out_chars']:,} / "
                    f"{s['norm_chars']:,} {flag} | 校验 {s['verified']}/{len(s['files'])}")
            for name in s["files"]:
                LOG.say(f"      - {name}")
        reports.append(book_report(res))
        payloads.append(result_json(res, args.cmd))

    if args.cmd == "analyze":
        rp = Path(args.report) if args.report else Path(args.out) / "分析报告.md"
        rp.parent.mkdir(parents=True, exist_ok=True)
        rp.write_text("# 小说结构分析报告\n\n" + "\n".join(reports), encoding="utf-8")
        LOG.say(f"\n分析报告：{rp.resolve()}")
        if args.json:
            for p in payloads:
                p["report_path"] = str(rp)

    if args.json:
        LOG.emit({
            "command": args.cmd, "ok": ok == len(files), "mode": args.mode,
            "summary": {"total": len(files), "succeeded": ok,
                        "failed": len(files) - ok, "loss_detected": loss},
            "books": payloads,
        })
    else:
        LOG.say(f"\n完成 {ok}/{len(files)} 本。")

    if loss:
        return EXIT_LOSS
    return EXIT_OK if ok == len(files) else EXIT_PARTIAL


def cmd_probe(args) -> int:
    files = gather(args)
    if not files:
        return err_exit("没有找到可处理的 txt 文件。", EXIT_NO_INPUT)

    rows = []
    for f in files:
        try:
            info = probe_file(f, args.from_enc)
        except Exception as e:  # noqa: BLE001
            info = {"path": str(f), "name": f.name, "ok": False, "error": str(e)}
        rows.append(info)
        if info.get("error"):
            LOG.say(f"  ✗ {f.name}: {info['error']}")
            continue
        warn = "  ⚠️ 含替换字符" if info.get("has_replacement_char") else ""
        LOG.say(f"  {f.name}")
        LOG.say(f"      编码={info['detected']}  BOM={info['bom'] or '无'}  "
                f"换行={info['eol']}  {info['bytes']:,} 字节  {info.get('chars', 0):,} 字{warn}")
        if info.get("ambiguous"):
            LOG.say(f"      ℹ️ 同时可被 {'/'.join(info['decodable_as'])} 解码"
                    f"（已自动选择 {info['detected']}）；如判断有误用 --from 强制指定")
        if info.get("stray_bom_chars"):
            LOG.say(f"      ⚠️ 正文内残留零宽 BOM 字符 {info['stray_bom_chars']} 个"
                    f"（encode/split 会自动清除）")

    if args.json:
        LOG.emit({"command": "probe", "ok": True, "count": len(rows), "files": rows})
    return EXIT_OK


def cmd_encode(args) -> int:
    try:
        target = resolve_encoding(args.to)
    except ValueError as e:
        return err_exit(str(e), EXIT_NO_INPUT)

    files = gather(args)
    if not files:
        return err_exit("没有找到可处理的 txt 文件。", EXIT_NO_INPUT)

    where = (f"写副本到 {Path(args.out_dir).resolve()}" if args.out_dir
             else "就地改写源文件（自动留 .bak 备份）")
    LOG.say(f"待处理 {len(files)} 个文件 | 目标编码 {target} | 换行 {args.eol} | {where}"
            + ("  [预演]" if args.dry_run else ""))

    results, ok, lossy, failed = [], 0, 0, 0
    for f in files:
        try:
            r = encode_file(f, args, LOG)
        except Exception as e:  # noqa: BLE001
            r = {"path": str(f), "name": f.name, "ok": False, "error": str(e)}
        results.append(r)
        if r.get("ok"):
            ok += 1
            if r.get("lossy"):
                lossy += 1
            extra = f" | 备份 {r['backup']}" if r.get("backup") else ""
            if r.get("backup_kept"):
                extra += f" | {r['backup_kept']}"
            LOG.say(f"  ✓ {r['name']}: {r['from']} → {target} | {r['action']}{extra}")
        else:
            failed += 1
            LOG.say(f"  ✗ {r['name']}: {r.get('error')}")
            if r.get("hint"):
                LOG.say(f"      {r['hint']}")

    summary = {"total": len(results), "succeeded": ok, "failed": failed, "lossy": lossy}
    if args.json:
        LOG.emit({"command": "encode", "ok": failed == 0 and lossy == 0,
                  "target_encoding": target, "eol": args.eol,
                  "in_place": not args.out_dir, "dry_run": args.dry_run,
                  "summary": summary, "files": results})
    else:
        LOG.say(f"\n完成 {ok}/{len(results)} 个文件"
                + (f"，其中 {lossy} 个有损" if lossy else "")
                + (f"，{failed} 个失败" if failed else "") + "。")

    if failed:
        return EXIT_LOSS if args.strict else EXIT_PARTIAL
    return EXIT_LOSS if lossy else EXIT_OK


def cmd_all(args) -> int:
    """一条命令跑完整流水线：probe → encode(可选) → analyze → split。"""
    LOG.say("== [1/4] probe：探测源文件编码 ==")
    cmd_probe(argparse.Namespace(inputs=args.inputs, from_enc=args.from_enc,
                                 json=False, quiet=args.quiet))

    if args.do_encode:
        LOG.say(f"\n== [2/4] encode：统一为 {args.to}（换行 {args.src_eol}）==")
        rc_enc = cmd_encode(argparse.Namespace(
            inputs=args.inputs, to=args.to, from_enc=args.from_enc, eol=args.src_eol,
            out_dir=args.encode_out_dir, no_backup=args.no_backup,
            strict=not args.lenient, dry_run=args.dry_run, json=False, quiet=args.quiet))
        if rc_enc != EXIT_OK:
            LOG.say("编码统一未全部成功，已中止后续步骤，避免基于错误的源文件切分。")
            return rc_enc
    else:
        LOG.say("\n== [2/4] encode：跳过（加 --encode 启用）==")

    LOG.say("\n== [3/4] analyze：分析卷/章结构 ==")
    rc_an = run_split_like(argparse.Namespace(**{
        **vars(args), "cmd": "analyze", "analyze_only": True, "report": None, "json": False}))

    LOG.say("\n== [4/4] split：切分输出 ==")
    rc_sp = run_split_like(argparse.Namespace(**{
        **vars(args), "cmd": "split", "analyze_only": False, "json": False}))

    # 子步骤的 JSON 已在上面关掉，这里只输出一个合并文档，保证 stdout 是单个 JSON
    rc = rc_an or rc_sp
    if args.json:
        books = []
        root = Path(args.out)
        for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.is_dir() else []:
            mf = d / "manifest.json"
            if mf.is_file():
                m = json.loads(mf.read_text(encoding="utf-8"))
                books.append({
                    "book": m["book"], "encoding": m["encoding"],
                    "volumes": m["volumes"], "chapters": m["chapters"],
                    "parts": len(m["files"]), "total_chars": m["total_chars"],
                    "out_dir": str(d),
                    "verified": m["verify"]["checked"], "mismatch": m["verify"]["mismatch"],
                })
        LOG.emit({"command": "all", "ok": rc == EXIT_OK, "exit_code": rc,
                  "encoded": args.do_encode, "target_encoding": args.to if args.do_encode else None,
                  "summary": {"books": len(books)}, "books": books})
    return rc


def main(argv: Optional[Sequence[str]] = None) -> int:
    global LOG
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        prog="novel_split.py",
        description="长篇小说编码统一 + 规范化 + 章节排序 + 分卷/分部分拆分（供 AI 分析）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_pr = sub.add_parser("probe", help="只探测编码/换行/BOM/可解码候选，不写盘")
    p_pr.add_argument("inputs", nargs="*", help="txt 文件 / 目录 / glob，可多个")
    p_pr.add_argument("--from", dest="from_enc", default=None,
                      help="强制按此编码解码（默认自动探测）")
    add_output_flags(p_pr)

    p_en = sub.add_parser("encode", help="把 TXT 无损统一到指定编码（默认转 UTF-8）")
    p_en.add_argument("inputs", nargs="*", help="txt 文件 / 目录 / glob，可多个")
    p_en.add_argument("--to", default="utf-8", help="目标编码，默认 utf-8"
                      "（支持 utf-8/utf-8-sig/gb18030/gbk/big5/utf-16 等）")
    p_en.add_argument("--from", dest="from_enc", default=None,
                      help="强制源编码（默认自动探测）；源文件被误判时用它")
    p_en.add_argument("--eol", choices=["keep", "crlf", "lf"], default="keep",
                      help="换行统一方式（默认 keep 不改）")
    p_en.add_argument("--out-dir", default=None,
                      help="写到该目录而不是就地改写源文件")
    p_en.add_argument("--no-backup", action="store_true",
                      help="就地改写时不生成 .bak（默认生成，且不覆盖已存在的 .bak）")
    p_en.add_argument("--strict", dest="strict", action="store_true", default=True,
                      help="严格无损：目标编码无法表示某个字符就报错（默认开启）")
    p_en.add_argument("--lenient", dest="strict", action="store_false",
                      help="允许用 U+FFFD 做有损替换，并在结果里标记 lossy")
    p_en.add_argument("--dry-run", action="store_true", help="只预演，不写盘")
    add_output_flags(p_en)

    p_an = sub.add_parser("analyze", help="只分析小说结构，不切分")
    add_common(p_an)
    p_an.add_argument("--report", default=None,
                      help="Markdown 报告输出路径（默认写到 --out/分析报告.md）")
    p_an.set_defaults(analyze_only=True)

    p_sp = sub.add_parser("split", help="规范化 + 排序 + 切分输出")
    add_common(p_sp)
    p_sp.add_argument("--full", action="store_true", help="额外输出规范化全本")
    p_sp.set_defaults(analyze_only=False)

    p_all = sub.add_parser("all", help="一条命令跑完 probe → encode(可选) → analyze → split")
    add_common(p_all)
    p_all.add_argument("--full", action="store_true", help="额外输出规范化全本")
    p_all.add_argument("--encode", dest="do_encode", action="store_true",
                       help="先统一源文件编码（默认不改）")
    p_all.add_argument("--to", default="utf-8", help="encode 的目标编码（默认 utf-8）")
    p_all.add_argument("--src-eol", choices=["keep", "crlf", "lf"], default="crlf",
                       help="encode 阶段统一源文件换行（默认 crlf；keep=不改）")
    p_all.add_argument("--encode-out-dir", default=None,
                       help="encode 写副本到此目录（默认就地改写源文件 + .bak）")
    p_all.add_argument("--no-backup", action="store_true", help="encode 就地改写时不生成 .bak")
    p_all.add_argument("--from", dest="from_enc", default=None, help="强制源编码")
    p_all.add_argument("--lenient", dest="lenient", action="store_true",
                       help="encode 允许有损替换")
    p_all.set_defaults(analyze_only=False)

    args = ap.parse_args(argv)
    LOG = Reporter(getattr(args, "json", False), getattr(args, "quiet", False))

    if args.cmd == "probe":
        return cmd_probe(args)
    if args.cmd == "encode":
        return cmd_encode(args)
    args.max_chars = args.max_chars or 0
    if args.cmd == "all":
        return cmd_all(args)
    return run_split_like(args)


if __name__ == "__main__":
    raise SystemExit(main())

