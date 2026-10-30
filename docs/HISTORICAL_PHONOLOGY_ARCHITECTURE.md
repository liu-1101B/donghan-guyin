# 历史音韵平台：第一阶段架构

## 本阶段目标

为“时代时间轴 + 学者拟音体系切换”建立可测试的基础层，不改动现有机器人语音链路，也不把尚未接入的数据伪装成可播放的历史读音。

## 三个独立概念

1. **历史时期**：时间轴导航区间。区间允许重叠，因为语音变化连续，研究分期也有差异。
2. **拟音/读音体系**：明确采用的学者、著作或标准，必须声明适用时期与版本。
3. **逐字读音记录**：某个字在某个体系中的读音及其证据、推导规则、来源、置信度。

时间轴选中某年，不应自动推断唯一发音。前端应显示“可用数据”“仅登记、未接入”或“暂无该字条”，不能用其他时代音值冒充。

## 已新增模块

- language/history/timeline.py：时期模型、年份查询、重叠时期处理。
- language/history/systems.py：拟音体系注册表，区分旧字表适配与仅登记元数据。
- language/history/reconstruction.py：统一逐字查询；未接入体系明确返回不可用，不猜测 IPA；`compare_character` 提供同字跨体系对照（值类型三分、缺失显式报缺）。
- language/history/qieyun_data.py：查询随仓库提供的《广韵》反切音韵地位表，保留同字多条小韵记录。
- data/historical/guangyun_positions.csv：来自 nk2028/tshet-uinh-data 的 CC0 1.0 数据副本；许可与上游内容 blob SHA 记录在 data/historical/README.md。
- language/history/provenance.py：来源、版本、页码/条目、推导规则、置信度等证据字段。
- tests/test_historical_phonology.py：覆盖时期、体系、缺失读音与旧数据库适配器。

模块不依赖 Streamlit、音频设备或 Jetson 专属库，可供网页、桌面和机器人共用。

## 时间轴范围约定

时期年份是产品导航范围，不是语言边界的精确断言。使用天文纪年：年份 0 表示公元前 1 年，-1 表示公元前 2 年。多个时期可以覆盖同一年。

“上古汉语”与“东汉”在此有意重叠：前者用于上古音研究入口，后者用于原项目实验字表入口；不代表两个标签是互斥且完全一致的学术分期。

## 体系注册表的学术边界

首批登记郑张尚芳、白一平—沙加尔等上古音参考体系，以及高本汉、王力、郑张尚芳等中古音参考体系。除下述原始资料入口外，这些学者体系目前仍只是元数据，尚未导入完整拟音表；查询时返回 not_integrated，不会合成虚构读音。

### 第一套已接入数据：广韵反切音韵地位表

本分支将 nk2028/tshet-uinh-data 的 `反切音韻地位/廣韻反切音韻地位表.csv` 固定副本放在 `data/historical/guangyun_positions.csv`。上游仓库标注 CC0 1.0，来源文件的 Git blob SHA 为 `93ca1b1551b30bba9c76fe21078f156b8299d9cc`。详情见 `data/historical/README.md`。

该表提供小韵首字、反切上下字及音韵地位描述。它是可追溯的中古音韵资料，不是 IPA、不是单一学者的拟音，也不应被直接送入 TTS。接口 `lookup_qieyun_positions(character)` 会保留同一字对应的所有小韵记录；通用 `lookup_reading(character, "guangyun_qieyun_position")` 返回首条记录并在备注中提示多条记录。结果使用 `source_status="source_record"`，并通过 `has_record` 与 `available` 区分“存在资料记录”和“有可合成 IPA”。

东汉旧字表继续以 han_eastern_experimental 暴露，但结果标记为 legacy_experimental，来源置信度为 unassessed。下一步需逐条核验来源、著作版本、推导链和争议。

### 东汉 → 中古 音类对应表（第一阶段收尾）

`language/history/eastern_mc_correspondence.py` 把东汉旧字表（703 字）锚定到上表的
3707 个首字（OpenCC `s2t` 对齐），产出两张**观测对应表**（不是音变规律）：

- 解析器 `parse_position_description`：`声母[开合][等|重纽AB]韵调` → 六字段，
  开合/等/重纽各自至多一次、可为空（表内确有 `端開登入` 这类无等描述，1425 条）。
  3872 条记录 0 漏网，并与 Qieyun 规范位置集逐字段对账（测试项，Qieyun 缺失时跳过）。
- 声母对应：30 个东汉母 → 中古 38 声母（初母仅 1 字且无锚定，不在表内）；
  韵母对应：东汉韵部 → 中古 58 韵，合计 526 条（字, 中古位置）对（部分锚定字有多条反切）。
- 每对附字表作为文字依据；`n < 3` 的对标 `is_exception`（如 见母→見51/匣1、
  透母→昌5/透4/徹1、阳韵→陽17/唐13/庚8）。
- 覆盖缺口如实暴露：703 字中 **493 有锚点、210 无**（人/今/他 在表中只作反切字，
  使 完全缺席），`unanchored_characters()` 可查，报告不回填。
- **锚点空间粒度 38 声母 / 58 韵 / 4 调**：CC0 表与 Qieyun 规范位置集在此粒度上
  完全一致，属上游数据粒度特性，不等于《广韵》传统 106 韵分法，任何文档与报告
  不得声称“覆盖 58/106 韵”。
- 报告：`scripts/correspondence_report.py`（默认完整中文报告；`--char 东` 单字锚点；
  `--json` 概要）。来源（CC0 + blob SHA）与三条局限（无锚点字、legacy 实验端、
  观测非规律）全部显式打印。

## 第二套已接入数据：六家中古学者拟音（Sinica 汉字构形资料库）

`language/history/sinica_scholar_data.py` 接入「隋唐_擬音_*.xlsx」六份
（已随仓库打包于 `data/historical/sinica_ccr_import/`，许可 PDM）。

| 体系 id | 学者 | 去重字数 | 记录 | 错位行 |
|---|---|---|---|---|
| `wangli_mc` | 王力 | 19523 | 25508 | 13 |
| `dongtonghe_mc` | 董同龢 | 19534 | 25515 | 0 |
| `zhoufagao_mc` | 周法高 | 19534 | 25513 | 5 |
| `lifanggui_mc` | 李方桂 | 19529 | 25507 | 0 |
| `chenxinxiong_mc` | 陈新雄 | 19477 | 25409 | 0 |
| `karlgren_mc` | 高本汉 | 6471 | 7673 | 0 |

同一个「融」六家给出 `jǐuŋ / juŋ / iuŋ / jiung / ǐoŋ / i̯uŋ`，
可直接用作「各体系不可混用」的示例。

接口：`lookup_reading(ch, system_id)`、`lookup_scholar_reading(ch, system_id)`、
`scholar_coverage(system_id)`；报告：`python scripts/coverage_report.py --all`。

### 接入时遇到的三个坑

1. **上游无聲調字段**：`tone` 恒为 `None`，本项目不推测、不补全。
2. **聲母 `0` 表示零声母**，不是数字；拼 IPA 时按无辅音处理。
3. **错位行的判据必须是「以元音开头」，不能是「含元音」**：
   李方桂方案用 `ji-` 表示喻母（如「融」= `ji` + `ung`），含元音却是合法声母，
   用「含元音」会误判该体系 974 行；而王力 13 行、周法高 5 行确实把韵母值
   填进了聲母列（`u` / `ɑ` / `əu` / `o` / `ǐɐn`），以元音开头，能被准确抓到。

错位行标记 `source_record_defect` 且不生成 IPA；多音字优先取非错位记录。

（「查得到 → 播得出」的打通见下文「第三阶段：发音引擎」。）

## 第三套已接入数据：五家上古（先秦）学者拟音（Sinica 汉字构形资料库）

同一模块 `language/history/sinica_scholar_data.py` 按 `dataset_id` 分发，
另接入「先秦」五表（001 高本漢—005 李方桂，56169 行，
与中古共用同一个 `sinica_ccr_records.jsonl.gz` 包，许可 PDM）。
006/007「兩漢」表不是逐字拟音，不接入。

| 体系 id | 学者 | 去重字数 | 记录 | 缺陷行 | 空韻母 | 韻部数 |
|---|---|---|---|---|---|---|
| `karlgren_oc` | 高本漢 | 5912 | 6992 | 8 | 535 | —（无韻部栏） |
| `wangli_oc` | 王力 | 6329 | 6961 | 8 | 3 | 30 |
| `dongtonghe_oc` | 董同龢 | 8948 | 11120 | 0 | 3 | 23 |
| `zhoufagao_oc` | 周法高 | 10219 | 12849 | 0 | 13 | 31 |
| `lifanggui_oc` | 李方桂 | 9001 | 11160 | 0 | 6 | 23 |

先秦表多一列「韻部」（001 表无此栏，接口报缺）；`Reading.rhyme_group` 与
`ScholarReading.upstream_note`（李方桂 96 行備註）逐字保留，不做语义加工。

### 机械修复与缺陷处理

- 零声母：王力 `0`（374 行）、李方桂「·」（U+0387，465 行）；点后可带介音
  （`·w`，153 行）。拼 IPA 按无辅音处理，介音保留（如「委」= `wjər`）。
- 上游 HTML 实体 `&#609`/`&#611`（高本漢、董同龢各 2 行）机械解码为 ȡ/ȣ，
  原值写入 note；王力全角 `ｐ` 还原为 `p`；**不做全局 NFKC**
  （李方桂中古表 `ńź` 是 n+U+0301+z 的分解序列，全局归一会破坏它）。
- 缺陷行 8+8+0+0+0 保留、`suspect=True`、IPA 置空并计数，不静默删除。
- 高本漢 535 行空韻母（530 空 + 5「?」）全部计数；查无该字报
  `missing_character`（如「融」「中」在其先秦表缺席）。

## 同字跨体系对照与 UI 覆盖表

`compare_character(character, period_id)` 返回 `CharacterComparison`：按时期注册表
顺序，每个体系一行 `SystemComparisonRow`（值 / 值类型 / 韻部 / 状态 / 上游備註 / 说明）。

- 值类型三分，不混用：`ipa`（学者拟音 IPA 与东汉实验字表）、`transcription`
  （PHONO-ML 与《中原音韵》转写，不是 IPA）、`position`（《广韵》反切音韵地位，不是 IPA）。
- 缺失、缺陷、未接入的体系保留为空值行并带显式 `source_status`
  （`missing_character` / `source_record_defect` / `not_integrated` 等），不用别家值补。
- 多音字：所有记录的读值并排保留；界面把重复值折叠显示为 `v ×n`，不丢条数。
- 参数契约：非单字字符抛 `ValueError`，未知时期抛 `KeyError`（复用 `get_period`）。

UI（`guyun_app.py`）「🔀 同字跨体系对照（争议项）」展开器：选时期 + 字符（默认 `融`），
输出对照表与差异摘要（是否一致、不同值个数、无记录体系名单），并附所选时期各体系的
覆盖表（字数 / 记录 / 缺陷行 / 空韻母 / 韻部数 / 備註行 / 零声母行；非逐字拟音数据集
以「—」占位并说明）。

测试：`CompareCharacterTests`（6 项）锁定上述契约，含高本漢先秦表「融」缺席、中古六家
六值不可折叠、东汉实验字表行存在、未知字全体系报缺。

## 第三阶段：发音引擎（text_to_ipa 路由 → 能力矩阵 → 双列 UI）

分三步完成，每步独立提交：

### ① `text_to_ipa(system_id=...)` 路由（`language/ancient_tts.py`）

- `text_to_ipa(classical, system_id=None)` 与 `synthesize_ancient(..., system_id=...)`
  接受体系 id；`_resolve_synthesis_system` 把选择解析为 `"legacy"`（东汉实验字表旧路径，
  行为与旧版逐字一致，`AncientResult.system_id` 保持 `None`）或学者体系 id。
- `han_eastern_experimental` 显式解析回 legacy 路径（与 703 字旧表等价）。
- 学者路径**永不回退现代拼音**：体系内缺字/源表缺陷行一律计 `unknown`（不伪造该体系读音）；
  非逐字 IPA 体系（反切地位 / PHONO-ML / 中原音韵转写 / 未接入）抛 `ValueError` 并说明原因，
  不静默换体系。
- `AncientResult.characters` 新增逐字明细：`(字, IPA 或 None, "covered"/"approx"/"unknown")`，
  五个分支（legacy 收录 / legacy 拼音近似 / legacy 失败 / 学者收录 / 学者缺字）全部填充，
  是 UI 双列展示的数据侧来源。

### ② IPA→合成器能力矩阵（`language/phoneme_capability.py`）

- `assess_ipa(ipa) -> IpAssessment`：把 IPA 串切成音段 token，逐 token 给出
  eSpeak 级（`full` 能读 / `approx` 能读但重音音色丢失 / `partial` 部分能读 /
  `untested` 未实测 / `silent` 实测被静默丢弃）与共振峰级（备用引擎口径）；
  汇总出 `espeak_level`、`dropped_tokens`（被丢弃音段）、`approx_tokens`。
- eSpeak 逐字丢弃是**实测行为**（`-v zh` 对未知字符按字符丢弃，不是整串失败），
  所以「partial」语义 = 该音节在音频里缺段，界面上逐字标出丢了哪些音段。
- 「能读出来」≠「音值正确」：`approx` 级符号（如 `â ă ï û ü í ǐ ǎ ĕ` 等重音变体）
  有声音但语言学特征丢失，必须显式标近似，不当成 full。
- `SILENT_FROZEN` / `APPROX_FROZEN` 是冻结集合，变更须附实测证据；
  `karlgren_mc` / `dongtonghe_mc` 的 `anomalous_chars` 是**数据质量标记**
  （上游含 ASCII 杂符），不是引擎能力问题。
- `preprocess_ipa` 重构：eSpeak 发送前的归一化以本模块的符号表为唯一事实来源，
  `sound_synth` 单向依赖本模块（`phoneme_capability` 不 import `sound_synth`）。
- `system_capability_report(system_id)`：整体系扫描（字数 / 各档位 / dropped 音段频次），
  报告数字被测试冻结（如 lifanggui_oc 11160 行全 full、9001 字干净；
  wangli_mc dropped ȶ 720 / ȡ 486 / ɽ 406 等）。

### ③ 重建可信度 × 合成能力双列 UI（`guyun_app.py`）

- 「拟音体系」selectbox 提供 12 个选项：默认（None = 东汉实验字表）+ 11 家学者体系。
- 选学者体系走 `process_input_scholar` → 7 元组
  `(classical, valid_ipa, audio_dh, mod, audio_mec, rows, scholar_info)`；
  选默认走旧 `process_input`（`scholar_info` 为 None），旧展示逻辑不受影响。
- `scholar_info` 契约：`{system_id, system_name, rows, level_counts, coverage, unknown}`；
  `rows` 每行 `{char, ipa, status, cap}`——**status 是数据侧**（收录 / 拼音近似 /
  缺字（不补拼音）），**cap 是引擎侧**（能读 / 近似 / 部分能读（丢 X）/ 未实测 / 静默），
  两列永不合并成一个分数。
- 界面：逐字对照表（15 行/页，`scholar_prev`/`scholar_next` 翻页）+
  「合成能力汇总」行（`level_counts` 按档计数）+ 覆盖率 caption
  （收录 N 字 / 缺字 M 个，注明不补拼音）。
- 音频卡片与下载文件名随体系动态化（`guyun_<system_id>_v<ver>.wav`）。

## 下一步实施顺序

1. 盘点 phonology_db.py，为条目补来源/版本/推导规则，同时保留旧字段兼容。
2. 已完成：第一套 CC0《广韵》音韵地位资料、六家中古学者拟音与五家上古（先秦）学者拟音接入，
   `scripts/coverage_report.py --all` 出 11 体系覆盖率报告；同字跨体系对照视图与 UI 覆盖表已接入（`compare_character`）。
3. 为多音字增加词级上下文选择，不以单字查表代替词汇读音。
4. 已完成：音素→TTS 能力矩阵（`phoneme_capability`），拟音可信度与合成器能力双列分报（③）。
5. 已完成：「拟音表 → 发音」先于 UI 接入（① 路由 + ② 矩阵），UI 只消费数据契约，不先于契约。

## 测试

在**工作树**（`donghan-guyin/.wt-feat-phon/`）内运行 `run_feat_tests.py`
（它把沙箱拒绝的 `0o700` mkdir 重映射为 `0o707`；原生 `python -m unittest`
会有 5 项假失败，仓库根的 `run_tests_sandbox.py` 也不要在该工作树 CWD 下运行）：

    $py run_feat_tests.py        # 107 项，全部通过

UI 冒烟（无头 Streamlit AppTest，确认脚本树无异常、拟音体系 selectbox 存在）：

    $py scripts/smoke_app.py     # 见交接说明的环境变量约定
