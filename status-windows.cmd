@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
    py -3 "%~dp0src\claude_zh.py" status
    goto finish
)
where python >nul 2>&1
if not errorlevel 1 (
    python "%~dp0src\claude_zh.py" status
    goto finish
)
echo Python 3 was not found. Install Python 3 before running.
:finish
echo.
pause
