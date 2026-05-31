"""Stage 0 — ingest. Normalize any input to a standard wav.

Entry points (docs/spec.md §2): local video/audio, YouTube URL, or an existing
subtitle file (handled upstream in the pipeline, not here).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Confirmed single working format for the whole pipeline (spec §11.1): 24k mono.
TARGET_SR = 24000
TARGET_CH = 1


def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def ingest(source: str, workdir: str) -> str:
    """Return path to a normalized wav (mono, TARGET_SR)."""
    work = Path(workdir)
    work.mkdir(parents=True, exist_ok=True)

    if _is_url(source):
        # Download bestaudio via yt-dlp, then normalize.
        raw = work / "download.%(ext)s"
        subprocess.run(
            ["yt-dlp", "-f", "bestaudio/best", "-o", str(raw), source],
            check=True,
        )
        src = next(work.glob("download.*"))
    else:
        src = Path(source)

    out = work / "ingest.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-ac", str(TARGET_CH), "-ar", str(TARGET_SR), str(out)],
        check=True,
    )
    return str(out)
