# 十一本书对比（构建）

| 文件 | 用途 |
|---|---|
| `scores.json` | 11 本前 3 章 / 前 10 章四问评分（8 本沿用上版，奇诡/幽暗/遍地为本轮新评；`source` 字段区分） |
| `metrics.py` | 从切片目录 + `output\<书名>_分析\stats.json` 复算 `_data\metrics.json` |
| `build.py` | 读取本目录 `scores.json` + `output\十一本书对比\_data\metrics.json`，重算名次、生成 3 张 SVG 与 `_data\tables.md` |

## 用法

```powershell
# 1) 抽前 10 章切片
py -3 tools\八本书文笔对比\extract_n.py <切片目录> 10 .\novels\*.txt
# 2) 复算机读指标
py -3 tools\十一本书对比\metrics.py <切片目录>
# 3) 生成图表与总表
py -3 tools\十一本书对比\build.py
```

输出：

- `output\十一本书对比\十一本书_可看性对比.svg`
- `output\十一本书对比\十一本书_十本章可看性.svg`
- `output\十一本书对比\十一本书_每段字数分布.svg`
- `output\十一本书对比\_data\scores.json`（由本目录 scores.json 同步）
- `output\十一本书对比\_data\tables.md`

## 口径

- 权重 A（均衡）：Q1 30% / Q2 25% / Q3 25% / Q4 20%。
- 权重 B（门槛优先）：35 / 30 / 20 / 15。
- 评分是“新读者进入效率”，不是文笔分；机读指标只做旁证。
- 分数改动只改 `scores.json`，重跑 `build.py` 即可同步图表与表；文字报告里的结论需人工复核。

## 机读指标来源

`metrics.json` 由前 10 章切片与 11 本 `output\<书名>_分析\stats.json` 复算；切片用
`tools\八本书文笔对比\extract_n.py`（通用脚本，目录名沿用旧项目）。图表用纯 SVG，无第三方依赖。
