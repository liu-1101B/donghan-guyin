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

已收到并检查这三个官方 ZIP。解析结果为 26 个工作簿、34 个工作表、共 378,214 条数据记录，所有源工作簿均无公式单元格；原始字段名和值作为字符串保留，没有把韵部标签推导成 IPA。分包记录数：上古音／两汉 56,169 条，中古时期 155,759 条，韵书 166,286 条。

规范化数据包已生成（压缩 JSONL 文件 SHA-256：395a7e81527e66a3a1ad5fd384f9e94f41dd03b315476ea0a8d2e08c8adae5e7；数据包 ZIP SHA-256：d49256dc9a36fdb99f4368b097472caa8a3a4b53419aaa00a285143749d7d8d8）。本开发分支已提交可复现的标准库导入脚本和带来源追溯的 SQLite 索引查询适配器；为避免声称不存在的远端文件，规范化数据载荷仍需由项目维护者放入分支，路径为 data/historical/sinica_ccr_import/sinica_ccr_records.jsonl.gz。规范化 ZIP 已在本次对话作为附件提供。

安装本次规范化包：
```bash
mkdir -p data/historical/sinica_ccr_import
unzip sinica_ccr_import_bundle.zip -d data/historical/sinica_ccr_import
```

从三个官方源 ZIP 重建：
```bash
python scripts/import_sinica_ccr.py \
  --old-chinese ccr01_shangguyin_data_xlsx.zip \
  --middle-chinese ccr02_zhongguyin_data_xlsx.zip \
  --rhyme-books ccr03_yunshu_data_xlsx.zip \
  --out-dir data/historical/sinica_ccr_import
```

数据载荷放到该目录后，Streamlit 的“中央研究院古今音资料库”面板即可查询。查询代码会在本地临时目录建立 SQLite 索引；若数据包未安装，界面会明确提示而不是返回空结果冒充数据已接入。
