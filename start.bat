@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo    古韵机器人 - Windows 启动器
echo ========================================
echo.

set "PYTHON=%CD%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" (
    echo 正在创建独立 Python 环境...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.12 -m venv .venv >nul 2>&1
        if errorlevel 1 py -3 -m venv .venv
    ) else (
        python -m venv .venv
    )
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。请安装 Python 3.10-3.12 并勾选 Add Python to PATH。
        pause
        exit /b 1
    )
)

echo 检查机器人依赖...
"%PYTHON%" -c "import streamlit, sounddevice, numpy, scipy, httpx, yaml, dotenv, miniaudio, edge_tts, vosk" >nul 2>&1
if errorlevel 1 (
    echo 首次运行或依赖不完整，正在安装 requirements-robot.txt...
    "%PYTHON%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo [错误] pip 更新失败。
        pause
        exit /b 1
    )
    "%PYTHON%" -m pip install -r requirements-robot.txt
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请查看上方日志。
        pause
        exit /b 1
    )
)

if not exist "models\vosk-small-cn\am\final.mdl" (
    echo.
    echo [提示] 未发现 Vosk 中文语音识别模型。
    echo 文字输入、文言回答和语音合成仍可使用；录音转文字需要该模型（约 44 MB）。
    choice /C YN /M "是否立即下载 Vosk 中文模型"
    if errorlevel 2 goto no_model
    echo 正在下载并解压模型...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; New-Item -ItemType Directory -Force -Path 'models' | Out-Null; Invoke-WebRequest 'https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip' -OutFile 'models\vosk-model-small-cn-0.22.zip'; Expand-Archive -Force 'models\vosk-model-small-cn-0.22.zip' 'models'; if (Test-Path 'models\vosk-small-cn') { Remove-Item -Recurse -Force 'models\vosk-small-cn' }; Move-Item 'models\vosk-model-small-cn-0.22' 'models\vosk-small-cn'; Remove-Item -Force 'models\vosk-model-small-cn-0.22.zip'"
    if errorlevel 1 (
        echo [警告] 模型下载失败。机器人仍会启动，文字输入可用；以后可重新运行 start.bat 安装模型。
    )
)
:no_model

echo.
echo 启动机器人新版界面：robot/app.py
echo 浏览器地址通常为 http://localhost:8501
echo 首次启动后若浏览器未自动打开，请复制 Streamlit 显示的 Local URL。
echo.
"%PYTHON%" -m streamlit run robot/app.py --server.headless true
pause
