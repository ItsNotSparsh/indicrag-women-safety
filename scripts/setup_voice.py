"""Fetch local ASR/TTS weights for the web app (existing cache is reused)."""
from pathlib import Path
from huggingface_hub import snapshot_download

ROOT=Path(__file__).resolve().parents[1]
for repo,folder,weights in [
    ("openai/whisper-base","whisper-base","model.safetensors"),
    ("vasista22/whisper-hindi-small","whisper-hindi-small","pytorch_model.bin"),
    *((f"facebook/mms-tts-{code}",f"tts-{code}","model.safetensors") for code in ("eng","hin","tam")),
]:
    snapshot_download(repo,local_dir=ROOT/"data/models"/folder,
                      allow_patterns=[weights,"*.json","merges.txt","vocab.txt","README.md","LICENSE*"])

