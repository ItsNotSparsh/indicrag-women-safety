from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PAGE_DIR = ROOT / "data" / "processed" / "official_pages"
MANIFEST_PATH = ROOT / "data" / "official_sources" / "source_manifest.csv"
OUT_DIR = ROOT / "data" / "processed" / "evidence_corpus"
OUT_FILE = OUT_DIR / "chunks.jsonl"
REPORT_FILE = OUT_DIR / "ingestion_report.json"

# Conservative first pass: contact listings are handled separately so stale
# phone/email details are not surfaced as general guidance.
EXCLUDED_SOURCE_TYPES = {"official public directory"}
MAX_WORDS = 180
OVERLAP_WORDS = 35
MIN_PAGE_WORDS = 10


def pack_page_text(text: str) -> list[str]:
    """Pack sentence fragments into bounded, overlapping chunks."""
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?।])\s+", re.sub(r"\s+", " ", text).strip())
        if s.strip()
    ]
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    for sentence in sentences:
        words = sentence.split()
        if len(words) > MAX_WORDS:
            # Hard-split unusually long table/list lines while preserving order.
            pieces = [
                " ".join(words[i : i + MAX_WORDS])
                for i in range(0, len(words), MAX_WORDS)
            ]
        else:
            pieces = [sentence]

        for piece in pieces:
            piece_words = piece.split()
            if current and current_words + len(piece_words) > MAX_WORDS:
                chunks.append(" ".join(current))
                tail: list[str] = []
                tail_count = 0
                for old_sentence in reversed(current):
                    old_words = old_sentence.split()
                    if tail_count + len(old_words) > OVERLAP_WORDS and tail:
                        break
                    tail.insert(0, old_sentence)
                    tail_count += len(old_words)
                current = tail
                current_words = tail_count

            current.append(piece)
            current_words += len(piece_words)

    if current:
        final = " ".join(current).strip()
        if not chunks or final != chunks[-1]:
            chunks.append(final)
    return chunks


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as f:
        manifest = {row["filename"]: row for row in csv.DictReader(f)}

    chunks: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    included_pages: dict[str, int] = {}
    for page_file in sorted(PAGE_DIR.glob("*.jsonl")):
        with page_file.open(encoding="utf-8") as f:
            for line_number, line in enumerate(f, 1):
                if not line.strip():
                    continue
                page = json.loads(line)
                filename = page.get("source_file", page_file.stem + ".pdf")
                source = manifest.get(filename, {})
                page_num = page.get("page", line_number)
                text = re.sub(r"\s+", " ", page.get("text", "")).strip()
                reason = None

                if source.get("source_type") in EXCLUDED_SOURCE_TYPES:
                    reason = "separate freshness-sensitive contact source"
                elif page.get("ocr_required"):
                    reason = "OCR missing"
                elif page.get("ocr_review_required"):
                    reason = "OCR confidence below review threshold"
                elif len(text.split()) < MIN_PAGE_WORDS:
                    reason = "too little extracted text"

                if reason:
                    skipped.append(
                        {
                            "source_file": filename,
                            "page": page_num,
                            "reason": reason,
                            "ocr_mean_confidence": page.get("ocr_mean_confidence"),
                        }
                    )
                    continue

                page_chunks = pack_page_text(text)
                if not page_chunks:
                    skipped.append(
                        {"source_file": filename, "page": page_num, "reason": "no text"}
                    )
                    continue

                included_pages[filename] = included_pages.get(filename, 0) + 1
                historical = any(
                    marker in source.get("scope_status", "").lower()
                    for marker in ("historical", "ended", "expired")
                )
                for chunk_index, chunk_text in enumerate(page_chunks, 1):
                    chunk_id = f"{Path(filename).stem}:p{page_num}:c{chunk_index}"
                    chunks.append(
                        {
                            "chunk_id": chunk_id,
                            "source_file": filename,
                            "source_title": page.get(
                                "source_title", source.get("title", Path(filename).stem)
                            ),
                            "source_type": source.get("source_type", "unknown"),
                            "scope_status": source.get("scope_status", "unverified"),
                            "historical_source": historical,
                            "language": page.get("language", source.get("language", "unknown")),
                            "page_start": page_num,
                            "page_end": page_num,
                            "text": chunk_text,
                            "word_count": len(chunk_text.split()),
                            "ocr_engine": page.get("ocr_engine"),
                            "ocr_mean_confidence": page.get("ocr_mean_confidence"),
                        }
                    )

    with OUT_FILE.open("w", encoding="utf-8", newline="\n") as f:
        for item in chunks:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    report = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "chunking": {
            "max_words": MAX_WORDS,
            "overlap_words": OVERLAP_WORDS,
            "minimum_page_words": MIN_PAGE_WORDS,
        },
        "source_manifest": str(MANIFEST_PATH.relative_to(ROOT)),
        "included_page_counts": included_pages,
        "chunk_count": len(chunks),
        "skipped_page_count": len(skipped),
        "skipped_pages": skipped,
        "outputs": {
            "chunks": str(OUT_FILE.relative_to(ROOT)),
            "report": str(REPORT_FILE.relative_to(ROOT)),
        },
    }
    REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "skipped_pages"}, ensure_ascii=False, indent=2))
    print(f"Skipped pages by reason: {json.dumps({reason: sum(x['reason'] == reason for x in skipped) for reason in sorted({x['reason'] for x in skipped})}, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
