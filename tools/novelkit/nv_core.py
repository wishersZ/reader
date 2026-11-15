# -*- coding: utf-8 -*-
"""NovelKit 核心：把 `tools/chai/chai.ps1` 的编排逻辑用 Python 重写一遍。

设计要点
--------
1. **进程内复用**：直接调用 `novel_split.main()` / `chai_stats.main()`，不再依赖
   系统 Python，也不经过 PowerShell —— 打包成 EXE 后依然能跑。
2. **同一套步骤**：probe → encode → analyze → split → stats(+verify) → 精读任务书，
   与 chai.ps1 保持一致，输出目录结构也一致。
3. **GUI / CLI 共用**：所有函数只通过 `log(str)` 输出，GUI 把它接到文本框，CLI 接到 stdout。

与 chai.ps1 的差异（有意为之）：
- 预演（dry-run）不再继续找产物目录，直接结束；
- 定位产出目录时，除了 mtime 也接受「书名精确匹配」；
- 任务书的表头注明由 NovelKit 生成。
"""
from __future__ import annotations

import io
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


def _ensure_tool_paths() -> None:
    """源码运行时把 novel_split / chai 的目录并入 sys.path；打包后模块已内置，这一步是空操作。"""
    here = Path(__file__).resolve().parent
    for rel in ("../novel_split", "../chai"):
        p = (here / rel).resolve()
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))


_ensure_tool_paths()

import chai_stats  # noqa: E402
import novel_split  # noqa: E402

APP_NAME = "NovelKit"
VERSION = "1.0.0"

Log = Callable[[str], None]


# ------------------------------------------------------------------ 路径


def app_dir() -> Path:
    """EXE 所在目录；源码运行时是脚本目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_workspace(start: Optional[Path] = None) -> Optional[Path]:
    """向上逐级找「工作区根」：含 tools/novel_split 或 novels 目录的那一层。"""
    seeds = []
    if start is not None:
        seeds.append(Path(start).resolve())
    seeds.append(app_dir())
    seeds.append(Path.cwd().resolve())
    for seed in seeds:
        if seed.is_file():
            seed = seed.parent
        for p in [seed, *seed.parents][:8]:
            if (p / "tools" / "novel_split" / "novel_split.py").is_file() or (p / "novels").is_dir():
                return p
    return None


def default_output_root(inp: Optional[Path] = None) -> Path:
    ws = find_workspace(inp)
    return (ws / "output") if ws else (app_dir() / "output")


# ------------------------------------------------------------------ 输入识别


_BOOK_RE = re.compile(r"《([^》]+)》")
_AUTHOR_RE = re.compile(r"作者[：:]\s*[^（(【\[]+")
_BRACKET_RE = re.compile(r"[（(【\[][^）)】\]]*[）)】\]]")
_STATUS_TAIL_RE = re.compile(r"(完本|完结|全本|全集|精校版|自修正版|修正版)\s*$")


def book_name_from_path(p: Path) -> str:
    """从文件名推书名：优先《》，否则剥作者/括号/状态尾巴。

    与 chai.ps1 的 Get-BookName 同口径，保证同一本书两次跑出的目录名一致。
    """
    stem = Path(p).stem
    m = _BOOK_RE.search(stem)
    if m:
        return m.group(1).strip()
    s = _AUTHOR_RE.sub("", stem)
    s = _BRACKET_RE.sub("", s)
    s = _STATUS_TAIL_RE.sub("", s)
    s = s.strip(" -_·　")
    return s or stem.strip()


def is_split_dir(p: Path) -> bool:
    """是否已拆好的目录（含索引/manifest，且有正文分份）。"""
    p = Path(p)
    if not p.is_dir():
        return False
    has_index = (p / "00_目录索引.md").is_file() or (p / "manifest.json").is_file()
    parts = [f for f in p.glob("*.txt") if not f.name.startswith(("00_", "01_", "_"))]
    return has_index and bool(parts)


def part_files(book_dir: Path) -> list[Path]:
    """正文分份（排除索引/清单/下划线开头的辅助文件）。"""
    return sorted(
        (f for f in Path(book_dir).glob("*.txt") if not f.name.startswith(("00_", "01_", "_"))),
        key=lambda f: f.name,
    )


# ------------------------------------------------------------------ 输出捕获


class LogStream(io.TextIOBase):
    """把模块的 print 逐行转给 log 回调（GUI 文本框 / CLI stdout）。"""

    def __init__(self, emit: Log):
        self._emit = emit
        self._buf = ""

    def write(self, s: str) -> int:  # noqa: D102
        self._buf += s
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._emit(line.rstrip("\r"))
        return len(s)

    def flush(self) -> None:  # noqa: D102
        if self._buf:
            self._emit(self._buf.rstrip("\r"))
            self._buf = ""


def _run_module(mod, argv: list[str], log: Log) -> int:
    """在捕获输出、替换 sys.stdout 的前提下调用子工具 main()。

    注意：log 很可能就是 print（或内部调用 print 的 lambda）。如果回调期间
    sys.stdout 还指向 LogStream，就会「print → LogStream → log → print」无限递归。
    因此回调时临时把 sys.stdout 切回真实输出流。
    """
    real_out = sys.stdout or sys.__stdout__

    def emit(msg: str) -> None:  # noqa: ANN001
        old = sys.stdout
        sys.stdout = real_out  # type: ignore[assignment]
        try:
            log(msg)
        finally:
            sys.stdout = old

    stream = LogStream(emit)
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = stream
    try:
        rc = mod.main(list(argv))
    finally:
        stream.flush()
        sys.stdout, sys.stderr = old_out, old_err
    return int(rc or 0)


# ------------------------------------------------------------------ 结果模型


@dataclass
class BookSummary:
    book: str
    chapters: object = ""
    chars: object = ""
    paragraphs: object = ""
    parts: object = ""
    mean: object = ""
    stdev: object = ""
    dialogue: object = ""
    analysis_dir: str = ""
    ok: bool = True


def _load_stats(analysis_dir: Path) -> Optional[dict]:
    f = Path(analysis_dir) / "stats.json"
    if not f.is_file():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _summary_from(book: str, analysis_dir: Path, stats: Optional[dict]) -> BookSummary:
    if not stats:
        return BookSummary(book=book, analysis_dir=str(analysis_dir), ok=False)
    t = stats.get("totals", {})
    m = stats.get("metrics", {})
    cl = m.get("chapter_len", {})
    return BookSummary(
        book=book,
        chapters=t.get("chapters", ""),
        chars=t.get("total_chars", ""),
        paragraphs=t.get("total_paragraphs", ""),
        parts=t.get("parts", ""),
        mean=cl.get("mean", ""),
        stdev=cl.get("stdev", ""),
        dialogue=m.get("dialogue_para_pct", ""),
        analysis_dir=str(analysis_dir),
    )


def _disp_width(s: str) -> int:
    """终端显示宽度：中文/全角算 2 列。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in str(s))


def _pad(s: object, width: int) -> str:
    s = "" if s is None else str(s)
    return s + " " * max(0, width - _disp_width(s))


def format_summary(rows: list[BookSummary]) -> str:
    headers = ["书名", "章数", "净字数", "段落数", "份数", "均章长", "章长SD", "对话占比", "分析目录"]
    keys = ["book", "chapters", "chars", "paragraphs", "parts", "mean", "stdev", "dialogue", "analysis_dir"]
    data = [[_pad(getattr(r, k), 0) for k in keys] for r in rows]
    widths = [max([_disp_width(h)] + [_disp_width(row[i]) for row in data]) for i, h in enumerate(headers)]
    lines = ["  ".join(_pad(h, widths[i]) for i, h in enumerate(headers)),
             "  ".join("-" * widths[i] for i in range(len(headers)))]
    for row in data:
        lines.append("  ".join(_pad(row[i], widths[i]) for i in range(len(headers))))
    return "\n".join(lines)


# ------------------------------------------------------------------ 精读任务书


_TASKBOOK_BODY = """## 二、每个 subagent 的固定交付格式

要求每份笔记**结构一致**，否则主 agent 无法汇总。逐章至少写清：

```markdown
### 第N章 章名
- 情节：本章发生了什么（2—4 句，只写事实）
- 功能：本章在结构上干什么（铺垫/转折/高潮/结算/降温/换轨）
- 爽点：本章命中了哪几类爽点（打脸/装逼/获取/升级/身份揭晓/收人/知识掠夺/建设/反派吃瘪）
- 章末钩：末句是什么，属于哪类钩（对白/宣言/悬念/危机/收获/拟声）
- 金句：本章最值得记的 1—2 句原文（逐字摘录，标行号）
```

卷（份）末额外写清：

- **本卷情节链**：因果相连的事件序列（不是清单，要能看出"因为…所以…"）
- **本卷功能定位**：这一卷在全书中承担什么
- **人物/关系变化**：谁的地位、实力、关系变了，变成什么
- **世界观新增**：新设定的首现处
- **技法观察**：视角、节奏、战斗写法、信息投喂、用梗密度
- **可核查统计**：本卷章数、均章长、最长/最短章

## 三、纪律（必须写进每个 subagent 的 prompt）

1. **只写读到的内容**，引用要能回到原文；不要编造、不要推断当成事实。
2. **章号以正文标题为准**，不要自行重排。
3. **区分三类事实**：①文本明写的 ②可合理推断的（标注"推断"）③作者未交代的（标注"未交代"）。
4. **统计数字只引用 `stats_摘要.md`**，不要自己心算。
5. 读不完就如实说读到第几章，**不要用摘要冒充精读**。

## 四、主 agent 的汇总顺序

1. 先读 `stats_摘要.md` 与 `chapters.csv`（数据底座）
2. 再逐份读 subagent 笔记（人物/情节/技法）
3. 最后写总报告，结构建议：
   定位与坐标系 → 宏观结构分期 → 情节与主线发动机 → 人物弧光 →
   世界观体系 → 叙事与写作风格 → **爽点配方与节奏规律** → 优点与缺陷 → 结论
4. **凡是结论都要能指回章号**；无法核查的标注为"待验证"。

## 五、本机可用的剖析工具

- 统计：`NovelKit.exe stats <output/书名>`
- 对账：`NovelKit.exe verify <output/书名>`
- 词表：`NovelKit.exe terms <output/书名> --top-n 200`
"""


def write_taskbook(book_dir: Path, analysis_dir: Path, book: str,
                   stats: Optional[dict], log: Log, dry_run: bool = False) -> Optional[Path]:
    """生成「分层精读任务书.md」——把 N 份正文分配给 N 个 subagent 的作业单。"""
    analysis_dir = Path(analysis_dir)
    files = part_files(book_dir)
    n = len(files)
    lines = [
        f"# 《{book}》分层精读任务书",
        "",
        "> 由 `NovelKit`（与 `tools/chai/chai.ps1` 同一套流程）自动生成。用途：把 N 份正文分配给 N 个 subagent",
        "> 逐章精读，每个 subagent 产出一份笔记，再由主 agent 汇总成总报告。",
        "",
        "## 一、任务分工",
        "",
        f"全书共 **{n} 份**，建议按下面的表格逐份派发（subagent 之间互不依赖，可并行）。",
        "",
        "| # | 正文文件 | 章数 | 净字数 | 起 | 止 |",
        "|---|---|---:|---:|---|---|",
    ]
    parts = (stats or {}).get("parts") or []
    if parts:
        for i, p in enumerate(parts, 1):
            lines.append(
                f"| {i} | `{p.get('file', '')}` | {p.get('chapters', '')} | "
                f"{p.get('chars', '')} | {p.get('first_heading', '')} | {p.get('last_heading', '')} |"
            )
    else:
        for f in files:
            lines.append(f"|  | `{f.name}` |  |  |  |")
    lines += ["", _TASKBOOK_BODY]
    text = "\n".join(lines).rstrip() + "\n"

    target = analysis_dir / "精读任务书.md"
    if not dry_run:
        analysis_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        log(f"  任务书：{target}")
        return target
    return None


# ------------------------------------------------------------------ 一键流水线


def _snapshot(out: Path) -> dict[Path, float]:
    snap: dict[Path, float] = {}
    if Path(out).is_dir():
        for p in Path(out).iterdir():
            if p.is_dir() and not p.name.endswith("_分析"):
                try:
                    snap[p] = p.stat().st_mtime
                except OSError:
                    pass
    return snap


def _locate_book_dirs(out: Path, book: Optional[str], before: dict[Path, float], log: Log) -> list[Path]:
    if book:
        guess = Path(out) / book
        if guess.is_dir():
            return [guess]
        log(f"  ⚠ 未找到目录 {guess}（书名可能被工具改写），改用时间戳定位")
    cands = []
    for p in Path(out).iterdir():
        if not p.is_dir() or p.name.endswith("_分析"):
            continue
        if not (p / "manifest.json").is_file():
            continue
        try:
            mt = p.stat().st_mtime
        except OSError:
            continue
        if p not in before or before[p] != mt:
            cands.append(p)
    cands.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        raise RuntimeError("切分完成但定位不到产出目录，请填写「书名」后重试")
    return cands


def run_chai(input_path: str | Path,
             out_root: str | Path | None = None,
             book: Optional[str] = None,
             parts: int = 0,
             max_chars: int = 0,
             terms: Optional[str] = None,
             min_count: int = 15,
             skip_encode: bool = False,
             dry_run: bool = False,
             tasks_only: bool = False,
             log: Log = print) -> list[BookSummary]:
    """一键拆书：与 chai.ps1 等价，返回每本书的汇总。"""
    src = Path(input_path).expanduser()
    if not src.exists():
        raise FileNotFoundError(f"输入不存在：{src}")
    src = src.resolve()
    out = Path(out_root).expanduser() if out_root else default_output_root(src)
    out = out.resolve()
    if not dry_run and not tasks_only:
        out.mkdir(parents=True, exist_ok=True)

    split_mode = is_split_dir(src)
    log("=== NovelKit 一键拆书 ===")
    log(f"输入        : {src}")
    log(f"输入类型    : {'已拆分的目录（跳过 ①—④，只跑统计）' if split_mode else '原始文本（跑完整流水线）'}")
    log(f"产物根目录  : {out}")

    book_dirs: list[Path] = []

    if split_mode:
        book_dirs.append(src)
        book = book or src.name
    else:
        if not book:
            book = book_name_from_path(src)
            log(f"推定书名    : {book}")

        log("")
        log("[1/5] probe —— 探测编码 / 换行 / BOM（不写盘）")
        if dry_run:
            log("  （预演：只探测，不改文件）")
        _run_module(novel_split, ["probe", str(src)], log)

        if not skip_encode:
            log("")
            log("[2/5] encode —— 无损统一到 UTF-8 + CRLF（就地改写，自动留 .bak）")
            enc = ["encode", str(src), "--to", "utf-8", "--eol", "crlf"]
            if dry_run:
                enc.append("--dry-run")
            rc = _run_module(novel_split, enc, log)
            if rc != 0:
                raise RuntimeError(
                    f"编码统一失败（退出码 {rc}）。若源文件已是 UTF-8，可勾选「跳过编码」。")
        else:
            log("")
            log("[2/5] encode —— 已按「跳过编码」跳过")

        log("")
        log("[3/5] analyze —— 分析卷 / 章结构")
        rc = _run_module(novel_split, ["analyze", str(src), "--out", str(out)], log)
        if rc not in (0, 1):
            raise RuntimeError(f"结构分析失败（退出码 {rc}）")

        log("")
        log("[4/5] split —— 规范化 + 排序 + 切分")
        sp = ["split", str(src), "--out", str(out)]
        if parts and parts > 0:
            sp += ["--parts", str(parts)]
        if max_chars and max_chars > 0:
            sp += ["--max-chars", str(max_chars)]
        if dry_run:
            sp.append("--dry-run")
        before = {} if dry_run else _snapshot(out)
        rc = _run_module(novel_split, sp, log)
        if rc != 0:
            raise RuntimeError(f"切分失败（退出码 {rc}）")

        if dry_run:
            log("")
            log("预演结束：未写任何文件（去掉「预演」后才会真正生成产物）。")
            return []

        book_dirs = _locate_book_dirs(out, book, before, log)

    summaries: list[BookSummary] = []
    for bd in book_dirs:
        bd = Path(bd)
        bname = bd.name
        analysis_dir = bd.parent / f"{bname}_分析"

        if not tasks_only:
            log("")
            log(f"[5/5] stats —— 机读统计：《{bname}》")
            st = ["stats", str(bd), "--book", bname, "--out", str(analysis_dir),
                  "--min-count", str(min_count)]
            if terms:
                st += ["--terms", terms]
            rc = _run_module(chai_stats, st, log)
            if rc != 0:
                log(f"  ⚠ 统计失败（退出码 {rc}），跳过本书")
                summaries.append(BookSummary(book=bname, analysis_dir=str(analysis_dir), ok=False))
                continue

            log("")
            log("  对账 verify：")
            rc = _run_module(chai_stats, ["verify", str(bd), "--book", bname], log)
            if rc != 0:
                log("  ⚠ 对账未通过——统计口径与拆分索引不一致，请看上面的差异说明")

        stats = _load_stats(analysis_dir)
        log("")
        log(f"生成精读任务书：《{bname}》")
        write_taskbook(bd, analysis_dir, bname, stats, log)
        summaries.append(_summary_from(bname, analysis_dir, stats))

    if summaries:
        log("")
        log("=== 完成 ===")
        for line in format_summary(summaries).splitlines():
            log(line)
        if any(s.ok for s in summaries):
            log("下一步：把「精读任务书.md」按份派给 subagent 逐章精读，再汇总成总报告。")
    else:
        log("没有生成统计产物。")
    return summaries


# ------------------------------------------------------------------ 单独动作


def resolve_book_dir(path: str | Path) -> Path:
    """把用户给的路径解析成「拆分产物目录」。"""
    p = Path(path).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"路径不存在：{p}")
    if p.is_dir() and is_split_dir(p):
        return p
    if p.is_dir():
        # 可能是 output 根：找里面唯一一本含 manifest 的书
        cands = [d for d in p.iterdir() if d.is_dir() and (d / "manifest.json").is_file()]
        if len(cands) == 1:
            return cands[0]
        if cands:
            raise ValueError(f"{p} 下有 {len(cands)} 本书，请直接指定其中一本")
    raise ValueError(f"不是拆分产物目录：{p}")


def run_stats(book_dir: str | Path, out_dir: str | Path | None = None,
              book: Optional[str] = None, terms: Optional[str] = None,
              min_count: int = 15, log: Log = print) -> int:
    bd = resolve_book_dir(book_dir)
    analysis_dir = Path(out_dir) if out_dir else bd.parent / f"{bd.name}_分析"
    argv = ["stats", str(bd), "--book", book or bd.name, "--out", str(analysis_dir),
            "--min-count", str(min_count)]
    if terms:
        argv += ["--terms", terms]
    return _run_module(chai_stats, argv, log)


def run_verify(book_dir: str | Path, book: Optional[str] = None, log: Log = print) -> int:
    bd = resolve_book_dir(book_dir)
    return _run_module(chai_stats, ["verify", str(bd), "--book", book or bd.name], log)


def run_terms(book_dir: str | Path, top_n: int = 100, min_count: int = 15,
              terms: Optional[str] = None, log: Log = print) -> int:
    bd = resolve_book_dir(book_dir)
    argv = ["terms", str(bd), "--top-n", str(top_n), "--min-count", str(min_count)]
    if terms:
        argv += ["--terms", terms]
    return _run_module(chai_stats, argv, log)


def run_probe(path: str | Path, log: Log = print) -> int:
    return _run_module(novel_split, ["probe", str(Path(path).expanduser())], log)


def run_tasks_only(book_dir: str | Path, log: Log = print) -> Optional[Path]:
    bd = resolve_book_dir(book_dir)
    analysis_dir = bd.parent / f"{bd.name}_分析"
    stats = _load_stats(analysis_dir)
    log(f"重新生成精读任务书：《{bd.name}》")
    return write_taskbook(bd, analysis_dir, bd.name, stats, log)
