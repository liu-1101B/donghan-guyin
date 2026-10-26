# Data source and licensing

## Guangyun phonological-position table

- Upstream repository: https://github.com/nk2028/tshet-uinh-data
- Upstream file: `反切音韻地位/廣韻反切音韻地位表.csv`
- Upstream repository license: CC0 1.0 Universal (see upstream `LICENSE`)
- Upstream file Git blob SHA: `93ca1b1551b30bba9c76fe21078f156b8299d9cc`
- Local copy: `data/historical/guangyun_positions.csv`

The bundled CSV is a source-data table of 反切 and 音韻地位 descriptions. It is not an IPA transcription, not itself a single scholar's reconstruction, and not evidence that every character had only one reading. The adapter indexes each 小韻首字 and preserves multiple records in source order. The row count should be read from the actual CSV rather than assumed from the last 小韻 number.

The CC0 dedication permits reuse to the greatest extent allowed by applicable law. This project retains source attribution and a content hash for reproducibility even though CC0 does not require attribution. Check the upstream repository for future corrections and schema changes; do not silently overwrite the pinned local copy.
