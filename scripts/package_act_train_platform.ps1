$ErrorActionPreference = "Stop"

$PythonExe = "D:\soft\29anaconda3\anaconda3\envs\act_server_py310\python.exe"
$PackageName = "act_train_platform"

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptRoot
$CondaEnvRoot = Split-Path -Parent $PythonExe
$CondaLibraryBin = Join-Path $CondaEnvRoot "Library\bin"
$BuildRoot = Join-Path $ProjectRoot "build"
$DistRoot = Join-Path $ProjectRoot "dist"
$PackageRoot = Join-Path $DistRoot $PackageName

function Resolve-FullPath([string]$PathValue) {
    return [System.IO.Path]::GetFullPath($PathValue)
}

function Assert-UnderProject([string]$PathValue) {
    $projectFull = Resolve-FullPath $ProjectRoot
    $targetFull = Resolve-FullPath $PathValue
    if (-not $targetFull.StartsWith($projectFull, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refuse to modify path outside project: $targetFull"
    }
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python environment not found: $PythonExe"
}
if (-not (Test-Path -LiteralPath $CondaLibraryBin)) {
    throw "Conda Library bin not found: $CondaLibraryBin"
}

Push-Location $ProjectRoot
try {
    $oldPath = $env:PATH
    $env:PATH = "$CondaLibraryBin;$oldPath"

    Assert-UnderProject $BuildRoot
    Assert-UnderProject $PackageRoot

    if (Test-Path -LiteralPath $BuildRoot) {
        Remove-Item -LiteralPath $BuildRoot -Recurse -Force
    }
    if (Test-Path -LiteralPath $PackageRoot) {
        Remove-Item -LiteralPath $PackageRoot -Recurse -Force
    }

    & $PythonExe -m PyInstaller `
        --noconfirm `
        --onedir `
        --clean `
        --console `
        --name $PackageName `
        --add-data "$ProjectRoot\static;static" `
        --add-data "$ProjectRoot\templates;templates" `
        --add-data "$ProjectRoot\docs;docs" `
        --add-data "$ProjectRoot\core\schema.sql;core" `
        --add-binary "$CondaLibraryBin\libcrypto-3-x64.dll;." `
        --add-binary "$CondaLibraryBin\libssl-3-x64.dll;." `
        --add-binary "$CondaLibraryBin\ffi.dll;." `
        --add-binary "$CondaLibraryBin\libbz2.dll;." `
        --add-binary "$CondaLibraryBin\libexpat.dll;." `
        --add-binary "$CondaLibraryBin\liblzma.dll;." `
        --add-binary "$CondaLibraryBin\zlib.dll;." `
        --hidden-import core.train_worker `
        --hidden-import uvicorn.logging `
        --hidden-import uvicorn.loops.auto `
        --hidden-import uvicorn.protocols.http.auto `
        --hidden-import uvicorn.protocols.websockets.auto `
        --hidden-import uvicorn.lifespan.on `
        --collect-submodules fastapi `
        --collect-submodules starlette `
        --collect-submodules pydantic `
        --collect-submodules uvicorn `
        --collect-submodules websockets `
        --collect-submodules multipart `
        --collect-all ultralytics `
        --collect-all torch `
        --collect-all torchvision `
        --collect-all cv2 `
        --collect-all pandas `
        --collect-all yaml `
        "$ProjectRoot\app.py"

    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE"
    }

    foreach ($dirName in @("static", "templates", "docs")) {
        $source = Join-Path $ProjectRoot $dirName
        $target = Join-Path $PackageRoot $dirName
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
        }
        Copy-Item -LiteralPath $source -Destination $target -Recurse -Force
    }

    $dataRoot = Join-Path $PackageRoot "data"
    foreach ($dirName in @("assets", "uploads", "imports", "frames", "datasets", "runs", "packages", "prelabels")) {
        New-Item -ItemType Directory -Force -Path (Join-Path $dataRoot $dirName) | Out-Null
    }

    Get-ChildItem -LiteralPath $ProjectRoot -File -Filter "*.pt" |
        ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $PackageRoot -Force }

    Write-Host ""
    Write-Host "act_train_platform package created:" -ForegroundColor Green
    Write-Host "  $PackageRoot"
    Write-Host ""
    Write-Host "Run on target machine:"
    Write-Host "  .\act_train_platform.exe --host 0.0.0.0 --port 18100"
}
finally {
    if ($null -ne $oldPath) {
        $env:PATH = $oldPath
    }
    Pop-Location
}
