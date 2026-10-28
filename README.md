# 🏛️ 古韵 · 东汉洛阳官音合成器

**白话 → 古文 → 东汉音IPA标注 → 三轨音频**

将现代白话文转译为文言文，并尝试生成**东汉洛阳官音的实验性拟音**（目标年代约为公元1—2世纪），可听、可视、可学。该结果属于研究原型输出，不应被理解为已获学界共识验证的唯一历史读音。

---

## 效果预览

| 输入白话 | 输出古文 | 实验性拟音示例 |
|---|---|---|
| 今天天气真好，我和朋友一起去河边散步 | 今日天象甚佳，余与友人偕往河边徐行 | krim ȵit tʰen ... lja ɦaŋ |

---

## 快速开始

### 方式一：独立合成器安装包（旧版界面）

从 Releases 下载 `古韵合成器_Setup_v3.0.0.exe`，双击安装即可。这个安装包运行的是独立合成器界面；若要使用 Linux/Jetson 机器人版的新版界面，请在 Windows 上运行下面的 `start.bat`。

### 方式二：Windows 运行机器人新版界面（推荐）

双击仓库根目录的 `start.bat`。它会创建独立的 `.venv`、安装 `requirements-robot.txt`，然后启动 `robot/app.py`（机器人新版界面）。首次启动会询问是否下载约 44 MB 的 Vosk 中文识别模型；不下载时，文字输入与语音合成仍可使用，录音转文字暂不可用。

也可以在命令行执行：

```bat
start.bat
```

浏览器地址通常是 `http://localhost:8501`。若端口被占用，请使用 Streamlit 终端输出的实际地址。

### 没有本地大模型的设备怎么办？

机器人不要求每台设备都安装大模型。Windows/普通 Linux 设备可以直接调用云端 OpenAI 兼容 API；也可以连接同一局域网内另一台 Linux 主机提供的模型服务。

1. 复制配置模板：在 Windows 终端运行 `copy .env.example .env`，然后用文本编辑器打开 `.env`。
2. 选择后端：
   - `LLM_PROVIDER=cloud`：直接使用云端服务，不尝试本机模型。
   - `LLM_PROVIDER=local`：只调用 `LOCAL_LLM_BASE`，它可以是局域网服务器地址，并非必须是本机。
   - `LLM_PROVIDER=auto`：先试模型服务，再试已配置的云端 API，最后使用本地规则。
   - `LLM_PROVIDER=rules`：不请求任何大模型，仅使用内置词典和规则回答。
3. 云端模式需要填写服务商提供的 API 根地址、模型名和密钥，例如：

```dotenv
LLM_PROVIDER=cloud
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=在这里填写你自己的密钥
```

上面只是配置格式示例；实际使用时请以你选择的模型服务商给出的 API 地址和模型名称为准。不要把真实密钥写进代码或提交到 Git。

若希望模型仍由自己的 Linux 服务器运行，可将 `LLM_PROVIDER` 设为 `local`，并把 `LOCAL_LLM_BASE` 指向该服务器的 OpenAI 兼容接口，例如 `http://192.168.1.20:8080/v1`；可按服务要求配置 `LOCAL_LLM_MODEL` 和 `LOCAL_LLM_API_KEY`。服务器需允许客户端所在网络访问，并正确设置防火墙。不要把未经鉴权的模型端口直接暴露到公网。

**隐私与降级：** 云端模式会把用户输入和用于上下文的近期对话发送给所配置的服务商；需按数据敏感程度选择。若没有本地模型、没有配置云端密钥，或网络调用失败，程序仍可运行，但会降级为固定规则回复，不能提供完整的大模型对话能力。

### 方式三：Windows 运行独立合成器旧界面

双击 `start_synthesizer.bat`，启动根目录的 `guyun_app.py`。它与机器人新版界面是两个不同入口。

### 方式四：Linux / Jetson 运行机器人界面

```bash
git clone https://github.com/liu-1101B/donghan-guyin
cd donghan-guyin
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-robot.txt
streamlit run robot/app.py
```

Windows 机器人界面的麦克风/扬声器通过 `sounddevice` 访问系统音频设备；Linux/Jetson 继续使用现有的 PipeWire/ALSA 音频链路。

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

1. **🏛️ 历史拟音实验输出** — 通过 eSpeak-ng 输入 IPA，再以共振峰参数合成回退；音频是现代引擎合成，不是东汉语音的真实录音
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

## 研究边界与证据说明

本项目是面向演示、探索与教学的实验性原型，**不声称已经完成经过同行评审的“东汉洛阳官音”定论式复原**。

README 所列技术来源包括上古音构拟体系、中古《切韵》对照、外部音典数据以及现代语音合成器。这些来源可以提供研究线索，但单靠把它们组合起来，不能自动证明每个字的音值就是公元 1—2 世纪洛阳读书音。尤其需要区分：

- 历史音韵资料中的原始记录与后世构拟；
- 本项目采用的声母、韵母、韵尾和声调推导规则；
- 缺少直接证据时采用的类推、近似和回退策略；
- 现代 TTS/共振峰合成对 IPA 的实现，与历史语音本身的差别。

当前版本的数据条目应被视为该项目采用的实验方案。若用于学术引用或历史语言学研究，请逐字核对来源、拟音依据和争议，不应仅引用本项目的播放结果作为历史读音证据。

后续提升可复核性的建议：

1. 为每个音韵条目记录来源、重构体系、适用时期、推导规则及置信度。
2. 将上古音、中古音和目标汉代拟音分层保存，避免把不同时期的标签直接混用。
3. 用公开参考字表和明确判分标准建立测试集；同时报告覆盖率、争议项和失败案例。
4. 将 packaging/ 下为打包做过的变体明确记录其相对根目录版本的差异，并在构建前进行自动一致性检查。

### 根目录与 packaging 目录

packaging/ 中包含为桌面打包准备的应用代码副本。这些文件与根目录同名文件并不完全相同，可能包含打包路径或运行方式相关改动；修改根目录源文件后，不应假定安装包会自动包含该修改。发布前请核对两套代码的差异，并记录哪些差异是有意保留的。

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
