# 古韵合成器 - 打包与构建指南

## 项目结构

```
donghan-guyin/
├── guyun_app.py              # 主应用 (Streamlit)
├── classical_translator.py   # 白话→古文 翻译引擎
├── phonology_db.py           # 东汉音韵数据库 (703字)
├── sound_synth.py            # 双引擎音频合成 (eSpeak-ng + 共振峰)
├── launcher.py               # PyInstaller 统一入口
├── requirements.txt          # Python 依赖
├── icon.png                  # 应用图标
├── build.bat                 # 一键构建脚本
├── download_espeak.py        # 下载 espeak-ng 脚本
├── 古韵合成器.iss            # Inno Setup 安装脚本
└── espeak-ng/                # eSpeak-ng 文件
```

## 构建步骤（在你的 Windows 电脑上执行）

### 前置条件

1. Python 3.10+ 并安装依赖:
   ```bash
   pip install pyinstaller
   pip install -r requirements.txt
   ```

2. Inno Setup 7（可选，用于生成 .exe 安装包）
   下载: https://jrsoftware.org/isinfo.php

### 第一步：下载 eSpeak-ng

```bash
python download_espeak.py
```

### 第二步：一键构建

```bash
python -m PyInstaller --noconfirm --clean --console --name "古韵合成器" --add-data "guyun_app.py;." --add-data "classical_translator.py;." --add-data "phonology_db.py;." --add-data "sound_synth.py;." --add-data "requirements.txt;." --collect-all streamlit --collect-all scipy --collect-all numpy --collect-all pypinyin --hidden-import edge_tts --hidden-import pypinyin --hidden-import qieyun --hidden-import gtts launcher.py
Copy-Item -Recurse -Force "espeak-ng\*" "dist\古韵合成器\espeak-ng"
& "C:\Program Files\Inno Setup 7\ISCC.exe" 古韵合成器.iss
```

### 第三步：分发给用户

- 分发 `古韵合成器_Setup_v2.0.exe` 安装包即可

## 技术说明

### launcher.py 工作原理

- `launcher.py` 是 PyInstaller 的入口点
- 它**直接 import streamlit** 并调用 `streamlit.web.cli.main()`
- PyInstaller 能正确追踪并打包所有 streamlit、numpy、scipy 依赖

### eSpeak-ng 路径查找

`sound_synth.py` 中的 `get_espeak_path()` 按以下优先级查找:
1. `{exe所在目录}\espeak-ng\espeak-ng.exe` (Inno Setup 安装)
2. `C:\Program Files\eSpeak NG\espeak-ng.exe` (MSI 安装)
3. 系统 PATH 中的 `espeak-ng`

### 拼音回退

应用完全使用本地 PINYIN_MAP (193 字) 做拼音回退，不依赖 pypinyin 三方库。
