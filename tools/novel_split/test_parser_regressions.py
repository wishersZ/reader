# -*- coding: utf-8 -*-
"""novel_split / chai_stats 解析回归测试 —— 防止章节识别改坏、或两侧口径漂移。

背景（2026-11 实测时发现并修复的问题）：
  1. 「序」被当成特殊章前缀，正文「序列之树，其上空……」被切成
     「序」+「列之树……」，凭空多出 44 个特殊章，还把前一章截短。
  2. 复合词黑名单判断时正则已把单位字后的空格吃掉，于是
     「第一百零二章 回归拉莫尔！」被「章回」黑名单误杀，4 章丢失。
  3. 反过来，「第二节车厢的前段……」被当成「第 2 章」（节 + 车）。
  4. 两侧口径漂移：切分侧接受「第10章三次初级兵种抽取」这种无空格标题，
     统计侧却要求分隔符，于是 stats 章数比索引少（实测一本少 51 章）。

用法：
    py -3 tools/novel_split/test_parser_regressions.py
退出码 0 = 全部通过；非 0 = 有用例失败。

注意：本机沙箱下不要用管道接子进程 stdout，这里一律重定向到文件。
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPLIT = HERE / "novel_split.py"
STATS = HERE.parent / "chai" / "chai_stats.py"
TMP = HERE / "_tmp_regress"

# (用例名, 正文行, 期望章数, 期望特殊章数)
CASES = [
    (
        "序/序列不误判 + 章后空格不误杀 + 节车厢不误判",
        [
            "序章 天地初开",
            "这是序章正文。",
            "",
            "第一章 起点",
            "正文一。",
            "序列之树，其上空，漫天繁星，犹如群星之海。",
            "第二章 回归拉莫尔！",
            "正文二。",
            "　　第二节车厢的前段，中段，尾段，车顶，车底。",
            "第三章 终点",
            "正文三。",
        ],
        3,   # 第一/二/三章；「第二节车厢」不算
        1,   # 只有真正的「序章」
    ),
    (
        "无分隔符的真标题两侧都要认（第10章三次初级兵种抽取）",
        [
            "第1章 开局",
            "正文。",
            "第2章三次初级兵种抽取",
            "正文。",
            "第3章 收尾",
            "正文。",
        ],
        3,
        0,
    ),
    (
        "书首目录块（连续 5 行标题）不算章节",
        [
            "第1章 甲",
            "第2章 乙",
            "第3章 丙",
            "第4章 丁",
            "第5章 戊",
            "正文开始。",
            "正文第二行。",
            "正文第三行。",
            "第1章 甲",
            "正文一。",
            "正文一之二。",
            "正文一之三。",
            "第2章 乙",
            "正文二。",
        ],
        2,
        0,
    ),
    (
        "特殊章【附录1.通用魔咒】两侧都要认",
        [
            "第1章 甲",
            "正文一。",
            "　　正文一之二。",
            "【附录1.通用魔咒】",
            "这里才是附录正文。",
            "　　正文二。",
        ],
        1,
        1,
    ),
    (
        "正文句「第一回战斗是……。」不能当成章节",
        [
            "第1章 开局",
            "正文。",
            "第一回战斗是羽川修拿下首胜局，对方被他重创，但他自己也未能抢回老婆。",
            "第2章 收尾",
            "正文。",
        ],
        2,
        0,
    ),
    (
        "标题里的「求月票/求订阅」不能当广告删掉",
        [
            "第1章 开局（求月票）",
            "正文一。",
            "第2章 收尾（求订阅）",
            "正文二。",
        ],
        2,
        0,
    ),
    (
        "正文里的「第543章之前好不容易过了」不算章（黑名单仍有效）",
        [
            "第1章 开局",
            "正文。",
            "第543章之前好不容易过了",
            "正文。",
            "第二回合补卡两张。",
            "第2章 收尾",
            "正文。",
        ],
        2,
        0,
    ),
    (
        "长正文句「——第一集老爸就被……」不能当成章节（散文闸门要对原始行做）",
        [
            "第1章 开局",
            "正文。",
            "　　——第一集老爸就被当成敌国间谍，被整整六个大夏龙雀围在终点站不说，转眼间竟然还得进紫禁城喝咖啡，世界上还有比这血崩的开局吗？",
            "第2章 收尾",
            "正文。",
        ],
        2,
        0,
    ),
]


def _run(args: list[str], log: Path) -> int:
    """跑子命令，输出重定向到文件（沙箱下不能用管道）。"""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    with io.open(log, "w", encoding="utf-8") as fh:
        proc = subprocess.run([sys.executable, *args], stdout=fh, stderr=fh, env=env)
    return proc.returncode


def run_case(lines: list[str]) -> dict:
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir()
    src = TMP / "测试书.txt"
    io.open(src, "w", encoding="utf-8", newline="").write("\r\n".join(lines) + "\r\n")
    out = TMP / "out"
    out.mkdir()
    log = TMP / "run.log"

    rc = _run([str(SPLIT), "analyze", str(src), "--out", str(out)], log)
    if rc not in (0, 1):   # analyze 遇到「章号重复/逆序」之类会返回 1，但报告是有效的
        return {"error": f"analyze 退出码 {rc}（{log}）"}
    rep = io.open(out / "分析报告.md", encoding="utf-8-sig").read()
    m = re.search(r"结构：\*\*卷 \d+ 个 / 章 (\d+) 章 / 特殊章 (\d+) 个\*\*", rep)
    if not m:
        return {"error": "分析报告里没有结构行"}

    rc = _run([str(SPLIT), "split", str(src), "--out", str(out), "--parts", "1"], log)
    if rc != 0:
        return {"error": f"split 退出码 {rc}（{log}）"}
    book_dir = out / "测试书"
    rc = _run([str(STATS), "stats", str(book_dir), "--out", str(out / "测试书_分析")], log)
    if rc != 0:
        return {"error": f"stats 退出码 {rc}（{log}）"}
    data = json.loads((out / "测试书_分析" / "stats.json").read_text(encoding="utf-8"))

    return {
        "chapters": int(m.group(1)),
        "specials": int(m.group(2)),
        "stats_chapters": int(data["totals"]["chapters"]),
        "stats_specials": int(data["totals"]["specials"]),
    }


def unit_drop_toc_unsorted() -> tuple[bool, str]:
    """_drop_toc 必须能处理乱序输入（「篇/集」标记是追加在末尾的）。

    乱序时旧实现把负的行距当成「<= 2」，会把相隔几十万行的标题串成假 run 整块删掉
    （实测《反派少爷只想过佛系生活》因此丢了第 1917 章）。
    """
    import novel_split as NS
    from types import SimpleNamespace

    found = [("chapter", "章", 0, "t", "raw", idx) for idx in (100, 0, 1, 2, 3, 4)]
    kept = NS.Parser._drop_toc(None, found, SimpleNamespace(notes=[]))
    kept_idx = [f[5] for f in kept]
    return kept_idx == [100], f"期望保留 [100]，实际 {kept_idx}"


def cleanup() -> None:
    shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    ok = 0
    try:
        for name, lines, want_ch, want_sp in CASES:
            res = run_case(lines)
            if "error" in res:
                print("失败  " + name)
                print("      " + res["error"])
                continue
            good = (res["chapters"], res["specials"]) == (want_ch, want_sp) \
                and (res["stats_chapters"], res["stats_specials"]) == (want_ch, want_sp)
            print(("通过  " if good else "失败  ") + name)
            if not good:
                print(f"      期望 章{want_ch}/特殊{want_sp}；"
                      f"analyze 章{res['chapters']}/特殊{res['specials']}；"
                      f"stats 章{res['stats_chapters']}/特殊{res['stats_specials']}")
            ok += good
    finally:
        cleanup()
    ok_unit, detail = unit_drop_toc_unsorted()
    print(("通过  " if ok_unit else "失败  ") + "目录闸门：乱序标记不能被串成假 run")
    if not ok_unit:
        print("      " + detail)
    ok += ok_unit
    total = len(CASES) + 1
    print(f"\n{ok}/{total} 通过")
    sys.exit(0 if ok == total else 1)
