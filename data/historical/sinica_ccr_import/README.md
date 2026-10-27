# Central Research Institute / NTU historical Chinese phonology data

Source page: https://xiaoxue.iis.sinica.edu.tw/ccrdata/

Independent official download packages:
- https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr01_shangguyin_data_xlsx.zip
- https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr02_zhongguyin_data_xlsx.zip
- https://xiaoxue.iis.sinica.edu.tw/ccrdata/file/ccr03_yunshu_data_xlsx.zip

The official page marks the independent downloadable sound/rhyme files with PDM and distinguishes them from the online database/compilation. Original workbook, sheet, row, field names and values are preserved.

Files:
- sinica_ccr_records.jsonl.gz: one JSON object per non-empty data row.
- manifest.json: package/workbook hashes and counts.
- summary.csv: sheet headers, row counts, and inferred navigation metadata.

Inferred period/system/record_type values are only for navigation. Original values remain under fields. No IPA or single historical pronunciation is inferred from rhyme-group labels.
