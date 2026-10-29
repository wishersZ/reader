# batch15 —— 网文「每 15 章拆分」工具与作业记录

用途：把长篇网文 TXT 按「每 15 章一个文件」切成批次 TXT，方便一份一份喂给大模型做拆书/精读。
产出格式：`第{批次3位}_第{起章4位}-{止章4位}章.txt`（最初对齐《弗雷尔卓德的孤狼完结》的拆分产物，该书已不在工作区）。

## 目录

| 路径 | 内容 |
|---|---|
| `*.py` | 14 个一次性脚本（拆分 / 合并 / 体检 / 统计） |
| `results\` | 脚本产出的全部读数与报告（.txt / .tsv），42 个 |
| `results\_archive_freljord\` | 已删除书目《弗雷尔卓德的孤狼完结》的旧产物，仅存档，脚本中对应入口已注释 |

## 本次作业（2026-10）

| 书 | 源文件 | 输出目录 | 批次数 |
|---|---|---|---|
| 幽暗主宰 | `G:\txt\novels\幽暗主宰_合并版.txt`（先合并去重，见 `G:\txt\novels\_notes\幽暗主宰_合并版_说明.md`） | `G:\txt\novels\幽暗主宰_每15章拆分\` | 70（序章+第1–1044章+最终章） |
| 混沌冠冕 | `G:\txt\novels\混沌冠冕.txt` | `G:\txt\novels\混沌冠冕_每15章拆分\` | 43（第1–645章） |

## 命名与格式约定

- 文件名：`第{批次3位}_第{起章4位}-{止章4位}章.txt`
- 每份 = 源文件对应行的**逐字原文切片**，不加任何标题头/分隔线/目录
- 第 001 批带上源文件前置信息，有序章的带序章，有最终章的追加在最后一批
- UTF-8 无 BOM，CRLF

## 脚本清单

| 脚本 | 作用 | 产出（都在 `results\`） |
|---|---|---|
| `merge_yinan.py` | 《幽暗主宰.txt》两套内容合并去重 → `幽暗主宰_合并版.txt` | — |
| `diag_yinan_partA.py` / `dump_partA_units.py` | 诊断干净版里的章号重复/跳号/错位 | `diag_partA.txt`、`partA_units.tsv` |
| `verify_merged.py` | 合并版体检（章号连续性、缺章占位、异常短章） | `verify_merged.txt` |
| `verify_split.py` | **独立**校验拆分产物：命名/区间接续/批内章数/编码/**逐字节零丢失（sha256）** | `verify_split_<书名>.txt` |
| `split15_yinan.py` / `split15_hundun.py` | 两个批次拆分脚本（外包给 LUNA 执行并自检） | `split15_*_报告.txt` |
| `make_index.py` | 合成各书 `00_总索引.md` | 索引写回 `novels\<书名>_亲爱情节扩写\` |
| `measure_nodes.py` / `scan_*.py` / `check_coverage.py` / `verify_anchors.py` | 节点句长、引号/边界覆盖、锚点核对 | `meas_*`、`quo_*`、`anc_*`、`cov_*`、`bnd_*` |

## 独立校验

```powershell
py -3 G:\txt\tools\batch15\verify_split.py "G:\txt\novels\幽暗主宰_合并版.txt" "G:\txt\novels\幽暗主宰_每15章拆分" 15
py -3 G:\txt\tools\batch15\verify_split.py "G:\txt\novels\混沌冠冕.txt"     "G:\txt\novels\混沌冠冕_每15章拆分"     15
```

（本机沙箱下不要把 python 的 stdout 用管道交给别的程序，会报 EPERM；报告由脚本自己写文件。
2026-10-29 复跑《混沌冠冕》：exit 0，逐字节零丢失通过，报告落在 `results\verify_split_混沌冠冕.txt`。）

## 已知内容缺口

`幽暗主宰` 源 TXT 本身缺 `第635、736、813、895` 四章（两套版本都没有），合并版里以占位行标出。
