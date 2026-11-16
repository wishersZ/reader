# G:\story 工作区迁移方案

> 把当前工作区从 `G:\txt` 迁移到 `G:\story`，同时把月读（`projects\reader`）的独立 Git 历史并入根仓库，最终由 `G:\story\.git` 统一管理。
>
> 编制日期：2026-11-16
> 适用对象：`G:\txt` 根仓库 + `G:\txt\projects\reader` 月读仓库
> 目标根目录：`G:\story`

---

## 目录

- [一、摘要与结论](#一摘要与结论)
- [二、现状审计（实测）](#二现状审计实测)
- [三、目标布局](#三目标布局)
- [四、迁移原则与默认决策](#四迁移原则与默认决策)
- [五、阶段总览](#五阶段总览)
- [六、Phase 0：预检与备份](#六phase-0预检与备份)
- [七、Phase 1：月读历史并入根仓库](#七phase-1月读历史并入根仓库)
- [八、Phase 2：整体改名](#八phase-2整体改名)
- [九、Phase 3：路径清理](#九phase-3路径清理)
- [十、Phase 4：功能验收](#十phase-4功能验收)
- [十一、Phase 5：提交、标签、清理](#十一phase-5提交标签清理)
- [十二、回滚预案](#十二回滚预案)
- [十三、风险与对策](#十三风险与对策)
- [十四、最终验收清单](#十四最终验收清单)
- [十五、执行分工与下一步](#十五执行分工与下一步)
- [十六、附录](#十六附录)

---

## 一、摘要与结论

### 1.1 推荐做法

**先并入月读历史，再整体改名。**

1. 在 `G:\txt` 内用 `git subtree add` 把月读的独立历史并入根仓库；
2. 把整个 `G:\txt` 改名为 `G:\story`（同盘改名，瞬时完成）；
3. 重新打开 `G:\story`，做路径清理和功能验收；
4. 两个 EXE 继续分别位于 `projects\reader` 和 `tools\novelkit`，由同一个 Git 根管理。

### 1.2 不要采用的做法

| 做法 | 问题 |
|---|---|
| 在 `G:\story` 新建仓库，复制月读和源码过去 | 丢历史；数据、`node_modules`、忽略文件容易漏；两份工作区容易混 |
| `git init` 后 `git add -A` | 会把 `novels`、`output`、`node_modules`、80 MB 安装包写进历史，仓库迅速膨胀 |
| 把月读作为 submodule | 仍然是两个 Git 目录，不符合“同一个 Git 管理” |
| 直接删除月读的 `.git` 再 `git add` | 月读历史全丢，以后无法同步上游 |
| 在 Qoder 当前会话里直接改名 | 当前会话工作目录就是 `G:\txt`，改名会让工具路径立即失效 |

### 1.3 预计工作量

| 阶段 | 内容 | 预计耗时 |
|---|---|---:|
| Phase 0 | 预检、备份、记录基线 | 20 分钟 |
| Phase 1 | 月读历史并入根仓库 | 30–45 分钟 |
| Phase 2 | 关闭 Qoder，整体改名 | 10 分钟 |
| Phase 3 | 路径清理与文档更新 | 30–60 分钟 |
| Phase 4 | Git、工具、阅读器、构建验收 | 30–45 分钟 |
| Phase 5 | 提交、标签、清理与迁移记录 | 20 分钟 |
| **合计** | | **约 2.5–3.5 小时** |

---

## 二、现状审计（实测）

### 2.1 目录与 Git

| 项目 | 实测结果 | 对迁移的影响 |
|---|---|---|
| `G:\story` | 存在、空目录、不是 Git 仓库 | 可以整体改名过去，不需要逐项复制 |
| `G:\txt` 根仓库 | 工作区干净，115 个跟踪文件，Git 对象约 0.7 MB，无 remote | 直接移动 `.git` 即可保留历史 |
| 月读仓库 | 工作区干净，28 个跟踪文件，Git 对象约 1.2 MB | 需要 subtree 导入，不能直接删 `.git` |
| 月读 remote | `origin = https://github.com/wishersZ/reader.git` | 迁移后作为 `yuedu` remote 保留同步能力 |
| 根仓库当前 HEAD | `a5fa749` | Phase 0 记录实际值，用于回滚 |
| 月读当前 HEAD | `1b1aa2b` | 同上 |

### 2.2 磁盘与进程

| 项目 | 实测结果 |
|---|---|
| 磁盘 | G: 同盘，932 GB，已用 758 GB，可用约 174 GB |
| 迁移方式 | 同盘目录改名，不产生额外空间占用 |
| 运行进程 | 检查时未发现 Electron / NovelKit / node 进程 |
| Qoder | 当前会话工作目录为 `G:\txt`，Phase 2 必须关闭 |

### 2.3 忽略规则

根 `.gitignore` 当前包含：

```text
novels/
output/
projects/reader/
node_modules/
dist/
__pycache__/
.skill-patch/
_trash/
混沌冠冕_重写版/
tools/novelkit/_pylib/
```

迁移时需要：

- **只删除** `projects/reader/` 这一行；
- `novels/`、`output/`、`混沌冠冕_重写版/`、`node_modules/`、`dist/` 等继续保留忽略；
- 如需发布目录，后续再增加 `release/`。

### 2.4 写死路径审计

核心可执行代码**没有**写死 `G:\txt`：

- `tools/chai/chai.ps1`
- `tools/novel_split/novel_split.py`
- `tools/novelkit/nv_core.py`（`find_workspace()` 向上查找 `tools/novel_split` 或 `novels`，见 `tools/novelkit/nv_core.py:58`）
- 月读 `projects/reader/src/**`

仍含 `G:\txt` 引用的文件共约 79 个，主要是：

- 活动文档与历史报告；
- `tools/batch15` 的一次性脚本与 62 个历史结果文件；
- 写书项目中的 4 个文件。

写书项目实测 4 个文件（README 里写的“10 份档案”已过期）：

| 文件 | 位置 |
|---|---|
| `混沌冠冕_重写版/05_进度.md` | 第 4–5 行 |
| `混沌冠冕_重写版/08_写书状态.md` | 第 4 行 |
| `混沌冠冕_重写版/README.md` | 第 7、11 行 |
| `混沌冠冕_重写版/_tools/compliance-check.mjs` | 第 19 行：`G:/txt/novels/混沌冠冕.txt` |

### 2.5 关键结论

1. 迁移技术风险低：同盘、空目标、两仓库干净、核心代码无绝对路径。
2. 最大风险是 **Phase 2 会打断当前 Qoder 会话**，必须外部执行。
3. 第二风险是 **写书项目的 4 个写死路径**，需要更新或保留 junction。
4. 月读的 `node_modules`、`dist`、`.npmrc` 是未跟踪文件，`git subtree add` 不会带过来，必须手动恢复。

---

## 三、目标布局

```text
G:\story\
├── .git\                      # 原 G:\txt 根仓库历史 + 月读 subtree 历史
├── README.md
├── docs\                      # 文档
├── projects\
│   └── reader\                # 月读（无嵌套 .git，由根仓库跟踪）
├── tools\
│   ├── novelkit\              # 拆书工具箱（EXE 源码 + build.ps1）
│   ├── novel_split\           # Python 解析/切分库
│   ├── chai\                  # 统计/术语/对账库
│   ├── batch15\               # 一次性脚本与历史结果
│   └── measure\               # 一次性测量脚本
├── novels\                    # Git 忽略；物理迁入
├── output\                    # Git 忽略；物理迁入
├── 混沌冠冕_重写版\            # Git 忽略；物理迁入
├── _trash\                    # Git 忽略；迁移时原样保留
└── .skill-patch\              # Git 忽略；迁移时原样保留
```

两个 EXE 的位置不变：

- 月读：`G:\story\projects\reader\dist\`
- 工具箱：`G:\story\tools\novelkit\dist\NovelKit.exe`

后续如果要做两 EXE 共享契约，可再增加 `shared\` 与 `scripts\`；本次迁移不强制。

---

## 四、迁移原则与默认决策

### 4.1 原则

1. **历史优先**：根仓库历史和月读历史都要保留。
2. **物理迁移不等于 Git 跟踪**：所有内容物理进入 `G:\story`，但数据、产物、依赖、EXE 继续忽略。
3. **同盘改名**：不做跨盘复制；改名失败可原样改回。
4. **可回滚**：每个阶段都有备份或反向操作。
5. **先验证后清理**：不删除任何备份，直到 Phase 4 全部通过。

### 4.2 默认决策

| 决策 | 默认值 | 说明 |
|---|---|---|
| 保留根仓库历史 | 是 | 移动现有 `.git` |
| 保留月读历史 | 是 | `git subtree add` |
| 保留月读上游同步 | 是 | 增加 `yuedu` remote |
| 保留旧路径 junction | 暂时保留 | `G:\txt → G:\story`，路径清理完成后可删 |
| 数据纳入 Git | 否 | `novels`、`output`、写书项目继续忽略 |
| 写书项目纳入 Git | 否 | 保持内容独立；如需版本化另建仓库 |
| 目录布局 | 保持现状 | 暂不改为 `apps\reader` / `apps\toolkit` |
| 迁移后是否推送远端 | 可选 | 根仓库当前无 remote，按需添加 |

---

## 五、阶段总览

| 阶段 | 内容 | 执行人 | 是否可回滚 |
|---|---|---|---|
| Phase 0 | 预检、备份、记录基线 | Qoder | 只读，无风险 |
| Phase 1 | 月读历史并入根仓库 | Qoder | 可回滚 |
| Phase 2 | 关闭 Qoder，整体改名 | **用户（外部终端）** | 可改名回滚 |
| Phase 3 | 路径清理与文档更新 | Qoder | 可回滚 |
| Phase 4 | 功能验收 | Qoder + 用户手动 GUI | 只读为主 |
| Phase 5 | 提交、标签、清理 | Qoder | 可回滚 |

> **硬性约束**：Phase 2 不能在当前 Qoder 会话内执行。当前会话的工作目录是 `G:\txt`，改名后所有相对路径和工具链都会失效。必须关闭 Qoder，在外部 PowerShell 中运行改名脚本，然后重新打开 `G:\story`。

---

## 六、Phase 0：预检与备份

### 6.1 关闭占用程序

关闭月读、NovelKit、所有 Node 进程、编辑器，以及打开 `G:\txt` 的资源管理器窗口。Qoder 在 Phase 1 可以暂留，Phase 2 前必须关闭。

```powershell
Get-Process | Where-Object { $_.Path -like 'G:\txt\*' } |
  Select-Object Id, ProcessName, Path
```

预期无输出。若有，逐个关闭。

### 6.2 确认两个仓库干净

```powershell
git -C G:\txt status --porcelain
git -C G:\txt\projects\reader status --porcelain
```

两者都必须为空。若有改动，先提交；不要带着未提交改动迁移。

### 6.3 记录基线

```powershell
# 当前 HEAD
git -C G:\txt rev-parse HEAD
git -C G:\txt\projects\reader rev-parse HEAD

# 跟踪文件数
git -C G:\txt ls-files | Measure-Object
git -C G:\txt\projects\reader ls-files | Measure-Object

# 当前分支
git -C G:\txt branch --show-current
git -C G:\txt\projects\reader branch --show-current
```

预期：

- 根仓库 `main`，HEAD `a5fa749`
- 月读仓库 `main`，HEAD `1b1aa2b`

实际值以执行时为准，并写入迁移记录。

### 6.4 记录数据目录清单

```powershell
$inv = [ordered]@{
  novels_files   = (Get-ChildItem G:\txt\novels -File -Recurse | Measure-Object).Count
  output_files   = (Get-ChildItem G:\txt\output -File -Recurse | Measure-Object).Count
  writing_files  = (Get-ChildItem 'G:\txt\混沌冠冕_重写版' -File -Recurse | Measure-Object).Count
  root_tracked   = (git -C G:\txt ls-files | Measure-Object).Count
  reader_tracked = (git -C G:\txt\projects\reader ls-files | Measure-Object).Count
}
$inv | ConvertTo-Json | Set-Content G:\migration-inventory-before.json
$inv | Format-List
```

如果 `output` 文件数统计过慢，可只记录书数与份数，或跳过该项；迁移后至少抽查几本书的份数与字数。

### 6.5 备份两段 Git 历史

```powershell
New-Item -ItemType Directory -Force G:\migration-backup | Out-Null

git -C G:\txt bundle create G:\migration-backup\root-before.bundle --all
git -C G:\txt\projects\reader bundle create G:\migration-backup\reader-before.bundle --all

git bundle verify G:\migration-backup\root-before.bundle
git bundle verify G:\migration-backup\reader-before.bundle
```

两个 `verify` 都应输出完整历史/`ok`。

### 6.6 建议额外备份关键数据

同盘改名不会复制数据，但无法防御误操作。建议把以下内容复制到其他盘或移动硬盘：

- `G:\txt\混沌冠冕_重写版`
- `G:\txt\novels`（至少保留 `_backup` 和 11 本正文）
- `G:\txt\output\十一本书对比`、`output\全部书籍_结构分析` 等不易重建的分析产物

### 6.7 确认目标目录为空

```powershell
(Get-ChildItem -Force G:\story | Measure-Object).Count
```

必须为 `0`。如果非空，停止迁移，先确认里面是什么。

### 6.8 确认磁盘

```powershell
Get-PSDrive G
Test-Path G:\story
git -C G:\story rev-parse --show-toplevel
```

预期：G: 同盘、`G:\story` 存在、`git` 报 “not a git repository”。

---

## 七、Phase 1：月读历史并入根仓库

这一阶段仍在 `G:\txt` 内操作，把月读从“嵌套独立仓库”变成“根仓库的 subtree”。

### 7.1 移开月读工作树（连 `.git` 一起）

移到仓库外，避免 subtree 导入时与根仓库的忽略目录互相干扰。

```powershell
if (Test-Path G:\migration-backup\reader-worktree) {
  throw 'G:\migration-backup\reader-worktree 已存在，停止'
}

Move-Item -LiteralPath G:\txt\projects\reader `
          -Destination G:\migration-backup\reader-worktree
```

### 7.2 从根 `.gitignore` 删除 `projects/reader/`

用编辑器打开 `G:\txt\.gitignore`，删除这一行：

```text
projects/reader/
```

如果要用 PowerShell 精确删除并保持 UTF-8 无 BOM：

```powershell
$p = 'G:\txt\.gitignore'
$t = [IO.File]::ReadAllText($p)
$t = $t -replace '(?m)^projects/reader/\s*\r?\n', ''
[IO.File]::WriteAllText($p, $t, [Text.UTF8Encoding]::new($false))
```

验证：

```powershell
Select-String -Path G:\txt\.gitignore -Pattern 'projects/reader'
git -C G:\txt diff -- .gitignore
```

应只剩“删除一行”的 diff。

> 不要用 `Set-Content -Encoding UTF8`：Windows PowerShell 5.1 会写入 BOM，给 `.gitignore` 带来无意义 diff。

### 7.3 提交取消忽略

```powershell
git -C G:\txt add .gitignore
git -C G:\txt commit -m "chore: 取消忽略 projects/reader，准备纳入根仓库"
```

### 7.4 subtree 导入

```powershell
git -C G:\txt subtree add `
  --prefix projects/reader `
  G:\migration-backup\reader-worktree main
```

预期：生成一条类似 `Add 'projects/reader/' from commit '1b1aa2b...'` 的合并提交。

如果提示 `git: 'subtree' is not a git command`，先确认 Git for Windows 完整安装；不要在未备份的情况下改用其他导入方式。

### 7.5 恢复被 subtree 忽略的运行文件

`git subtree add` 只导入月读**已跟踪**的 28 个文件；`node_modules`、`dist`、`.npmrc` 是未跟踪/忽略文件，不会自动过来。必须从备份工作树移回：

```powershell
Move-Item G:\migration-backup\reader-worktree\node_modules `
          G:\txt\projects\reader\node_modules

if (Test-Path G:\migration-backup\reader-worktree\dist) {
  Move-Item G:\migration-backup\reader-worktree\dist `
            G:\txt\projects\reader\dist
}

if (Test-Path G:\migration-backup\reader-worktree\.npmrc) {
  Move-Item G:\migration-backup\reader-worktree\.npmrc `
            G:\txt\projects\reader\.npmrc
}
```

如果 `Move-Item` 因文件锁失败，改用：

```powershell
robocopy G:\migration-backup\reader-worktree\node_modules `
         G:\txt\projects\reader\node_modules /E /MOVE
```

`node_modules` 必须恢复，否则月读无法 `npm start`。`dist` 是旧安装包，可以恢复，也可以删除后重新构建。

### 7.6 验证导入结果

```powershell
git -C G:\txt log --oneline -- projects/reader | Select-Object -First 5
Test-Path G:\txt\projects\reader\.git          # 期望 False
git -C G:\txt ls-files projects/reader | Measure-Object   # 期望约 28
git -C G:\txt status --porcelain               # 期望为空
Test-Path G:\txt\projects\reader\node_modules   # 期望 True
```

如果 `projects/reader/.git` 存在，说明导入方式不对，停止并检查；不要继续。

### 7.7 为月读保留上游同步入口

```powershell
git -C G:\txt remote add yuedu https://github.com/wishersZ/reader.git
git -C G:\txt fetch yuedu
git -C G:\txt log --oneline yuedu/main -1
```

以后同步月读上游使用：

```powershell
git -C G:\txt subtree pull --prefix projects/reader yuedu main `
  -m "chore: 同步月读上游"
```

> 不要用 `git pull` 直接拉月读上游，否则会把根仓库整体历史搞乱。

### 7.8 Phase 1 回滚

如果导入失败：

```powershell
# 1) 回到导入前的根提交（用 Phase 0 记录的 HEAD）
git -C G:\txt reset --hard <旧 HEAD>

# 2) 把月读工作树移回原位
#    如果 node_modules 等已移动，先移回
Move-Item G:\migration-backup\reader-worktree G:\txt\projects\reader

# 3) 验证
Test-Path G:\txt\projects\reader\.git   # True
git -C G:\txt\projects\reader status --porcelain
```

> `git reset --hard` 是破坏性操作，仅在确认工作区没有其他改动时使用；两段历史都有 bundle 备份。

---

## 八、Phase 2：整体改名

> **必须由用户在外部 PowerShell 执行。** 当前 Qoder 会话的工作目录是 `G:\txt`，改名会让会话立即失效。

### 8.1 关闭 Qoder 和所有相关进程

关闭 Qoder、所有终端、月读、NovelKit、编辑器和资源管理器窗口。确认：

```powershell
Get-Process | Where-Object { $_.Path -like 'G:\txt\*' } |
  Select-Object Id, ProcessName, Path
```

无输出。

### 8.2 准备外部脚本

在 `G:\migrate-to-story.ps1` 写入：

```powershell
$ErrorActionPreference = 'Stop'
$src = 'G:\txt'
$dst = 'G:\story'

if (-not (Test-Path -LiteralPath $src)) { throw "源目录不存在：$src" }
if (-not (Test-Path -LiteralPath $dst)) {
    New-Item -ItemType Directory -Path $dst | Out-Null
}
if ((Get-ChildItem -Force -LiteralPath $dst | Measure-Object).Count -ne 0) {
    throw "目标目录非空，停止：$dst"
}

Remove-Item -LiteralPath $dst
Rename-Item -LiteralPath $src -NewName 'story'

Set-Location G:\story
Write-Host '改名完成，当前 HEAD：'
git rev-parse --short HEAD
git status --short
```

### 8.3 运行脚本

在外部 PowerShell 中：

```powershell
powershell -ExecutionPolicy Bypass -File G:\migrate-to-story.ps1
```

预期：`G:\txt` 消失，`G:\story` 出现；`git status` 为空；HEAD 仍是 Phase 1 后的提交。

如果报“目录正被另一进程使用”，说明 Qoder/编辑器/终端仍占用；全部关闭后重试。不要用强制删除绕过。

### 8.4 可选：保留旧路径兼容

```powershell
cmd /c mklink /J G:\txt G:\story
```

验证：

```powershell
$i = Get-Item G:\txt -Force
$i.LinkType   # Junction
$i.Target     # G:\story
```

注意事项：

- junction 只用于兼容写死 `G:\txt` 的写书项目和外部提示词；
- Qoder 应重新打开 `G:\story` 真实路径，不要打开 junction；
- 不要通过 `G:\txt` 和 `G:\story` 同时跑 Git 操作；
- 以后删除 junction 必须用 `cmd /c rmdir G:\txt`，不要用 `Remove-Item -Recurse`，后者有跟随链接删除目标内容的风险。

### 8.5 重新打开 Qoder

用 Qoder 打开 `G:\story`，不要继续旧的 `G:\txt` 会话。

### 8.6 Phase 2 回滚

```powershell
# 关闭 Qoder 和所有占用进程
if ((Get-Item G:\txt -Force -ErrorAction SilentlyContinue).LinkType -eq 'Junction') {
    cmd /c rmdir G:\txt
}
Rename-Item -LiteralPath G:\story -NewName txt
```

数据是同盘改名，没有复制，改名回来即可恢复。

---

## 九、Phase 3：路径清理

### 9.1 核心代码不需要改

以下工具都使用相对路径或向上查找：

- `tools/chai/chai.ps1`
- `tools/novel_split/novel_split.py`
- `tools/novelkit/nv_core.py`（`find_workspace()`）
- 月读 `projects/reader/src/**`

迁移后 NovelKit 的 `where` 应自动显示 `G:\story`。

### 9.2 写书项目：4 个文件必须处理

| 文件 | 位置 |
|---|---|
| `混沌冠冕_重写版/05_进度.md` | 第 4–5 行 |
| `混沌冠冕_重写版/08_写书状态.md` | 第 4 行 |
| `混沌冠冕_重写版/README.md` | 第 7、11 行 |
| `混沌冠冕_重写版/_tools/compliance-check.mjs` | 第 19 行 |

把它们改成 `G:\story\...` / `G:/story/...`。如果保留 junction，可以暂不改，但建议改掉，避免长期混淆。

### 9.3 更新 README 与活动文档

至少更新：

- `README.md`：标题、目录树、快速开始里的 `G:\txt`；
- `README.md` 第 49 行：把“10 份档案写死路径”改成实测的 4 个文件，并说明迁移后已更新；
- `docs/README.md` 与仍会照着执行的文档。

历史报告可以保留旧路径，它们是历史记录，不必批量改写。

### 9.4 历史脚本与结果

`tools/batch15` 有 62 个已跟踪文件，很多结果文件里有旧路径。建议：

- `results/` 下的历史读数保留，不改；
- 如果 `split15_*.py` 等脚本以后还要重跑，再单独更新脚本里的路径；
- 在 `tools/batch15/README.md` 加一句“历史路径以 `G:\txt` 为准，迁移后为 `G:\story`”。

### 9.5 已有产物里的旧路径

`output\<书名>\manifest.json` 和 `<book>_分析\stats.json` 里的 `source` / `source_dir` 是历史来源记录，不影响统计和对账。建议保留，不批量改写；重跑后自然变成新路径。

### 9.6 全量扫描活动文件

```powershell
Get-ChildItem G:\story -Recurse -File -Include *.md,*.mjs,*.js,*.py,*.ps1,*.json |
  Where-Object { $_.FullName -notmatch '\\(node_modules|output|novels|_trash|dist|results)\\' } |
  Select-String -Pattern 'G:[\\/]{1,2}txt' |
  Select-Object Path, LineNumber, Line
```

逐条判断：活动文档/脚本要改，历史记录可保留。

---

## 十、Phase 4：功能验收

### 10.1 Git

```powershell
cd G:\story
git rev-parse --show-toplevel      # G:/story
git status --porcelain             # 空
git log --oneline -5
git log --oneline -- projects/reader | Select-Object -First 5
git ls-files | Measure-Object      # 约 143
Test-Path projects\reader\.git     # False
```

### 10.2 Python 拆分与统计

```powershell
py -3 tools\novel_split\test_parser_regressions.py
# 期望 9/9

py -3 tools\chai\chai_stats.py verify output\混沌冠冕
# 期望“校验通过”
```

### 10.3 工具箱

```powershell
tools\novelkit\dist\NovelKit.exe --version
tools\novelkit\dist\NovelKit.exe where
# 期望 G:\story

tools\novelkit\dist\NovelKit.exe probe novels
```

### 10.4 月读

```powershell
cd G:\story\projects\reader
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
npm start
```

手动检查：

- 书架还在，进度还在（用户数据在 `%APPDATA%`，与工作区路径无关）；
- 能打开一本书；
- 拆分导出能写盘；
- 如 Electron 因路径报错，执行 `npm ci` 后重试。

提交前再跑：

```powershell
npm test
```

### 10.5 构建两个 EXE

```powershell
G:\story\tools\novelkit\build.ps1
G:\story\tools\novelkit\dist\NovelKit.exe --version

cd G:\story\projects\reader
npm run dist
```

### 10.6 数据完整性

对比 Phase 0 的 `inventory-before.json`：

```powershell
(Get-ChildItem G:\story\novels -File -Recurse | Measure-Object).Count
(Get-ChildItem G:\story\output -File -Recurse | Measure-Object).Count
(Get-ChildItem 'G:\story\混沌冠冕_重写版' -File -Recurse | Measure-Object).Count
```

数量应一致。再抽查几本小说/拆分文件能正常读取。

### 10.7 写书项目

```powershell
node G:\story\混沌冠冕_重写版\_tools\compliance-check.mjs
```

如脚本需要参数，按它 README 的方式运行；关键是能读到 `G:\story\novels\混沌冠冕.txt`。

### 10.8 junction（如保留）

```powershell
Get-Content G:\txt\README.md | Select-Object -First 3
git -C G:\txt status --porcelain
```

能正常读取/查询即可；不要在两个路径上同时做写操作。

---

## 十一、Phase 5：提交、标签、清理

### 11.1 提交文档与路径更新

```powershell
cd G:\story
git add README.md docs tools
git status --short
git commit -m "docs: 工作区迁移到 G:\story，更新路径与目录说明"
```

只提交源码/文档；`node_modules`、`output`、`novels`、写书项目不会进入暂存区。

### 11.2 打标签

```powershell
git tag -a migration-story-20261116 -m "迁移工作区根目录到 G:\story"
```

### 11.3 迁移记录

建议新增 `docs/迁移记录-2026-11-16.md`，记录：

- 迁移前后 HEAD；
- 两段 bundle 备份路径；
- `git subtree` 引入月读的提交；
- 验收结果（9/9、verify、npm test、两个 EXE 构建）；
- 仍未清理的旧路径（历史文档、batch15 结果）。

### 11.4 清理

确认验收全部通过后：

```powershell
# 删除月读的临时工作树副本；bundle 备份保留至少 30 天
Remove-Item -LiteralPath G:\migration-backup\reader-worktree -Recurse -Force
```

`_trash` 目录按原维护约定单独审查，不要在这次迁移里顺手清空。

如果所有旧路径都已更新，且没有外部提示词/快捷方式依赖 `G:\txt`，再删除 junction：

```powershell
$i = Get-Item G:\txt -Force
if ($i.LinkType -eq 'Junction' -and $i.Target -contains 'G:\story') {
    cmd /c rmdir G:\txt
}
```

---

## 十二、回滚预案

| 阶段 | 回滚方式 |
|---|---|
| Phase 1 导入失败 | `git reset --hard <旧 HEAD>`，把 `G:\migration-backup\reader-worktree` 移回 `G:\txt\projects\reader` |
| Phase 2 改名后发现问题 | 删除 junction（若有），`Rename-Item G:\story -NewName txt` |
| 根仓库损坏 | `git clone G:\migration-backup\root-before.bundle G:\restore-root` |
| 月读仓库损坏 | `git clone G:\migration-backup\reader-before.bundle G:\restore-reader` |
| 数据误删/误改 | 同盘改名不会复制数据；若已改动，需从外部备份恢复 |

建议在 Phase 2 前额外把 `混沌冠冕_重写版` 和 `novels` 复制一份到其他盘或移动硬盘；同盘改名虽然不丢数据，但无法防御误操作。

### 12.1 验证 bundle 可恢复

在正式迁移前可先做一次恢复演练：

```powershell
git clone G:\migration-backup\root-before.bundle G:\restore-test-root
git clone G:\migration-backup\reader-before.bundle G:\restore-test-reader

git -C G:\restore-test-root log --oneline -3
git -C G:\restore-test-reader log --oneline -3
```

确认无误后删除 `G:\restore-test-root`、`G:\restore-test-reader`。

---

## 十三、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| 当前 Qoder 会话占用 `G:\txt` | 改名失败或会话失效 | 关闭 Qoder，外部 PowerShell 执行改名，再打开 `G:\story` |
| 写书项目写死路径 | 写作流程断链 | 改 4 个文件，或保留 `G:\txt` junction |
| 月读历史丢失 | 无法回溯/同步上游 | 先 `git bundle` 备份，再 `git subtree add` |
| `node_modules` 未随 subtree 过去 | 月读无法启动 | 从备份工作树移回，或 `npm ci` |
| 误把数据/EXE 提交 | 仓库膨胀 | 保留现有 `.gitignore`，迁移后先 `git status` 审查 |
| 上游同步冲突 | 月读升级困难 | 根仓库加 `yuedu` remote，后续 `git subtree pull` |
| junction 删除误伤 | 可能删除目标内容 | 只用 `cmd /c rmdir`，不用 `Remove-Item -Recurse` |
| 历史文档旧路径 | 照旧文档执行会失败 | 更新活动文档；历史报告保留并标注旧根 |
| 已有产物 `source` 路径 | 报告显示旧路径 | 属历史记录；不影响统计，重跑后更新 |
| PowerShell 写入 BOM | `.gitignore` 出现无意义 diff | 用编辑器或 .NET `UTF8Encoding(false)` |
| 文件被占用 | 改名失败 | 关闭月读/NovelKit/编辑器；必要时重启后重试 |

---

## 十四、最终验收清单

- [ ] `G:\story` 是 Git 根，`git status` 干净
- [ ] 根仓库历史仍在，包含 `a5fa749` 等旧提交
- [ ] 月读历史已并入，`projects\reader\.git` 不存在
- [ ] 月读 `node_modules` 已恢复，`npm start` 正常
- [ ] Python 解析回归 9/9
- [ ] `NovelKit.exe where` 输出 `G:\story`
- [ ] `NovelKit.exe verify output\混沌冠冕` 通过
- [ ] `npm test` 全绿
- [ ] NovelKit 与月读安装包都能从新根构建
- [ ] 写书项目 4 个路径已更新，或 junction 可用
- [ ] `novels` / `output` / 写书项目文件数与迁移前一致
- [ ] `novels`、`output`、`node_modules`、`dist` 未进入 Git
- [ ] 旧 `G:\txt` 已消失，或确认为指向 `G:\story` 的 junction
- [ ] 已打迁移标签并记录 bundle 备份位置

---

## 十五、执行分工与下一步

### 15.1 分工

| 工作 | 执行人 |
|---|---|
| Phase 0 预检、备份、基线 | Qoder |
| Phase 1 subtree 导入、node_modules 恢复 | Qoder |
| Phase 2 关闭 Qoder、外部改名 | **用户** |
| Phase 3 路径清理 | Qoder |
| Phase 4 Git/Python/NovelKit 验收 | Qoder |
| Phase 4 月读 GUI 手动检查、`npm test` | 用户 + Qoder |
| Phase 5 提交、标签、清理 | Qoder |

### 15.2 执行前必须确认

1. `G:\story` 仍为空；
2. 两个仓库 `git status` 仍干净；
3. 关键数据已额外备份到其他盘（建议）；
4. 可以在 Phase 2 关闭 Qoder 并重新打开 `G:\story`；
5. 是否保留 `G:\txt → G:\story` junction（默认保留到路径清理完成）。

### 15.3 建议执行顺序

1. 先执行 Phase 0、Phase 1；
2. 生成 `G:\migrate-to-story.ps1`，由用户关闭 Qoder 后运行；
3. 重新打开 `G:\story`；
4. 执行 Phase 3–5，完成验收和标签。

---

## 十六、附录

### 16.1 关键路径速查

| 用途 | 路径 |
|---|---|
| 新工作区根 | `G:\story` |
| 旧工作区根 | `G:\txt`（迁移后可能为 junction） |
| 月读源码 | `G:\story\projects\reader` |
| 工具箱源码 | `G:\story\tools\novelkit` |
| 拆分库 | `G:\story\tools\novel_split` |
| 统计库 | `G:\story\tools\chai` |
| 小说数据 | `G:\story\novels`（Git 忽略） |
| 分析产物 | `G:\story\output`（Git 忽略） |
| 写书项目 | `G:\story\混沌冠冕_重写版`（Git 忽略） |
| 迁移备份 | `G:\migration-backup` |
| 外部改名脚本 | `G:\migrate-to-story.ps1` |

### 16.2 关键命令速查

```powershell
# 备份
git -C G:\txt bundle create G:\migration-backup\root-before.bundle --all
git -C G:\txt\projects\reader bundle create G:\migration-backup\reader-before.bundle --all

# 导入月读历史
git -C G:\txt subtree add --prefix projects/reader G:\migration-backup\reader-worktree main

# 未来同步月读上游
git -C G:\txt subtree pull --prefix projects/reader yuedu main -m "chore: 同步月读上游"

# 验收
py -3 tools\novel_split\test_parser_regressions.py
tools\novelkit\dist\NovelKit.exe where
tools\novelkit\dist\NovelKit.exe verify output\混沌冠冕
```

### 16.3 迁移记录模板

```markdown
# 工作区迁移记录（2026-11-16）

- 迁移前根目录：G:\txt
- 迁移后根目录：G:\story
- 根仓库迁移前 HEAD：
- 月读仓库迁移前 HEAD：
- 根仓库迁移后 HEAD：
- 月读 subtree 导入提交：
- bundle 备份：
  - G:\migration-backup\root-before.bundle
  - G:\migration-backup\reader-before.bundle
- 数据文件数对比：
  - novels：
  - output：
  - 写书项目：
- 验收结果：
  - Python 回归：
  - NovelKit where：
  - NovelKit verify：
  - npm test：
  - NovelKit 构建：
  - 月读构建：
- 未清理项：
  - 历史文档中的旧路径
  - tools/batch15/results 中的旧路径
  - output 产物中的 source/source_dir 旧路径
- 备注：
```

---

> **最后提醒**：Phase 2 是唯一会打断当前会话的步骤。执行前关闭 Qoder，运行 `G:\migrate-to-story.ps1`，然后用 Qoder 打开 `G:\story`。在 Phase 4 全部通过之前，不要删除 `G:\migration-backup` 里的任何备份。
