"""Deterministic acceptance checks for supported emergency, rights and directory routes."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"app"))
from service import CENTRES, directory, respond
cases = [
    ("mere koi picha kr rha hai","en","emergency"),
    ("koi mera peechha kar rahi hai","mix","emergency"),
    ("do log mera peecha kr rhe hain","mix","emergency"),
    ("What does stalking mean?","en","guide"),
    ("Someone is following me","en","emergency"),("बचाओ","hi","emergency"),
    ("Mujhe bachao","mix","emergency"),("என்னைத் துரத்துகிறார்கள்","ta","emergency"),
    ("How do I file a Zero FIR?","en","guide"),("कार्यस्थल पर शिकायत कैसे लिखूँ?","hi","guide"),
    ("Ghar mein domestic violence ho toh?","mix","guide"),("பணியிடப் புகார் எப்படி அளிப்பது?","ta","guide"),
    ("Was the violence my fault?","en","guide"),("Kya meri galti thi?","mix","guide"),
    ("Kya mere nearest OSC mein bed khaali hai?","mix","unknown"),
    ("What punishment will the judge give in my case?","en","unknown")]
for q,lang,kind in cases:
    reply=respond(q,lang)
    assert reply["kind"]==kind,(q,reply["kind"])
    if kind=="guide": assert reply["url"].startswith(("https://","/source/"))
    if kind=="emergency":assert reply["buttons"][0][1]=="112"
assert all(r["phone"]!="181" for r in directory("West Bengal","","en"))
assert any(r["phone"]=="1090" for r in directory("Uttar Pradesh","","hi"))
assert any(r["language_confirmed"] for r in directory("Tamil Nadu","Chennai","ta"))
assert any(r["name"]=="One Stop Centre" for r in directory("Tamil Nadu","Chennai","ta"))
print(f"{len(cases)} routing cases and four directory checks passed; {len(CENTRES)} source listings.")

