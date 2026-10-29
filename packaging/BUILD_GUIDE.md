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

---

# v4.0.0：打包机器人新版界面（便携版，不做安装包）

v4 打的是 `robot/app.py`（新版机器人界面），不是 `guyun_app.py`。产物是**免安装便携目录 + zip**，
不需要 Inno Setup。

```powershell
# 在 packaging 目录下
python -m PyInstaller --noconfirm --clean 古韵机器人.spec
# 把 eSpeak-ng 放进 _internal（sound_synth 按 __file__ 找同级的 espeak-ng/）
New-Item -ItemType Directory -Force dist\古韵机器人\_internal\espeak-ng | Out-Null
Copy-Item -Recurse -Force ..\..\guyun_packaging\espeak-ng\* dist\古韵机器人\_internal\espeak-ng
# 加两个 bat（启动 / 下载识别模型）后打 zip
tar.exe -a -c -f dist\古韵机器人_v4.0.0_windows_x64.zip -C dist 古韵机器人
```

要点（踩过的坑）：

- **入口必须是独立的 launcher**：`launcher_v4.py` 负责把 `_internal` 加进 `sys.path`、`chdir` 过去、
  再 `streamlit run robot/app.py`；关掉 fileWatcher，否则 frozen 模式会去 reload 源码。
- **项目代码按数据文件打包**（`datas.append((robot/, "robot"))` 这种），运行时当普通包 import，
  不要指望 PyInstaller 静态分析出 `robot.app`。
- **自定义组件目录** `components/hold_to_record/` 必须一起打进去，`robot/recorder.py` 用
  `__file__/../components` 找它，frozen 下落在 `_internal/components`，正好对得上。
- **识别模型不进包**（228MB）；随包放一个 `下载识别模型.bat` 从 hf-mirror 拉。
- **只在 frozen 下才暴露的 bug**：语音输入的"模型是否就绪"原来写死查 `models/vosk-small-cn`，
  源码环境两个模型都在所以没发现，打包版只有 SenseVoice → 误报"未安装"。已改成
  `available_backends()` 探测。
- 打包后体积约 480MB（streamlit + numpy/scipy + onnxruntime），zip 约 188MB。

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
