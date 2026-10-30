# 交接说明（给下一个会话／模型）

> 更新时间：2026-10-30　分支：`feat/historical-phonology-foundation`

新会话接手时，先读这一页，再读 [`docs/v5-goal.md`](v5-goal.md)（六阶段路线与逐阶段差距）。

## 一、仓库位置与分支

- 仓库根：`donghan-guyin/`，当前根目录检出的是 **`main`**
- 本分支的工作树：**`donghan-guyin/.wt-feat-phon/`** ← 所有开发都在这里
- 分支：`feat/historical-phonology-foundation`
- 状态：**领先 `origin` 71 个提交，全部本地未推送**（没有推送凭据）
- 工作区：干净，仅一个非本会话遗留的未跟踪文件 `run_feat_tests.py`

## 二、运行环境（照抄即可）

```powershell
$py = "C:\Users\HP\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
$ws = "C:\Users\HP\Documents\deepseek-harness\default-workspace"
$env:PYTHONPATH = "$ws\.libs_pyarrow17;$ws\.libs_guyun"
$env:PYTHONUTF8 = "1"; $env:PYTHONIOENCODING = "utf-8"
```

依赖装在 `.libs_guyun`，`pyarrow 17` 单独叠在 `.libs_pyarrow17`（必须优先）。

### 四个必须知道的坑

1. **依赖上限互相咬合，别动**
   `numpy<2` + `scipy<1.14`（Qieyun 需要）与 `pyarrow<18`（否则 pyarrow 要求 numpy≥2）。
   三者钉在 `requirements.txt`，改动前先读那里的注释。
2. **跑测试要用 `run_tests_sandbox.py`**
   原生 `python -m unittest` 会有 5 项假失败 —— 沙箱拒绝写入 `tempfile.mkdtemp()`
   创建的 `0o700` 目录。该脚本把 `0o700` 重映射为 `0o707`。
3. **Streamlit 必须带 `--global.developmentMode=false`**
   因为依赖是 `pip --target` 装的，`__file__` 不含 `site-packages`，会被误判成开发模式，
   然后报 `server.port does not work when global.developmentMode is true`。
4. **git 已设 `http.sslBackend=openssl`**
   本机 schannel 后端是坏的（`SEC_E_NO_CREDENTIALS`），openssl 正常。该设置已写入仓库本地配置。
   pip 一律走 `pip_safe.py`。

## 三、v5 路线与当前进度

路线（详见 v5-goal.md）：**一 历史语言体系 → 二 古音资料库 → 三 发音引擎 → 四 智能对话 → 五 机器人交互 → 六 工程化**

用户已定：**先 B（第二阶段）再 A（第三阶段），C 不急**。

### 第二阶段（进行中）

**已完成**：接入第一个学者体系 —— 王力中古（`wangli_mc`）

- 数据源已在仓库内：`data/historical/sinica_ccr_import/sinica_ccr_records.jsonl.gz`
  （Sinica 漢字構形資料庫，PDM）
- 25521 条匹配 → 25508 条加载 → **19523 个去重字**、4772 个多音字
- 接口：`lookup_reading(ch, "wangli_mc")`、`lookup_scholar_reading(ch, "wangli_mc")`、
  `scholar_coverage("wangli_mc")`
- 覆盖率报告：`python scripts/coverage_report.py`
- 契约（不要破坏）：
  - **上游没有声调字段**，`tone` 恒为 `None`，不得补全
  - 聲母 `0` 表示零声母，不是数字
  - 13 行源表错位（聲母列填了韵母值，如「弩」=`u`）→ 标记
    `source_record_defect` 且**不给 IPA**；多音字优先取非错位记录
  - 跳过数必须计数并暴露，不得静默吞掉

**待做**：

1. 接入第二个体系。同一数据包里还有：董同龢、周法高、李方桂、陳新雄、高本漢（中古）。
   做法：`language/history/sinica_scholar_data.py` 的 `SCHOLAR_SYSTEMS` 加一行
   （模块里已记 `AVAILABLE_BUT_UNREGISTERED`），同时在 `systems.py` 登记，
   并给 `reconstruction.py` 的 scholar 分支补测试。
2. 覆盖率与「可合成」之间的缺口仍在。

### 第三阶段（下一步，未开始）

**核心缺口**：`language/ancient_tts.py` 的 `text_to_ipa()` **没有 `system_id` 参数**，
只查 `phonology_db` 的 703 字旧表。也就是说：界面上选任何体系，发音永远是东汉旧表。

要做：

1. `text_to_ipa(classical, system_id=...)` → 改走 `lookup_reading(ch, system_id)`
2. 建「音素 → eSpeak」能力矩阵：哪些 IPA 能读、哪些必须回退共振峰
   （`ȶ` `ȡ` `ɽ` `ǐ` 这类符号是重点风险）
3. 拟音可信度与合成器能力**分别报告**，不要混成一个分数

## 四、已验证可用的能力（2026-10-30 实测）

| 能力 | 状态 |
|---|---|
| 白话→古文（词典） | ✅ |
| 东汉音 IPA（703 字） | ✅ |
| 古韵合成 eSpeak | ✅ 32540 采样点 / 1.48s |
| Edge TTS 现代朗读 | ✅ MP3 |
| 录音 + 回放 | ✅ selftest True |
| 语音识别 | ✅ SenseVoice 逐字正确；Vosk 兜底可用 |
| 文言对谈 API | ✅ 8/8 成功（推理模型 token 已修） |
| 设备播放 | ✅ 5 个输出设备 |

模型已下好在 `.wt-feat-phon/models/`（sense-voice 229 MB、vosk-small-cn 65 MB），
`models/` 与 `espeak-ng/` 都被 gitignore，换机器要重跑
`python scripts/download_models.py`（支持断点续传）。

## 五、最近的工作节奏

- 每完成一块就单独提交，提交信息写清「为什么」而非「改了什么」
- 涉及数据时，宁可报「缺」也不编造（这是本项目的既有契约）
- 文档与代码要同步改：`docs/v5-goal.md` 的状态表、`docs/HISTORICAL_PHONOLOGY_ARCHITECTURE.md`
