from __future__ import annotations
import argparse, json, re
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader
from PIL import Image, ImageOps, ImageEnhance
import numpy as np
import easyocr

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'data'/'official_sources'
OUT=ROOT/'data'/'processed'/'official_pages'
MODEL_DIR=ROOT/'data'/'models'/'easyocr'

def get_image(page):
    xobjs=page.get('/Resources',{}).get('/XObject',{})
    candidates=[]
    for _,ref in xobjs.items():
        obj=ref.get_object()
        if obj.get('/Subtype')=='/Image': candidates.append((int(obj.get('/Width',0))*int(obj.get('/Height',0)),obj))
    if not candidates: return None
    obj=max(candidates,key=lambda x:x[0])[1]
    return Image.open(BytesIO(obj.get_data())).convert('RGB')

def run_doc(reader, filename, lang, page_filter=None):
    image_file='One_Stop_Centre_SOP_Hindi_Enhanced_2x.pdf' if filename=='One_Stop_Centre_SOP_Hindi.pdf' else filename
    pdf=PdfReader(str(SRC/image_file)); outpath=OUT/f'{Path(filename).stem}.jsonl'
    old=[]
    if outpath.exists(): old=[json.loads(s) for s in outpath.read_text(encoding='utf-8').splitlines() if s.strip()]
    records={x['page']:x for x in old}
    for n,page in enumerate(pdf.pages,1):
        if page_filter and n not in page_filter: continue
        current=records.get(n,{})
        if current.get('text') and not current.get('ocr_required'): continue
        img=get_image(page)
        if img is None: continue
        img=img.resize((img.width*2,img.height*2),Image.Resampling.LANCZOS)
        img=ImageOps.autocontrast(img,cutoff=0.3)
        result=reader.readtext(np.array(img),detail=1,paragraph=False)
        text=' '.join(t[1].strip() for t in result if t[1].strip())
        conf=round(sum(float(t[2]) for t in result)/len(result),3) if result else 0.0
        records[n]={'source_file':filename,'source_title':current.get('source_title',Path(filename).stem),'page':n,'language':lang,'text':text,'ocr_required':False,'ocr_engine':'EasyOCR 1.7.2','ocr_mean_confidence':conf,'ocr_review_required':conf<0.70}
        print(f'{filename} page {n}/{len(pdf.pages)} confidence={conf} characters={len(text)}',flush=True)
    with outpath.open('w',encoding='utf-8') as f:
        for n in sorted(records): f.write(json.dumps(records[n],ensure_ascii=False)+'\n')
    return len(pdf.pages)

p=argparse.ArgumentParser(); p.add_argument('--sample-pages',type=int,nargs='*'); args=p.parse_args()
MODEL_DIR.mkdir(parents=True,exist_ok=True)
reader=easyocr.Reader(['hi','en'],gpu=False,model_storage_directory=str(MODEL_DIR),user_network_directory=str(MODEL_DIR / "user_network"),verbose=True)
flt=set(args.sample_pages) if args.sample_pages else None
run_doc(reader,'One_Stop_Centre_SOP_Hindi.pdf','Hindi',flt)



