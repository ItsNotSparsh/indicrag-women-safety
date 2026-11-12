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
