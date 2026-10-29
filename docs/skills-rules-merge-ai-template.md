# 技能库改动记录：《AI写小说规则模板.md》→ 网文工坊技能库

**改动日期**：2026-09-29
**来源文档**：`G:\txt\docs\rules\AI写小说规则模板.md`（0–9 层规则模板，含 Unslop / Novel-Craft / webnovel-handbook 三处来源）
**落点**：`C:\Users\Administrator\.dsh\skills`（网文工坊 33 个 bundle，同步自 `tance-mang/chinese-webnovel-skills`，commit ecf552f）
**暂存与备份**：`G:\txt\.skill-patch\`（`backup\` 为改动前副本，`out\` 为改动后副本，`new\` 为新增库，`apply.ps1` 为补丁脚本）

> ⚠️ 该技能库在工作区之外，且带 `_webnovel-repo-info/SYNC-INFO.txt` 同步标记：**下次从上游仓库重新同步会覆盖这些改动**。若要长期保留，需把本次改动回灌到上游仓库。

---

## 一、落点映射（模板 → 技能库）

| 模板层 | 内容 | 落点 |
|---|---|---|
| 第 0 层 元规则 | 样本优先 / 写时放开写写完再审 / AI 不做核心决定 / 打破规则配配额 | **新增** `references/meta-rules.md`；接入 `expand`（写作前确认第 6 条）、`cowrite`（原则）、`deslop`（改稿纪律）、`human`（原则）、`aidetect`（配合） |
| 第 9 层 总判断 + 六大通病 | "先问像不像一个人在压力现场的反应"；过度对称/总结/顺滑/正确/干净/通顺 | 同上 `meta-rules.md`；`human` 诊断补第 6 项、原则补自检顺序 |
| 第 2 层 语言 | AI 高频词法黑名单（含按钮式氛围词、装腔系动词、宏大抽象名词） | `references/anti-ai-checklist.md` **新增第八节**；`deslop` 症状表补一行 |
| 第 2 层 语言 | AI 最认得出的十个句式（否定平行 / 戏剧倒计时 / 自问自答 / 三连排比 / 首语重复 / 尾巴式升华 / 假区间 / 填充转折 / 破折号滥用 / 独立成段金句） | `anti-ai-checklist.md` **新增第九节** + 自检清单；`aidetect` 指标对应说明 |
| 第 2 层 结构 | 意象配额、不表演深刻、不预告结尾、不递归总结、拒绝趋同美学 | `anti-ai-checklist.md` **新增第十节** + 自检清单 |
| 第 2 层 节奏 | 节奏压缩、允许平庸句存在、禁止短句瀑布 | `references/sentence-rhythm.md` **新增第三节**（原三/四顺延为四/五）；`deslop` 症状表补一行 |
| 第 1 层 上下文 | 本章最小输入包（12 项）、三人以上场景先定摄像机/关系轴/情绪节拍、世界观分层喂 | `expand/SKILL.md` 写作前确认后新增「本章最小输入包」块 |
| 第 3 层 叙事 | 删句测试、每句必须有功能、场景摩擦、证据可争夺、动机不解释、功能性动作不直球、新信息有来源、动作链可拍摄、叙述者要有性格 | **新增** `references/narrative-craft.md`（一~三节）；接入 `expand`/`review`/`deslop`/`aidetect` |
| 第 6 层 结构 | 预先规划延迟揭示、章末用具体未完成动作、每章可感知增量、扩写必须有新增实质、结构不方块化、正文不写标题/项目符号/加粗 | 同上 `narrative-craft.md` 第四节；`expand` 节奏/文字/输出三处 |
| 第 4 层 人物 | 性格调色盘、行为禁区 5–12 条、禁区是弓打破是箭、情感强度匹配场景、让角色不自洽、每个主要角色有自己的目标 | `character/SKILL.md`（主角设计 4 条新 bullet、人设卡加【行为禁区】、配角段） |
| 第 5 层 对话 | 写台词前四标注（目标/遮掩/关系杠杆/句子形状）、说出口≠心里想的、每句台词承担场景动作、禁止念主题、对话会跑题、换个人说也成立=重写、一人一套腔 3–5 句 | `dialogue/SKILL.md` 工作流新增第 4 步 +「好台词的硬门槛」段 |
| 第 7 层 交付自检 | AI 含量分级（低/中/高/极高）、高一档禁止只做词句替换、作者味保护优先、最小修订口径、禁止自夸与台账复述 | `review/SKILL.md` 新增段 + 原则；`deslop` 新增「改稿纪律」；`expand` 输出改为三行简述 |
| 第 8 层 长篇管理 | 每 3 章批次复盘（角色状态/伏笔/情感债/时间线）、跨窗口接力给结构化摘要、不依赖当前提示词记设定 | `memory/SKILL.md` 原则补 3 条 |

**未改动**（现有条目已覆盖，避免重复）：标点规范（引号/省略号/破折号/顿号）、极端词、同义反复、排比、语域一致、show-don't-tell、留白、一人一腔 —— 均已在 `anti-ai-checklist.md` / `deslop` / `dialogue` / `human-texture.md` 中成立。

---

## 二、改动清单（11 个文件 + 2 个新增）

**新增（各 33 个 bundle 各一份副本）**
- `references/meta-rules.md`
- `references/narrative-craft.md`

**修改（共享库，33 份副本同步）**
- `references/anti-ai-checklist.md`（147 → 193 行）
- `references/sentence-rhythm.md`（66 → 78 行）

**修改（各自主技能）**
- `deslop/SKILL.md`、`human/SKILL.md`、`expand/SKILL.md`、`dialogue/SKILL.md`、`character/SKILL.md`、`review/SKILL.md`、`aidetect/SKILL.md`、`memory/SKILL.md`、`cowrite/SKILL.md`

补丁共 24 条，全部精确锚点命中（脚本 `apply.ps1` 对每条做"命中/未命中"校验，未命中即失败退出）。

---

## 三、验证

- 4 个 references 在 33 个 bundle 内哈希唯一，且与暂存副本逐字节一致。
- 9 个 SKILL.md 与暂存副本逐字节一致。
- 文件编码 UTF-8 无 BOM、行尾 LF（与库内原有文件一致）。
- 章节编号连续：`sentence-rhythm.md` 一→五、`anti-ai-checklist.md` 一→十。

## 四、回滚

```powershell
# 从备份恢复 11 个被改文件；新增的 2 个库需手动删除 33 份副本
$dst = 'C:\Users\Administrator\.dsh\skills'; $bk = 'G:\txt\.skill-patch\backup'
foreach ($n in @('deslop','human','expand','dialogue','character','review','aidetect','memory','cowrite')) {
  Copy-Item "$bk\skills\$n.SKILL.md" "$dst\$n\SKILL.md" -Force
}
Get-ChildItem $dst -Directory | Where-Object { $_.Name -ne '_webnovel-repo-info' } | ForEach-Object {
  $refDir = Join-Path $_.FullName 'references'
  foreach ($r in @('anti-ai-checklist.md','sentence-rhythm.md')) { Copy-Item "$bk\references\$r" (Join-Path $refDir $r) -Force }
  Remove-Item (Join-Path $refDir 'meta-rules.md'),(Join-Path $refDir 'narrative-craft.md') -Force -ErrorAction SilentlyContinue
}
```
