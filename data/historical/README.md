# Data source and licensing

## Guangyun phonological-position table

- Upstream repository: https://github.com/nk2028/tshet-uinh-data
- Upstream file: `反切音韻地位/廣韻反切音韻地位表.csv`
- Upstream repository license: CC0 1.0 Universal (see upstream `LICENSE`)
- Upstream file Git blob SHA: `93ca1b1551b30bba9c76fe21078f156b8299d9cc`
- Local copy: `data/historical/guangyun_positions.csv`

The bundled CSV is a source-data table of 反切 and 音韻地位 descriptions. It is not an IPA transcription, not itself a single scholar's reconstruction, and not evidence that every character had only one reading. The adapter indexes each 小韻首字 and preserves multiple records in source order. The row count should be read from the actual CSV rather than assumed from the last 小韻 number.

The CC0 dedication permits reuse to the greatest extent allowed by applicable law. This project retains source attribution and a content hash for reproducibility even though CC0 does not require attribution. Check the upstream repository for future corrections and schema changes; do not silently overwrite the pinned local copy.

## PHONO-ML Middle Chinese transcriptions

- Upstream repository: https://github.com/alxdrdelaporte/PHONO-ML_database
- Upstream file: `phonoML_characters.csv`
- Dataset license: CC BY 4.0 International; attribution and license link required. See `PHONO-ML_ATTRIBUTION.md`.
- Upstream file Git blob SHA: `e371665481c70b56534a618f42f620567ae5a762`
- Local copy: `data/historical/phono_ml_characters.csv`

This is a database of Baxter–Sagart style Middle Chinese transcriptions, automatically derived from Guangyun data. The upstream project reports 26,224 character/transcription pairs and 20,276 distinct characters, and warns that some errors may remain. It is not IPA audio and does not imply that a string can be passed directly to a TTS engine. Multiple readings are preserved.

## Zhongyuan Yinyun reconstructions

- Upstream repository: https://github.com/nk2028/zhongyuan-data
- Upstream file: `中原音韻.tsv`
- License: CC0 1.0 Universal (see upstream LICENSE).
- Upstream file Git blob SHA: `74b2b30565a2ac4c47b309fe1ff804c6b438c4a9`
- Local copy: `data/historical/zhongyuan_yinyun.tsv`

The table records 小韻, character, initial/final/tone labels, and separate reconstructions attributed to Yang Naisi, Ning Jifu, Xue Fengsheng, and unt. Each scheme is exposed as a separate system ID; do not collapse the columns into one canonical pronunciation. The transcriptions are retained as source values and are not declared TTS-ready.


## Academia Sinica 古今音资料库：官方独立下载数据

官方授权页：https://xiaoxue.iis.sinica.edu.tw/ccrdata/

该页明确区分在线数据库/汇编（整体受编辑著作型态保护）与独立下载的声韵资料文件；后者采用 **Public Domain Mark (PDM)** 发布，官方说明可在法律允许范围内视为无著作权利限制的信息，无需另行向编辑者申请版权及相关权利授权。项目会保留来源和 PDM 声明。

已收到并检查这三个官方 ZIP。GitHub Actions 已重新从官方来源下载三个压缩包，并逐一验证其 SHA-256 与用户上传文件一致，随后执行规范化导入、计数断言和真实查询验证。规范化数据载荷现已提交在本分支的 `data/historical/sinica_ccr_import/sinica_ccr_records.jsonl.gz`。

解析统计：
- 26 个工作簿、34 个工作表、378,214 条非空数据记录；源工作簿均无公式单元格。
- 上古音／两汉 56,169 条；魏晋南北朝至隋唐 155,759 条；历代韵书 166,286 条。
- 每条记录保留源 URL、源工作簿、工作簿 SHA-256、工作表、原始行号、许可标记、原始字段名和值。原始字段中的韵部、反切、学者转写不会被擅自归一化成 IPA。
- 规范化 JSONL gzip SHA-256：`13208d7373477e805af9ff14a884215d9ccac7e091b4470a28ea18b8a206b0cc`（6,795,609 bytes）。
- GitHub Actions 导入日志成功验证 378,214 条记录，并查询到东汉“東”的韵部记录。

查询面板在首次查询时会于系统临时目录构建 SQLite 索引，不会改写仓库数据，也避免每次把完整数据集加载进内存。标准库导入器位于 `scripts/import_sinica_ccr.py`，用于将相同的官方 ZIP 重建为规范化数据。

如需从官方源 ZIP 重建：
```bash
python scripts/import_sinica_ccr.py \
  --old-chinese ccr01_shangguyin_data_xlsx.zip \
  --middle-chinese ccr02_zhongguyin_data_xlsx.zip \
  --rhyme-books ccr03_yunshu_data_xlsx.zip \
  --out-dir data/historical/sinica_ccr_import
```

官方 PDM 标记适用于独立下载的声韵资料文件；不要因此推断整个网站界面、程序或在线数据库汇编整体都没有著作权限制。
