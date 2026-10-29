# -*- coding: utf-8 -*-
"""合成每本书的 00_总索引.md：文件清单 + 字数 + 各组索引片段 + 覆盖/边界体检摘要。

用法：py -3 make_index.py
"""
import re
import statistics
from pathlib import Path

RE_NODE_MEASURE = re.compile(r"^###\s*节点", re.M)
RE_S4 = re.compile(r"^\s*4\.\s*\*\*(节点详述|扩写正文)\*\*", re.M)
RE_S5 = re.compile(r"^\s*5\.\s*\*\*", re.M)


def section4_lengths(text):
    """逐节点第4节去空白字符数。"""
    marks = [m.start() for m in RE_NODE_MEASURE.finditer(text)]
    vals = []
    for i, st in enumerate(marks):
        en = marks[i + 1] if i + 1 < len(marks) else len(text)
        chunk = text[st:en]
        m4 = RE_S4.search(chunk)
        if not m4:
            vals.append(0)
            continue
        m5 = RE_S5.search(chunk, m4.end())
        body = chunk[m4.end(): m5.start() if m5 else len(chunk)]
        vals.append(len(re.sub(r"\s", "", body)))
    return vals


BOOKS = [
    ("幽暗主宰", r"G:\txt\novels\幽暗主宰_亲爱情节扩写",
     r"G:\txt\tools\batch15\results\cov_yinan.txt", r"G:\txt\tools\batch15\results\bnd_yinan.txt",
     "`幽暗主宰_暧昧与后宫情节点整理.md`"),
    ("混沌冠冕", r"G:\txt\novels\混沌冠冕_亲爱情节扩写",
     r"G:\txt\tools\batch15\results\cov_hundun.txt", r"G:\txt\tools\batch15\results\bnd_hundun.txt",
     "`混沌冠冕_暧昧与后宫情节点整理.md`"),
    # 源书《弗雷尔卓德的孤狼完结》已不在工作区（2026-10 整理），条目保留存档：
    # ("弗雷尔卓德的孤狼完结", r"G:\txt\novels\弗雷尔卓德的孤狼完结_亲爱情节扩写",
    #  r"G:\txt\tools\batch15\results\_archive_freljord\cov_freljord.txt", r"G:\txt\tools\batch15\results\_archive_freljord\bnd_freljord.txt",
    #  "`弗雷尔卓德的孤狼完结_暧昧与后宫情节点整理.md`"),
]

RE_NODE = re.compile(r"^###\s*节点", re.M)


def wc(p: Path) -> int:
    return len(p.read_text(encoding="utf-8"))


def main():
    for book, outdir, cov, bnd, ref in BOOKS:
        d = Path(outdir)
        if not d.exists():
            print(f"跳过（目录不存在）: {outdir}")
            continue
        files = sorted(p for p in d.glob("*.md") if not p.name.startswith(("_", "00_")))
        parts = [p for p in sorted(d.glob("_索引片段_*.md"))]

        lines = [f"# 《{book}》亲爱情节扩写 · 总索引", ""]
        lines += [f"> 体例：逐关系扩展档案（与 {ref} 第九节同体例）。",
                  "> 每个节点固定七段：场景定位／前因／现场状态／节点详述／关系性质／后果与伏笔／回查锚点。",
                  "> 亲密内容信息写全，但不仿写原文行文、不虚构对白原文；强迫与操纵线保留操纵可见性；",
                  "> 未成年／幼态对象与兄妹线为零情欲内容。", ""]

        total_nodes = 0
        lines.append("## 一、文件清单")
        lines.append("")
        lines.append("| 文件 | 节点数 | 全文字数 | 第4节 min | 第4节 中位 | 第4节 max | 第4节<600 |")
        lines.append("|---|---|---|---|---|---|---|")
        allv = []
        for p in files:
            t = p.read_text(encoding="utf-8")
            n = len(RE_NODE.findall(t))
            total_nodes += n
            vals = [v for v in section4_lengths(t) if v > 0]
            allv += vals
            if vals:
                lines.append(f"| `{p.name}` | {n} | {wc(p)} | {min(vals)} | "
                             f"{int(statistics.median(vals))} | {max(vals)} | "
                             f"{sum(1 for v in vals if v < 600)} |")
            else:
                lines.append(f"| `{p.name}` | {n} | {wc(p)} | - | - | - | - |")
        lines.append(f"| **合计** | **{total_nodes}** | **{sum(wc(p) for p in files)}** | "
                     f"{min(allv) if allv else '-'} | "
                     f"{int(statistics.median(allv)) if allv else '-'} | "
                     f"{max(allv) if allv else '-'} | "
                     f"{sum(1 for v in allv if v < 600)} |")
        lines.append("")
        if allv:
            lines.append(f"> 实测口径：每个 `### 节点` 的第4节正文去空白字符数。"
                         f"共 {len(allv)} 个节点；普通门槛 600、关键节点门槛 1800，"
                         f"达标情况见各 `_索引片段_*.md`。")
            lines.append("")

        if parts:
            lines.append("## 二、分组覆盖记录")
            for p in parts:
                lines.append("")
                lines.append(f"<!-- {p.name} -->")
                lines.append(p.read_text(encoding="utf-8").strip())
            lines.append("")

        for title, path in (("三、覆盖矩阵体检（整理稿条目 ↔ 输出节点）", cov),
                            ("四、边界扫描（收紧词表后）", bnd)):
            f = Path(path)
            if f.exists():
                txt = f.read_text(encoding="utf-8").strip().splitlines()
                lines.append(f"## {title}")
                lines.append("")
                lines.append("```")
                lines += txt[:120]
                if len(txt) > 120:
                    lines.append(f"…（完整报告见 {path}）")
                lines.append("```")
                lines.append("")

        lines.append("## 五、口径与返工记录")
        lines.append("")
        lines.append("- v1 → v2：第4节由“扩写正文（小说笔法）”改为“节点详述（研究档案口吻）”，"
                     "删除自造台词与文学化环境补写，只保留原文逐字摘引（≤40 字）与要点转述。")
        lines.append("- 各代理第二轮任务：补真实原文锚点（原“待核”项）、加深节点详述、更新字数统计。")
        lines.append("")

        (d / "00_总索引.md").write_text("\n".join(lines), encoding="utf-8")
        print(f"{book}: {len(files)} 文件 / {total_nodes} 节点 -> {d / '00_总索引.md'}")


if __name__ == "__main__":
    main()
