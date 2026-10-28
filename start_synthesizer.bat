@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo    古韵独立合成器 - Windows 启动器
echo ========================================
echo.

set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.12 -m venv .venv >nul 2>&1
        if errorlevel 1 py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败，请安装 Python 3.10-3.12。
        pause
        exit /b 1
    )
)

"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 独立合成器依赖安装失败。
    pause
    exit /b 1
)

"%PYTHON%" -m streamlit run guyun_app.py --server.headless true
pause
