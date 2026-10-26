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
