<#
.SYNOPSIS
    重新打包 NovelKit.exe（PyInstaller 单文件）。

.DESCRIPTION
    1) 确保 PyInstaller 可用（没有就取 wheel 到 _pylib，不走 pip 的临时解包）；
    2) 用 --onefile --console 打包，把 novel_split / chai_stats 显式带进去；
    3) 冒烟测试 --version / where。

    注意：全程 $ErrorActionPreference='Continue' + 只看退出码。
    Windows PowerShell 5.1 在 Stop 模式下会把原生程序的 stderr 当成致命错误
    （PyInstaller 会往 stderr 写 INFO/WARNING），照 Stop 写会在打包中途莫名中断。

.EXAMPLE
    .\tools\novelkit\build.ps1

.EXAMPLE
    .\tools\novelkit\build.ps1 -SkipSmoke
#>
[CmdletBinding()]
param(
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Continue'
$here = $PSScriptRoot
$root = Split-Path -Parent (Split-Path -Parent $here)   # tools\novelkit → 仓库根
$pylib = Join-Path $here '_pylib'
$work = Join-Path $root '.tmp\pyi'

$env:PYTHONPATH = $pylib
$env:PYTHONUTF8 = '1'
$env:TEMP = Join-Path $root '.tmp\pip'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP, (Join-Path $work 'build') | Out-Null

Write-Host '== 1/3 检查 PyInstaller ==' -ForegroundColor Cyan
py -3 -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '   未安装，取 wheel 到 _pylib ...' -ForegroundColor Yellow
    py -3 (Join-Path $here 'bootstrap_pyinstaller.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 准备失败（检查网络，或手动把 wheel 解包到 _pylib）' }
} else {
    Write-Host '   已就绪'
}

Write-Host '== 2/3 打包 ==' -ForegroundColor Cyan
py -3 -m PyInstaller `
    --noconfirm --clean --onefile --console `
    --name NovelKit `
    --distpath (Join-Path $here 'dist') `
    --workpath (Join-Path $work 'build') `
    --specpath $work `
    --paths (Join-Path $root 'tools\novel_split') `
    --paths (Join-Path $root 'tools\chai') `
    --hidden-import novel_split `
    --hidden-import chai_stats `
    (Join-Path $here 'novelkit.py')
if ($LASTEXITCODE -ne 0) { throw '打包失败' }

$exe = Join-Path $here 'dist\NovelKit.exe'
if (-not (Test-Path $exe)) { throw "没有生成 $exe" }

if (-not $SkipSmoke) {
    Write-Host '== 3/3 冒烟测试 ==' -ForegroundColor Cyan
    & $exe --version
    & $exe where
    if ($LASTEXITCODE -ne 0) { throw '冒烟测试失败' }
}

$size = [math]::Round((Get-Item $exe).Length / 1MB, 2)
Write-Host "`n完成：$exe（$size MB）" -ForegroundColor Green
