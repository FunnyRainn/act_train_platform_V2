@echo off
chcp 65001 >nul
setlocal
set "TOOL=%~dp0train_config_transfer.exe"
if not exist "%TOOL%" (echo 失败：缺少 train_config_transfer.exe，请保持工具目录完整。& pause& exit /b 2)
set /p "TRAIN_ROOT=请输入新机器 Train 根目录："
set /p "PACKAGE=请输入已解压迁移包目录："
"%TOOL%" import --train-root "%TRAIN_ROOT%" --package "%PACKAGE%"
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
