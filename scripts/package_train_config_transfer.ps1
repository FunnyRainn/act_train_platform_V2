$ErrorActionPreference = "Stop"

# 构建机使用普通 Python Launcher；生成的 EXE 在目标机不依赖 Python 或 Conda。
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $PSScriptRoot "train_config_transfer.py"
$ToolSource = Join-Path $PSScriptRoot "train_config_transfer"
$BuildRoot = Join-Path $ProjectRoot "build\train_config_transfer"
$DistRoot = Join-Path $ProjectRoot "dist\train_config_transfer"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "构建机未找到 Windows Python Launcher（py）。" }
& py -3 -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) { throw "构建机缺少 PyInstaller。目标机不需要安装该依赖。" }

& py -3 -m PyInstaller --noconfirm --clean --onefile --console --name train_config_transfer --workpath $BuildRoot --distpath $DistRoot $Source
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码：$LASTEXITCODE" }

Copy-Item -LiteralPath (Join-Path $ToolSource "01-导出Train配置.cmd") -Destination $DistRoot -Force
Copy-Item -LiteralPath (Join-Path $ToolSource "02-导入Train配置.cmd") -Destination $DistRoot -Force
Copy-Item -LiteralPath (Join-Path $ToolSource "03-恢复导入前Train配置.cmd") -Destination $DistRoot -Force
Copy-Item -LiteralPath (Join-Path $ToolSource "README.md") -Destination $DistRoot -Force
Write-Host "Train 配置转移工具已生成：$DistRoot" -ForegroundColor Green
