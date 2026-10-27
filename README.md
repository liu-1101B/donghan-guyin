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

### 方式一：下载安装包（推荐）

从 Releases 下载 `古韵合成器_Setup_v3.0.0.exe`，双击安装即可。

### 方式二：双击运行（开发调试）

```
双击 start.bat
```

首次运行会自动安装依赖，之后浏览器打开 `http://localhost:8501`。

### 方式三：命令行

```bash
git clone https://github.com/liu-1101B/donghan-guyin
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

## 历史音系研究模块\n\n已新增历史时期时间轴、学者体系注册、来源追溯与离线数据查询。当前接入《广韵》音韵地位原始资料、PHONO-ML Baxter–Sagart 风格中古音转写，以及《中原音韵》多个学者方案。查询入口与数据许可说明见 [历史音韵架构](docs/HISTORICAL_PHONOLOGY_ARCHITECTURE.md)、[数据资源总表](docs/HISTORICAL_PHONOLOGY_DATA_CATALOG.md) 和 [数据来源/许可](data/historical/README.md)。这些历史转写默认不被当作 TTS 可直接使用的 IPA。\n\n## 研究边界与证据说明

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

## 历史音系探索平台（开发分支）

分支 `feat/historical-phonology-foundation` 将项目扩展为“历史时期 × 拟音体系 × 逐字读音”的可追溯研究原型。

### 当前已接入的数据

- **《广韵》音韵地位**：小韵首字、反切上下字、音韵地位原始描述；CC0-1.0。
- **PHONO-ML**：Baxter–Sagart 风格中古音转写，约 20,276 个不同汉字、26,224 组字音对应关系；CC BY 4.0，署名说明见 `data/historical/PHONO-ML_ATTRIBUTION.md`。
- **《中原音韵》**：5,877 条数据记录，按杨耐思、宁继福、薛凤生、unt 等方案分别查询；CC0-1.0。

每份快照都有来源链接、上游 Git Blob SHA、数据类型和许可信息，详见 [数据来源/许可](data/historical/README.md)、[机器可读清单](data/historical/manifest.json) 和 [数据资源总表](docs/HISTORICAL_PHONOLOGY_DATA_CATALOG.md)。

### 代码与界面

- `language/history/timeline.py`：历史时期导航范围与年份查询；允许时期重叠。
- `language/history/systems.py`：注册不同历史时期与拟音方案，区分已接入数据和仅登记元数据。
- `language/history/reconstruction.py`：统一逐字查询；未接入的数据不会被猜测或伪装成真实读音。
- `language/history/qieyun_data.py`、`phono_ml_data.py`、`zhongyuan_data.py`：三类数据的离线查询适配器。
- `language/history/provenance.py`：保存来源、版本、条目位置、推导规则与置信度。
- `guyun_app.py`：页面底部新增「历史音系探索（研究预览）」折叠面板，可按时期、方案和单字查询已接入记录。
- `tests/test_historical_phonology.py`：测试时期、数据检索、多方案标识、来源追溯及“无 IPA 不伪装成可合成”。
- `.github/workflows/historical-phonology-tests.yml`：自动运行 Python 编译检查与历史音系回归测试。

运行测试：

```bash
python -m compileall -q language/history guyun_app.py
python -m unittest discover -s tests -p "test_historical_phonology.py" -v
```

### 学术边界

《广韵》音韵地位、PHONO-ML 转写、《中原音韵》各家重构和项目旧东汉实验字表不是同一种数据。历史转写默认存放于 `Reading.transcription`，不冒充 IPA，也不承诺能直接交给 eSpeak-ng 或其他 TTS。现有 703 字东汉表仍是实验性拟音；要建立可信的东汉洛阳音方案，还需要逐条补齐证据来源、推导规则并进行学术核验。

---

## 后续扩展计划

- [ ] 更多汉字音韵数据（703 → 2000+）
- [ ] 历代音切换（先秦《诗经》音、隋唐《切韵》音、宋代《中原音韵》音）
- [ ] RVC/GPT-SoVITS AI 音色优化
- [ ] 多音字智能选音
- [ ] 字源注解
