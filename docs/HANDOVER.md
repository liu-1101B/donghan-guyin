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

**已完成**：接入**六家**中古学者拟音（Sinica 汉字构形资料库，PDM，数据已在仓库内）

| 体系 | 去重字数 | 记录 | 错位行 |
|---|---|---|---|
| `wangli_mc` 王力 | 19523 | 25508 | 13 |
| `dongtonghe_mc` 董同龢 | 19534 | 25515 | 0 |
| `zhoufagao_mc` 周法高 | 19534 | 25513 | 5 |
| `lifanggui_mc` 李方桂 | 19529 | 25507 | 0 |
| `chenxinxiong_mc` 陈新雄 | 19477 | 25409 | 0 |
| `karlgren_mc` 高本汉 | 6471 | 7673 | 0 |

- 接口：`lookup_reading(ch, system_id)`、`lookup_scholar_reading(ch, system_id)`、
  `scholar_coverage(system_id)`
- 报告：`python scripts/coverage_report.py --all`
- 契约（不要破坏）：
  - **上游没有声调字段**，`tone` 恒为 `None`，不得补全
  - 聲母 `0` 表示零声母，不是数字
  - 错位行判据是「**以元音开头**」，不能改成「含元音」——
    李方桂用 `ji-` 表示喻母，用「含元音」会误判 974 行
  - 错位行标 `source_record_defect` 且**不给 IPA**；多音字优先取非错位记录
  - 跳过数必须计数并暴露，不得静默吞掉
- 性能：整个数据包按 system 分组后只解析一次（`_bundle_rows`），
  六个体系全套测试从 36 秒降到 4.5 秒

**待做**：

1. Sinica 的上古方案（先秦各学者，56169 条）尚未接入 —— 注意上古表结构不同：
   有「韻部」字段、没有「韻母」，不能直接复用中古的加载逻辑。
2. 「同一个字六家拟音对照」的视图还没做（`融` 是现成例子）。

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
