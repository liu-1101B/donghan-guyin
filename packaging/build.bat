@echo off
chcp 65001 >nul
title 构建古韵合成器安装包

echo ================================================
echo  古韵合成器 - 一键构建脚本
echo ================================================

if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
if exist *.spec del /q *.spec

if not exist espeak-ng\espeak-ng.exe (
    echo [警告] espeak-ng\espeak-ng.exe 未找到
    choice /c yn /n
    if errorlevel 2 exit /b 1
)

echo 步骤 1: PyInstaller 打包...
pyinstaller --noconfirm --clean --console --name 古韵合成器 --add-data guyun_app.py;. --add-data classical_translator.py;. --add-data phonology_db.py;. --add-data sound_synth.py;. --add-data requirements.txt;. --collect-all streamlit --collect-all scipy --collect-all numpy --collect-all pypinyin --hidden-import edge_tts --hidden-import pypinyin --hidden-import qieyun --hidden-import gtts launcher.py
if errorlevel 1 (
    echo PyInstaller 打包失败
    pause
    exit /b 1
)

if exist espeak-ng\espeak-ng.exe (
    echo 复制 espeak-ng...
    mkdir dist\古韵合成器\espeak-ng 2>nul
    xcopy /e /y espeak-ng\* dist\古韵合成器\espeak-ng)

echo 步骤 2: 创建启动脚本...
(
echo @echo off
echo cd /d %%%%~dp0
echo start 古韵合成器.exe
) > dist\古韵合成器\启动.bat

REM Inno Setup
set ISCC=
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set ISCC=C:\Program Files\Inno Setup 6\ISCC.exe
if not "%ISCC%"=="" (
    echo 编译安装包...
    "%ISCC%" 古韵合成器.iss
) else (
    echo [信息] 未找到 Inno Setup，跳过安装包
)

echo.
echo ================================================
echo  构建完成！
echo  可分发文件: dist\古韵合成器echo ================================================
pause
