"""Stage 3 — speaker -> voice mapping.

For each chalna speaker_id: auto-extract a clean, non-overlapping reference clip
from the separated Vocals stem and clone it (cross-lingual), unless a manual
override is supplied. Optionally consult the voice registry to reuse a consistent
voice for a recurring speaker. See docs/spec.md §7.
"""
from __future__ import annotations

from .schema import Doc, Voice
from .tts.base import TTSEngine, VoiceHandle


def extract_ref(vocals_path: str, doc: Doc, speaker_id: str) -> tuple[str, str | None]:
    """Pick the longest clean (non-overlapping) span for speaker_id and cut a ref clip.
    Returns (ref_audio_path, ref_text|None)."""
    raise NotImplementedError("select best span from doc.segments + cut from vocals_path")


def resolve_voices(doc: Doc, engine: TTSEngine, manual: dict[str, Voice] | None = None) -> dict[str, VoiceHandle]:
    """Build a VoiceHandle per speaker_id (manual override wins; else auto-extract)."""
    raise NotImplementedError("combine manual overrides + auto extraction + registry")
