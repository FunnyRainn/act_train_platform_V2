@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"

where conda >nul 2>nul
if errorlevel 1 (
    echo conda command not found. Please add conda to PATH first.
    pause
    exit /b 1
)

cd /d "%PROJECT_DIR%"
call conda activate act_server_py310_V2
if errorlevel 1 (
    echo Failed to activate conda environment: act_server_py310_V2
    pause
    exit /b 1
)

python app.py --host 0.0.0.0 --port 28100
