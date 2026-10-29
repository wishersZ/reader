# G:\txt 工作区

长篇小说「整理 → 拆分 → 供 AI 分析 / 重写」的工作区，同时存放整合了拆分功能的月读阅读器源码。

根目录只放本 README、`.gitignore` 和下面列出的目录，不放数据文件或临时产物。

## 目录结构

```
G:\txt\
├── README.md                    本文件：工作区总说明
├── novels\                      小说数据区（不进版本库）
│   ├── *.txt                    10 个正文文件（7 本已统一编码，见下表；另有 3 本未统计，见下）
│   ├── _backup\                 编码统一前的 5 个原件（*.txt.bak，GBK / 带 BOM）
│   ├── _alt\                    同一本书的替代来源版本（未参与拆分）
│   ├── 混沌冠冕_每15章拆分\ 等   单本书的拆章 / 扩写工作目录
│   ├── _notes\                  各书的整理稿、拆书报告、对比结论（非正文）
│   └── 混沌冠冕_重写版_备份_20261021\  重写项目的旧副本备份
├── output\                      拆分与统计产物（不进版本库，可随时重新生成）
│   ├── <书名>\                  分卷/分部分正文 + 目录索引 + manifest
│   ├── <书名>_分析\             机读统计 + 精读任务书 + 逐章笔记
│   └── 混沌冠冕_分析\           整体/分段分析报告、关系节点数据
├── docs\                        文档
│   ├── README.md                文档索引（先看这个）
│   ├── rules\                   写作规则与方法论（规则模板 / 爽文流程 / 写书流程设计 / 研究笔记）
│   ├── research\                宿主插件与网文生态研究（DSH 插件分析、方法论笔记）
│   ├── reader-integration.md    月读整合说明：架构、改动、验证、已知限制
│   ├── rules-audit-2026-10-29.md          规则审计与更新记录
│   └── skills-rules-merge-ai-template.md  技能库改动记录
├── tools\                       工具区（进版本库）
│   ├── novel_split\             长篇小说拆分命令行工具（Python，仅用标准库）
│   ├── chai\                    一键拆书 + 机读统计
│   ├── batch15\                 15 章一批的拆分脚本 + `results\` 读数（见其 README）
│   ├── measure\                 一次性测量脚本与读数（H2 指标、关系节点筛选，见其 README）
│   └── 已装写作技能-说明.md      已装技能包记录
├── projects\
│   └── reader\                  月读 —— Electron 桌面阅读器（独立 git 仓库，已整合拆分导出）
├── 混沌冠冕_重写版\              活跃写书项目（档案内写死该绝对路径，勿移动/改名）
├── .plugin-stage\               插件分析暂存（不进版本库，可整目录删除）
└── .skill-patch\                技能库改动暂存（不进版本库，可整目录删除）
```

## 维护约定

- **新文件先归位再入库**：正文 → `novels\`；分析与统计 → `output\<书名>_分析\`；文档 → `docs\rules\` 或 `docs\research\`；脚本 → `tools\`。
- **根目录不留散文件**：只允许 README、`.gitignore` 和上面列出的目录；临时产物放 `tools\measure\`，或直接删。
- **`混沌冠冕_重写版\` 钉死在根目录**：它的 10 份档案把 `G:\txt\混沌冠冕_重写版` 写死为工作目录，移动/改名会断链，必须先改档案。
- **数据与产物不进版本库**：`novels\`、`output\`、`projects\reader\`、`.plugin-stage\`、`.skill-patch\` 均在 `.gitignore` 中。

## 快速开始

```powershell
# 0) 【推荐】一键拆书：原始 TXT → 分卷正文 + 机读统计 + 精读任务书
.\tools\chai\chai.ps1 -Input .\novels\混沌冠冕.txt
#    已拆好的目录只补统计：.\tools\chai\chai.ps1 -Input .\output\混沌冠冕

# 1) 看小说文件的编码底细（不写盘）
py -3 tools\novel_split\novel_split.py probe novels

# 2) 拆分成多份 TXT（有卷按卷，无卷每份约 10 万字）
py -3 tools\novel_split\novel_split.py split novels --out output

# 3) 一条命令跑完 probe → analyze → split
py -3 tools\novel_split\novel_split.py all novels --out output

# 4) 只跑统计 / 对账 / 看词表
py -3 tools\chai\chai_stats.py stats output\混沌冠冕
py -3 tools\chai\chai_stats.py verify output\混沌冠冕
py -3 tools\chai\chai_stats.py terms output\混沌冠冕 --top-n 200

# 5) 运行月读（带拆分导出功能）
cd projects\reader
npm install
npm start
```

## 小说数据

| 书名 | 章数 | 卷 | 拆分份数 | 净字数 |
|---|---:|---:|---:|---:|
| 反派少爷只想过佛系生活 | 1926 | 1 | 96 | 9,917,918 |
| 从纯血龙族开始不做人 | 1165 | 0 | 26 | 2,583,666 |
| 带着写轮眼降临东京 完本 | 1196 | 0 | 33 | 3,223,635 |
| 我在东京教剑道 | 744 | 7 | 7 | 3,045,687 |
| 从全面战争开始爆兵反清 | 704 | 0 | 34 | 3,439,267 |
| 带着火影重生日本东京 | 939 | 0 | 22 | 2,109,597 |
| 混沌冠冕 | 644 | 0 | 29 | 2,882,918 |

上表 7 本全部为 **UTF-8 无 BOM + CRLF**，是编码统一后的结果；统一前的原件保存在
`novels\_backup\`，已逐字比对确认无损（只改了编码与换行，正文一字未动）。

另有 3 个正文文件未纳入上表：`遍地英灵的二十一世纪⊙琉璃色⊙全本.txt`（新收，未拆分）、
`幽暗主宰.txt` 与 `幽暗主宰_合并版.txt`（同书两版，未做全书统计）。另在 `novels\_alt\`
存有 `从全面战争开始爆兵反清 作者：夏洛特·贝什米特小说在线阅读.txt`（10.4 MB），
是同书的替代来源，与 `novels\从全面战争开始爆兵反清.txt` 内容不同，未参与拆分。

拆分产物共 **247 个正文文件、27,202,688 净字数**，每一份都经过「各份净字数之和 == 全书净字数」
以及逐文件回读校验，**零丢失**。

## 版本控制

- `projects\reader\` 是**独立 git 仓库**（月读上游 + 本地整合改动），有自己的提交历史。
- 本工作区自身的仓库只跟踪**工具与文档**：`tools\`、`docs\`、`README.md`。
- `novels\`（数据）、`output\`（可再生成）、`projects\reader\`（嵌套仓库）、`node_modules\`、
  `.plugin-stage\`、`.skill-patch\`、`混沌冠冕_重写版\`（写书项目内容）均在 `.gitignore` 中排除。

## 相关文档

- **文档索引** → `docs\README.md`
- 写作规则与方法论 → `docs\rules\`（《AI写小说规则模板》《爽文流程》《写书流程设计》）
- 宿主插件与网文生态研究 → `docs\research\`
- 规则审计记录 → `docs\rules-audit-2026-10-29.md`
- 拆分工具的参数、输出格式、同类开源工具调研 → `tools\novel_split\README.md`
- **拆书流程的方法论、指标口径、验证方式、踩坑记录** → `tools\chai\README.md`
- 月读整合的架构、改动清单、验证结果、已知限制 → `docs\reader-integration.md`

## 拆书产物怎么用

`tools\chai\chai.ps1` 一条命令产出四类中间产物，目的是让长篇**可以被分析**：

| 产物 | 位置 | 用途 |
|---|---|---|
| 分卷正文 | `output\<书名>\<书名>_第N部分.txt` | 每份约 10 万字，可整份喂给模型 |
| 结构索引 | `output\<书名>\00_目录索引.md` | 每份装了哪些章、起止章号、净字数 |
| 机读统计 | `output\<书名>_分析\stats_摘要.md` | 章长分布、段落与对话占比、章末钩型、高频术语首现章 |
| 精读任务书 | `output\<书名>_分析\精读任务书.md` | 把 N 份正文分配给 N 个 subagent 的固定作业单 |

**推荐用法**：先读 `stats_摘要.md` 拿到数据底座 → 按任务书派发逐章精读 → 最后汇总成总报告。
跨书对比时并排看各自的 `stats.json`，标准差、对话占比、短段占比的差异会直接说明
它们的写法有何本质不同（例如《混沌冠冕》章长标准差 476＝固定节拍器式，
《我在东京教剑道》1872＝弹性式）。
