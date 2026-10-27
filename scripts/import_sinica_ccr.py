#!/usr/bin/env python3
"""Convert official Academia Sinica / NTU historical-phonology ZIPs to JSONL.gz.

Uses only the standard library. The original column labels and cell values are
preserved; inferred period/system/type fields are navigation metadata only.
"""
from __future__ import annotations
import argparse, csv, gzip, hashlib, io, json, re, zipfile
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

NS = {"m":"http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r":"http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
LANDING = "https://xiaoxue.iis.sinica.edu.tw/ccrdata/"
PACKAGES = {
 "sinica_ccr_old_chinese": {"url":LANDING+"file/ccr01_shangguyin_data_xlsx.zip","scope":"上古音／两汉"},
 "sinica_ccr_middle_chinese":{"url":LANDING+"file/ccr02_zhongguyin_data_xlsx.zip","scope":"魏晋南北朝至隋唐"},
 "sinica_ccr_rhyme_books":{"url":LANDING+"file/ccr03_yunshu_data_xlsx.zip","scope":"历代韵书"},
}
def sha256_file(path: Path) -> str:
 h=hashlib.sha256()
 with path.open("rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
 return h.hexdigest()
def col_index(ref: str) -> int:
 m=re.match(r"([A-Z]+)",ref)
 if not m:return 0
 n=0
 for c in m.group(1): n=n*26+ord(c)-64
 return n-1
def iter_sheets(data: bytes):
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  wb=ET.fromstring(z.read("xl/workbook.xml"))
  rels=ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
  targets={x.attrib["Id"]:x.attrib["Target"] for x in rels}
  shared=[]
  if "xl/sharedStrings.xml" in z.namelist():
   ss=ET.fromstring(z.read("xl/sharedStrings.xml"))
   shared=["".join(t.text or "" for t in si.findall(".//m:t",NS)) for si in ss.findall("m:si",NS)]
  for sh in wb.findall("m:sheets/m:sheet",NS):
   target=targets[sh.attrib["{"+NS["r"]+"}id"]]
   path=target if target.startswith("xl/") else "xl/"+target
   root=ET.fromstring(z.read(str(PurePosixPath(path))))
   sd=root.find("m:sheetData",NS)
   if sd is None: continue
   rows=[]
   for row in sd.findall("m:row",NS):
    rn=int(row.attrib.get("r","0")); vals={}
    for cell in row.findall("m:c",NS):
     ci=col_index(cell.attrib.get("r","A1")); typ=cell.attrib.get("t"); v=cell.find("m:v",NS)
     if typ=="s" and v is not None:
      try: val=shared[int(v.text)]
      except (ValueError,IndexError,TypeError): val=""
     elif typ=="inlineStr": val="".join(t.text or "" for t in cell.findall(".//m:t",NS))
     elif v is not None: val=v.text or ""
     else: val="".join(t.text or "" for t in cell.findall(".//m:t",NS))
     vals[ci]=str(val)
    if vals and any(v.strip() for v in vals.values()): rows.append((rn,vals))
   if not rows: continue
   hrow, hcells=rows[0]
   maxcol=max(max(hcells),*(max(v) for _,v in rows[1:]),0)
   headers=[(hcells.get(i,"") or "").strip() or f"column_{i+1}" for i in range(maxcol+1)]
   yield sh.attrib["name"],headers,rows[1:]
def infer(package_id, workbook, sheet):
 period=""; system=workbook.rsplit(".",1)[0]; kind="source_record"
 if package_id=="sinica_ccr_old_chinese":
  if "先秦" in workbook: period="先秦"; system=workbook.split("先秦_",1)[-1].rsplit(".",1)[0]; kind="scholar_reconstruction"
  elif "西漢" in workbook: period="西汉"; system="韵部资料"; kind="historical_rhyme_group"
  elif "東漢" in workbook: period="东汉"; system="韵部资料"; kind="historical_rhyme_group"
 elif package_id=="sinica_ccr_middle_chinese":
  period=next((p for token,p in [("魏","魏"),("晉","晋"),("南北朝","南北朝"),("隋唐","隋唐")] if token in workbook),"")
  if "_擬音_" in workbook: system=workbook.split("_擬音_",1)[-1].rsplit(".",1)[0]; kind="scholar_reconstruction"
  else: system="时代韵部资料"; kind="historical_rhyme_group"
 else:
  period="韵书资料"; system=workbook.split("_",1)[-1].rsplit(".",1)[0]; kind="rhyme_book_entry"
  if "又音" in sheet: kind="pronunciation_variant"
  elif "又切" in sheet: kind="fanqie_variant"
  elif "校勘" in sheet: kind="collation_note"
  elif "擬音" in sheet: kind="scholar_reconstruction"
 return period,system,kind
def convert(package_id, archive_path, gz_out, summary):
 meta=PACKAGES[package_id]
 pkg={"id":package_id,"archive_name":archive_path.name,"archive_sha256":sha256_file(archive_path),
      "source_url":meta["url"],"scope":meta["scope"],"license_mark":"PDM","workbooks":[]}
 total=0
 with zipfile.ZipFile(archive_path) as archive:
  for wn in archive.namelist():
   if not wn.lower().endswith(".xlsx"): continue
   wbbytes=archive.read(wn); wbsha=hashlib.sha256(wbbytes).hexdigest()
   wbinfo={"name":wn,"sha256":wbsha,"sheets":[]}
   for sn,headers,rows in iter_sheets(wbbytes):
    period,system,kind=infer(package_id,wn,sn); n=0; nochar=0
    for rn,cells in rows:
     fields={h:str(cells.get(i,"") or "") for i,h in enumerate(headers)}
     if not any(v.strip() for v in fields.values()): continue
     char=(fields.get("字") or fields.get("字頭") or fields.get("字頭字") or "").strip()
     if not char:nochar+=1
     record={"dataset_id":package_id,"source_url":meta["url"],"source_landing_page":LANDING,
      "license_mark":"PDM","period":period,"system":system,"record_type":kind,
      "source_workbook":wn,"source_workbook_sha256":wbsha,"source_sheet":sn,"source_row":rn,
      "character":char,"fields":fields}
     gz_out.write((json.dumps(record,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8"))
     n+=1;total+=1
    wbinfo["sheets"].append({"name":sn,"headers":headers,"data_rows":n,"rows_with_no_character":nochar})
    summary.append({"package_id":package_id,"workbook":wn,"sheet":sn,"period":period,"system":system,
     "record_type":kind,"data_rows":n,"headers":" | ".join(headers),"source_url":meta["url"],"source_workbook_sha256":wbsha})
   pkg["workbooks"].append(wbinfo)
 pkg["workbook_count"]=len(pkg["workbooks"]);pkg["data_row_count"]=total
 return pkg
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument("--old-chinese",required=True,type=Path);p.add_argument("--middle-chinese",required=True,type=Path)
 p.add_argument("--rhyme-books",required=True,type=Path);p.add_argument("--out-dir",type=Path,default=Path("data/historical/sinica_ccr_import"))
 a=p.parse_args()
 inputs={"sinica_ccr_old_chinese":a.old_chinese,"sinica_ccr_middle_chinese":a.middle_chinese,"sinica_ccr_rhyme_books":a.rhyme_books}
 for f in inputs.values():
  if not f.is_file():p.error(f"archive not found: {f}")
 a.out_dir.mkdir(parents=True,exist_ok=True)
 records=a.out_dir/"sinica_ccr_records.jsonl.gz"; summaries=[]
 manifest={"schema_version":1,"source_title":"台湾中央研究院／台大汉字古今音资料库官方独立下载声韵资料",
  "source_landing_page":LANDING,"license_mark":"PDM",
  "license_note":"官方网页对独立下载声韵文件标示 PDM，并将其与在线数据库汇编整体区分。",
  "normalization_note":"原始字段和值以字符串保留；period/system/record_type 是基于文件名的导航元数据。",
  "dataset_file":records.name,"packages":[]}
 with records.open("wb") as raw, gzip.GzipFile(fileobj=raw,mode="wb",compresslevel=9,mtime=0) as gz:
  for pid,path in inputs.items(): manifest["packages"].append(convert(pid,path,gz,summaries))
 manifest["total_workbooks"]=sum(x["workbook_count"] for x in manifest["packages"])
 manifest["total_sheets"]=sum(len(w["sheets"]) for x in manifest["packages"] for w in x["workbooks"])
 manifest["total_records"]=sum(x["data_row_count"] for x in manifest["packages"])
 manifest["normalized_file_sha256"]=sha256_file(records);manifest["normalized_file_size_bytes"]=records.stat().st_size
 (a.out_dir/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 with (a.out_dir/"summary.csv").open("w",encoding="utf-8-sig",newline="") as f:
  writer=csv.DictWriter(f,fieldnames=list(summaries[0]));writer.writeheader();writer.writerows(summaries)
 readme=f"""# Central Research Institute / NTU historical Chinese phonology data

Source page: {LANDING}

Independent official download packages:
- {PACKAGES['sinica_ccr_old_chinese']['url']}
- {PACKAGES['sinica_ccr_middle_chinese']['url']}
- {PACKAGES['sinica_ccr_rhyme_books']['url']}

The official page marks the independent downloadable sound/rhyme files with PDM and distinguishes them from the online database/compilation. Original workbook, sheet, row, field names and values are preserved.

Files:
- sinica_ccr_records.jsonl.gz: one JSON object per non-empty data row.
- manifest.json: package/workbook hashes and counts.
- summary.csv: sheet headers, row counts, and inferred navigation metadata.

Inferred period/system/record_type values are only for navigation. Original values remain under fields. No IPA or single historical pronunciation is inferred from rhyme-group labels.
"""
 (a.out_dir/"README.md").write_text(readme,encoding="utf-8")
 print(json.dumps({"out_dir":str(a.out_dir),"records":manifest["total_records"],"workbooks":manifest["total_workbooks"],
  "sheets":manifest["total_sheets"],"file_size":records.stat().st_size,"sha256":manifest["normalized_file_sha256"],
  "packages":[{"id":x["id"],"workbooks":x["workbook_count"],"records":x["data_row_count"]} for x in manifest["packages"]]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
