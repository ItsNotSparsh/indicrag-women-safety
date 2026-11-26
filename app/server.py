"""Run with the project interpreter: python app/server.py"""
import io
import json
import wave
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from urllib.parse import urlsplit
import numpy as np
from service import HERE, ROOT, CENTRES, GUIDES, LANGS, directory, respond

AUDIO_LOCK = Lock()
PORT = 8765


@lru_cache(maxsize=1)
def recognizer(lang):
    from transformers import pipeline
    folder = ROOT / "data/models" / ("whisper-hindi-small" if lang in {"hi","mix"} else "whisper-base")
    return pipeline("automatic-speech-recognition",model=str(folder),device="cpu")


@lru_cache(maxsize=1)
def speaker(code):
    from transformers import AutoTokenizer,VitsModel
    folder=ROOT/"data/models"/("tts-"+code)
    return AutoTokenizer.from_pretrained(folder),VitsModel.from_pretrained(folder).eval()


def speech(text,lang):
    import re
    import torch
    code={"hi":"hin","ta":"tam","mix":"eng","en":"eng"}[lang]
    tok,model=speaker(code)
    samples=[]
    for sentence in re.split(r"(?<=[.!?।])\s+|\n+",text):
        if not sentence.strip(): continue
        # Spell emergency numbers as digits, since MMS vocabularies omit numerals.
        digits={"hin":"शून्य एक दो तीन चार पाँच छह सात आठ नौ","tam":"பூஜ்யம் ஒன்று இரண்டு மூன்று நான்கு ஐந்து ஆறு ஏழு எட்டு ஒன்பது","eng":"zero one two three four five six seven eight nine"}[code].split()
        sentence=re.sub(r"[0-9]+",lambda m:" "+" ".join(digits[int(c)] for c in m[0])+" ",sentence)
        inputs=tok(sentence,return_tensors="pt")
        if inputs.input_ids.shape[-1]<3: continue
        with torch.inference_mode(): samples.append(model(**inputs).waveform.squeeze().numpy().reshape(-1))
        samples.append(np.zeros(1600))
    if not samples: raise ValueError("Empty speech")
    output=io.BytesIO()
    with wave.open(output,"wb") as w:
        w.setparams((1,2,model.config.sampling_rate,0,"NONE",""))
        w.writeframes((np.clip(np.concatenate(samples),-1,1)*32767).astype("<i2").tobytes())
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass

    def send_data(self,value,kind="application/json",status=200):
        data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        for k,v in {"Content-Type":kind,"Content-Length":str(len(data)),"Cache-Control":"no-store","Referrer-Policy":"no-referrer","X-Content-Type-Options":"nosniff","Content-Security-Policy":"default-src 'self'; media-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"}.items():self.send_header(k,v)
        self.end_headers()
        self.wfile.write(data)

    def allowed(self):
        return self.headers.get("Host","") in {f"localhost:{PORT}",f"127.0.0.1:{PORT}"} and self.headers.get("Sec-Fetch-Site","")!="cross-site"

    def do_GET(self):
        if not self.allowed():return self.send_data({},status=403)
        path=urlsplit(self.path).path
        if path=="/config":
            places={}
            for s,d,_ in CENTRES: places.setdefault(s,set()).add(d)
            places.setdefault("Tamil Nadu",set()).update(["Virudhunagar","Chennai"])
            return self.send_data(dict(locations={s:sorted(v) for s,v in places.items()},guides=[{"id":c["id"],"title":c["title"]} for c in GUIDES]))
        files={"/":("index.html","text/html; charset=utf-8"),"/app.js":("app.js","text/javascript; charset=utf-8"),"/app.css":("app.css","text/css")}
        if path in files:
            name,kind=files[path]
            return self.send_data((HERE/name).read_bytes(),kind)
        for filename in ("One_Stop_Centre_SOP_English.pdf","Women_Helpline_181_SOP_English.pdf"):
            p=ROOT/"data/official_sources"/filename
            if path=="/source/"+filename and p.exists():return self.send_data(p.read_bytes(),"application/pdf")
        self.send_data({},status=404)

    def do_POST(self):
        if not self.allowed() or self.headers.get("Origin",f"http://{self.headers['Host']}")!=f"http://{self.headers['Host']}":
            return self.send_data({},status=403)
        try:
            size=int(self.headers.get("Content-Length",0))
            if not 0<size<=1920000:return self.send_data({},status=413)
            raw=self.rfile.read(size)
            if self.path.startswith("/listen/"):
                lang=self.path.split("/")[-1]
                if lang not in LANGS or size%2 or size<3200: raise ValueError()
                pcm=np.frombuffer(raw,dtype="<i2").astype("float32")/32768
                if np.abs(pcm).max()<0.003:return self.send_data({"text":""})
                with AUDIO_LOCK:
                    kwargs = {} if lang in {"hi","mix"} else {"language":{"en":"english","ta":"tamil"}[lang],"task":"transcribe"}
                    result=recognizer(lang)(pcm,generate_kwargs=kwargs)
                return self.send_data({"text":result["text"].strip()})
            params=json.loads(raw)
            lang=params.get("language","en")
            if lang not in LANGS:raise ValueError()
            if self.path=="/directory":return self.send_data(directory(params.get("state",""),params.get("district",""),lang))
            if self.path=="/ask":
                q=params.get("question","").strip()
                if not 0<len(q)<=1200:raise ValueError()
                return self.send_data(respond(q,lang,params.get("state",""),params.get("guide")))
            if self.path=="/speak":
                t=params["text"].strip()
                if not 0<len(t)<=2400:raise ValueError()
                with AUDIO_LOCK: data=speech(t,lang)
                return self.send_data(data,"audio/wav")
            self.send_data({},status=404)
        except (ValueError,KeyError,StopIteration,TypeError,AttributeError):
            self.send_data({"error":"Invalid request."},status=400)
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception as exc:
            print("Service error:",type(exc).__name__,flush=True)
            self.send_data({"error":"Component unavailable. Check the local installation."},status=503)


if __name__=="__main__":
    print(f"Open http://127.0.0.1:{PORT}",flush=True)
    ThreadingHTTPServer(("127.0.0.1",PORT),Handler).serve_forever()


