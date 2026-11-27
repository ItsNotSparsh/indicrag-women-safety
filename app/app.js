'use strict';
const $=id=>document.getElementById(id), lang=()=>$('lang').value;
const ui={
 en:['Find support','Ask a question','Ask','Speak','Immediate help','Rights and action guides','Find local services','Read aloud','Stop recording','Searching…','Source','Quick exit ↗','Choose a state','All districts','I need help now'],
 hi:['सहायता खोजें','अपना सवाल पूछें','पूछें','बोलें','तुरंत मदद','अधिकार और शिकायत की प्रक्रिया','स्थानीय सेवाएँ','सुनें','रिकॉर्डिंग रोकें','खोज जारी है…','स्रोत','तुरंत बाहर जाएँ ↗','राज्य चुनें','सभी ज़िले','बचाओ'],
 mix:['Madad dhundhein','Apna sawaal poochhein','Poochhein','Bolein','Turant madad','Rights aur complaint guides','Local services','Sunein','Recording rokein','Dhundh rahe hain…','Source','Quick exit ↗','State chunein','Sab districts','bachao'],
 ta:['உதவி பெறுங்கள்','கேள்வி கேளுங்கள்','கேள்','பேசு','அவசர உதவி','உரிமைகளும் வழிமுறைகளும்','உள்ளூர் சேவைகள்','வாசிக்க','பதிவை நிறுத்து','தேடுகிறது…','ஆதாரம்','விரைவாக வெளியேறு ↗','மாநிலம் தேர்வு','அனைத்து மாவட்டங்கள்','காப்பாற்று']};
const guideLabels={hi:['ज़ीरो एफआईआर','कार्यस्थल पर उत्पीड़न','घरेलू हिंसा','पीछा करना','ऑनलाइन उत्पीड़न','भौतिक साक्ष्य','निःशुल्क विधिक सहायता','महिला आयोग','हिंसा के बाद सहायता','यौन उत्पीड़न','साझा घर'],ta:['ஜீரோ எஃப்.ஐ.ஆர்','பணியிடப் புகார்','குடும்ப வன்முறை','பின்தொடர்தல்','இணையத் துன்புறுத்தல்','தடயங்களைப் பாதுகாத்தல்','இலவச சட்ட உதவி','மகளிர் ஆணையம்','வன்முறைக்குப் பின் உதவி','பாலியல் துன்புறுத்தல்','பகிர்ந்த வீடு']};
let cfg,reply,stream,ctx,node,frames=[],recordTimer,player,objectURL,version=0,recEpoch=0,dirEpoch=0,exited=false;
const el=(tag,content)=>{const x=document.createElement(tag);x.textContent=content;return x};
function link(label,href){const a=el('a',label);a.href=href;if(!href.startsWith('tel:')){a.target='_blank';a.rel='noopener noreferrer'}return a}
async function post(path,params){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(params)});if(!r.ok){const error=await r.json().catch(()=>({}));throw Error(error.error||'Service unavailable. Try again.')}return r.json()}
function stopAudio(){if(player)player.pause();if(objectURL)URL.revokeObjectURL(objectURL);player=null;objectURL=null}
function cleanMic(){clearTimeout(recordTimer);node?.disconnect();stream?.getTracks().forEach(t=>t.stop());ctx?.close().catch(()=>{});ctx=null;node=null;stream=null;$('mic').textContent=ui[lang()][3]}
function clearReply(){version++;stopAudio();reply=null;$('answer').className='';$('answer').replaceChildren();$('listen').hidden=true;$('status').textContent=''}
function wipe(){exited=true;recEpoch++;cleanMic();clearReply();frames=[];$('q').value='';$('resources').replaceChildren()}
function exitPage(){wipe();location.replace('https://www.google.com/search?q=weather')}
$('exit').onclick=exitPage;document.addEventListener('keydown',e=>{if(e.key==='Escape')exitPage()});window.addEventListener('pagehide',wipe);window.addEventListener('pageshow',e=>{if(e.persisted)location.reload()});
function emergencyCard(){
 recEpoch++;cleanMic();frames=[];clearReply();const langCode=lang();const msg={en:'If you can safely call, use 112 for immediate help.',hi:'यदि सुरक्षित हो तो तुरंत सहायता के लिए 112 डायल करें।',ta:'பாதுகாப்பாக அழைக்க முடிந்தால் உடனடி உதவிக்கு 112 அழைக்கவும்.',mix:'Agar safe ho toh turant madad ke liye 112 call karein.'}[langCode];
 reply={answer:msg,language:langCode};const a=$('answer');a.className='urgent-box';a.append(el('p',msg));
 const buttons=[['112','Emergency'],['1930','Financial cyber fraud']];if($('state').value!=='West Bengal')buttons.splice(1,0,['181','Women Helpline (except West Bengal)']);
 for(const [n,l] of buttons){const b=link(n+' · '+l,'tel:'+n);b.className='call';a.append(b)}a.append(el('br',''),link('Official helplines','https://www.india.gov.in/directory/helpline'));$('listen').hidden=false;
}
async function ask(question,guide){
 clearReply();const id=version;$('status').textContent=ui[lang()][9];
 try{const x=await post('/ask',{question,guide,language:lang(),state:$('state').value});if(id!==version||exited)return;reply=x;const a=$('answer');a.className=x.kind==='emergency'?'urgent-box':'';
 if(guide)a.focus();if(x.label)a.append(el('strong',x.label));a.append(el('p',x.answer));
 if(x.buttons)for(const [n,p,u] of x.buttons){const b=link(n,'tel:'+p);b.className='call';a.append(b,link(ui[lang()][10],u),el('br',''))}
 if(x.evidence){const details=el('details','');const caption={en:'View original English passage',hi:'मूल अंग्रेज़ी अंश देखें',mix:'Original English passage dekhein',ta:'மூல ஆங்கிலப் பகுதியைக் காண்க'};details.append(el('summary',caption[lang()]),el('blockquote',x.evidence));a.append(details)}
 if(x.query_type){const info=el('details','');info.append(el('summary',({en:'Answer details',hi:'उत्तर का विवरण',mix:'Jawab ki details',ta:'பதில் விவரங்கள்'})[lang()]));
 info.append(el('p',x.query_type+' · '+x.answerability),el('p',x.explanation));
 if(x.confidence!=null)info.append(el('small',x.confidence_basis+' · '+x.confidence+' (match score)'));
 a.append(info)}
 if(x.multiple_sources)for(const proof of x.supporting_passages){const detail=el('details','');detail.append(el('summary',proof.source),el('blockquote',proof.text),link(proof.source,proof.url));a.append(detail)}
 if(x.url)a.append(link(x.source,x.url));
 if(x.kind==='directory'){const go=el('button',ui[lang()][6]);go.type='button';go.onclick=()=>{$('directoryPanel').open=true;$('state').focus()};a.append(go)}if(x.kind==='guide'){a.append(document.createTextNode(' · '),link('Legal aid / विधिक सहायता','https://nalsa.gov.in/faqs/'))}$('listen').hidden=false;$('status').textContent='';
 }catch(e){if(id===version)$('status').textContent=e.message}
}
$('form').onsubmit=e=>{e.preventDefault();ask($('q').value)};$('urgent').onclick=emergencyCard;
async function toggleMic(){
 if(stream){
   const rate=ctx.sampleRate, count=frames.reduce((a,f)=>a+f.length,0),samples=new Float32Array(count);let offset=0;for(const f of frames){samples.set(f,offset);offset+=f.length}
   const id=recEpoch;cleanMic();frames=[];if(!count)return;
   const offline=new OfflineAudioContext(1,Math.ceil(count*16000/rate),16000);
   const buffer=offline.createBuffer(1,count,rate);buffer.copyToChannel(samples,0);const source=offline.createBufferSource();source.buffer=buffer;source.connect(offline.destination);source.start();
   const res=(await offline.startRendering()).getChannelData(0);const bytes=Int16Array.from(res,x=>Math.max(-1,Math.min(1,x))*32767);
   $('status').textContent='Transcribing…';const r=await fetch('/listen/'+lang(),{method:'POST',body:bytes});if(!r.ok)throw Error('Transcription unavailable.');
   const {text}=await r.json();if(exited||id!==recEpoch)return;$('q').value=text;$('status').textContent=text?'Review, then press '+ui[lang()][2]+'.':'No speech detected.';return
 }
 const id=++recEpoch;stopAudio();const s=await navigator.mediaDevices.getUserMedia({audio:true});if(exited||id!==recEpoch){s.getTracks().forEach(t=>t.stop());return}
 stream=s;ctx=new AudioContext();const input=ctx.createMediaStreamSource(s);node=ctx.createScriptProcessor(4096,1,1);frames=[];
 node.onaudioprocess=e=>frames.push(e.inputBuffer.getChannelData(0).slice());input.connect(node);node.connect(ctx.destination);
 $('mic').textContent=ui[lang()][8];recordTimer=setTimeout(()=>$('mic').click(),24000)
}
$('mic').onclick=async()=>{try{await toggleMic()}catch(e){cleanMic();$('status').textContent=e.message}};
$('listen').onclick=async()=>{if(!reply)return;stopAudio();const id=version;try{const r=await fetch('/speak',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:reply.speech_text||reply.answer,language:reply.speech_text&&lang()==='mix'?'hi':(reply.language||lang())})});if(!r.ok)throw Error('Playback unavailable.');const b=await r.blob();if(exited||id!==version)return;objectURL=URL.createObjectURL(b);player=new Audio(objectURL);await player.play()}catch(e){$('status').textContent=e.message}};
async function resources(){const id=++dirEpoch;try{const rows=await post('/directory',{language:lang(),state:$('state').value,district:$('district').value});if(id!==dirEpoch||exited)return;const box=$('resources');box.replaceChildren();const shown=rows.filter(r=>!$('languageFilter').checked||r.language_confirmed);if(!shown.length){box.append(el('p',{en:'No published listing matches these filters.',hi:'इन फ़िल्टर से मेल खाती कोई प्रकाशित सेवा नहीं मिली।',mix:'In filters se koi published listing nahi mili.',ta:'இந்தத் தேர்வுகளுக்குப் பொருந்தும் சேவைப் பதிவு இல்லை.'}[lang()]))}for(const r of shown){const div=el('div','');div.className='resource';div.append(el('strong',r.name),el('small',r.place+(r.languages?' · '+r.languages:'')));if(r.phone)div.append(link(r.phone,'tel:'+r.phone),document.createTextNode(' · '));div.append(link(ui[lang()][10],r.url));box.append(div)}}catch(e){if(id===dirEpoch&&!exited)$('resources').textContent=e.message}}
function districts(){const s=$('district');s.replaceChildren(new Option(ui[lang()][13],''));for(const d of cfg.locations[$('state').value]||[])s.add(new Option(d,d));resources()}
const exampleQuestions = [
  {
    "en": "What help is available at a Sakhi One Stop Centre?",
    "hi": "वन स्टॉप सेंटर में क्या मदद मिलती है?",
    "mix": "One Stop Centre pe kya madad milti hai?",
    "ta": "ஒரு நிறுத்த மையத்தில் என்ன உதவி கிடைக்கும்?"
  },
  {
    "en": "Can I send a message or email instead of calling the helpline?",
    "hi": "बोलकर कॉल करने के अलावा महिला हेल्पलाइन से संपर्क के क्या तरीके हैं?",
    "mix": "Phone par baat kiye bina Women Helpline ko message ya email kar sakti hoon?",
    "ta": "தொலைபேசியில் பேசாமல் மகளிர் உதவி மையத்தைத் தொடர்புகொள்ளலாமா?"
  },
  {
    "en": "Can I get help from an OSC without identity documents?",
    "hi": "दस्तावेज़ या पहचान पत्र नहीं है तो क्या केंद्र मदद करेगा?",
    "mix": "Mere paas ID proof ya documents nahi hain. Kya OSC madad karega?",
    "ta": "அடையாள ஆவணங்கள் இல்லாவிட்டாலும் மையத்தில் உதவி கிடைக்குமா?"
  }
];
const introduction = {
 en:['Try a question','Ask about women’s support services in India and read the official source behind an answer.'],
 hi:['एक सवाल चुनें','भारत में महिलाओं के लिए उपलब्ध सेवाओं के बारे में पूछें और उत्तर का आधिकारिक स्रोत पढ़ें।'],
 mix:['Ek sawaal chunein','India mein women’s support services ke baare mein poochhein aur jawaab ka official source dekhein.'],
 ta:['ஒரு கேள்வியைத் தேர்ந்தெடுக்கவும்','இந்தியாவில் பெண்களுக்கான உதவி சேவைகளைப் பற்றிக் கேட்டு, பதிலுக்கான அதிகாரப்பூர்வ ஆதாரத்தைப் படிக்கலாம்.']
};
function renderExamples(){
 const language=lang();
 $('examplesTitle').textContent=introduction[language][0];
 $('introText').textContent=introduction[language][1];
 $('examples').replaceChildren(...exampleQuestions.map(versions=>{
   const question=versions[language];
   const button=el('button',question);
   button.type='button';
   button.onclick=()=>{clearReply();$('q').value=question;$('q').focus()};
   return button;
 }));
}
function render(){renderExamples();const labels=ui[lang()];document.documentElement.lang={mix:'hi-Latn',hi:'hi',ta:'ta',en:'en'}[lang()];
 ['heading','askTitle','submit','mic','urgent','guidesTitle','directoryTitle','listen'].forEach((id,i)=>$(id).textContent=labels[i]);$('exit').textContent=labels[11];$('guides').replaceChildren();
 for(const [i,g] of cfg.guides.entries()){const b=el('button',guideLabels[lang()]?.[i]||g.title);b.onclick=()=>ask(g.title,g.id);$('guides').append(b)}
 const chosen=$('state').value;$('state').replaceChildren(new Option(labels[12],''));for(const s of Object.keys(cfg.locations).sort())$('state').add(new Option(s,s));$('state').value=chosen;districts()}
$('lang').onchange=()=>{recEpoch++;cleanMic();clearReply();render()};$('state').onchange=()=>{clearReply();districts()};$('district').onchange=resources;$('languageFilter').onchange=resources;
fetch('/config').then(r=>r.json()).then(x=>{cfg=x;render()}).catch(()=>{$('status').textContent='Could not load the directory.'});





