param([string]$PythonExe = "", [string]$BuildDirectory = "", [string]$OutputDirectory = "")
$ErrorActionPreference = "Stop"

# 构建机使用普通 Python Launcher；生成的 EXE 在目标机不依赖 Python 或 Conda。
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Source = Join-Path $PSScriptRoot "train_config_transfer.py"
$ToolSource = Join-Path $PSScriptRoot "train_config_transfer"
$BuildRoot = Join-Path $ProjectRoot "build\train_config_transfer"
$DistRoot = Join-Path $ProjectRoot "dist\train_config_transfer"
if ($BuildDirectory) { $BuildRoot = [IO.Path]::GetFullPath($BuildDirectory) }
if ($OutputDirectory) { $DistRoot = [IO.Path]::GetFullPath($OutputDirectory) }
# 正式输出绝不覆盖，构建缓存仅位于调用者明确指定的本任务目录。
if (Test-Path -LiteralPath $DistRoot) { throw "输出目录已存在，禁止覆盖：$DistRoot" }
$PythonArgs = @()
if (-not $PythonExe) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw "构建机未找到Python；请通过PythonExe指定构建解释器。现场使用不需要Python。" }
    $PythonExe = "py"
    $PythonArgs = @("-3")
}

& $PythonExe @PythonArgs -m PyInstaller --version *> $null
if ($LASTEXITCODE -ne 0) { throw "构建机缺少 PyInstaller。目标机不需要安装该依赖。" }

New-Item -ItemType Directory -Path $BuildRoot -Force | Out-Null
& $PythonExe @PythonArgs -m PyInstaller --noconfirm --clean --onefile --console --name train_config_transfer --specpath $BuildRoot --workpath $BuildRoot --distpath $DistRoot $Source
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败，退出码：$LASTEXITCODE" }

Copy-Item -LiteralPath (Join-Path $ToolSource "01-导出Train配置.cmd") -Destination $DistRoot -Force
Copy-Item -LiteralPath (Join-Path $ToolSource "02-导入Train配置.cmd") -Destination $DistRoot -Force
Copy-Item -LiteralPath (Join-Path $ToolSource "03-恢复导入前Train配置.cmd") -Destination $DistRoot -Force
Copy-Item -LiteralPath (Join-Path $ToolSource "README.md") -Destination (Join-Path $DistRoot "使用说明.md")
Write-Host "Train 配置转移工具已生成：$DistRoot" -ForegroundColor Green
