# tools\measure

一次性测量脚本与读数。脚本按「在 `G:\txt` 根目录执行」写成（内部用 `output\...` 相对路径），不是常驻工具。

| 文件 | 用途 |
|---|---|
| `_filter_nodes.py` | 从 `output\混沌冠冕_分析\关系节点\range_*.json` 里按章号、引文校验、人物筛出高信号节点，写 `highsignal_*.json` |
| `measure_report.txt` | 对 `novels\混沌冠冕_亲爱情节扩写` 的节点句长统计（节点数 / min / 中位 / max / <800 字节点数） |
| `meas_h2_final.txt`、`meas_h2_round.txt` | 同一统计的过程读数与最终读数（内容基本一致，保留用于对账） |

要重跑：先在根目录 `cd G:\txt`，再执行 `py -3 tools\measure\_filter_nodes.py` 之类；改数据目录时改脚本首部的 `src` / `dst`。
