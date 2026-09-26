# G:\txt 工作区

长篇小说「整理 → 拆分 → 供 AI 分析」的工作区，同时存放整合了拆分功能的月读阅读器源码。

根目录只保留 5 个子目录，不放任何数据文件或临时产物。

## 目录结构

```
G:\txt\
├── README.md                    本文件：工作区总说明
├── novels\                      小说数据区（不进版本库）
│   ├── *.txt                    7 本，已统一为 UTF-8 + CRLF
│   └── _backup\                 编码统一前的 5 个原件（*.txt.bak，GBK / 带 BOM）
├── tools\                       工具区（进版本库）
│   ├── novel_split\             长篇小说拆分命令行工具（Python，仅用标准库）
│   │   ├── novel_split.py       probe / encode / analyze / split / all 五个子命令
│   │   ├── README.md            完整参数说明与同类工具调研
│   │   └── run_all.cmd          一键包装（等价于 all 子命令）
│   └── verify_reader_clone.py   校验 reader 工作区与 GitHub 上游是否逐字节一致
├── output\                      拆分产物（不进版本库，可随时重新生成）
│   └── <书名>\                  分卷/分部分的正文 + 目录索引 + manifest
├── projects\
│   └── reader\                  月读 —— Electron 桌面阅读器（独立 git 仓库，已整合拆分导出）
└── docs\
    └── reader-integration.md    月读整合说明：架构、改动、验证、已知限制
```

## 快速开始

```powershell
# 1) 看小说文件的编码底细（不写盘）
py -3 tools\novel_split\novel_split.py probe novels

# 2) 拆分成多份 TXT（有卷按卷，无卷每份约 10 万字）
py -3 tools\novel_split\novel_split.py split novels --out output

# 3) 一条命令跑完 probe → analyze → split
py -3 tools\novel_split\novel_split.py all novels --out output

# 4) 运行月读（带拆分导出功能）
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

7 本全部为 **UTF-8 无 BOM + CRLF**，是编码统一后的结果；统一前的原件保存在
`novels\_backup\`，已逐字比对确认无损（只改了编码与换行，正文一字未动）。

拆分产物共 **247 个正文文件、27,202,688 净字数**，每一份都经过「各份净字数之和 == 全书净字数」
以及逐文件回读校验，**零丢失**。

## 版本控制

- `projects\reader\` 是**独立 git 仓库**（月读上游 + 本地整合改动），有自己的提交历史。
- 本工作区自身的仓库只跟踪**工具与文档**：`tools\`、`docs\`、`README.md`。
- `novels\`（数据）、`output\`（可再生成）、`projects\reader\`（嵌套仓库）、`node_modules\`
  均在 `.gitignore` 中排除。

## 相关文档

- 拆分工具的参数、输出格式、同类开源工具调研 → `tools\novel_split\README.md`
- 月读整合的架构、改动清单、验证结果、已知限制 → `docs\reader-integration.md`
