# 东汉古音 v5 开发路线

> 路线提出：刘佳祺　记录：2026-10-30　适用分支：`feat/historical-phonology-foundation`
>
> 本文取代此前草稿，是 v5 的正式阶段划分。每阶段下方的「现状」均为代码盘点结论，不是规划措辞。

## 路线总览

| 阶段 | 核心方向 | 目标 |
|---|---|---|
| 第一阶段 | 历史语言体系 | 从东汉古音扩展为跨历史时期的语言系统 |
| 第二阶段 | 古音资料库 | 整合不同学者的拟音方案、音韵资料及文献来源 |
| 第三阶段 | 发音引擎 | 支持不同历史时期、学派和拟音方案切换 |
| 第四阶段 | 智能对话 | 优化现代汉语、文言文、历史语音之间的转换 |
| 第五阶段 | 机器人交互 | 完善语音交互、连续对话和多种发声模式 |
| 第六阶段 | 工程化 | 完善数据管理、配置、日志、测试和跨平台打包 |

## 阶段与现有模块的对应

| 阶段 | 现有落点 |
|---|---|
| 一 | `language/history/timeline.py`、`systems.py` |
| 二 | `language/history/{qieyun,phono_ml,zhongyuan,sinica_ccr}_data.py`、`data/historical/`、`scripts/import_sinica_ccr.py` |
| 三 | `language/ancient_tts.py`、`sound_synth.py`、`packaging/download_espeak.py` |
| 四 | `services/llm_client.py`、`language/classical_translator.py`、`language/turn_engine.py`、`language/style_prompt.py` |
| 五 | `robot/`（`app.py`、`recorder.py`、`windows_audio.py`、`audio_io.py`、`session.py`）、`components/hold_to_record/` |
| 六 | `tests/`、`.github/workflows/`、`config/settings.yaml`、`scripts/download_models.py`、`packaging/` |

---

## 第一阶段：历史语言体系

**现状（已具备）**

`timeline.py` 定义 6 个时期，允许区间重叠（语音演变是连续的）：

| id | 年份 | 标签 |
|---|---|---|
| `old_chinese` | -1200 ~ 220 | 上古汉语 |
| `eastern_han` | 25 ~ 220 | 东汉 |
| `middle_chinese` | 581 ~ 907 | 中古汉语 |
| `late_middle_chinese` | 800 ~ 1279 | 晚唐至宋 |
| `early_mandarin` | 1200 ~ 1911 | 近代汉语 |
| `modern_chinese` | 1912 ~ 2100 | 现代汉语 |

`period_at(year)` 返回覆盖该年的**所有**时期，不强行收敛为唯一结论。

**差距**

时期目前只是「导航标签 + 数据分区」，还不是「语言系统」：没有跨时期的音变规则链，
无法回答「同一句话在东汉、中古、近代分别怎么说」。`docs/HISTORICAL_PHONOLOGY_ARCHITECTURE.md`
也明确写了：选中某一年不应自动推断唯一发音。

**下一步**

先做有据可查的**音类对应**（不是音值）：以《广韵》地位为锚，建 东汉 → 中古 的声母/韵母
对应表，并标注每条的文献依据与例外。

---

## 第二阶段：古音资料库

**现状（已接入 4 套实数据，共 379 万+ 条）**

| 数据 | 条目 | 许可/来源 | 接口 |
|---|---|---|---|
| 《广韵》反切音韵地位 | 3800+ | CC0（nk2028/tshet-uinh-data，blob SHA 已记录） | `lookup_qieyun_positions` |
| PHONO-ML 中古转写（Baxter–Sagart） | 20000+ | 见 `data/historical/PHONO-ML_ATTRIBUTION.md` | `lookup_phono_ml` |
| 中原音韵（5 家拟音） | 5000+ | 见 `data/historical/README.md` | `lookup_zhongyuan` |
| 中研院汉字构形库（含东汉韵部） | 378214 | PDM（Sinica CCR） | `lookup_sinica_ccr_records` |

另有 10 个**仅登记元数据**的体系（郑张尚芳上古、白一平—沙加尔上古、高本汉/王力/郑张尚芳中古、
现代普通话等），查询返回 `not_integrated`，不编造 IPA。

**差距（关键）**

14 个注册体系里 **0 个能产出可合成 IPA** —— 逐个实测 `available` 全为 `False`：

```
guangyun_qieyun_position      source_record          available=False
phono_ml_baxter_sagart_mc     source_reconstruction  available=False
zhongyuan_*（5 个）            source_reconstruction  available=False
zhengzhang_oc / baxter_sagart_oc / karlgren_mc /
wangli_mc / zhengzhang_mc / mandarin_modern            not_integrated
```

也就是说：资料能查、能追溯来源，但没有任何一条能直接送到发音引擎。
真正的「拟音表逐字导入 + 覆盖率报告」还没做。

**下一步**

选定**一个**体系做完整闭环（建议王力或郑张尚芳中古），导入逐字拟音，产出
`覆盖字数 / 总字数 / 争议项 / 失败案例` 报告，再谈第二个体系。

---

## 第三阶段：发音引擎

**现状**

- 双引擎可用：eSpeak-ng 1.52（捆绑，`ESPEAK_DATA_PATH` 已正确设置）+ 共振峰合成回退
- 实测：`synth_with_espeak` 3 音节出 32540 采样点 / 1.48s，确认非回退
- 现代朗读走 Edge TTS，实测可用

**差距（v5 最核心的缺口）**

发音链路与数据层是**断开**的：

```python
# language/ancient_tts.py
def text_to_ipa(classical: str) -> AncientResult:
    ...
    data = lookup_char(ch)      # ← 只查 phonology_db 的 703 字东汉旧表
```

`text_to_ipa` / `synthesize_ancient` 都没有 `system_id` / `period` 参数。
界面上可以在「历史音韵查询」里选时期和体系，但**合成永远走东汉旧表**，
选的体系对声音没有任何影响。

而且即使接上，第二阶段也还没有可合成数据 —— 两个阶段互为前提。

**下一步**

1. 给 `text_to_ipa` 增加 `system_id`，改为调用 `lookup_reading(ch, system_id)`；
2. 建立「音素 → eSpeak」能力矩阵，明确哪些 IPA 能读、哪些必须回退共振峰；
3. 拟音可信度与合成器能力**分别报告**，不要混为一个分数。

---

## 第四阶段：智能对话

**现状（本轮已验证）**

- `llm_client` 双模式：API（`cloud`）/ 本地词典（`local-dictionary`），词典未命中时宁可不答也不编造
- API 模式 8/8 连续成功（修复推理模型 token 预算后）
- `make_turn` 自然/古韵两种发声都产出真实音频（MP3 35712 B / WAV 348696 B）
- 多轮历史保留最近 6 轮进上下文、8 轮进会话

**差距**

- 翻译仍以 `simple_translate` 词典级为主，长句与生僻表达质量有限
- 「现代汉语 ↔ 文言文 ↔ 历史语音」三者之间的**对照**还没串起来：
  一句话无法一次给出东汉音 / 中古音 / 现代音三个版本
- 没有多音字的词级上下文选音

**下一步**

给一句话生成多时期音频对照；翻译层在词典未命中时接 LLM；多音字按词切分选音。

---

## 第五阶段：机器人交互

**现状**

- v4 界面：按住说话、双模式、设备选择、对话历史（无头渲染 0 异常）
- 本机链路已验：录音 2s + 回放成功、11 个输出设备、2 个麦克风
- ASR：SenseVoice 逐字正确，Vosk 兜底可用

**差距**

- Jetson AGX Orin + 蓝牙音箱的真机链路**从未在此环境验证**（只有 Linux 脚本与 Windows 分支）
- 无连续对话（唤醒词 / 打断 / 抢话处理）
- 发声模式只有「自然 / 古韵」两种，未与第一阶段的时期体系联动

**下一步**

列真机回归清单（蓝牙配对、A2DP sink、音量、断连重连），再做打断与连续对话。

---

## 第六阶段：工程化

**现状**

- 测试：`tests/test_historical_phonology.py` 23 项，CI 跑 `compileall` + `unittest`（带路径过滤）
- 配置：`config/settings.yaml` + `.env`（界面可写，已入 `.gitignore`）
- 数据下载：`scripts/download_models.py` 支持 HTTP Range 续传 + 镜像轮换
- 打包：`packaging/`（v3 PyInstaller + v4 便携包）

**差距**

- **日志**是 `print`，无级别、无轮转、无结构化字段，排障靠人肉
- **测试只覆盖音韵数据层**：音频合成、TTS、ASR、LLM 全靠手工验证（本轮 11 项就是手测的）
- 依赖上限（`numpy<2`、`scipy<1.14`、`pyarrow<18`）只写在注释里，**CI 没有断言**，
  谁改了 requirements 也不会红
- 跨平台是两条互不相干的路径（Linux 脚本 vs Windows 便携包），没有统一抽象

**下一步**

1. 结构化日志（级别 + 模块前缀），替换散落的 print；
2. 把本轮的 11 项手测固化成自动化冒烟（音频、ASR、LLM 可用 mock）；
3. CI 加依赖断言：`Qieyun` 可导入、`pyarrow/numpy/scipy` 版本匹配；
4. 收口根目录与 `packaging/` 的分叉（`sound_synth.py` 已经分叉过）。

---

## 当前已交付基线（2026-10-30 实测）

| # | 功能 | 状态 |
|---|---|---|
| 1 | 白话 → 古文 | ✅ 词典模式 |
| 2 | 东汉音 IPA 标注 | ✅ 703 字库 |
| 3 | 古韵合成（历史拟音轨） | ✅ eSpeak 真实出声 |
| 4 | 现代朗读（Edge TTS） | ✅ |
| 5 | 机械参考轨 | ✅ |
| 6 | 按住说话录音 | ✅ 本机链路通 |
| 7 | 语音识别 ASR | ✅ SenseVoice + Vosk |
| 8 | 文言对谈（LLM） | ✅ API 与词典双模式 |
| 9 | 设备播放 | ✅ 5 个输出设备 |
| 10 | 多轮对话历史 | ✅ |
| 11 | 历史音韵查询 | ✅ 378214 条 |

这份基线是**现状**，不是 v5 的完成标准。v5 的完成标准是上面六个阶段都到位。

## v5 完成判据

1. 六个阶段各自的「下一步」全部落实，且每项有可复现验证。
2. 至少一个学者体系能从「查得到」走到「播得出」，并附覆盖率与争议项报告。
3. 发音引擎能按时期/体系切换，且切换结果在音频上可区分。
4. 任何降级（回退、缺失、未接入）都在界面上显式标注，不出现功能凭空消失。
5. 新机器按 README 能从零装到可用，包括模型下载与依赖上限校验。
