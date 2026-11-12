from __future__ import annotations
import csv, json, re
from datetime import date
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "official_sources"
OUT_DIR = ROOT / "data" / "processed" / "official_pages"
MANIFEST = ROOT / "data" / "official_sources" / "source_manifest.csv"
TODAY = date.today().isoformat()

# Keep the untouched original scans as source of truth. The enhanced Hindi PDF is a display aid.
DOCS = {
    "Mission_Shakti_Guidelines_2021-22_to_2025-26.pdf": {
        "title": "Mission Shakti Scheme Implementation Guidelines",
        "language": "English",
        "source_type": "official guideline",
        "scope_status": "historical; stated cycle ended 2025-26",
    },
    "One_Stop_Centre_SOP_English.pdf": {
        "title": "Standard Operating Procedures for One Stop Centres",
        "language": "English",
        "source_type": "official SOP",
        "scope_status": "core source; verify effective date and current status",
    },
    "One_Stop_Centre_SOP_Hindi.pdf": {
        "title": "Standard Operating Procedure for One Stop Centre",
        "language": "Hindi",
        "source_type": "official SOP scan",
        "scope_status": "core source; scanned; OCR needed",
    },
    "Women_Helpline_181_SOP_English.pdf": {
        "title": "Women Helpline 181 Standard Operating Procedures",
        "language": "English",
        "source_type": "official SOP",
        "scope_status": "core source; verify effective date and current status",
    },
    "OSC_State_Nodal_Officer_Directory.pdf": {
        "title": "One Stop Centre State Nodal Officer Directory",
        "language": "English",
        "source_type": "official public directory",
        "scope_status": "contact metadata; verify current before display",
    },
}

rows=[]
for filename, meta in DOCS.items():
    path=SOURCE_DIR / filename
    if not path.exists():
        rows.append({"filename":filename,**meta,"downloaded_date":"","pages":"","text_pages":"","status":"MISSING"})
        continue
    reader=PdfReader(str(path))
    text_pages=0
    jsonl=OUT_DIR / f"{path.stem}.jsonl"
    with jsonl.open("w",encoding="utf-8") as out:
        for page_num,page in enumerate(reader.pages,1):
            raw=page.extract_text() or ""
            text=re.sub(r"\s+"," ",raw).strip()
            if len(text)>40: text_pages+=1
            record={"source_file":filename,"source_title":meta["title"],"page":page_num,"language":meta["language"],"text":text,"ocr_required":len(text)<40}
            out.write(json.dumps(record,ensure_ascii=False)+"\n")
    status="TEXT_EXTRACTED" if text_pages==len(reader.pages) else ("PARTIAL_OCR_REQUIRED" if text_pages else "OCR_REQUIRED")
    rows.append({"filename":filename,**meta,"downloaded_date":TODAY,"pages":len(reader.pages),"text_pages":text_pages,"status":status})

with MANIFEST.open("w",newline="",encoding="utf-8-sig") as f:
    fields=["filename","title","language","source_type","scope_status","downloaded_date","pages","text_pages","status"]
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
print(json.dumps(rows,ensure_ascii=False,indent=2))
print("\nPage-level outputs:",OUT_DIR)
print("Manifest:",MANIFEST)
