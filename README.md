# IndicRAG-QA women-safety information prototype

## Environment

Use Python 3.12 and the project virtual environment. The repository pins CUDA-enabled PyTorch for the RTX 4050 laptop. In a Windows CMD terminal, from this folder:

```bat
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

For exact installed versions, use `requirements-lock.txt`.

## Official source ingestion

Refresh page-level text and the source manifest:

```bat
python scripts\extract_official_sources.py
```

Build the initial retrieval corpus:

```bat
python scripts\build_evidence_corpus.py
```

The builder writes `data\processed\evidence_corpus\chunks.jsonl` and `ingestion_report.json`. Every chunk keeps its source title, PDF filename, language, page citation, and scope status. It skips missing OCR, OCR marked for review, pages with too little text, and the contact directory (kept separate because contact details need freshness checks). Historical Mission Shakti guidelines remain tagged as historical. Review the ingestion report before using these chunks for answers.

The Hindi One Stop Centre SOP and some OSC English pages still need reviewed OCR before they can enter the corpus. The enhanced Hindi PDF is a visual aid; the untouched original remains the source of truth.

## Project scope

The prototype retrieves public, official women-safety service information. It is not an emergency dispatch service or legal adviser. Benchmark corpora such as GLUECoS and COMI-LINGUA are used only for language-handling evaluation and are kept separate from official answer sources.

## Search in English, Hindi or Hinglish

Activate the project environment in CMD and use UTF-8 for Devanagari:

```bat
chcp 65001
set PYTHONUTF8=1
python scripts\search_official.py "One Stop Centre mein kya help milti hai?"
```

On a new checkout, rebuild chunks from the local official PDFs first and download the pinned model with the project environment active:

```bat
hf download intfloat/multilingual-e5-small --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3 --include "*.json" "model.safetensors" "sentencepiece.bpe.model" --local-dir data/models/multilingual-e5-small
```

The first search embeds the core SOP passages; subsequent searches reuse the local index. Results are PDF excerpts with page citations. Hindi and Hinglish search quality still needs labelled evaluation.

## Ask questions in chat

From the activated project environment in Windows CMD:

```bat
chcp 65001
set PYTHONUTF8=1
python scripts\chat_official.py
```

The terminal and web app share an answer router. The terminal selects a response
language from the question. Use `--language en`, `hi`, `mix` or `ta` to override
it. Use `/reset` to clear the last topic or `/exit` to quit.

Also install the pretrained multilingual passage reranker once per machine in
the activated environment. The same command works in Windows CMD and macOS:

```text
hf download cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 --revision 1427fd652930e4ba29e8149678df786c240d8825 --include "*.json" "model.safetensors" "sentencepiece.bpe.model" --local-dir data/models/mmarco-reranker
```

For the optional original Qwen generation experiment, use
`python scripts/chat_official.py --experimental-generator`. It additionally requires
the local Qwen/Qwen2.5-1.5B-Instruct checkpoint under `data/models/qwen-answer`.

## Saheli web app

From the Desktop project folder in Windows CMD, run `start_app.cmd`, then open
<http://127.0.0.1:8765>. Use Ctrl+C in the terminal to stop it. The server binds
to the local computer. The existing search and experimental chat commands are
also available.

Select English, Hindi, Roman Hinglish or Tamil. Ask a question or open a
source-linked guide. The web app retrieves curated legal guidance and SOP
answers; a related English PDF extract is labelled as such. Other legal questions
refer to NALSA. The emergency action is available without loading an LLM.
State and district selection uses no GPS. Local listings are source snapshots;
a listed address does not establish that a bed, staff member or service is
available now. Only organisations explicitly listing a requested language appear
when the language checkbox is selected. Police and NGO coverage is selective.

Click Speak, allow microphone access, then stop recording. Review the transcript
before submitting it. Clips are limited to about 24 seconds. Read aloud plays
local speech; Roman Hinglish guide answers have a Hindi reading. No cloud speech
account is necessary. Real-world accents and ambient noise can affect recognition.
For a new machine, provision the existing E5 model, SOP files and environment
first (see above), then run `python scripts/setup_voice.py`. The models are
stored under `data/models`. Check each model card's licence before redistribution;
the Facebook MMS TTS models are offered for noncommercial use.

Quick exit, also available through Esc, stops recording and playback, clears the
current view and replaces the tab with a weather search. It does not erase
browser history, downloaded PDFs, OS activity or sites opened in other tabs.
The application writes no queries, transcripts, recordings, or selected districts
to disk. Localhost-only service, no account, analytics or application access logs.

### Sources and evaluation

Legal and service guide citations are in `app/guides.json`. The directory includes
770 OSC entries transcribed from the [Ministry directory](https://spniwcd.wcd.gov.in/uploads/pdf/1719920005_9NAs3KlT9d%20%282%29.pdf).
Names and addresses reflect that publication. Source links were checked on
25 November 2026; listing an organisation does not constitute telephone verification.
The default answer path checks each translated SOP entry against its local PDF
and extracted page. For paraphrases it retrieves candidates with multilingual E5
and BM25, then reranks them with mMARCO MiniLM. The browser provides an expandable
English quotation and PDF page link for these answers. Other topics can return a
labeled original-language excerpt when the reranker finds supporting material.
Reranking uses CUDA when available and otherwise runs on CPU. The experimental
Qwen generator and trained pilot adapter are separate experiments.

Run `python evaluation/check_sop_answers.py` for the labeled answer, citation and
abstention checks. The JSON output includes each question, expected result, actual
response and latency. Regression and development questions have been used in
repairing the app. Their scores measure covered behavior. The release set was
run on the final router without tuning on those questions. Inspect each response
in the JSON output to distinguish a wrong answer from a missed answer.

Run the reproducible routing checks with `python evaluation/check_support_app.py`.
The route-distribution audit uses [IndicGuard](https://huggingface.co/datasets/l3cube-pune/IndicGuard)
Hindi test prompts (CC BY 4.0). Its aggregate output is in
`evaluation/indicguard-web-results.json`. General prompt-safety labels alone
cannot grade whether someone received appropriate assistance.

For [SurakshaEval](https://huggingface.co/datasets/SurakshaAI/SurakshaEval)
(Banerjee et al., CC BY-NC-SA 4.0), obtain the gated Hindi test JSONL using
an approved account, save it to `work/assist/suraksha.jsonl`, and run:

```bat
python evaluation/check_safety.py work/assist/suraksha.jsonl --question-field question_indic --limit 116 --output evaluation/suraksha-hi-routes.json
```
