# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 规格文件：古韵机器人 v4.0.0（Windows 便携版，onedir）。

用法（在 packaging 目录下）：
    python -m PyInstaller --noconfirm --clean 古韵机器人.spec
产物：
    dist/古韵机器人/  （整个目录可直接拷走，双击 启动.bat 运行）
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(os.getcwd(), os.pardir))
PACKAGING = os.getcwd()

datas = []
binaries = []
hiddenimports = []

# 第三方依赖：整包收（streamlit 的静态资源、sherpa-onnx / vosk 的原生库都在里面）
for pkg in [
    "streamlit", "sherpa_onnx", "vosk", "miniaudio", "edge_tts", "opencc",
    "pypinyin", "qieyun", "sounddevice", "numpy", "scipy",
    "yaml", "dotenv", "altair", "pyarrow", "pandas",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:          # 某个包不可用时不要整体失败
        print(f"[spec] 跳过 {pkg}: {exc}")

# 本项目源码/资源：运行时按普通 Python 包 import，所以放成数据文件即可
for folder in ["robot", "services", "language", "components", "config"]:
    src = os.path.join(ROOT, folder)
    if os.path.isdir(src):
        datas.append((src, folder))

for filename in ["classical_translator.py", "phonology_db.py", "sound_synth.py"]:
    src = os.path.join(ROOT, filename)
    if os.path.isfile(src):
        datas.append((src, "."))

# 主题配置：streamlit 读 cwd/.streamlit/config.toml
theme = os.path.join(ROOT, ".streamlit", "config.toml")
if os.path.isfile(theme):
    datas.append((theme, ".streamlit"))

hiddenimports += [
    "streamlit.runtime.scriptrunner.magic_funcs",
    "robot.app", "robot.audio_io", "robot.windows_audio", "robot.recorder",
    "robot.session", "robot.voice_router",
    "services.asr_client", "services.llm_client", "services.tts_client",
    "language.ancient_tts", "language.turn_engine", "language.style_prompt",
]

a = Analysis(
    ["launcher_v4.py"],
    pathex=[ROOT, PACKAGING],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide6", "notebook", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="古韵机器人",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="古韵机器人",
)
