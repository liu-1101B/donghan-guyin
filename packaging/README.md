# 🏛️ 古韵 · 东汉洛阳官音合成器

**白话 → 古文 → 东汉音IPA标注 → 三轨音频**

将现代白话文转译为文言文，并复原其**东汉洛阳官音**（约公元1-2世纪洛阳读书音），可听、可视、可学。

## 效果预览

输入"今天天气真好，我和朋友一起去河边散步"：

- **古文翻译**: 今日天象甚佳，余与友人偕往河边徐行
- **东汉音 IPA**: krim ȵit tʰen zjaʔ dʑimʔ ɕis, ja ʔjɨʔ ɦʷəʔ dʑaŋ ɦa ben ket ...

---

## 项目结构

```
donghan-guyin/
├── guyun_app.py              # 主界面 (Streamlit)
├── phonology_db.py           # 东汉音韵数据库 (700+ 字)
├── classical_translator.py   # 白话→古文翻译引擎
├── sound_synth.py            # 双引擎合成 (eSpeak-ng + 共振峰)
├── launcher.py               # PyInstaller 打包入口
├── build.bat                 # 一键构建 EXE 脚本
├── download_espeak.py        # 下载 eSpeak-ng 辅助脚本
├── 古韵合成器.iss            # Inno Setup 安装脚本
├── icon.png                  # 应用图标
├── requirements.txt          # Python 依赖
├── start.bat                 # 开发调试启动脚本
└── BUILD_GUIDE.md            # 打包与构建完整指南
```

---

## 快速开始（开发调试）

### 方式一：双击运行

```
双击 start.bat
```

首次运行会自动安装依赖，之后浏览器打开 `http://localhost:8501`。

### 方式二：命令行

```bash
pip install -r requirements.txt
streamlit run guyun_app.py
```

---

## 构建 EXE 安装包

详见 [BUILD_GUIDE.md](BUILD_GUIDE.md)。

简要步骤：
1. `python download_espeak.py` — 下载 eSpeak-ng
2. `pip install pyinstaller` — 安装 PyInstaller
3. 双击 `build.bat` — 一键构建

产物：
- `dist\古韵合成器\` — 可直接分发的文件夹
- `古韵合成器_Setup_v2.0.exe` — 安装包（需 Inno Setup 7）

---

## 核心链路

```
白话文输入 → classical_translator (古文翻译) → phonology_db (IPA查询)
    → sound_synth (eSpeak-ng + 共振峰双引擎) → guyun_app (三轨音频流式展示)
```

---

## 三轨音频

1. **🏛️ 东汉官音** — eSpeak-ng 合成，真实东汉发音
2. **🗣️ 现代朗读** — Edge-TTS 微软语音
3. **⚙️ 机械参考** — 纯参数合成，学术参考

音韵分析表展示每个字的声母、韵母、声调、切韵对照及古今差异特征。

---

## 技术来源

- **上古韵构拟**：郑张尚芳（2003）《上古韵系》、白一平-沙加尔（2014）体系
- **中古韵对照**：《切韵》音系（`qieyun-python` 开源库）
- **音频合成**：eSpeak-ng IPA 引擎 + 共振峰参数合成回退
- **现代朗读**：Edge-TTS（微软 Azure 语音服务）

---

## 后续计划

- [ ] 更多汉字音韵数据（700+ → 2000+）
- [ ] 历代音切换（先秦、隋唐、宋代）
- [ ] AI 音色优化
- [ ] 多音字智能选音
- [ ] 字源注解
