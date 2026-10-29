<#
.SYNOPSIS
  一键拆书 —— 从原始 TXT 到「机读统计 + 分层分析任务书」的完整流水线。

.DESCRIPTION
  把《混沌冠冕》那套拆书流程固化成一条命令。五个阶段：

    ① probe    探测编码/换行/BOM，不写盘
    ② encode   无损统一编码（默认 UTF-8 + CRLF，就地改写并留 .bak）
    ③ analyze  分析卷/章结构
    ④ split    规范化 + 排序 + 按卷/按约 10 万字切分 → output/<书名>/
    ⑤ stats    机读统计（章长/段落/对话占比/章末钩型/术语首现）
               → output/<书名>_分析/{chapters.csv, terms.csv, stats.json, stats_摘要.md}

  之后再生成「分层精读任务书」（把 N 份正文分配给 N 个 subagent 逐章精读），
  这是把 10 万字级原料变成可用结论的关键一步。

.PARAMETER Input
  原始小说 TXT 文件，或包含多个 TXT 的目录。也接受已经拆好的 output/<书名> 目录
  （此时自动跳过 ①—④，只跑 ⑤）。

.PARAMETER Book
  书名。默认从文件名推导。

.PARAMETER Parts
  切分份数。不指定则按每份约 10 万字自动决定。

.PARAMETER MaxChars
  每份净字数上限（与 -Parts 二选一）。

.PARAMETER OutRoot
  拆书产物根目录。默认 <仓库根>\output。每本书放在 <OutRoot>\<书名>，
  统计产物放在 <OutRoot>\<书名>_分析。

.PARAMETER Terms
  人工确认的专名（逗号分隔），强制进 terms.csv，例如 -Terms "亚伦,苏伦,莎尔"。

.PARAMETER MinTermCount
  术语候选的最低总频次，默认 15。词表噪音大就调高。

.PARAMETER SkipEncode
  跳过编码统一（源文件已是 UTF-8 且换行规范时可用）。

.PARAMETER Force
  目标目录已存在时覆盖。默认遇到已存在会停下来询问。

.PARAMETER DryRun
  只预演，不写盘（传递给 novel_split）。

.PARAMETER TasksOnly
  只生成分层精读任务书，不重跑统计。

.EXAMPLE
  # 最常用：一本原始 txt 一路跑到统计 + 任务书
  .\chai.ps1 -Input ..\novels\混沌冠冕.txt

.EXAMPLE
  # 整个目录批量处理
  .\chai.ps1 -Input ..\novels

.EXAMPLE
  # 只跑统计（已经拆好了）
  .\chai.ps1 -Input ..\output\混沌冠冕

.EXAMPLE
  # 指定份数 + 人工专名
  .\chai.ps1 -Input ..\novels\混沌冠冕.txt -Parts 29 -Terms "亚伦,苏伦,莎尔,爱丽丝塞尔"
#>
[CmdletBinding()]
param(
  # 注意：参数名不要用 $Input —— 它是 PowerShell 的自动变量，会被覆盖成空值，
  # 导致 Resolve-Path 收到空字符串而报
  # "Cannot bind argument to parameter 'LiteralPath' because it is an empty string"。
  # 因此本参数名为 $Path，并保留 -Input 作为别名以便习惯用法。
  [Parameter(Mandatory = $true, Position = 0)]
  [Alias('Input', 'i')]
  [string]$Path,

  [string]$Book,
  [int]$Parts = 0,
  [int]$MaxChars = 0,
  [string]$OutRoot,
  [string]$Terms,
  [int]$MinTermCount = 15,
  [switch]$SkipEncode,
  [switch]$Force,
  [switch]$DryRun,
  [switch]$TasksOnly
)

$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------- 环境准备
# Python 源码与输出都是 UTF-8：Windows 的 Python 默认按 cp936 打开源码/输出，
# 必须显式打开 UTF-8 模式，否则中文会乱码或报错。
$env:PYTHONUTF8 = '1'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # tools\chai → 仓库根
if (-not $OutRoot) { $OutRoot = Join-Path $RepoRoot 'output' }

$SplitTool = Join-Path $RepoRoot 'tools\novel_split\novel_split.py'
$StatsTool = Join-Path $PSScriptRoot 'chai_stats.py'

function Say([string]$msg, [string]$color = 'Cyan') { Write-Host $msg -ForegroundColor $color }
function Step([string]$n, [string]$msg) { Write-Host "`n[$n] $msg" -ForegroundColor Cyan }
function Die([string]$msg) { Write-Host "错误：$msg" -ForegroundColor Red; exit 1 }

function Resolve-Python {
  foreach ($c in @('py', 'python')) {
    $cmd = Get-Command $c -ErrorAction SilentlyContinue
    if ($cmd) { return $c }
  }
  Die '找不到 Python。请安装 Python 3.10+ 并确保 py 或 python 在 PATH 中。'
}

$PY = Resolve-Python

<#
  调用 Python。

  **踩坑记录（Windows PowerShell 5.1 + 原生 stderr）**
  ------------------------------------------------------------
  在本脚本 $ErrorActionPreference='Stop' 之下，被调用的原生命令只要往
  stderr 写一行，PowerShell 就会生成 ErrorRecord，并可能抛
  "NativeCommandError" 中断脚本 —— **即使该进程退出码是 0**。
  实测 `2>$null` 与 `2>&1 | Out-Null` 都压不住（错误记录已经生成）。

  因此这里改走 **cmd /c**：由 cmd 启动进程并回传退出码，
  PowerShell 不再解析该子进程的 stderr，也就不会产生 NativeCommandError。
  判定成功与否**一律只看退出码**。

  （配套约定：`chai_stats.py` 的进度提示走 stdout，只有真正的错误走 stderr。）
#>
function Invoke-Py {
  param(
    [string[]]$pyArgs,
    [switch]$ShowProgress
  )
  $parts = @()
  if ($PY -eq 'py') { $parts += @('py', '-3') } else { $parts += 'python' }
  foreach ($a in $pyArgs) {
    if ($a -match '[\s"]') {
      $parts += '"' + ($a -replace '"', '\"') + '"'
    } else {
      $parts += $a
    }
  }
  $cmdline = ($parts -join ' ')

  if ($ShowProgress) {
    Write-Host "    > $cmdline" -ForegroundColor DarkGray
    cmd /c $cmdline
    $rc = $LASTEXITCODE
    Write-Host "    (exit $rc)" -ForegroundColor DarkGray
    return $rc
  }
  cmd /c $cmdline | Out-Null
  return $LASTEXITCODE
}

if (-not (Test-Path $SplitTool)) { Die "找不到拆分工具：$SplitTool" }
if (-not (Test-Path $StatsTool)) { Die "找不到统计工具：$StatsTool" }

# ---------------------------------------------------------------- 判定输入类型
$inPath = (Resolve-Path -LiteralPath $Path).Path
$isSplitDir = $false
if (Test-Path -LiteralPath $inPath -PathType Container) {
  # 已拆好的目录：含 00_目录索引.md 或 manifest.json，且有分卷 txt
  $hasIndex = (Test-Path (Join-Path $inPath '00_目录索引.md')) -or
              (Test-Path (Join-Path $inPath 'manifest.json'))
  $hasParts = @(Get-ChildItem $inPath -Filter '*.txt' -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -notlike '00_*' -and $_.Name -notlike '01_*' -and $_.Name -notlike '_*' }).Count -gt 0
  if ($hasIndex -and $hasParts) { $isSplitDir = $true }
}

<#
  从文件名推书名。网文文件名很脏，常见形态：
    《混沌冠冕》.txt
    《带着火影重生日本东京》作者：雨后不带刀（完结）.txt
    从全面战争开始爆兵反清.txt
    带着写轮眼降临东京 完本.txt
  策略：优先取《》里的内容；否则剥掉「作者：…」「（…）」「(…)」「… 完本/完结/全本」等尾巴。
  推不出来也不致命——后续会用输出目录名兜底，或由 -Book 指定。
#>
function Get-BookName([string]$filePath) {
  $stem = [System.IO.Path]::GetFileNameWithoutExtension($filePath)
  # 1) 《书名》优先
  $m = [regex]::Match($stem, '《([^》]+)》')
  if ($m.Success) { return $m.Groups[1].Value.Trim() }
  # 2) 剥掉作者与状态尾巴
  $s = $stem
  $s = [regex]::Replace($s, '作者[：:]\s*[^（(【\[]+', '')
  $s = [regex]::Replace($s, '[（(【\[][^）)】\]]*[）)】\]]', '')
  $s = [regex]::Replace($s, '(完本|完结|全本|全集|精校版|自修正版|修正版)\s*$', '')
  $s = $s.Trim(' ', '-', '_', '·', '　')
  if ($s) { return $s }
  return $stem.Trim()
}

Write-Host "`n=== 一键拆书 ===" -ForegroundColor Green
Say "输入        : $inPath"
Say "输入类型    : $(if ($isSplitDir) { '已拆分的目录（跳过 ①—④，只跑统计）' } else { '原始文本（跑完整流水线）' })"
Say "产物根目录  : $OutRoot"
Say "Python      : $PY (PYTHONUTF8=1)"

# ---------------------------------------------------------------- 阶段 ①—④
$bookDirs = @()

if ($isSplitDir) {
  $bookDirs += $inPath
  if (-not $Book) { $Book = Split-Path -Leaf $inPath }
} else {
  # 推书名（用于定位输出目录）：优先用 -Book，否则从文件名推
  if (-not $Book) {
    $Book = Get-BookName $inPath
    Say "推定书名    : $Book"
  }

  Step '1/5' 'probe —— 探测编码 / 换行 / BOM（不写盘）'
  if ($DryRun) { Say '  （-DryRun：仅预演）' 'DarkGray' }
  Invoke-Py @($SplitTool, 'probe', $inPath) | Out-Null

  if (-not $SkipEncode) {
    Step '2/5' 'encode —— 无损统一到 UTF-8 + CRLF（就地改写，自动留 .bak）'
    $encArgs = @($SplitTool, 'encode', $inPath, '--to', 'utf-8', '--eol', 'crlf')
    if ($DryRun) { $encArgs += '--dry-run' }
    $rc = Invoke-Py $encArgs
    if ($rc -ne 0) { Die "编码统一失败（退出码 $rc）。若源文件已是 UTF-8，可加 -SkipEncode 跳过。" }
  } else {
    Step '2/5' 'encode —— 已按 -SkipEncode 跳过'
  }

  Step '3/5' 'analyze —— 分析卷/章结构'
  $anArgs = @($SplitTool, 'analyze', $inPath, '--out', $OutRoot)
  $rc = Invoke-Py $anArgs
  if ($rc -ne 0 -and $rc -ne 1) { Die "结构分析失败（退出码 $rc）" }

  Step '4/5' 'split —— 规范化 + 排序 + 切分'
  $spArgs = @($SplitTool, 'split', $inPath, '--out', $OutRoot)
  if ($Parts -gt 0) { $spArgs += @('--parts', "$Parts") }
  if ($MaxChars -gt 0) { $spArgs += @('--max-chars', "$MaxChars") }
  if ($DryRun) { $spArgs += '--dry-run' }
  # 记下切分前的目录时间戳，切分后用「最新变化」定位本次产出的书目录，
  # 避免把 output 下所有书都当成这次的产物（那样会误跑一堆统计）。
  $before = @{}
  if (Test-Path $OutRoot) {
    Get-ChildItem $OutRoot -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -notlike '*_分析' } |
      ForEach-Object { $before[$_.FullName] = $_.LastWriteTimeUtc }
  }
  $rc = Invoke-Py $spArgs
  if ($rc -ne 0) { Die "切分失败（退出码 $rc）" }

  # 定位本次产出的书目录：优先按书名精确匹配，其次取「切分后新出现或刚变新」的那个
  if ($Book) {
    $guess = Join-Path $OutRoot $Book
    if (Test-Path -LiteralPath $guess) {
      $bookDirs += $guess
    } else {
      Write-Host "  ⚠ 未找到目录 $guess（书名可能被工具改写），改用时间戳定位" -ForegroundColor Yellow
      $Book = ''
    }
  }
  if (-not $Book) {
    $cand = Get-ChildItem $OutRoot -Directory -ErrorAction SilentlyContinue |
      Where-Object { $_.Name -notlike '*_分析' } |
      Where-Object { Test-Path (Join-Path $_.FullName 'manifest.json') } |
      Where-Object {
        (-not $before.ContainsKey($_.FullName)) -or
        ($before[$_.FullName] -ne $_.LastWriteTimeUtc)
      } | Sort-Object LastWriteTimeUtc -Descending
    if ($cand.Count -eq 1) {
      $bookDirs += $cand[0].FullName
      $Book = $cand[0].Name
    } elseif ($cand.Count -gt 1) {
      # 一次切了多本（输入是目录）：全部处理，这是期望行为
      $bookDirs += $cand | Select-Object -ExpandProperty FullName
    } else {
      Die "切分成功但定位不到产出目录，请用 -Book 显式指定书名"
    }
  }
}

$bookDirs = $bookDirs | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique
if (-not $bookDirs) { Die "没有找到可统计的拆分产物目录（预期含 manifest.json / 00_目录索引.md）" }

# ---------------------------------------------------------------- 阶段 ⑤ 统计
$summary = @()
foreach ($bd in $bookDirs) {
  $bname = Split-Path -Leaf $bd
  $analysisDir = Join-Path (Split-Path -Parent $bd) "${bname}_分析"

  if (-not $TasksOnly) {
    Step '5/5' "stats —— 机读统计：《$bname》"
    $stArgs = @($StatsTool, 'stats', $bd, '--book', $bname,
                '--out', $analysisDir, '--min-count', "$MinTermCount")
    if ($Terms) { $stArgs += @('--terms', $Terms) }
    $rc = Invoke-Py $stArgs
    if ($rc -ne 0) { Write-Host "  统计失败（退出码 $rc），跳过本书" -ForegroundColor Yellow; continue }

    $rc = Invoke-Py @($StatsTool, 'verify', $bd, '--book', $bname)
    if ($rc -ne 0) {
      Write-Host "  ⚠ 对账未通过——统计口径与拆分索引不一致，请先看上面的差异说明" -ForegroundColor Yellow
    }
  }

  # 读取统计结果供汇总
  $sj = Join-Path $analysisDir 'stats.json'
  if (Test-Path $sj) {
    $j = Get-Content $sj -Raw -Encoding UTF8 | ConvertFrom-Json
    $summary += [pscustomobject]@{
      书名   = $bname
      章数   = $j.totals.chapters
      净字数 = $j.totals.total_chars
      段落数 = $j.totals.total_paragraphs
      份数   = $j.totals.parts
      均章长 = $j.metrics.chapter_len.mean
      章长SD = $j.metrics.chapter_len.stdev
      对话占比 = $j.metrics.dialogue_para_pct
      分析目录 = $analysisDir
    }
  }

  # ------------------------------------------------------------ 分层精读任务书
  $taskFile = Join-Path $analysisDir '精读任务书.md'
  $partFiles = Get-ChildItem $bd -Filter '*.txt' -File |
    Where-Object { $_.Name -notlike '00_*' -and $_.Name -notlike '01_*' -and $_.Name -notlike '_*' } |
    Sort-Object Name
  $n = $partFiles.Count
  $lines = @()
  $lines += "# 《$bname》分层精读任务书"
  $lines += ''
  $lines += '> 由 `tools/chai/chai.ps1` 自动生成。用途：把 N 份正文分配给 N 个 subagent'
  $lines += '> 逐章精读，每个 subagent 产出一份笔记，再由主 agent 汇总成总报告。'
  $lines += ''
  $lines += '## 一、任务分工'
  $lines += ''
  $lines += "全书共 **$n 份**，建议按下面的表格逐份派发（subagent 之间互不依赖，可并行）。"
  $lines += ''
  $lines += '| # | 正文文件 | 章数 | 净字数 | 起 | 止 |'
  $lines += '|---|---|---:|---:|---|---|'
  if (Test-Path $sj) {
    $i = 0
    foreach ($p in $j.parts) {
      $i++
      $lines += "| $i | ``$($p.file)`` | $($p.chapters) | $($p.chars) | $($p.first_heading) | $($p.last_heading) |"
    }
  } else {
    foreach ($p in $partFiles) { $lines += "| | ``$($p.Name)`` | | | | |" }
  }
  $lines += ''
  $lines += '## 二、每个 subagent 的固定交付格式'
  $lines += ''
  $lines += '要求每份笔记**结构一致**，否则主 agent 无法汇总。逐章至少写清：'
  $lines += ''
  $lines += '```markdown'
  $lines += '### 第N章 章名'
  $lines += '- 情节：本章发生了什么（2—4 句，只写事实）'
  $lines += '- 功能：本章在结构上干什么（铺垫/转折/高潮/结算/降温/换轨）'
  $lines += '- 爽点：本章命中了哪几类爽点（打脸/装逼/获取/升级/身份揭晓/收人/知识掠夺/建设/反派吃瘪）'
  $lines += '- 章末钩：末句是什么，属于哪类钩（对白/宣言/悬念/危机/收获/拟声）'
  $lines += '- 金句：本章最值得记的 1—2 句原文（逐字摘录，标行号）'
  $lines += '```'
  $lines += ''
  $lines += '卷（份）末额外写清：'
  $lines += ''
  $lines += '- **本卷情节链**：因果相连的事件序列（不是清单，要能看出"因为…所以…"）'
  $lines += '- **本卷功能定位**：这一卷在全书中承担什么'
  $lines += '- **人物/关系变化**：谁的地位、实力、关系变了，变成什么'
  $lines += '- **世界观新增**：新设定的首现处'
  $lines += '- **技法观察**：视角、节奏、战斗写法、信息投喂、用梗密度'
  $lines += '- **可核查统计**：本卷章数、均章长、最长/最短章'
  $lines += ''
  $lines += '## 三、纪律（必须写进每个 subagent 的 prompt）'
  $lines += ''
  $lines += '1. **只写读到的内容**，引用要能回到原文；不要编造、不要推断当成事实。'
  $lines += '2. **章号以正文标题为准**，不要自行重排。'
  $lines += '3. **区分三类事实**：①文本明写的 ②可合理推断的（标注"推断"）③作者未交代的（标注"未交代"）。'
  $lines += '4. **统计数字只引用 `stats_摘要.md`**，不要自己心算。'
  $lines += '5. 读不完就如实说读到第几章，**不要用摘要冒充精读**。'
  $lines += ''
  $lines += '## 四、主 agent 的汇总顺序'
  $lines += ''
  $lines += '1. 先读 `stats_摘要.md` 与 `chapters.csv`（数据底座）'
  $lines += '2. 再逐份读 subagent 笔记（人物/情节/技法）'
  $lines += '3. 最后写总报告，结构建议：'
  $lines += '   定位与坐标系 → 宏观结构分期 → 情节与主线发动机 → 人物弧光 →'
  $lines += '   世界观体系 → 叙事与写作风格 → **爽点配方与节奏规律** → 优点与缺陷 → 结论'
  $lines += '4. **凡是结论都要能指回章号**；无法核查的标注为"待验证"。'
  $lines += ''
  $lines += '## 五、本机可用的剖析工具'
  $lines += ''
  $lines += '- 统计：`py -3 tools/chai/chai_stats.py stats <output/书名>`'
  $lines += '- 对账：`py -3 tools/chai/chai_stats.py verify <output/书名>`'
  $lines += '- 词表：`py -3 tools/chai/chai_stats.py terms <output/书名> --top-n 200`'
  $lines += ''
  if (-not $DryRun) {
    $lines | Set-Content -LiteralPath $taskFile -Encoding UTF8
    Write-Host "  任务书：$taskFile" -ForegroundColor DarkGray
  }
}

# ---------------------------------------------------------------- 汇总
Write-Host "`n=== 完成 ===" -ForegroundColor Green
if ($summary.Count -gt 0) {
  $summary | Format-Table -AutoSize
  Write-Host '下一步：把「精读任务书.md」按份派给 subagent 逐章精读，再汇总成总报告。' -ForegroundColor Green
} else {
  Write-Host '没有生成统计产物。' -ForegroundColor Yellow
}
exit 0
