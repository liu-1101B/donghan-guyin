# 打包与构建

打包的是**新版机器人界面** `robot/app.py`（v4 起）。产物是**免安装便携目录 + zip**，不需要 Inno Setup。

> 历史：v3 那套「PyInstaller + Inno Setup、打包 `guyun_app.py` 独立合成器，并把源码复制一份到
> `packaging/`」的脚本已经移除——两套代码各改各的，没人能保证它们一致。需要旧流程时从 git 历史取
> （`git show v4.0.0:packaging/build.bat` 之类）。`icon.png` 与 `ChineseSimplified.isl` 保留，
> 将来要做 Setup.exe 还用得上。

## 前置

```powershell
# 在仓库根目录
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-robot.txt
.\.venv\Scripts\python -m pip install pyinstaller
```

eSpeak-ng 的 Windows 二进制不随仓库走（23 MB），从 eSpeak-ng 官方或旧打包目录取一份，
放到 `packaging\espeak-ng\` 备用。

## 构建（四步）

```powershell
cd packaging

# 1) PyInstaller onedir
..\.venv\Scripts\python -m PyInstaller --noconfirm --clean 古韵机器人.spec

# 2) eSpeak-ng 进 _internal（sound_synth 按 __file__ 找同级的 espeak-ng/）
New-Item -ItemType Directory -Force dist\古韵机器人\_internal\espeak-ng | Out-Null
Copy-Item -Recurse -Force espeak-ng\* dist\古韵机器人\_internal\espeak-ng

# 3) 放两个 bat + 使用说明（内容见「发行包组成」）

# 4) 打 zip（用系统自带的 tar.exe，比 Compress-Archive 快得多）
tar.exe -a -c -f dist\古韵机器人_v4.0.0_windows_x64.zip -C dist 古韵机器人
```

体积参考：目录约 480 MB（streamlit + numpy/scipy + onnxruntime），zip 约 188 MB。

## 发行包组成

```
古韵机器人/
├── 古韵机器人.exe          # launcher_v4 的编译产物
├── 启动.bat                # 启动服务并自动打开浏览器
├── 下载识别模型.bat        # 从 hf-mirror 拉 SenseVoice（228 MB），首次使用必点
├── 使用说明.txt
└── _internal/              # Python、依赖、espeak-ng、界面源码、config、.streamlit
```

模型**不打进包**（体积），由 bat 下载到 `_internal\models\sense-voice\`。

## 关键点（都踩过）

- **入口必须是独立的 launcher**（`launcher_v4.py`）：它把 `_internal` 加进 `sys.path`、`chdir` 过去，
  再 `streamlit run robot/app.py`；必须关掉 fileWatcher / runOnSave —— frozen 下它会试图 reload 源码。
- **项目代码按数据文件打包**（`datas.append((robot 目录, "robot"))` 这种），运行时当普通包 import。
  别指望 PyInstaller 静态分析出 `robot.app` 的依赖。
- **自定义组件** `components/hold_to_record/` 要一起进去：`robot/recorder.py` 按
  `__file__/../components` 找它，frozen 下正好落在 `_internal/components`。
- **只在 frozen 下才现形的 bug**：语音输入原先写死查 `models/vosk-small-cn` 来判断"模型是否就绪"，
  源码环境两个模型都在所以没暴露；打包版只带 SenseVoice → 误报"未安装"。已改成 `available_backends()`。
  以后任何"按路径判断"的逻辑，都要先问：打包后这个路径还在吗？
- **验收要验打包版，不是源码**：起 exe → 打 `/_stcore/health` → 用 Playwright 驱动真实页面
  （按住说话、双模式、古韵合成出声），别只看"能打开"。

## 上传

GitHub 资产名**必须是 ASCII**（中文会被洗成下划线），上传走 `uploads.github.com`
（`github.com` 抽风时它通常还通）。发布说明见仓库根目录 `CHANGELOG.md`。
