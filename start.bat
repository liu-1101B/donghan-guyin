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
        echo [错误] 创建虚拟环境失败。请安装 Python 3.10 及以上版本并勾选 Add Python to PATH。
        pause
        exit /b 1
    )
)

echo 检查机器人依赖...
"%PYTHON%" -c "import streamlit, sounddevice, numpy, scipy, httpx, yaml, dotenv, miniaudio, edge_tts, vosk, pypinyin, qieyun, opencc" >nul 2>&1
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

if not exist "models\sense-voice\tokens.txt" (
    if exist "models\vosk-small-cn\am\final.mdl" goto has_model
    echo.
    echo [提示] 未发现语音识别模型。
    echo 文字输入、文言回答和语音合成不需要模型；语音输入（按住说话）需要。
    echo 推荐 SenseVoice（中英日韩粤，约 228 MB，中文准确率明显高于 Vosk 小模型）。
    choice /C YN /M "是否立即从镜像下载 SenseVoice 模型"
    if errorlevel 2 goto no_model
    echo 正在下载模型（约 228 MB，来自 hf-mirror）...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $d='models\sense-voice'; New-Item -ItemType Directory -Force -Path $d | Out-Null; $b='https://hf-mirror.com/csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main'; Invoke-WebRequest \"$b/model.int8.onnx\" -OutFile \"$d/model.int8.onnx\"; Invoke-WebRequest \"$b/tokens.txt\" -OutFile \"$d/tokens.txt\""
    if errorlevel 1 (
        echo [警告] 模型下载失败。机器人仍会启动，文字输入可用；以后可重新运行 start.bat 安装模型。
    )
)
:has_model
:no_model

echo.
echo 启动机器人新版界面：robot/app.py
echo 浏览器地址通常为 http://localhost:8501
echo 首次启动后若浏览器未自动打开，请复制 Streamlit 显示的 Local URL。
echo.
"%PYTHON%" -m streamlit run robot/app.py --server.headless true
pause
