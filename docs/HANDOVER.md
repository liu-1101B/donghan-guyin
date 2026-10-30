# 交接说明（给下一个会话／模型）

> 更新时间：2026-10-30　分支：`feat/historical-phonology-foundation`

新会话接手时，先读这一页，再读 [`docs/v5-goal.md`](v5-goal.md)（六阶段路线与逐阶段差距）
和 [`docs/HISTORICAL_PHONOLOGY_ARCHITECTURE.md`](HISTORICAL_PHONOLOGY_ARCHITECTURE.md)（数据与引擎架构）。

## 一、仓库位置与分支

- 仓库根：`donghan-guyin/`，当前根目录检出的是 **`main`**
- 本分支的工作树：**`donghan-guyin/.wt-feat-phon/`** ← 所有开发都在这里
- 分支：`feat/historical-phonology-foundation`
- 状态：**领先 `origin` 81 个提交，全部本地未推送**（没有推送凭据，**不要推送**）
- 工作区约定：`run_feat_tests.py`（工作树根，未跟踪，测试运行器，**保留**）

## 二、运行环境（照抄即可）

```powershell
$py = "C:\Users\HP\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$ws = "C:\Users\HP\Documents\deepseek-harness\default-workspace"
$env:PYTHONPATH = "$ws\.libs_guyun2;$ws\.libs_pyarrow17;$ws\.libs_guyun"
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
```

三个目录，顺序重要（**`.libs_guyun2` 必须最先**）：

| 目录 | 内容 | 说明 |
|---|---|---|
| `.libs_guyun2` | numpy 2.5.4、scipy 1.18.1 | 2026-10-30 重建的数值栈（原因见坑 1） |
| `.libs_pyarrow17` | pyarrow 17.0.0 | 仅测试约定用；app 本身用 `.libs_guyun` 里的 pyarrow 26 |
| `.libs_guyun` | 其余全部：streamlit 1.66.1、pandas 3.1.0、pyarrow 26.0.0、pypinyin、edge_tts、gTTS、qieyun、vosk、sherpa_onnx、altair、networkx 2.5.1（已打补丁）等 | 主依赖栈 |

依赖安装一律走 `pip_safe.py`（沙箱 0o700 问题），缓存 `--cache-dir .pip_cache`。

### 必须知道的坑（2026-10-30 环境重建后）

1. **numpy 必须 ≥2，`requirements.txt` 里旧的上限注释已作废**
   streamlit 的传递依赖 pandas 3.1.0 硬性要求 numpy ≥ 2.0.2；旧文档钉的
   `numpy<2 + scipy<1.14 + pyarrow<18` 组合与 pandas 3.1.0 不兼容，`st.dataframe`
   直接 ImportError。现行为：numpy 2.5.4 + scipy 1.18.1（在 `.libs_guyun2`）+
   pyarrow 26.0.0（在 `.libs_guyun`），`requirements.txt` 已同步更新。
2. **qieyun 依赖 networkx 2.5.1 的 `np.float_`，numpy 2.0 已移除该别名**
   修复方式：`.libs_guyun\networkx\readwrite\graphml.py` 与 `gexf.py` 各 1 处
   `np.float_` → `np.float64`（语义等价）。**重装 networkx 或换 numpy 时要重新检查
   「切韵对照」能否导入**（`from Qieyun import 字頭2音韻地位_出處們`）。
3. **`.libs_guyun` 里有 `numpy_stale_126` / `scipy_stale_113` / `*.libs_stale` 残留目录**
   旧的 numpy 1.26.4 / scipy 1.13.1 的 `.pyd` 文件被某种 OS 层保护**无法删除也无法写入**
   （icacls 显示用户有 F、无 Deny ACE、无进程占用；`os.remove`/`Remove-Item`/写打开
   全部 Access Denied，但**目录重命名可以**——已改名为 `*_stale*` 移出导入路径）。
   它们是死重量，`import numpy/scipy` 永远解析到 `.libs_guyun2`，不要试图再删，
   也不要让 `.libs_guyun` 排在 `.libs_guyun2` 前面。
4. **跑测试要用工作树根的 `run_feat_tests.py`**（现跑 `test_historical_phonology.py`
   + `test_llm_provider.py`，132 项全绿；robot 冒烟 `tests/test_robot_app_smoke.py`
   不在其中，要单独跑）
   原生 `python -m unittest` 会有 5 项假失败——沙箱拒绝写入 `tempfile.mkdtemp()`
   创建的 `0o700` 目录，该脚本把 `0o700` 重映射为 `0o707`。
   仓库根的 `run_tests_sandbox.py` **不要**在工作树 CWD 下运行。
   UI 冒烟：`$py scripts/smoke_app.py`（无头 AppTest，检查脚本树无异常 + 拟音体系 selectbox）。
5. **Streamlit 必须带 `--global.developmentMode=false`**
   因为依赖是 `pip --target` 装的，`__file__` 不含 `site-packages`，会被误判成开发模式，
   然后报 `server.port does not work when global.developmentMode is true`。
6. **git 已设 `http.sslBackend=openssl`**
   本机 schannel 后端是坏的（`SEC_E_NO_CREDENTIALS`），openssl 正常。已写入仓库本地配置。

### 其它环境备忘

- 沙箱 pwsh 以 Low Mandatory Level 运行；`whoami`/`tasklist` 走 python 子进程会被拒，
  进程扫描用 `Get-CimInstance Win32_Process`。`.ps1` 脚本在此环境会撞执行策略 /
  PS5.1 解析问题——**用直接一行命令**。
- 工作树文件带旧会话的 label grant（`S-1-4-225216295-…`），当前会话的 grant 只覆盖
  工作区根与部分目录；跨目录写文件若遇 Access Denied，优先换写法（如 pwsh 直写）而非重试。
- 上游数据文件里可能含**分解形式 Unicode**（如 n+U+0301），源码里需要时用显式
  `\uXXXX` 转义且**必须从运行时 `ord()` 实测值抄写**，禁止手拼；不做全局 NFKC。

## 三、v5 路线与当前进度

路线（详见 v5-goal.md）：**一 历史语言体系 → 二 古音资料库 → 三 发音引擎 → 四 智能对话 → 五 机器人交互 → 六 工程化**

用户已定：**先 B（第二阶段）再 A（第三阶段），C 不急**。

### 第二阶段 ✅ 已完成（提交 `5809b41`、`63e146a` 等）

- 接入 Sinica CCR **11 家学者拟音**（中古 6 + 上古 5，PDM，数据包在仓库内），
  加《广韵》反切音韵地位（CC0）、PHONO-ML、中原音韵，共 14 个注册体系。
- 接口：`lookup_reading`、`lookup_scholar_reading`、`scholar_coverage`、
  `compare_character`（同字跨体系对照，值类型三分 ipa/transcription/position）；
  报告 `python scripts/coverage_report.py --all`。
- UI：「🔀 同字跨体系对照（争议项）」展开器 + 各体系覆盖表。
- 数据契约（**不要破坏**）：上游无声调字段 `tone` 恒 `None` 不补全；声母 `0` = 零声母；
  错位行判据「以元音开头」不能改「含元音」（李方桂 `ji-` 喻母会误判 974 行）；
  错位行 `source_record_defect` 且不给 IPA；跳过数必须计数并暴露。

### 第三阶段 ✅ 已完成（三步独立提交 + 本提交）

1. **`text_to_ipa(system_id=...)` 路由**（`4c3c783`）：11 家学者体系可送发音引擎；
   `han_eastern_experimental` ≡ legacy 旧路径；非 IPA 体系抛 `ValueError`；
   学者路径缺字计 unknown，**不补现代拼音**。
2. **IPA→eSpeak 能力矩阵**（`0af9c9f`）：`language/phoneme_capability.py`
   `assess_ipa` / `system_capability_report` / `preprocess_ipa` 重构；
   能读 ≠ 音值正确；eSpeak 逐字丢弃是实测行为；报告数字被测试冻结。
3. **重建可信度 × 合成能力双列 UI**（本提交）：`guyun_app.py`「拟音体系」selectbox
   （默认 + 11 家）；`process_input_scholar` 7 元组；逐字对照表数据侧/引擎侧分列，
   `AncientResult.characters` 逐字明细；合成能力汇总 + 覆盖率 caption；
   音频卡片/下载名随体系动态化。

测试：`run_feat_tests.py` 107 项全绿；
`scripts/smoke_app.py` AppTest 冒烟通过（6 个 selectbox，含「拟音体系」）。

### 第一阶段收尾 ✅ 已完成（东汉→中古音类对应表，单提交）

- 新模块 `language/history/eastern_mc_correspondence.py`：
  - `parse_position_description`：`声母[开合][等|重纽AB]韵调` → 六字段（单遍右起，
    每字段至多一次）；3872 条 0 漏网，与 Qieyun 规范位置集逐字段对账 3872/3872。
  - 锚点：703 字（`EASTERN_HAN_DB`，`s2t` 对齐）中 **493 有锚点 / 210 无**
    （`unanchored_characters()` 可查，不回填；人/今/他 只作反切字、使 缺席）。
  - `initial_correspondence()`：30 东汉母→中古声母（初母 1 字无锚定，不在表内）；
    `final_correspondence()`：东汉韵部→中古韵名；合计 **526 条（字,中古位置）对**，
    每对附字表作文字依据，`n<3` 标 `is_exception`。
  - 钉住的散点示例：见母→見51/匣1、匣母→匣24/云13/影2、透母→昌5/透4/徹1、
    阳韵→陽17/唐13/庚8、鱼韵(上)→魚11/麻6/模5/虞2、钟韵→鍾12（1:1）。
- **锚点空间 38 声母 / 58 韵 / 4 调**：CC0 表与 Qieyun 规范集同粒度（双向 missing=[]），
  属上游数据粒度，**不是**《广韵》106 韵分法——文档与报告一律不声称 106 覆盖。
- 报告 CLI：`scripts/correspondence_report.py`（默认完整报告 / `--char` 单字 / `--json`），
  来源（CC0 + blob SHA）与三条局限全部显式打印。
- 性质：对应表是**锚定交集上的观测共现**（非音变规律），模块 docstring 与报告标题均写明。
- 测试：`EasternMcCorrespondenceTests` 21 项（解析器 6 + 覆盖/钉数 11 + 单字查询 2 +
  来源报告 2 + Qieyun 对账 1，Qieyun 缺时跳过）。

### 第四阶段 ① ✅ 已完成（一句话三时期音频对照，单提交）

- 新模块 `language/era_audio.py`：`EraAudio`（key/label/data/kind/status/note/ipa/
  coverage_pct/approx/unknown）+ `make_era_comparison(sentence, middle_system="wangli_mc", ...)`
  → (东汉, 中古, 现代) 三段**各自独立合成**；状态诚实（`ok`/`text_empty`/
  `synth_empty`/`tts_unavailable`），绝不伪造音频；未知 `middle_system` 显式抛 `KeyError`。
- `robot/app.py` `_gen_worker`：三段音频 → **四段**（新增 `reply_mc`，默认王力体系，
  `synthesize_ancient(system_id=...)`）；payload `audios` 新增 `system`/`system_label`/
  `ipa`/`coverage`/`unknown`；`_PHASE_LABEL`/`_PROGRESS` 同步。
- 结果面板新增「三时期对照 · 同一回答」三列（东汉 / 中古 / 现代）：各带独立播放 +
  下载；古韵两列显示 IPA + 覆盖% + 缺字；现代汉语断网显示诚实说明；
  无应答轮次也渲染该节（显示词典未命中说明，不生成对照）。
- 现代汉语段只做真 Edge TTS，断网则该段为空并说明——**不做本地共振峰兜底**（项目契约）。
- 测试：`EraComparisonTests` 3 项（同句「天子」东汉 tʰen vs 王力中古 tʰien、
  现代双分支、text_empty、未知体系 KeyError）+ `WorkerFourAudioTests` 2 项
  （四段 payload / 无应答诚实为空，LLM/TTS/声卡全打桩）；
  `run_feat_tests.py` 110 项全绿，robot app 冒烟 3 项全绿。

### 第四阶段 ② ✅ 已完成（词典未命中接 LLM 翻译，单提交）

- `services/llm_client.py`：
  - `dict_miss_chars(text)`：字级词典覆盖——按出现顺序、去重，返回不出现在
    任何 `TRANSLATION_DICT` key 里的 CJK 字（字级近似，只用于如实标注与触发
    回退，不用于回填）。
  - `_call_translate(...)`：只翻译的调用（`build_translate_prompt` 纯文言输出），
    与 `_call_chat` 同 `trust_env`/超时策略；输出为空或被截断就抛异常，
    绝不把残缺 JSON 当翻译返回。
  - `generate_turn(..., allow_llm_translate=False)` + `_local_fallback(...)`：
    返回新增 `translation_source`（`dictionary` | `llm`）、`missed_chars`、
    `dict_translation`（LLM 补译时保留词典原结果）。
  - **契约**：LLM 只补「翻译」一层，`reply`/`reply_modern` 恒为空——
    「宁可不答不编造」不因 LLM 参与而放宽；开关默认关（opt-in）、
    仅词典模式生效、无密钥/LLM 失败时静默回退词典翻译并如实标注；
    api 模式失败回退时不向同一端点发起第二次 LLM 调用。
  - 顺带修旧 bug：`_call_chat` 非截断失败（断网/401/超时）没有 `break`，
    会加大 max_tokens 无意义地重试一次（旧测试 `assert_called_once` 即被
    违反，此前该测试不在 runner 里所以没暴露）。
- `language/turn_engine.py`：`make_turn(..., allow_llm_translate=False)` 透传，
  `Turn` 新增 `translation_source`。
- `robot/app.py`：对话模式区新增复选框「词典未命中时允许 LLM 辅助翻译」
  （默认 = 是否已有密钥；无密钥时提示不可用）；payload 新增
  `translation_source`/`missed_chars`；元信息行「· 翻译 LLM」；
  翻译行尾「（LLM 补译 · 词典缺 N 字：…）」。
- 旧钉住的 `test_dictionary_miss_returns_no_fabricated_reply` **原样未动**
  （默认关 ⇒ 行为不变）。
- 测试：`run_feat_tests.py` 改为跑两个文件（`test_historical_phonology.py`
  110 + `test_llm_provider.py` 22 = **132 项全绿**）；新增
  `DictMissCharTests` 3 项（`量子计算`→`[量,子,计,算]`、`今天天气真好`→`[]`、
  顺序去重、非 CJK 忽略）+ `DictMissLLMTranslateTests` 7 项（开关/无密钥/
  失败回退/预设应答命中不走 LLM/api 标注/api 失败不二次调用）+
  `DictTranslateCallTests` 2 项（prompt 形态 + 局域网 trust_env、截断抛错）+
  `TurnEngineTranslationSourceTests` 1 项；robot app 冒烟 3 项全绿
  （worker 桩加 `allow_llm_translate` 形参，并断言新 payload 字段）；
  `scripts/smoke_app.py` 6 个 selectbox 正常。

### 下一阶段（第四阶段余下，用户已定顺序）

- ✅ ① 一句话多时期音频对照（东汉 / 中古 / 现代同句三版）——已完成；
- ✅ ② 翻译层词典未命中时接 LLM（宁可不答不编造，标注 dict vs LLM）——已完成；
- ③ 多音字按词切分选音；
- Jetson 真机链路回归清单（见 v5-goal.md 第五阶段）。

## 四、已验证可用的能力（2026-10-30 实测）

| 能力 | 状态 |
|---|---|
| 白话→古文（词典，缺字如实标注） | ✅ `dict_miss_chars` 字级覆盖 |
| 词典未命中 LLM 补译（opt-in，标注来源） | ✅ `allow_llm_translate`，回答恒不编造 |
| 东汉音 IPA（703 字，legacy 路径） | ✅ |
| 11 家学者拟音逐字合成 | ✅ eSpeak 出声，双列对照 UI |
| 东汉→中古音类对应表 | ✅ 493/703 锚定，526 对，30 母/58 韵粒度，`scripts/correspondence_report.py` |
| 古韵合成 eSpeak | ✅ 32540 采样点 / 1.48s |
| Edge TTS 现代朗读 | ✅ MP3 |
| 三时期音频对照（东汉 / 中古王力 / 现代） | ✅ `language/era_audio.py`，robot 面板三列 |
| 切韵对照（Qieyun） | ✅（依赖坑 2 的 networkx 补丁） |
| 录音 + 回放 | ✅ selftest True |
| 语音识别 | ✅ SenseVoice 逐字正确；Vosk 兜底可用 |
| 文言对谈 API | ✅ 8/8 成功（推理模型 token 已修） |
| 设备播放 | ✅ 5 个输出设备 |

模型已下好在 `.wt-feat-phon/models/`（sense-voice 229 MB、vosk-small-cn 65 MB），
`models/` 与 `espeak-ng/` 都被 gitignore，换机器要重跑
`python scripts/download_models.py`（支持断点续传）。

## 五、工作节奏约定

- 每完成一块就单独提交，提交信息写清「为什么」而非「改了什么」
- 涉及数据时，宁可报「缺」也不编造（这是本项目的既有契约）
- 文档与代码要同步改：`docs/v5-goal.md` 的状态表、`docs/HISTORICAL_PHONOLOGY_ARCHITECTURE.md`
- **不要推送**（无凭据）；不要动 `main` 检出的根工作树
