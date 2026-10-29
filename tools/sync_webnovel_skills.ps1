<#
同步「网文工坊 chinese-webnovel-skills」到 DSH 的用户级 skill 根目录。

为什么需要这个脚本：
  DSH 的 skill-filesystem 只识别「深度 1」的两种形态：
    <root>/<name>/SKILL.md   （目录 bundle）
    <root>/<name>.md         （平铺文件）
  并且它把每个 bundle 的 `resourceBase` 设成 **该 bundle 自己的目录**，
  加载时提示模型「相对路径按此基目录解析」。
  而网文工坊的 33 个 SKILL.md 里写的是 `references/xxx.md`，
  在它原仓库里相对的是**仓库根**，不是技能自己的目录。
  因此必须把共享的 references/ 一并复制进**每个**技能 bundle，
  相对路径才会解析到正确位置。

用法：
  pwsh -File tools\sync_webnovel_skills.ps1                 # 同步到默认位置
  pwsh -File tools\sync_webnovel_skills.ps1 -DryRun         # 只看会做什么
  pwsh -File tools\sync_webnovel_skills.ps1 -Dest <path>    # 指定 skill 根
  pwsh -File tools\sync_webnovel_skills.ps1 -WhatIfClean    # 额外报告目标里的非本包技能
#>
[CmdletBinding()]
param(
  [string]$Dest = (Join-Path $env:USERPROFILE '.dsh\skills'),
  [string]$RepoUrl = 'https://github.com/tance-mang/chinese-webnovel-skills.git',
  [string]$Stage = (Join-Path $PSScriptRoot '..\.skillstage'),
  [switch]$DryRun,
  [switch]$WhatIfClean
)

$ErrorActionPreference = 'Stop'

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Info($msg) { Write-Host "    $msg" }

# ---------- 1. 取源（改用 HTTP/1.1 + 放宽低速超时，国内网络更稳） ----------
$env:GIT_HTTP_LOW_SPEED_LIMIT = '1000'
$env:GIT_HTTP_LOW_SPEED_TIME  = '180'

$stagePath = [System.IO.Path]::GetFullPath($Stage)
if (Test-Path (Join-Path $stagePath '.git')) {
  Write-Step "更新暂存仓库：$stagePath"
  if (-not $DryRun) {
    git -C $stagePath -c http.version=HTTP/1.1 fetch --depth 1 origin 2>&1 | Out-Null
    git -C $stagePath -c http.version=HTTP/1.1 reset --hard origin/HEAD 2>&1 | Out-Null
  }
} else {
  Write-Step "克隆：$RepoUrl"
  if (Test-Path $stagePath) { Remove-Item $stagePath -Recurse -Force }
  if (-not $DryRun) {
    git -c http.version=HTTP/1.1 clone --depth 1 --quiet $RepoUrl $stagePath 2>&1 | Out-Null
  }
}

$skillsSrc = Join-Path $stagePath 'skills'
$refsSrc   = Join-Path $stagePath 'references'
if (-not $DryRun) {
  if (-not (Test-Path $skillsSrc)) { throw "找不到 skills 目录：$skillsSrc" }
  if (-not (Test-Path $refsSrc))   { throw "找不到 references 目录：$refsSrc" }
}

$skillDirs = Get-ChildItem $skillsSrc -Directory | Sort-Object Name
$refFiles  = Get-ChildItem $refsSrc -File
$commit    = if ($DryRun) { '(dry-run)' } else { (git -C $stagePath rev-parse --short HEAD) }

Write-Step "发现 $($skillDirs.Count) 个技能 / $($refFiles.Count) 个共享参考库（commit $commit）"

# ---------- 2. 目标根 ----------
if (-not (Test-Path $Dest)) {
  Write-Step "创建 skill 根目录：$Dest"
  if (-not $DryRun) { New-Item -ItemType Directory -Path $Dest -Force | Out-Null }
}
$resolved = Resolve-Path $Dest -ErrorAction SilentlyContinue
if ($resolved) { $Dest = $resolved.Path }

# 已有的、不属于本包的技能（不动它们）
$known = $skillDirs.Name
$foreign = @()
if (Test-Path $Dest) {
  $foreign = Get-ChildItem $Dest -Directory |
    Where-Object { $known -notcontains $_.Name } |
    Select-Object -ExpandProperty Name
}

# ---------- 3. 逐个技能：bundle 目录 + 内嵌 references ----------
$totalBytes = 0
foreach ($sd in $skillDirs) {
  $target = Join-Path $Dest $sd.Name
  $targetRefs = Join-Path $target 'references'

  if ($DryRun) {
    Write-Info "[dry] $($sd.Name)  ->  $target  (+ references x$($refFiles.Count))"
    continue
  }

  if (Test-Path $target) { Remove-Item $target -Recurse -Force }
  New-Item -ItemType Directory -Path $target -Force | Out-Null
  Copy-Item (Join-Path $sd.FullName 'SKILL.md') (Join-Path $target 'SKILL.md') -Force

  # 技能自带的额外资源（scripts / assets 等），本包目前没有，保留以防上游新增
  Get-ChildItem $sd.FullName -Force |
    Where-Object { $_.Name -ne 'SKILL.md' } |
    ForEach-Object { Copy-Item $_.FullName (Join-Path $target $_.Name) -Recurse -Force }

  # 共享参考库塞进本 bundle，使 `references/xxx.md` 相对路径可解析
  New-Item -ItemType Directory -Path $targetRefs -Force | Out-Null
  Copy-Item (Join-Path $refsSrc '*') $targetRefs -Recurse -Force

  $sz = (Get-ChildItem $target -Recurse -File | Measure-Object Length -Sum).Sum
  $totalBytes += $sz
  Write-Info ("{0,-12} {1,7:N0} KB" -f $sd.Name, ($sz / 1KB))
}

# ---------- 4. 顺带放一份原始仓库快照，便于查 changelog / CLI 版 ----------
if (-not $DryRun) {
  $meta = Join-Path $Dest '_webnovel-repo-info'
  if (Test-Path $meta) { Remove-Item $meta -Recurse -Force }
  New-Item -ItemType Directory -Path $meta -Force | Out-Null
  foreach ($f in @('README.md','CHANGELOG.md','LICENSE','PUBLISHING.md')) {
    $src = Join-Path $stagePath $f
    if (Test-Path $src) { Copy-Item $src (Join-Path $meta $f) -Force }
  }
  @(
    "source: $RepoUrl"
    "commit: $commit"
    "synced: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    "layout: 33 个目录 bundle（每个内含 references/ 副本）"
    "note: 'references/' 在每个 bundle 内各有一份副本，因为 DSH 按 bundle 目录解析相对路径。"
  ) | Set-Content (Join-Path $meta 'SYNC-INFO.txt') -Encoding UTF8
}

# ---------- 5. 报告 ----------
Write-Step "完成"
if (-not $DryRun) {
  Write-Info ("技能数：{0}    总大小：{1:N1} MB" -f $skillDirs.Count, ($totalBytes / 1MB))
  Write-Info "目标根：$Dest"
}
if ($foreign.Count -gt 0) {
  Write-Host ""
  Write-Host "目标根里还有 $($foreign.Count) 个非本包技能（未改动）：" -ForegroundColor Yellow
  $foreign | ForEach-Object { Write-Host "    - $_" }
}
Write-Host ""
Write-Host "生效方式：skill 目录被监听，新增/改名/删除无需重启。" -ForegroundColor Green
Write-Host "在 DSH 里对 Agent 说「用 start 技能带我走一遍」即可；或叫它按名字加载某个技能。" -ForegroundColor Green
