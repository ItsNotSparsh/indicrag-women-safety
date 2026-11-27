"""Local rights and support service. Requests and recordings are never written to disk."""
import json
import re
import sys
from pathlib import Path
from threading import Lock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "scripts"))
GUIDES = json.loads((HERE/"guides.json").read_text(encoding="utf-8-sig"))
CENTRES = [json.loads(line) for line in (HERE/"centres.jsonl").read_text(encoding="utf-8-sig").splitlines()]
OSC_URL = "https://spniwcd.wcd.gov.in/uploads/pdf/1719920005_9NAs3KlT9d%20%282%29.pdf"
NALSA = "https://nalsa.gov.in/"
LANGS = ("en","hi","mix","ta")
EMERGENCY = re.compile(r"\b(bachao|bachaao|save me|following me|being followed|following us|attacking me|hitting me|immediate danger|in danger|someone is chasing|threatening me|maar raha|maar rahe|p(?:i|ee)chh?a{1,2}\s+k(?:a)?r\s+r(?:a)?h[aei]|unsafe right now|help me now|being attacked|locked me in)\b|बचाओ|पीछा कर रह|मार रह|जान को खतरा|खतरे में|காப்பாற்று|துரத்துகிற|பின்தொடர்கிற|ஆபத்தில்|தாக்குகிற|kaapathunga",re.I)
LOCK = Lock()
NO_ANSWER = dict(zip(LANGS, [
    "The sources here do not settle that question. A legal aid clinic can discuss your circumstances.",
    "यहाँ उपलब्ध स्रोतों से इस सवाल का स्पष्ट जवाब नहीं मिलता। विधिक सहायता केंद्र से अपने मामले पर बात कर सकती हैं।",
    "Available sources mein iska clear jawab nahi mila. Legal aid clinic se apne case par baat kar sakti hain.",
    "இங்குள்ள ஆதாரங்களில் தெளிவான பதில் கிடைக்கவில்லை. சட்ட உதவி மையத்தை அணுகலாம்."]))


def urgent(q):
    return bool(EMERGENCY.search(q) or q.strip(" !?.।").lower() in {"help","sos","madad","मदद","உதவி","help me","मुझे मदद चाहिए","mujhe bachao","எனக்கு உடனடி உதவி வேண்டும்"})


def links(state):
    items = [("Emergency · 112","112","https://www.mha.gov.in/emergency-response-support-system-erss")]
    if state.casefold() != "west bengal":
        items.append(("Women Helpline · 181 (except West Bengal)","181","https://www.wcd.gov.in/women/help"))
    items.append(("Financial cyber fraud · 1930","1930","https://www.india.gov.in/directory/helpline"))
    return items


def directory(state, district, language):
    def entry(name,place,url,phone="",languages=""):
        return dict(name=name,place=place,url=url,phone=phone,languages=languages)
    result = [entry(n,"India",u,p) for n,p,u in links(state)]
    if state.casefold()=="uttar pradesh":
        result.append(entry("Women Power Line","Uttar Pradesh","https://uppolice.gov.in/article/hi/women-power-line","1090"))
    if state.casefold()=="tamil nadu" and district.casefold() in {"","virudhunagar"}:
        result.append(entry("All Women Police Station","Rajapalayam, Virudhunagar · local number 224352","https://www.tnurbantree.tn.gov.in/rajapalayam/important-contacts/"))
    result.append(entry("PCVC · Dhwani","National NGO hotline · appointments in Chennai","https://pcvconline.org/our-programs/","18001027282","English, Tamil, Malayalam, Telugu, Kannada, Hindi"))
    if state:
        result.extend(entry("One Stop Centre",d+" · "+a,OSC_URL) for s,d,a in CENTRES
                      if s.casefold()==state.casefold() and (not district or d.casefold()==district.casefold()))
    preferred = {"hi":"Hindi","mix":"Hindi","ta":"Tamil","en":"English"}.get(language,"English")
    for r in result:
        r["language_confirmed"] = preferred in r["languages"].split(", ")
    return result


def card_result(card,lang):
    return dict(kind="guide",label=card.get("label",card["title"]),answer=card.get(lang,card["en"]),
                language=lang if lang in card else "en",speech_text=card["hi"] if lang=="mix" else card.get(lang,card["en"]),source=card["title"],url=card["url"])


# Resource capacity in an SOP and a person's current booking have different sources.
LIVE_STATUS = re.compile(
    r"live (?:bed|occupancy|availability|status)|(?:bed|room|shelter) vacanc|empty bed|free beds? (?:now|tonight)|"
    r"(?:bed|room|space|spot|place|staff).{0,45}(?:kh(?:aa|a)li|available|tonight|open right now)|"
    r"(?:tonight|right now|aaj raat).{0,45}(?:beds?|space|vacan|jagah)|"
    r"(?:complaint|case|report).{0,35}(?:status|closed today|aaj close|been closed|been resolved|still open)|"
    r"(?:book|reserve|guarantee).{0,24}(?:room|bed|space|place)|(?:bed|room).{0,24}(?:booked|reserved)|"
    r"(?:on duty|duty par).{0,30}(?:now|today|kaun)|(?:right now|abhi).{0,25}(?:staff|duty)|"
    r"खाली|(?:आज|अभी).{0,45}(?:बेड|बिस्तर|जगह).{0,15}उपलब्ध|रिक्त बिस्तर|शिकायत.{0,20}(?:बंद|स्थिति)|अभी.{0,25}ड्यूटी|காலியாக|புகாரின் நிலை", re.I
)


def _route(q,lang,state="",guide=None):
    if urgent(q):
        return dict(kind="emergency",buttons=links(state),answer=dict(zip(LANGS,["If you can safely call, use 112 for immediate help.","यदि सुरक्षित रूप से कॉल कर सकती हैं, तुरंत मदद के लिए 112 डायल करें।","Agar safe ho toh turant madad ke liye 112 call karein.","பாதுகாப்பாக அழைக்க முடிந்தால் உடனடி உதவிக்கு 112 அழைக்கவும்."]))[lang])
    if guide:
        return card_result(next(c for c in GUIDES if c["id"]==guide),lang)
    fallback = dict(kind="unknown", answer={
        "en": "I couldn’t verify an answer in the available sources.",
        "hi": "उपलब्ध स्रोतों में इस सवाल का पुष्ट उत्तर नहीं मिला।",
        "mix": "Available sources mein is sawaal ka verified jawab nahi mila.",
        "ta": "கிடைக்கும் ஆதாரங்களில் இந்தக் கேள்விக்கான பதிலை உறுதிப்படுத்த முடியவில்லை."
    }[lang])
    if LIVE_STATUS.search(q):
        return dict(fallback,answer=dict(zip(LANGS,["These documents contain no live availability or personal case records. Contact the service directly.","इन दस्तावेज़ों में वर्तमान उपलब्धता या व्यक्तिगत केस की स्थिति नहीं है। संबंधित सेवा से संपर्क करें।","Live availability ya personal case status in documents mein nahi hai. Service se directly contact karein.","தற்போதைய இடவசதி அல்லது தனிப்பட்ட வழக்கு நிலை இங்கு இல்லை. சேவையை நேரடியாக அணுகவும்."]))[lang],url="https://missionshakti.wcd.gov.in/",source="Mission Shakti")
    if re.search(r"nearest|near me|local services|nazdeek|paas.{0,12}(?:osc|centre)|नज़दीक|नजदीक|पास (?:का|वाला) (?:सेंटर|केंद्र)|அருகில்",q,re.I):
        msg={"en":"Select your state and district below to see published local services.","hi":"नीचे राज्य और ज़िला चुनकर स्थानीय सेवाओं की सूची देखें।","mix":"Neeche state aur district chun kar local services dekhein.","ta":"கீழே மாநிலத்தையும் மாவட்டத்தையும் தேர்ந்தெடுத்து உள்ளூர் சேவைகளைப் பார்க்கவும்."}
        return dict(kind="directory",answer=msg[lang],source="Ministry OSC directory",url=OSC_URL)
    if re.search(r"penalty|punishment|sentence for|जेल|सजा|सज़ा|jail|punishment|தண்டனை",q,re.I):
        return dict(fallback,answer=NO_ANSWER[lang],source="NALSA · Legal aid",url=NALSA)
    for card in GUIDES:
        if re.search(card["pattern"],q,re.I):
            return card_result(card,lang)
    with LOCK:
        from sop_search import evidence
        return evidence(q, lang) or fallback

def respond(q, lang, state="", guide=None):
    from sop_search import input_language
    # Explicitly separated questions can require evidence from two different SOPs.
    parts = re.split(r"(?<=[?？।])\s+|\s*;\s*", q.strip())
    if len(parts)==2 and all(parts) and not guide and not urgent(q):
        replies = [respond(part,lang,state) for part in parts]
        if all(r["kind"]=="answer" and r["supporting_passages"] for r in replies):
            proofs = [r["supporting_passages"][0] for r in replies]
            if len({v["url"].split("#")[0] for v in proofs})==2:
                text = "\n\n".join(r["answer"] for r in replies)
                return dict(kind="answer",answer=text,language=lang,
                            query_type=" / ".join(dict.fromkeys(r["query_type"] for r in replies)),
                            answerability="ANSWERABLE",confidence=None,confidence_basis="Two source matches",
                            explanation="Each part is supported by its separately cited SOP passage.",
                            supporting_passages=proofs, multiple_sources=True)
        # Keep each clause's conclusion and citation even when only one is answerable.
        if all(r["kind"] in {"unknown","answer","excerpt"} for r in replies):
            proofs = [proof for r in replies for proof in r["supporting_passages"]]
            complete = all(r["answerability"]=="ANSWERABLE" for r in replies)
            return dict(kind="answer" if complete else "unknown", language=lang,
                        answer="\n\n".join(r["answer"] for r in replies),
                        query_type=" / ".join(dict.fromkeys(r["query_type"] for r in replies)),
                        answerability="ANSWERABLE" if complete else "UNANSWERABLE",
                        confidence=None, confidence_basis="Separate evidence checks",
                        explanation="Each question was checked separately against the SOPs.",
                        supporting_passages=proofs, multiple_sources=bool(proofs))
    result = _route(q, lang, state, guide)
    detected = input_language(q)
    tag = {"en":"English", "hi":"Indic (Hindi)", "ta":"Indic (Tamil)", "mix":"Indic / code-mixed (Roman Hindi)"}[detected]
    if detected in {"hi","ta"} and re.search(r"[a-zA-Z]{2,}",q):
        tag = "Code-mixed (" + ("Hindi" if detected=="hi" else "Tamil") + " / English)"
    kind = result["kind"]
    result.update(query_type=tag, answerability="UNANSWERABLE" if kind=="unknown" else
                  "ANSWERABLE" if kind in {"answer","excerpt","guide"} else "SERVICE ROUTE")
    result.setdefault("confidence",None)
    result.setdefault("confidence_basis","Verified rule match" if kind=="answer" else "No scored evidence match")
    passage = result.get("evidence") or (result["answer"] if kind=="excerpt" else "")
    result["supporting_passages"] = [dict(text=passage,source=result["source"],url=result["url"])] if passage else []
    result["explanation"] = {"answer":"The cited SOP passage supports this answer.",
        "excerpt":"The text shown is an extract from the cited SOP page.",
        "unknown":"Insufficient information available in the provided documents.",
        "guide":"This guide links to the published source for its guidance.",
        "directory":"Use the directory to look up a published service.",
        "emergency":"Immediate-help routing was triggered by the message."}[kind]
    return result
