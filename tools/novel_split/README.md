# novel_split.py —— 长篇小说编码统一 + 拆分工具（供 AI 分析）

把动辄几 MB、编码混杂、排版凌乱的网文 TXT，**先无损统一编码**，再整理成干净 UTF-8，
按章节排好序，切成**每份约 10 万字的若干 TXT**，让大模型能一份一份读完整本书而不爆上下文。

## 五个子命令

| 子命令 | 作用 | 是否写盘 |
|---|---|---|
| `probe` | 探测编码 / BOM / 换行 / 可解码候选，**先跑这个看文件底细** | 否 |
| `encode` | 把 TXT **无损**统一到指定编码（默认 UTF-8） | 是（默认就地 + `.bak`） |
| `analyze` | 分析卷/章结构，输出 Markdown 报告 | 只写报告 |
| `split` | 规范化 + 排序 + 按卷/按数量切分 | 是 |
| `all` | 一条命令跑完 `probe → encode(可选) → analyze → split` | 是 |

所有子命令都支持 `--json`（stdout 只输出机器可读 JSON，人类提示转 stderr）和 `--quiet`，
方便 AI 或脚本直接调用。

**退出码**：`0` 全部成功 · `1` 部分失败 · `2` 没有输入 · `3` 校验失败或严格模式下编码无法无损表示。

## 它解决的四件事

| # | 问题 | 本工具的做法 |
|---|---|---|
| 1 | 编码混杂（UTF-8 / UTF-8 BOM / GBK / GB18030 / UTF-16） | `encode` 无损统一到指定编码，**强制规定**目标编码 |
| 2 | 排版凌乱（半角空格、Tab、全角空格混用；广告水印；3+ 连续空行） | 正文统一缩进、清理广告、压缩空行 |
| 3 | 章节乱、章号有缺有重 | 识别章节并排序，**章号重置**（每卷从 001 重新数）自动处理 |
| 4 | 太长，超出上下文 | **有卷按卷**切，**无卷按自定义数量**均分 |

## 快速开始

```powershell
# 0) 先看每个文件的编码底细（不写盘）
py -3 novel_split.py probe "G:\txt\novels"

# 1) 把原始小说无损统一成 UTF-8（就地改写，自动留 .bak 备份）
py -3 novel_split.py encode "G:\txt\novels" --to utf-8 --eol crlf

# 2) 分析结构，不切分（强烈建议先跑）
py -3 novel_split.py analyze "G:\txt\novels" --out "G:\txt\output"

# 3) 按默认策略拆分（有卷按卷，无卷每份约 10 万字）
py -3 novel_split.py split "G:\txt\novels" --out "G:\txt\output"

# 4) 只要一本，指定份数
py -3 novel_split.py split "G:\txt\novels\混沌冠冕.txt" --parts 20 --out "G:\txt\output\单本"

# 5) 给 AI/脚本用：拿 JSON
py -3 novel_split.py analyze "G:\txt\novels" --json --quiet
py -3 novel_split.py split "G:\txt\novels" --dry-run --json --quiet

# 6) 一条命令跑完 probe → encode → analyze → split
py -3 novel_split.py all "G:\txt\novels" --encode --to utf-8 --src-eol crlf
```

也可以直接双击/调用 `run_all.cmd`（等价于 `all` 子命令的薄包装）。

## encode：无损统一编码

```powershell
py -3 novel_split.py encode G:\txt\novels  --to utf-8            # 只转编码，换行不动（最小改动）
py -3 novel_split.py encode G:\txt\novels  --to utf-8 --eol crlf # 编码 + 换行一起统一
py -3 novel_split.py encode G:\txt\novels  --to utf-8 --dry-run  # 预演，看会动哪些文件
py -3 novel_split.py encode G:\txt\novels  --to gbk --out-dir D:\gbk_out   # 不动源文件，写副本
py -3 novel_split.py encode 某书.txt --from gbk --to utf-8          # 源文件被误判时强制指定
```

行为约定：

- **无损**：必须先能严格编码，且**回读后与原文完全一致**才写盘。目标编码表示不了的字符
  （如 emoji 转 GBK）直接报错并给出建议，**不会静默替换成 `?`**；确要强行转换用 `--lenient`，
  结果里会标记 `lossy`。
- **可回退**：就地改写时自动生成 `<原名>.txt.bak`；如果 `.bak` 已存在则**不覆盖**，保住最早的原件。
- **幂等**：文件已经是目标编码和换行时直接 `skip`，不产生多余写入，可安全重复执行。
- **写后回读校验**：写完立即重新读取比对字节与文本，失败会报错（防止杀软/磁盘干扰）。
- 支持 `utf-8` / `utf-8-sig` / `gb18030` / `gbk` / `gb2312` / `big5` / `utf-16` / `utf-16-le|be` 等。
- 顺带清除正文里残留的零宽 `U+FEFF`（多 BOM 拼接的 TXT 很常见，不清掉会混进正文）。

## 每本书的输出目录

```
output/书名/
├── 00_目录索引.md          ← 先给 AI 看这个：每份文件装了什么、起止章节、字数
├── 01_章节清单.tsv          ← 全部章节的序号/卷/章号/标题/原行号/净字数
├── manifest.json           ← 机器可读清单（含校验结果）
├── 书名_第一卷 化龙.txt      ← 正文，UTF-8、CRLF、段首 2 个全角空格
├── _已删除行.txt            ← 被当作广告/水印删掉的行（可人工复核）
└── _排序调整.tsv            ← 仅当排序真的搬动了章节时才生成
```

正文文件里**不注入任何额外标记**（没有 YAML 头、没有分隔线），所以可以直接整份喂给模型，
也可以随时和原文对账：所有份的净字数之和 == 全文净字数，工具会自动回读校验并在索引里写明。

## 常用参数（`split` / `analyze`）

| 参数 | 说明 |
|---|---|
| `--mode auto\|volume\|parts\|chars` | 切分策略；`chars` = 按字数上限切 |
| `--parts N` | 无卷时分成几份；不指定则按每份约 10 万字自动决定 |
| `--max-chars N` | 每份净字数上限（与 `--parts` 二选一） |
| `--sort auto\|force\|off` | `auto` 默认分段排序；`force` 整卷按章号重排；`off` 保持原顺序 |
| `--indent N` | 正文缩进的全角空格数（默认 2，`0` = 不缩进） |
| `--eol crlf\|lf` / `--bom` | 输出换行符 / 是否输出 BOM |
| `--keep-ads` | 不清理广告水印（怀疑误删正文时用） |
| `--heading-style normalize` | 把 `第1章：标题`、`第一章 标题` 统一成 `第1章 标题` |
| `--dump-markers` | 输出识别到的每一个标题行，便于排查误判 |
| `--dry-run` | 只统计、不写文件 |
| `--json` / `--quiet` | 机器可读输出 / 静默 |

## 它认哪些章节/卷格式

已实测覆盖下列写法（含 GBK 与 UTF-8 两种编码）：

```
第1章 标题        第001章 标题       第一章 标题        第1章：标题
===第一章 标题===                   第1回/第1节/第1话/第1篇/第1集
第一卷 化龙        第二部 逆袭        卷1 风起
序章 / 楔子 / 引子 / 前言 / 番外 / 终章 / 尾声 / 后记 / 完本感言
```

识别的难点在**别把正文当标题**，工具用四道闸门拦：

1. **复合词黑名单**：`第二回合补卡两张。`、`第543章之前好不容易过了…` 这类正文会被否掉，
   而 `第10章重新开场抽取` 这种"真标题但没空格"能保住。
2. **长度闸门**：标题整行 > 60 字，或含句号且 > 30 字，视为正文。
3. **密集列表闸门**：连续 ≥5 行都是标题、彼此只隔 ≤2 行 → 判定为目录页/系统面板列表
   （实测拦住了小说里角色正在翻的《魔神》目录页，以及一串 `序九：…序一：…`）。
4. **空壳重复闸门**：同卷同章号、标题为空或与兄弟相同、正文 < 50 字 → 判为重复标题剔除
   （其行文并入前一章，不丢内容）。

## 关于"排序"，一个重要的实测发现

原始文件里的章号"逆序"绝大多数**不是文件被弄乱了**，而是这两种情况：

- **章号重置**：每卷从 `第001章` 重新开始（《我在东京教剑道》7 个卷全部如此）。
  全局按章号排序会把这本书彻底打乱 —— 所以工具**按卷分组、组内排序、自动分段**。
- **原书笔误 / 作者的话**：例如把 `第1119章` 插在 1020 章中间，或夹一句 `第三章正在码，凌晨弄完`。

因此 `--sort auto` 在实测的 7 本书上**一章都没有搬动**，只在报告里如实告知"发现了 N 处逆序"。
如果确认某本书真的被打乱，用 `--sort force` 强制重排，搬动了哪些章会记在 `_排序调整.tsv`。

## 给 AI / 脚本的调用约定

1. **只读先探**：`probe --json` 拿到每个文件的 `detected` / `eol` / `bom` / `ambiguous`
   / `stray_bom_chars`，据此决定是否需要 `encode`、是否需要 `--from` 强制指定。
2. **幂等可重跑**：`encode` 已符合的文件返回 `action: "skip"`；`split` 每次覆盖输出目录。
   重复执行不会累积副作用，适合 AI 反复调用。
3. **不猜结果，看退出码**：`0` 成功 / `1` 部分失败 / `2` 无输入 / `3` 校验失败或无法无损编码。
4. **`--dry-run` 先预演**：任何写盘动作都支持预演，返回结构与真实执行一致，便于先确认再执行。
5. **stdout 只放 JSON**：加 `--json` 后，进度与提示全部走 stderr，stdout 可直接 `json.loads`。

`split --json` 每本书返回的关键字段：

```jsonc
{
  "command": "split", "ok": true,
  "book": "混沌冠冕", "source": "G:\\txt\\混沌冠冕.txt",
  "encoding": "utf-8", "decode_lossless": true,
  "volumes": 0, "chapters": 644, "specials": 1, "moved_lines": 4,
  "mode": "按数量3份", "moves": 0, "notes": ["..."],
  "out_dir": "output\\混沌冠冕",
  "total_chars": 2882918, "normalized_chars": 2882918,
  "loss": 0,                       // 必须为 0，否则退出码 3
  "verified_files": 3, "file_count": 3,
  "files": [                       // 每份的定位信息，AI 靠它做检索
    { "file": "混沌冠冕_第一部分.txt", "chapters": 212, "chars": 962927,
      "first_chapter": "第1章 一个不太可能的弥赛亚",
      "last_chapter": "第212章 命运的枪声！" }
  ]
}
```

## 同类开源工具调研结论

| 工具 | 能力 | 与本需求的差距 |
|---|---|---|
| [luul11/TxtSplitTool](https://github.com/luul11/TxtSplitTool) | 桌面 GUI；按章节切成**每章一个文件**；或按输入数量均匀切 N 份 | 没有"卷"的概念；不做编码转换与排版规范化；输出颗粒是章不是卷 |
| [Weeexiao/Novel-Chapterizer](https://github.com/Weeexiao/Novel-Chapterizer) | Next.js 网页版；多编码（UTF-8/GBK/GB2312）、自定义正则、导出 MD/TXT/ZIP/EPUB | 逐章输出，不按卷打包；浏览器端操作，不便批量/脚本化 |
| [Anarcadia/chuanban-chaishu-skills](https://github.com/Anarcadia/chuanban-chaishu-skills) | **最接近**：`novel_splitter.py` 支持卷/部/篇/章/节/话/回/集 多层识别 + chardet 编码探测，配套 Claude Code 拆书 skills | 一次只按**单一层级**切，输出是每章一个 `.md`；不做排版规范化；**会把你的源文件 `shutil.move` 搬走**；无零丢失校验 |
| [rockbenben/novel-processor](https://github.com/rockbenben/novel-processor) | 一键修复排版：智能换行、章节重排、繁简转换、广告清理 | 只整理不拆分，不产出分卷/分部分文件 |
| [voocel/ainovel-cli](https://github.com/voocel/ainovel-cli) | 多 agent 全自动 AI 小说**生成** | 方向相反，不处理既有长篇的切分 |

**结论**：现有工具覆盖了"逐章切分"和"排版修复"，但**没有**一个同时做到
「卷优先整本打包 → 无卷按自定义数量均分 → 编码与排版规范化 → 章号重置安全排序 → 零丢失可校验」。
所以这个脚本是自建的，但它借鉴了 `chuanban-chaishu-skills` 的多层级识别思路。

## 已知局限

- 章节标题格式千奇百怪，遇到没见过的写法请先 `analyze` 看报告；必要时用
  `--chapter-regex` / `--volume-regex` 传入自定义正则（需含 `num`/`unit`/`rest` 命名组）。
- 按卷切分时**各卷大小天然不均**（实测 21 万字 ~ 87 万字）。若某卷仍然超过上下文，
  对该卷单独再跑一次 `--mode parts` 即可。
- 工具只做搬运和整理，**不修改一个字**（广告清理除外，且被删行全部存档可复核）。
