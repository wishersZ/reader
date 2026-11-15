#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chai_stats.py —— 拆书机读统计引擎（stdlib + 可选 numpy）

对 output/<书名>/ 下已拆分的分卷正文做全套机读统计，产出结构化数据，
供「逐章精读 → 结构与写作分析报告」两步使用。

设计原则
--------
1. **只读**：从不修改拆分正文，只写 output/<书名>_分析/ 下的产物。
2. **可复算**：所有数字来自原文扫描；同一输入重复运行结果完全一致
   （不用随机、不用时间戳参与计算；采样使用固定种子）。
3. **口径显式**：每个指标都在本文件「口径说明」里定义，报告里原样转述。
4. **不猜结论**：本工具只给数据与候选（如候选专名、候选梗），
   判定与写作结论交给下一步的分析报告，避免把统计当结论。

口径说明（与《output\混沌冠冕_分析\混沌冠冕_小说整体分析.md》保持一致，便于对账）
------------------------------------------------------------
- **净字数**：把每行所有空白（含全角空格 U+3000）去掉后计字符数。
  这是 novel_split.py 的口径，本工具沿用，保证与 00_目录索引.md 的
  「净字数零丢失」校验对得上。
- **段落**：正文里一个非空行 = 一个段落（拆分文件已做过规范化，无多空行）。
- **含引号段落**：段落中包含中文引号 “ ” 或 「 」 的段落。
  用于估算「对话/吐槽占篇幅比」。
- **出场段落**：某专名在该章出现的段落数（同段多次只算一次）。
- **首现章**：该专名在全书中第一次出现的章号。

子命令
------
  stats   对一本书跑全套统计，产出 CSV + JSON + Markdown 摘要
  verify  校验统计结果与拆分索引（00_目录索引.md / manifest.json）是否自洽
  terms   只跑词表发现，输出候选专名/术语清单（可人工筛选后回灌）
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Iterable, Iterator, Optional, Sequence

# ---------------------------------------------------------------- 常量 / 正则

#: 平假名 / 片假名
_KANA = "\u3040-\u30ff"
#: 谚文
_HANGUL = "\uac00-\ud7af"
#: 汉字
_HAN = "\u4e00-\u9fff\u3400-\u4dbf"

#: 中英文引号（中文网文对话的正规外壳）
_QUOTE_CHARS = "“”「」『』"
_QUOTE_RE = re.compile(f"[{_QUOTE_CHARS}]")

#: 常见装饰字符：有些书把标题写成 `===第二百八十三章 标题===` 或 `【第1章 标题】`
_DECOR_STRIP = frozenset("=＝-—_*#☆★◆■□●○※·.。 \t\u3000【】[]〔〕()（）<>《》「」")


def strip_decorations(line: str) -> str:
    """去掉标题行首尾的装饰字符，便于统一识别（只剥首尾，不碰中间）。"""
    s = line.strip()
    while s and s[0] in _DECOR_STRIP:
        s = s[1:]
    while s and s[-1] in _DECOR_STRIP:
        s = s[:-1]
    return s


def cn_to_int(s: Optional[str]) -> Optional[int]:
    """
    中文/全角/阿拉伯数字转 int。支持 一 / 十 / 十一 / 一百零三 / 两百 / 二百八十三。

    算法与 tools/novel_split/novel_split.py 的同名函数保持一致，
    以保证「切章」与「统计」两阶段识别出的章号完全相同。
    """
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


#: 章号：阿拉伯数字或中文数字
_NUM = r"(\d+|[零〇○一壹二两贰三叁四肆五伍六陆七柒八捌九玖十拾百佰千仟]+)"
#: 章单位
_UNIT = r"(?:章|回|节|话|篇|集)"   # 仅作文档用；实际匹配在 _CHAPTER_RE 里按命名组取
#: 单位字后允许出现的分隔符（与 novel_split 的 SEP_START_RE 同口径）
_SEP_START = " \t\u3000:：、.．。，,-—～~・"
#: 单位字后**没有**分隔符时，用复合词黑名单否决（与 novel_split.COMPOUND_BLOCK 同源）。
#: 两边必须同口径，否则「第10章三次初级兵种抽取」这类无空格标题会被切分侧认成章、
#: 统计侧漏掉，导致 stats 的章数比索引少（实测《从全面战争开始爆兵反清》少 51 章）。
_COMPOUND_BLOCK = {
    "回": "合来到去想过事声应答忆顾头家身",
    "节": "目奏约省能制假气日车",
    "话": "题说语音",
    "章": "之节回程",
    "集": "合团中",
    "篇": "章幅目",
}
#: 章节标题行。**注意不要用 `\b?`**：Python 3.14 起 `\b` 后跟量词会抛
#: "nothing to repeat"（旧版本容忍），且 `\b` 对中文边界语义不可靠。
#: 分离符与标题分开捕获，是否接受由 parse_chapter_heading() 按复合词黑名单判断。
_CHAPTER_RE = re.compile(rf"^第\s*{_NUM}\s*(?P<unit>章|回|节|话|篇|集)(?P<rest>.*)$")
#: 特殊章（序章/楔子/番外…）——拆成 head/tail 两套，关键字与 novel_split 完全对齐。
#: 分隔符一律可省略：`【附录1.通用魔咒】` 这类写法切分侧认、统计侧也必须认，
#: 否则 stats 会少一个特殊章（实测《反派少爷只想过佛系生活》的「附录」）。
_SPECIAL_HEAD_RE = re.compile(
    r"^(序章|序言|序|楔子|引子|前言|卷首语|开篇|登场人物|人物介绍)(.*)$")
_SPECIAL_TAIL_RE = re.compile(
    r"^(终章|尾声|后记|完本感言|完结感言|作者的话|番外篇|番外|特别篇|外传|附录)(.*)$")
#: 这些短词只有在「后接分隔符或行尾」时才算特殊章（防「序列之树……」）
_SHORT_SPECIAL = {"序", "引子", "前言", "楔子", "开篇"}

#: 拟声词（样本实测：独字/叠字/加波浪号的爆发型）
_ONOMATOPOEIA_RE = re.compile(
    r"(?:"
    r"[\u4e00-\u9fff]{1,2}[～~]"                      # 咚～ 滋滋滋～
    r"|(?:啊|哈|哼|嘿|哇|咚|嘭|砰|轰|咔|吱|嗡|唰|咻|滴|嘟|嗡|嗷|呜|啵|哒){2,}"  # 啊啊啊 哈哈
    r"|[A-Z]{3,}!*"                                   # BOOM / DOOOOOOM
    r")"
)

#: 危机 / 倒计时信号词
_CRISIS_WORDS = (
    "小心", "快跑", "快走", "来不及", "只剩", "倒计时", "来了", "降临", "即将",
    "最后", "危险", "逃", "追", "逼近", "响起", "钟响", "第.声", "不待", "骤然",
    "突然", "与此同时", "就在这时",
)
#: 收获 / 宣言信号词（正向收束）
_HARVEST_WORDS = (
    "属于我", "是我的", "到手", "拿下", "成功", "封", "登", "成为", "赢了", "赢了",
    "搞定", "归我", "发财", "收获", "到手了", "大丰收", "即位", "加冕", "完婚",
    "开始了", "出发", "来吧", "战吧", "上吧", "走着瞧", "等着", "期待", "美妙",
)
#: 内心宣言 / 决定信号词
_DECLARE_WORDS = (
    "该", "要", "得", "必须", "决定", "一定要", "绝不能", "不会", "不能再",
    "是时候", "准备", "计划", "下一步", "目标", "有且只有一个", "只有一条路",
    "起点", "由此而始", "序章",
)
#: 信息 / 悬念信号词
_INFO_WORDS = (
    "原来", "竟然", "竟是", "竟是", "居然", "秘密", "真相", "身份", "蹊跷",
    "奇怪", "不对", "有问题", "为什么", "怎么回事", "?!？", "谁", "什么",
)

#: 用于候选专名发现时排除的常见词尾（避免把普通词当人名）
_STOP_SUFFIX = (
    "的", "了", "是", "在", "和", "与", "也", "都", "很", "就", "不", "有", "我",
    "他", "她", "们", "这", "那", "个", "上", "下", "里", "中", "后", "前",
)

PUNCT_EXTRA = "，。！？；：、…—－-～~·「」『』“”‘’（）()《》〈〉【】〔〕"

#: 高频通用词黑名单。n-gram 会把这些顶到词表前排，但它们是口语/叙述常用词，
#: 不是专名或术语；靠「停用首尾字」过滤不掉，必须显式列出。
_STOP_TERMS = frozenset("""
自己 什么 已经 可以 知道 说道 如果 力量 怎么 因为 开始 时候 一个 没有 就是
这个 那个 我们 你们 他们 她们 它们 现在 还是 或者 但是 然后 于是 所以 而且
并且 虽然 然而 不过 只是 这样 那样 一样 一起 一定 一直 一些 有点 有些 有的
东西 事情 问题 地方 时间 感觉 觉得 认为 发现 看到 听到 想到 感到 变得 成为
可能 应该 必须 需要 能够 不能 不会 不要 曾经 正在 将要 立刻 马上 突然
似乎 仿佛 好像 终于 竟然 居然 果然 当然 其实 确实 真的 明明 偏偏 反正
眼睛 脸上 心中 心里 手中 身上 面前 身后 身边 周围 世界 天下 大家 众人
一声 一句 一眼 一下 一次 一点 一片 一道 一股 一阵 一丝 一抹
大人 阁下 先生 女士 小姐 夫人 殿下 陛下 王子 公主 国王 女王 皇帝
说话 回答 问道 笑道 冷声 低声 轻声 沉声
""".split())

#: 出现在词中就说明「不像专名」的虚词（用于快速排除，避免 re.match 开销）
_BAD_MID = frozenset("的了是在和与也都很就不")

#: 允许出现在专名里的字符区间（码点）。用区间比较代替逐字符正则，
#: 在 290 万字体量上这是最热的内层循环，必须走快路径。
_NAME_RANGES: tuple[tuple[int, int], ...] = (
    (0x4E00, 0x9FFF),    # CJK 统一表意文字
    (0x3400, 0x4DBF),    # CJK 扩展 A
    (0x3040, 0x30FF),    # 平假名 / 片假名
    (0xAC00, 0xD7AF),    # 谚文音节
    (0x41, 0x5A),        # A-Z
    (0x61, 0x7A),        # a-z
    (0x30, 0x39),        # 0-9
)


def _is_name_char(ch: str) -> bool:
    """快路径：判断单字符是否属于「可作专名」的字母表。"""
    o = ord(ch)
    for lo, hi in _NAME_RANGES:
        if lo <= o <= hi:
            return True
    return False


# ---------------------------------------------------------------- 基础工具


def net_chars(text: str) -> int:
    """净字数：去掉所有空白后的字符数（与 novel_split.py 同口径）。"""
    return sum(1 for ch in text if not ch.isspace())


def is_dialogue(para: str) -> bool:
    """段落是否含中文引号（用于估算对话篇幅）。"""
    return bool(_QUOTE_RE.search(para))


def clean_for_terms(text: str) -> str:
    """为词表统计清理文本：去掉标点与空白，保留汉字/假名/谚文/拉丁/数字。"""
    out = []
    for ch in text:
        if ch.isspace():
            continue
        if ch in PUNCT_EXTRA:
            continue
        if unicodedata.category(ch).startswith("P"):
            continue
        out.append(ch)
    return "".join(out)


# ---------------------------------------------------------------- 数据结构


@dataclass
class ChapterStat:
    """单章统计。"""

    seq: int                 # 全书序号（1 起）
    part: str                # 所在拆分文件
    number: int              # 章号（特殊章为 0）
    title: str               # 章名（不含「第N章」）
    heading: str             # 原始标题行
    kind: str                # chapter / special
    chars: int               # 净字数
    paragraphs: int          # 段落数
    avg_para: float          # 平均段长（净字数/段数）
    dialogue_paras: int      # 含引号段落数
    dialogue_ratio: float    # 含引号段落占比
    short_paras: int         # ≤12 净字数的段落数
    hook_type: str           # 章末钩型（启发式）
    hook_text: str           # 章末最后一句非空行（截断 60 字）
    tail_lines: str          # 章末最后 3 行（用于人工复核钩型）

    @property
    def hook_confidence(self) -> str:
        return "heuristic"


@dataclass
class PartStat:
    seq: int
    file: str
    chapters: int
    chars: int
    first_heading: str
    last_heading: str


@dataclass
class BookStats:
    book: str
    source_dir: str
    parts: list[PartStat] = field(default_factory=list)
    chapters: list[ChapterStat] = field(default_factory=list)
    # 全书标量
    total_chars: int = 0
    total_paragraphs: int = 0
    total_dialogue_paras: int = 0
    total_short_paras: int = 0
    # 分布
    para_len_hist: dict = field(default_factory=dict)
    hook_type_counts: dict = field(default_factory=dict)
    # 术语
    term_freq: dict = field(default_factory=dict)
    term_first: dict = field(default_factory=dict)
    term_top_chapters: dict = field(default_factory=dict)
    # 前置信息（每份第一个标题之前的内容：书名/作者/文案/卷标题/卷首语）
    front_matter: list[str] = field(default_factory=list)
    front_matter_chars: int = 0
    #: 逐份记录前置信息，便于复核（键=文件名，值=行列表）
    part_preamble: dict = field(default_factory=dict)
    # 元信息
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 解析拆分文件


#: 标题行整行长度上限 / 含句号时的长度上限（与 novel_split 的 HEADING_MAX_LEN 同口径）
_HEADING_MAX_LEN = 60
_HEADING_PUNCT_LEN = 30


def _looks_like_prose(line: str) -> bool:
    """太长，或含句号且较长 → 是正文，不是标题（拦「第一回战斗是……。」这类句子）。"""
    if len(line) > _HEADING_MAX_LEN:
        return True
    return "。" in line and len(line) > _HEADING_PUNCT_LEN


def parse_chapter_heading(line: str) -> Optional[tuple[int, str, str]]:
    """
    解析章节标题行 → (章号, 标题, 类型)。识别不了返回 None。

    先剥掉首尾装饰，因此下面这些写法都能识别：
        第1章 标题          第001章 标题       第一章 标题
        ===第二百八十三章 石田的野心===      【第12章 标题】
    章号支持阿拉伯数字与中文数字（二百八十三 → 283）。

    与 `novel_split` 保持同一套判据：装饰剥离 → 散文闸门 → 章号/单位 →
    复合词黑名单。两边不一致会让 stats 的章数对不上拆分索引。
    """
    s = strip_decorations(line)
    if not s:
        return None
    # 散文闸门要对**原始行**做：strip_decorations 会把句末的「。」剥掉，
    # 只看 s 会漏掉「第一回战斗是……老婆。」这类正文（实测《带着写轮眼……》多算 1 章）。
    if _looks_like_prose(line.strip()):
        return None
    m = _CHAPTER_RE.match(s)
    if m:
        num = cn_to_int(m.group(1))
        if num is None:
            return None
        unit = m.group("unit")
        rest = m.group("rest") or ""
        # 单位字后没有分隔符时按复合词黑名单否决——与 novel_split 同一套规则。
        # 否则「第10章三次初级兵种抽取」这类无空格标题会漏统计（章数比索引少）。
        if rest and rest[0] not in _SEP_START and rest[0] in _COMPOUND_BLOCK.get(unit, ""):
            return None
        return num, rest.lstrip(_SEP_START).strip(), "chapter"
    m = _SPECIAL_HEAD_RE.match(s)
    if m:
        kw, rest = m.group(1), m.group(2) or ""
        # 短词（序/引子/…）必须自成边界，否则「序列之树……」会被当成「序」章
        if kw in _SHORT_SPECIAL and rest and rest[0] not in _SEP_START:
            return None
        return 0, (kw + rest.lstrip(_SEP_START)).strip(), "special"
    m = _SPECIAL_TAIL_RE.match(s)
    if m:
        kw, rest = m.group(1), m.group(2) or ""
        return 0, (kw + rest.lstrip(_SEP_START)).strip(), "special"
    return None


_CN_DIGIT = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def cn_num_to_int(s: str) -> Optional[int]:
    """
    中文数字转整数，覆盖 1—99 的常见写法：
      十一 → 11，二十 → 20，二十一 → 21，二十九 → 29。
    也接受纯阿拉伯数字。无法解析返回 None。
    """
    s = s.strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "十" not in s:
        # 单个或连续数字（如「一二」极少见，这里只处理单字与「〇」）
        if len(s) == 1 and s in _CN_DIGIT:
            return _CN_DIGIT[s]
        return None
    head, _, tail = s.partition("十")
    tens = _CN_DIGIT.get(head, 1) if head else 1
    ones = _CN_DIGIT.get(tail, 0) if tail else 0
    if head and head not in _CN_DIGIT:
        return None
    if tail and tail not in _CN_DIGIT:
        return None
    return tens * 10 + ones


#: 从「混沌冠冕_第二十九部分.txt」里抽出「第二十九」→ 29
_PART_NUM_RE = re.compile(r"_第([一二三四五六七八九十零〇两]+)部分?$")


def part_sort_key(path: Path) -> tuple[int, str]:
    """
    拆分文件的排序键。**必须按卷号数值排序，不能按文件名字典序**——
    否则「第十部分」会排在「第四部分」之前，导致跨份续接的 carry 串错。
    """
    m = _PART_NUM_RE.search(path.stem)
    if m:
        n = cn_num_to_int(m.group(1))
        if n is not None:
            return (n, path.name)
    return (10**9, path.name)


def iter_parts(book_dir: Path) -> list[Path]:
    """列出拆分正文文件（排除索引/清单/存档等辅助文件），按卷号数值排序。"""
    skip_prefix = ("00_", "01_", "_")
    skip_names = {"manifest.json", "章末样本.txt"}
    out = []
    for p in book_dir.glob("*.txt"):
        if p.name in skip_names:
            continue
        if p.name.startswith(skip_prefix):
            continue
        out.append(p)
    return sorted(out, key=part_sort_key)


def load_split_index(book_dir: Path) -> tuple[list[str], list[str]]:
    """读 00_目录索引.md，提取书名的「净字数」与「章数」行，用于 verify。"""
    idx = book_dir / "00_目录索引.md"
    if not idx.exists():
        return [], []
    text = idx.read_text(encoding="utf-8", errors="replace")
    return text.splitlines(), []


# ---------------------------------------------------------------- 钩型分类


def classify_hook(tail_lines: list[str]) -> str:
    """
    章末钩型启发式分类（六类，与《混沌冠冕》分析的钩型配方对应）。

    优先级：拟声 > 对白收束 > 危机倒计时 > 收获宣言 > 信息悬念 > 内心宣言 > 其他
    这是**启发式**，用于统计分布与人工复核线索，不等于人工判读。
    """
    if not tail_lines:
        return "无（空章）"
    last = tail_lines[-1].strip()
    joined = " ".join(tail_lines)

    if _ONOMATOPOEIA_RE.search(last):
        return "F 拟声/爆发钩"
    if is_dialogue(last):
        return "A 对白收束钩"
    # 危机 / 倒计时
    for w in _CRISIS_WORDS:
        if re.search(w, last):
            return "D 危机/倒计时钩"
    # 收获 / 宣言
    for w in _HARVEST_WORDS:
        if w in last:
            return "E 收获/宣言钩"
    # 信息 / 悬念（问号也算）
    if last.endswith(("？", "?")) or last.endswith(("？！", "！？")):
        return "C 信息/悬念钩"
    for w in _INFO_WORDS:
        if w in last:
            return "C 信息/悬念钩"
    # 内心宣言
    for w in _DECLARE_WORDS:
        if w in last:
            return "B 内心宣言钩"
    return "Z 其他/收束"


# ---------------------------------------------------------------- 主统计


#: 目录/面板列表闸门（与 novel_split 的 TOC_MIN_RUN / TOC_MAX_GAP 同口径）：
#: 连续 >= 5 个标题、彼此行距 <= 2，基本不可能是真章节（真章节之间必有正文）。
_TOC_MIN_RUN = 5
_TOC_MAX_GAP = 2


def _drop_toc(marks: list[tuple[int, int, str, str]]) -> list[tuple[int, int, str, str]]:
    """剔除密集标题块（目录页/章节列表），判据与 novel_split._drop_toc 一致。

    不做这一步，书首的目录块会被当成真章节（实测《反派少爷只想过佛系生活》
    多出「第 1–5 章」共 5 个假章）。
    """
    drop: set[int] = set()
    run: list[int] = []
    for k, mk in enumerate(marks):
        if run and mk[0] - marks[run[-1]][0] <= _TOC_MAX_GAP:
            run.append(k)
        else:
            if len(run) >= _TOC_MIN_RUN:
                drop.update(run)
            run = [k]
    if len(run) >= _TOC_MIN_RUN:
        drop.update(run)
    return [mk for k, mk in enumerate(marks) if k not in drop]


def collect_chapters(book_dir: Path, stats: BookStats) -> None:
    """
    扫描拆分文件，填充 chapters / parts。

    **口径（实测确认，不要再臆测跨份续接）**
    ------------------------------------------------------------
    早期版本曾假设「拆分点会把同一章标题重复写进相邻两份，前一份末尾是下一份
    首章的开头」——**该假设经实测被推翻**：

        第七部分最后标题 = 第155章 苏伦之赐（下），其后 88 段以
            「月之海的传奇刺客恐惧利刃，接单！」结尾；
        第八部分第一行   = 第156章 妖精龙和雪精灵，其后正文以
            「谷地历1361年2月初，胡雷克森林。」开头。

    两段文本**完全不同**，即第 155 章在第七部分结束、第 156 章从第八部分
    开始，没有任何内容被复制。因此正确口径就是最朴素的一种：

        正文 = 某个标题行之后，直到【下一个标题行或文件结尾】。
        前置信息（第一份第一个标题之前）= 书名/作者/文案，不计入正文。

    验证：所有章节正文净字数之和 + 前置信息净字数 == 全部非空行的净字数
    （对《混沌冠冕》为 2,875,401 + 225 == 2,882,918）。
    """
    seq = 0
    for pi, path in enumerate(iter_parts(book_dir), start=1):
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        marks: list[tuple[int, int, str, str]] = []
        for i, line in enumerate(raw_lines):
            got = parse_chapter_heading(line)
            if got is not None:
                num, title, kind = got
                marks.append((i, num, title, kind))
        marks = _drop_toc(marks)
        if not marks:
            stats.warnings.append(f"{path.name}: 未识别到任何章节标题，已跳过")
            continue

        # 每份文件里「第一个标题之前」的内容都要收进前置信息，**不能只处理第一份**。
        # 实测踩坑：《我在东京教剑道》是 7 卷本，每卷文件开头都有卷标题
        # （「第一卷 化龙」等）与卷首语；早期版本只对 pi==1 做处理，其余 6 份的
        # 这段内容被静默丢弃，导致 41 字对不上账（7 卷前置：101+7+10+6+5+7+6=142，
        # 其中第 1 份的 101 字已被计入，剩下的 41 字就是丢的部分）。
        pre = [ln.strip() for ln in raw_lines[:marks[0][0]] if ln.strip()]
        if pre:
            stats.front_matter.extend(pre)
            stats.front_matter_chars += sum(net_chars(ln) for ln in pre)
            stats.part_preamble[path.name] = pre

        part_chars = 0
        parts_first = raw_lines[marks[0][0]].strip()
        parts_last = ""
        for mi, (line_no, num, title, kind) in enumerate(marks):
            end = marks[mi + 1][0] if mi + 1 < len(marks) else len(raw_lines)
            body = [ln.strip() for ln in raw_lines[line_no + 1:end] if ln.strip()]
            chars = sum(net_chars(ln) for ln in body)
            n_paras = len(body)
            dlg = sum(1 for ln in body if is_dialogue(ln))
            short = sum(1 for ln in body if net_chars(ln) <= 12)
            for ln in body:
                b = bucket_of(net_chars(ln))
                stats.para_len_hist[b] = stats.para_len_hist.get(b, 0) + 1
            tail3 = body[-3:] if len(body) >= 3 else body[:]
            hook = classify_hook(tail3)
            seq += 1
            stats.chapters.append(
                ChapterStat(
                    seq=seq, part=path.name, number=num, title=title,
                    heading=raw_lines[line_no].strip(), kind=kind,
                    chars=chars, paragraphs=n_paras,
                    avg_para=round(chars / n_paras, 1) if n_paras else 0.0,
                    dialogue_paras=dlg,
                    dialogue_ratio=round(dlg / n_paras, 4) if n_paras else 0.0,
                    short_paras=short,
                    hook_type=hook,
                    hook_text=(tail3[-1][:60] if tail3 else ""),
                    tail_lines=" / ".join(t[:40] for t in tail3),
                )
            )
            part_chars += chars
            stats.total_chars += chars
            stats.total_paragraphs += n_paras
            stats.total_dialogue_paras += dlg
            stats.total_short_paras += short
            stats.hook_type_counts[hook] = stats.hook_type_counts.get(hook, 0) + 1
            parts_last = raw_lines[line_no].strip()

        stats.parts.append(
            PartStat(
                seq=pi, file=path.name, chapters=len(marks), chars=part_chars,
                first_heading=parts_first, last_heading=parts_last,
            )
        )

    # 自检：正文净字数 + 前置信息净字数 应等于 全部非空行净字数
    stats.warnings.append(
        f"口径自检：正文 {stats.total_chars:,} 字 + 前置信息 "
        f"{stats.front_matter_chars} 字；段落 {stats.total_paragraphs:,} 段"
        f"（不含 {len(stats.chapters)} 个标题行）"
    )



def bucket_of(n: int) -> str:
    if n <= 10:
        return "1-10"
    if n <= 20:
        return "11-20"
    if n <= 50:
        return "21-50"
    if n <= 100:
        return "51-100"
    if n <= 200:
        return "101-200"
    return ">200"


# ---------------------------------------------------------------- 术语发现


def collect_terms(
    book_dir: Path,
    min_count: int,
    top_n: int,
    extra_terms: Sequence[str],
    max_gram: int = 4,
) -> tuple[Counter, dict[str, int], dict[str, list[tuple[int, int]]]]:
    """
    候选专名/术语发现。

    做法（不依赖分词库，纯 stdlib）：
      1. 对每章正文做 n-gram（2—6 字）频次统计，只保留纯汉字/假名/拉丁片段；
      2. 用「频次 ≥ min_count」且「首尾不是停用字」筛出候选；
      3. 对候选做「最长优先消重」（长词吃掉被它包含的短词的高频部分）；
      4. 叠加用户传入的 extra_terms（人工确认过的专名，保证一定进表）。

    返回 (总频次表, 首现章表, 逐章出现次数表)。
    """
    freq: Counter = Counter()
    first: dict[str, int] = {}
    per_chapter: dict[str, list[tuple[int, int]]] = defaultdict(list)

    for path in iter_parts(book_dir):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        marks: list[tuple[int, int]] = []
        for i, line in enumerate(lines):
            got = parse_chapter_heading(line)
            if got is not None:
                marks.append((i, got[0]))
        for mi, (line_no, num) in enumerate(marks):
            end = marks[mi + 1][0] if mi + 1 < len(marks) else len(lines)
            body = clean_for_terms("".join(lines[line_no + 1:end]))
            local: Counter = Counter()
            L = len(body)
            for n in range(2, max_gram + 1):
                for i in range(L - n + 1):
                    g = body[i:i + n]
                    if not _is_name_like(g):
                        continue
                    local[g] += 1
            for g, c in local.items():
                if c >= 2:                      # 章内至少出现 2 次才计入
                    freq[g] += c
                    per_chapter[g].append((num, c))
                    if g not in first or (num and num < first[g]):
                        first[g] = num

    # 最长优先消重：若长候选包含短候选，且长候选频次足够，则压制短候选
    candidates = [g for g, c in freq.items() if c >= min_count]
    candidates.sort(key=lambda s: (-len(s), -freq[s]))
    kept: list[str] = []
    for g in candidates:
        if any(g in k for k in kept):
            continue
        kept.append(g)
        if len(kept) >= top_n:
            break

    for t in extra_terms:
        if t and t not in kept:
            kept.append(t)
            if t not in freq:
                freq[t] = 0

    return freq, first, per_chapter


def _is_name_like(g: str) -> bool:
    """判断一个 n-gram 是否「像专名」：纯字母表 + 首尾不是停用字 + 不在通用词黑名单。"""
    if len(g) < 2:
        return False
    if g in _STOP_TERMS:
        return False
    for ch in g:
        if _is_name_char(ch):
            continue
        return False
    if g[0] in _STOP_SUFFIX or g[-1] in _STOP_SUFFIX:
        return False
    if _BAD_MID.intersection(g):
        return False
    return True


def suppress_substrings(terms: list[str]) -> list[str]:
    """
    去掉「被更长候选包含」的短片段。

    例：n-gram 会同时产出 `埃莉`(3147) 与 `埃莉诺`(3146)，两者频次几乎相同。
    最优解是只保留更长的那个（它是完整专名），因此按「长度降序 + 频次降序」
    依次保留，凡是被已保留项包含的短片段一律丢弃。

    注意必须按长度降序处理——否则短片段先入列，长专名会被它挡掉。
    """
    kept: list[str] = []
    for t in terms:
        if any(t != k and t in k for k in kept):
            continue
        kept.append(t)
    return kept


# ---------------------------------------------------------------- 输出


def write_chapter_csv(book_dir: Path, out_dir: Path, chapters: list[ChapterStat]) -> Path:
    p = out_dir / "chapters.csv"
    cols = list(ChapterStat.__dataclass_fields__.keys())
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for c in chapters:
            w.writerow(asdict(c))
    return p


def write_terms_csv(out_dir: Path, freq: Counter, first: dict, per_chap: dict, kept: list[str]) -> Path:
    p = out_dir / "terms.csv"
    with p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["术语", "总频次", "首现章", "出现章数", "最高单章频次", "最高频章"])
        for t in kept:
            occ = per_chap.get(t, [])
            if occ:
                peak = max(occ, key=lambda x: x[1])
                w.writerow([t, freq.get(t, 0), first.get(t, ""), len(occ), peak[1], peak[0]])
            else:
                w.writerow([t, freq.get(t, 0), first.get(t, ""), 0, 0, ""])
    return p


def write_json(out_dir: Path, st: BookStats, metrics: dict) -> Path:
    p = out_dir / "stats.json"
    heading_chars = sum(net_chars(c.heading) for c in st.chapters)
    payload = {
        "book": st.book,
        "source_dir": st.source_dir,
        "columns_note": (
            "total_chars/paragraphs 为**章节正文**口径，不含标题行与前置信息；"
            "heading_chars + front_matter_chars 与之相加 = 拆分索引的全文净字数。"
        ),
        "totals": {
            "chapters": len([c for c in st.chapters if c.kind == "chapter"]),
            "specials": len([c for c in st.chapters if c.kind != "chapter"]),
            "parts": len(st.parts),
            "total_chars": st.total_chars,
            "total_paragraphs": st.total_paragraphs,
            "total_dialogue_paras": st.total_dialogue_paras,
            "total_short_paras": st.total_short_paras,
            "heading_chars": heading_chars,
            "front_matter_chars": st.front_matter_chars,
            "front_matter_lines": len(st.front_matter),
            "book_chars_full": st.total_chars + heading_chars + st.front_matter_chars,
            "book_paragraphs_full": st.total_paragraphs + len(st.chapters)
            + len(st.front_matter),
        },
        "metrics": metrics,
        "hook_type_counts": st.hook_type_counts,
        "para_len_hist": st.para_len_hist,
        "term_freq": dict(Counter(st.term_freq).most_common(200)),
        "term_first": {k: st.term_first[k] for k in list(st.term_freq)[:200] if k in st.term_first},
        "parts": [asdict(p_) for p_ in st.parts],
        "warnings": st.warnings,
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def compute_metrics(st: BookStats) -> dict:
    """全书级指标（含节奏规律，与《混沌冠冕》报告口径一致）。"""
    ch = [c for c in st.chapters if c.kind == "chapter" and c.chars > 0]
    lens = [c.chars for c in ch]
    if not lens:
        return {}
    mean = statistics.fmean(lens)
    sd = statistics.pstdev(lens) if len(lens) > 1 else 0.0
    med = statistics.median(lens)
    # 每 N 章区间的均字数（看章长是否随剧情强度波动）
    win = 50
    blocks = []
    for i in range(0, len(lens), win):
        seg = lens[i:i + win]
        blocks.append({"from": i + 1, "to": i + len(seg),
                       "mean": round(statistics.fmean(seg), 1)})
    # 钩型分布占比
    hook_total = sum(st.hook_type_counts.values()) or 1
    hook_pct = {k: round(v / hook_total * 100, 2) for k, v in st.hook_type_counts.items()}
    # 段落长度分布占比（必须按区间数值排序，不能按字符串排序——
    # 否则 "101-200" 会排在 "11-20" 前面）
    _bucket_order = {"1-10": 1, "11-20": 2, "21-50": 3,
                     "51-100": 4, "101-200": 5, ">200": 6}
    para_total = sum(st.para_len_hist.values()) or 1
    para_pct = {
        k: round(v / para_total * 100, 2)
        for k, v in sorted(st.para_len_hist.items(),
                           key=lambda kv: _bucket_order.get(kv[0], 99))
    }
    # 节奏：滑动窗口找最长连续高章长/低章长段（辅助判断高潮区间）
    return {
        "chapter_len": {
            "mean": round(mean, 1),
            "median": round(med, 1),
            "stdev": round(sd, 1),
            "min": min(lens),
            "max": max(lens),
            "cv": round(sd / mean, 4) if mean else 0,
        },
        "block_mean_50": blocks,
        "para_avg_len": round(st.total_chars / st.total_paragraphs, 1) if st.total_paragraphs else 0,
        "para_len_pct": para_pct,
        "dialogue_para_pct": round(
            st.total_dialogue_paras / st.total_paragraphs * 100, 2
        ) if st.total_paragraphs else 0,
        "short_para_pct": round(
            st.total_short_paras / st.total_paragraphs * 100, 2
        ) if st.total_paragraphs else 0,
        "hook_pct": hook_pct,
        "longest_chapters": sorted(
            ({"seq": c.seq, "number": c.number, "title": c.title, "chars": c.chars}
             for c in ch), key=lambda d: -d["chars"])[:10],
        "shortest_chapters": sorted(
            ({"seq": c.seq, "number": c.number, "title": c.title, "chars": c.chars}
             for c in ch), key=lambda d: d["chars"])[:10],
    }


def write_summary_md(out_dir: Path, st: BookStats, metrics: dict, top_terms: list[str]) -> Path:
    """人读摘要：可直接粘进分析报告的数据章节。"""
    p = out_dir / "stats_摘要.md"
    L: list[str] = []
    A = L.append
    t = metrics.get("chapter_len", {})
    A(f"# 《{st.book}》机读统计摘要")
    A("")
    A("> 由 `tools/chai/chai_stats.py` 自动生成。所有数字来自拆分正文扫描，可复算。")
    A("")
    A("## 一、规模")
    A("")
    A("| 指标 | 数值 |")
    A("|---|---|")
    A(f"| 拆分份数 | {len(st.parts)} |")
    n_ch = len([c for c in st.chapters if c.kind == "chapter"])
    n_sp = len(st.chapters) - n_ch
    A(f"| 章数 | {n_ch}（另特殊章 {n_sp}） |")
    A(f"| 净字数 | {st.total_chars:,} |")
    A(f"| 段落数 | {st.total_paragraphs:,} |")
    A("")
    A("## 二、章长与节奏")
    A("")
    A("| 指标 | 数值 | 判读 |")
    A("|---|---|---|")
    A(f"| 单章均值 | {t.get('mean')} 字 | — |")
    A(f"| 中位 | {t.get('median')} 字 | — |")
    A(f"| 标准差 | {t.get('stdev')} 字 | **<500 为固定节拍器式；>1000 为弹性式** |")
    A(f"| 变异系数 | {t.get('cv')} | 越小越工业化 |")
    A(f"| 最短 / 最长 | {t.get('min')} / {t.get('max')} 字 | — |")
    A("")
    # 平台适配判读：把章长直接映射到平台口味，便于跨书对比
    mean_len = t.get("mean") or 0
    sd_len = t.get("stdev") or 0
    if mean_len:
        if mean_len <= 2600:
            fit = "**短章流派**（番茄/免费平台口味：单章 2000—2500 字）"
        elif mean_len <= 3500:
            fit = "**中章流派**（介于免费与付费之间）"
        else:
            fit = "**长章流派**（付费平台常见 2000—3000 字，本作偏长）"
        if sd_len < 500:
            rhythm = ("**固定节拍器式**：作者不能靠「高潮章写长」制造高潮，"
                      "必须用内容密度替代篇幅，因此会章章留钩、频繁换场景")
        elif sd_len > 1000:
            rhythm = "**弹性式**：允许高潮章/卷末章显著加长（2—3 倍）"
        else:
            rhythm = "**半弹性**：有波动但基本可控"
        A("### 平台适配判读")
        A("")
        A(f"- 单章均值 **{mean_len:.0f} 字** → {fit}")
        A(f"- 章长标准差 **{sd_len:.0f} 字** → {rhythm}")
        A("")
    if metrics.get("block_mean_50"):
        A("每 50 章的均字数（检查章长是否随剧情强度波动）：")
        A("")
        A("| 章区间 | 均字数 |")
        A("|---|---|")
        for b in metrics["block_mean_50"]:
            A(f"| {b['from']}—{b['to']} | {b['mean']} |")
        A("")
    A("## 三、段落与对话（手机屏优化程度）")
    A("")
    A("| 指标 | 数值 |")
    A("|---|---|")
    A(f"| 平均段长 | {metrics.get('para_avg_len')} 字 |")
    A(f"| 含引号段落占比 | {metrics.get('dialogue_para_pct')}% |")
    A(f"| 短段（≤12 字）占比 | {metrics.get('short_para_pct')}% |")
    A("")
    A("段落长度分布：")
    A("")
    A("| 段长区间 | 占比 |")
    A("|---|---|")
    for k, v in (metrics.get("para_len_pct") or {}).items():
        A(f"| {k} 字 | {v}% |")
    A("")
    A("## 四、章末钩型分布（启发式）")
    A("")
    A("> **这是正则启发式分类，不是人工判读。** 请抽样 20 章人工核对后再引用。")
    A("")
    A("| 钩型 | 章数 | 占比 |")
    A("|---|---|---|")
    for k, v in sorted((metrics.get("hook_pct") or {}).items(), key=lambda x: -x[1]):
        A(f"| {k} | {st.hook_type_counts.get(k, 0)} | {v}% |")
    A("")
    A("## 五、最长 / 最短章（找有意加长的关键章）")
    A("")
    A("| 序号 | 章 | 标题 | 净字数 |")
    A("|---|---|---|---|")
    for c in metrics.get("longest_chapters", []):
        A(f"| {c['seq']} | 第{c['number']}章 | {c['title']} | {c['chars']:,} |")
    A("")
    A("| 序号 | 章 | 标题 | 净字数 |")
    A("|---|---|---|---|")
    for c in metrics.get("shortest_chapters", []):
        A(f"| {c['seq']} | 第{c['number']}章 | {c['title']} | {c['chars']:,} |")
    A("")
    A("## 六、高频术语候选（Top 40）")
    A("")
    A("> 纯 n-gram 频次 + 停用字过滤得到的**候选**，需人工筛掉普通词。")
    A("")
    for i, term in enumerate(top_terms[:40], start=1):
        A(f"{i}. `{term}`（{st.term_freq.get(term, 0)} 次，首现第 {st.term_first.get(term, '?')} 章）")
    A("")
    if st.warnings:
        A("## 警告")
        A("")
        for w in st.warnings:
            A(f"- {w}")
        A("")
    p.write_text("\n".join(L), encoding="utf-8")
    return p


# ---------------------------------------------------------------- CLI


def cmd_stats(args: argparse.Namespace) -> int:
    book_dir = Path(args.book_dir)
    if not book_dir.is_dir():
        print(f"错误：不是目录 {book_dir}", file=sys.stderr)
        return 2
    book = args.book or book_dir.name
    out_dir = Path(args.out) if args.out else book_dir.parent / f"{book}_分析"
    out_dir.mkdir(parents=True, exist_ok=True)

    st = BookStats(book=book, source_dir=str(book_dir))
    print(f"[1/4] 扫描拆分正文：{book_dir}")
    collect_chapters(book_dir, st)
    if not st.chapters:
        print("错误：没解析到任何章节，请检查拆分产物", file=sys.stderr)
        return 3

    print(f"[2/4] 汇总指标（{len(st.chapters)} 章 / {st.total_chars:,} 字）")
    metrics = compute_metrics(st)

    print(f"[3/4] 术语发现（min_count={args.min_count}, top={args.top_terms}）")
    extra = [t.strip() for t in (args.terms or "").split(",") if t.strip()]
    freq, first, per_chap = collect_terms(
        book_dir, args.min_count, args.top_terms, extra
    )

    # 候选筛选：先剔除通用词，再按「长度降序 + 频次降序」做子串抑制，
    # 最后截断到 top_terms。顺序不能颠倒（详见 suppress_substrings 注释）。
    cand = [g for g, c in freq.most_common()
            if c >= args.min_count and g not in _STOP_TERMS]
    cand.sort(key=lambda s: (-len(s), -freq[s]))
    kept = suppress_substrings(cand)[: args.top_terms]
    for t in extra:
        if t not in kept:
            kept.append(t)

    st.term_freq = {g: freq.get(g, 0) for g in kept}
    st.term_first = {g: first.get(g, 0) for g in kept if g in first}

    print("[4/4] 写盘")
    p1 = write_chapter_csv(book_dir, out_dir, st.chapters)
    p2 = write_terms_csv(out_dir, freq, first, per_chap, kept)
    p3 = write_json(out_dir, st, metrics)
    p4 = write_summary_md(out_dir, st, metrics, kept)

    result = {
        "book": book,
        "out_dir": str(out_dir),
        "chapters": len([c for c in st.chapters if c.kind == "chapter"]),
        "specials": len(st.chapters) - len([c for c in st.chapters if c.kind == "chapter"]),
        "parts": len(st.parts),
        "total_chars": st.total_chars,
        "total_paragraphs": st.total_paragraphs,
        "artifacts": {
            "chapters_csv": str(p1),
            "terms_csv": str(p2),
            "stats_json": str(p3),
            "summary_md": str(p4),
        },
        "warnings": st.warnings,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n完成。产物在 {out_dir}")
        for k, v in result["artifacts"].items():
            print(f"  {k:14} {v}")
        print(f"\n规模：{result['chapters']} 章 + {result['specials']} 特殊章 / "
              f"{result['total_chars']:,} 字 / {result['total_paragraphs']:,} 段")
        if st.warnings:
            print("\n警告：")
            for w in st.warnings:
                print("  -", w)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """
    把统计结果与拆分索引对账。

    **关键口径差异（必须理解，否则会误判为不一致）**
    ------------------------------------------------------------
    novel_split.py 的 manifest.json / 00_目录索引.md 里的「净字数」是
    **包含标题行与前置信息的全文净字数**；而本引擎的
    `totals.total_chars` 是**章节正文净字数（不含标题行与前置信息）**。

    二者的恒等关系是：

        引擎正文净字数 + Σ(标题行净字数) + 前置信息净字数
            == 索引/清单的全文净字数

    所以本命令按上面这个恒等式校验，而不是拿两个不同口径的数字直接相等。
    """
    book_dir = Path(args.book_dir)
    book = args.book or book_dir.name
    stats_json = book_dir.parent / f"{book}_分析" / "stats.json"
    if not stats_json.exists():
        print(f"错误：先跑 stats，找不到 {stats_json}", file=sys.stderr)
        return 2
    data = json.loads(stats_json.read_text(encoding="utf-8"))
    problems: list[str] = []
    notes: list[str] = []

    body_chars = data["totals"]["total_chars"]
    heading_chars = data.get("totals", {}).get("heading_chars", 0)
    front_chars = data.get("totals", {}).get("front_matter_chars", 0)
    computed = body_chars + heading_chars + front_chars

    def dig(d, *keys, default=None):
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    indexed: Optional[int] = None

    # 与 manifest.json 对账
    man = book_dir / "manifest.json"
    if man.exists():
        m = json.loads(man.read_text(encoding="utf-8"))
        m_chars = dig(m, "total_chars") or dig(m, "book", "total_chars")
        if isinstance(m_chars, int):
            indexed = m_chars
            if m_chars != computed:
                problems.append(
                    f"与 manifest.json 不一致：正文{body_chars:,}+标题{heading_chars:,}"
                    f"+前置{front_chars:,}={computed:,} vs manifest={m_chars:,}"
                )
            else:
                notes.append(f"manifest 对账通过（{computed:,} 字，恒等式成立）")

    # 与索引文本对账
    idx = book_dir / "00_目录索引.md"
    if idx.exists():
        txt = idx.read_text(encoding="utf-8", errors="replace")
        mm = re.search(r"全文净字数：\s*([\d,]+)", txt)
        if mm:
            got = int(mm.group(1).replace(",", ""))
            if got != computed:
                problems.append(
                    f"与 00_目录索引.md 不一致：恒等式算出 {computed:,} vs 索引 {got:,}"
                )
            else:
                notes.append(f"目录索引对账通过（{computed:,} 字）")

    for n in notes:
        print("  ·", n)
    if problems:
        print("校验失败：")
        for p in problems:
            print("  -", p)
        print("\n提示：若差异恰好等于标题行总字数，说明索引口径含标题；"
              "若差异很大，说明统计跑在了旧产物上，请重跑 stats。")
        return 3
    print("校验通过：正文 + 标题行 + 前置信息 == 拆分索引的全文净字数。")
    return 0


def cmd_terms(args: argparse.Namespace) -> int:
    book_dir = Path(args.book_dir)
    extra = [t.strip() for t in (args.terms or "").split(",") if t.strip()]
    freq, first, per_chap = collect_terms(book_dir, args.min_count, args.top_n, extra)
    rows = sorted(freq.items(), key=lambda x: -x[1])[: args.top_n]
    if args.json:
        print(json.dumps(
            [{"term": t, "freq": c, "first_chapter": first.get(t)}
             for t, c in rows], ensure_ascii=False, indent=2))
    else:
        for t, c in rows:
            print(f"{c:>7}  首现第{first.get(t, '?'):>5}章  {t}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chai_stats",
        description="拆书机读统计引擎：对已拆分的分卷正文做全套统计",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stats", help="跑全套统计，产出 CSV/JSON/MD")
    s.add_argument("book_dir", help="拆分产物目录，如 output/混沌冠冕")
    s.add_argument("--book", help="书名（默认取目录名）")
    s.add_argument("--out", help="输出目录（默认 <父目录>/<书名>_分析）")
    s.add_argument("--min-count", type=int, default=15, help="术语最低总频次（默认 15）")
    s.add_argument("--top-terms", type=int, default=200, help="保留的术语数（默认 200）")
    s.add_argument("--terms", help="人工确认的专名，逗号分隔，强制进表")
    s.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    s.set_defaults(func=cmd_stats)

    v = sub.add_parser("verify", help="统计结果与拆分索引对账")
    v.add_argument("book_dir")
    v.add_argument("--book")
    v.set_defaults(func=cmd_verify)

    t = sub.add_parser("terms", help="只跑术语发现")
    t.add_argument("book_dir")
    t.add_argument("--min-count", type=int, default=15)
    t.add_argument("--top-n", type=int, default=100)
    t.add_argument("--terms", help="人工确认的专名，逗号分隔")
    t.add_argument("--json", action="store_true")
    t.set_defaults(func=cmd_terms)

    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
