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
- language/history/reconstruction.py：统一逐字查询；未接入体系明确返回不可用，不猜测 IPA。
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

**注意**：这一步只解决「查得到」，没有解决「播得出」。`ancient_tts.text_to_ipa()`
仍只查 703 字旧表，发音链路与数据层尚未打通。

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

## 下一步实施顺序

1. 盘点 phonology_db.py，为条目补来源/版本/推导规则，同时保留旧字段兼容。
2. 已完成第一套 CC0《广韵》音韵地位资料、六家中古学者拟音与五家上古（先秦）学者拟音接入，`scripts/coverage_report.py --all` 出 11 体系覆盖率报告。
3. 为多音字增加词级上下文选择，不以单字查表代替词汇读音。
4. 为音素到 TTS 的映射建立能力矩阵；拟音可信度与合成器能力分别报告。
5. 最后把时间轴和体系选择接入 Streamlit UI；UI 不应先于数据契约。

## 测试

在仓库根目录运行：

    python -m unittest discover -s tests -p "test_historical_phonology.py"
