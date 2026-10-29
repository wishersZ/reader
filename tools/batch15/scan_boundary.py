# -*- coding: utf-8 -*-
"""边界扫描：扩写产物里有没有越线内容。

用法：py -3 scan_boundary.py <扩写目录> <输出报告.txt> [--strict-names 名字1,名字2...]

三类检测：
  A. 露骨词表命中（直接列出行）
  B. 未成年/幼态角色名 与 亲密词 在同一段共现（列出段落首句）
  C. 强迫/操纵词与情色化词共现（提示是否把强迫写成了情色享受）
"""
import re
import sys
from pathlib import Path

EXPLICIT = """阴茎 阴道 龟头 阴唇 乳头 乳尖 肉棒 抽插 抽送 射精 精液 淫水 爱液 下体 私处
性器 花穴 蜜穴 肉穴 高潮 呻吟 挺入 淫叫 床技 里外翻搅
勃起 勃大 硬挺 酥胸 裸体 全裸 胴体 娇喘 泄身 顶弄 摩挲下""".split()

# 词形误报白名单：出现在这些语境里就不算露骨描写
EXPLICIT_OK_CTX = "吞没 贯穿 插入 性交 做爱 交合".split()
# 免责声明/边界说明特征词：含这些词的段落不参与"未成年共现"判定
DISCLAIMER = "不得 不能 不提供 非恋爱 零情欲 降级 不构成 不等于 不予 禁止 不按 不应 不作 边界 儿童状态 梳理".split()

MINOR_NAMES = "艾琳丝特 魔女之子 芙兰朵露 薇薇安 娜贝利乌斯 娑娜 阿卡丽 佐伊 安妮 烙飒 小狼 妮蔻 布耶尔".split()
INTIMACY = "吻 亲 抚摸 情欲 欲望 裸 赤裸 身体 床上 同床 抱 依偎 喘息 体温 酥 软".split()
COERCE = "强迫 强吻 性侵 刻印 魅惑 操纵 控制 诱导 迷乱 失神 昏迷 无法反抗 意识混乱 药酒 失忆".split()
EROTIC = "快感 愉悦 享受 主动迎合 甘之如饴 舒服 沉溺 欲仙".split()


def paras(text):
    buf, out = [], []
    for line in text.splitlines():
        if line.strip() == "":
            if buf:
                out.append("".join(buf))
                buf = []
        else:
            buf.append(line.strip())
    if buf:
        out.append("".join(buf))
    return out


def main(out_dir, report_path):
    files = sorted(Path(out_dir).glob("*.md"))
    rep = [f"扩写目录: {out_dir}  文件数 {len(files)}", ""]
    a_hits, b_hits, c_hits = [], [], []
    for p in files:
        text = p.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            for w in EXPLICIT:
                if w in line:
                    if w in EXPLICIT_OK_CTX:
                        continue  # 词形误报（黑暗吞没 / 贯穿后续）
                    a_hits.append((p.name, i, w, line.strip()[:70]))
                    break
        for para in paras(text):
            minor = [n for n in MINOR_NAMES if n in para]
            if minor and any(w in para for w in INTIMACY):
                if any(d in para for d in DISCLAIMER):
                    continue  # 反向免责声明段（"不得按恋爱理解"等），不算越线
                b_hits.append((p.name, minor, para[:70]))
            if any(w in para for w in COERCE) and any(w in para for w in EROTIC):
                if any(d in para for d in DISCLAIMER):
                    continue
                c_hits.append((p.name, para[:70]))

    rep.append(f"A. 露骨词命中: {len(a_hits)}")
    for f, i, w, s in a_hits[:80]:
        rep.append(f"   {f}:{i} [{w}] {s}")
    rep.append("")
    rep.append(f"B. 未成年/幼态角色名 + 亲密词 同段: {len(b_hits)}")
    for f, names, s in b_hits[:80]:
        rep.append(f"   {f} {names} :: {s}")
    rep.append("")
    rep.append(f"C. 强迫/操纵词 + 情色化词 同段: {len(c_hits)}")
    for f, s in c_hits[:80]:
        rep.append(f"   {f} :: {s}")
    Path(report_path).write_text("\n".join(rep), encoding="utf-8")
    return len(a_hits), len(b_hits), len(c_hits)


if __name__ == "__main__":
    a, b, c = main(sys.argv[1], sys.argv[2])
    print(f"done: explicit={a} minor={b} coerce_erotic={c}")
