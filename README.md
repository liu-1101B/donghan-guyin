# 🏛️ 古韵 · 东汉洛阳官音合成器

**白话 → 古文 → 东汉音IPA标注 → 三轨音频**

将现代白话文转译为文言文，并复原其**东汉洛阳官音**（约公元1-2世纪洛阳读书音），可听、可视、可学。

---

## 效果预览

| 输入白话 | 输出古文 | 东汉音 IPA |
|---|---|---|
| 今天天气真好，我和朋友一起去河边散步 | 今日天象甚佳，余与友人偕往河边徐行 | krim ȵit tʰen ... lja ɦaŋ |

---

## 快速开始

### 方式一：下载安装包（推荐）

从 Releases 下载 `古韵合成器_Setup_v3.0.0.exe`，双击安装即可。

### 方式二：双击运行（开发调试）

```
双击 start.bat
```

首次运行会自动安装依赖，之后浏览器打开 `http://localhost:8501`。

### 方式三：命令行

```bash
git clone https://github.com/2750527986liu-maker/donghan-guyin
cd donghan-guyin
pip install -r requirements.txt
streamlit run guyun_app.py
```

---

## 项目文件说明

| 文件 | 功能 |
|---|---|
| `guyun_app.py` | 主界面（Streamlit） |
| `phonology_db.py` | 东汉音韵数据库（**703字**） |
| `classical_translator.py` | 白话→古文翻译引擎 |
| `sound_synth.py` | 双引擎音频合成（eSpeak-ng + 共振峰） |
| `db_expander.py` | 数据库扩充工具（API 导入 + 谐声推导） |
| `yindian_importer.py` | 从 yindian-manus 项目导入音韵数据 |
| `test_expander.py` | 扩充工具测试脚本 |
| `requirements.txt` | Python 依赖清单 |
| `start.bat` | Windows 一键启动脚本 |
| `packaging/` | PyInstaller + Inno Setup 打包构建 |

---

## 三轨音频

1. **🏛️ 东汉官音** — eSpeak-ng 合成（真实 IPA 语音引擎），回退共振峰参数合成
2. **🗣️ 现代朗读** — Edge-TTS 微软语音
3. **⚙️ 机械参考** — 纯参数合成，学术用

音韵分析表展示每个字的声母、韵母、声调、切韵对照及古今差异特征（全浊声母、闭唇 -m、入声塞尾、疑母 ng- 等）。

---

## 技术来源

- **上古韵构拟**：郑张尚芳（2003）《上古韵系》、白一平-沙加尔（2014）体系
- **中古韵对照**：《切韵》音系（`qieyun-python` 开源库）
- **音频合成**：eSpeak-ng IPA 引擎 + 共振峰参数合成（纯 Python，无需 GPU）
- **现代朗读**：Edge-TTS（微软 Azure 语音服务）
- **音典 API**：nk2028 音典数据库

---

## 打包为 EXE

详见 [packaging/BUILD_GUIDE.md](packaging/BUILD_GUIDE.md)。

```bash
cd packaging
pip install pyinstaller
python download_espeak.py
build.bat
```

产物：`dist/古韵合成器/` 文件夹 + Inno Setup 安装包。

---

## 后续扩展计划

- [ ] 更多汉字音韵数据（703 → 2000+）
- [ ] 历代音切换（先秦《诗经》音、隋唐《切韵》音、宋代《中原音韵》音）
- [ ] RVC/GPT-SoVITS AI 音色优化
- [ ] 多音字智能选音
- [ ] 字源注解
