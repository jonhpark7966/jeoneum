"""Stage 3 — speaker -> voice mapping.

For each chalna speaker_id: use a manual override if given, else auto-extract a
clean reference clip from the separated Vocals stem and clone it (cross-lingual).
A single provided voice is applied to every speaker (useful while diarization is
unreliable, or for plain-SRT single-voice input). See docs/spec.md §7.

A reference clip may carry its transcript in a sidecar `.txt` of the same basename
(e.g. ref.wav + ref.txt); it is loaded automatically when Voice.ref_text is unset.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from .schema import Doc, Voice
from .tts.base import TTSEngine, VoiceHandle


def _resolve_ref_text(voice: Voice) -> str | None:
    if voice.ref_text:
        return voice.ref_text
    if voice.ref_audio:
        sidecar = Path(voice.ref_audio).with_suffix(".txt")
        if sidecar.exists():
            return sidecar.read_text(encoding="utf-8").strip()
    return None


def extract_ref(
    audio_path: str, doc: Doc, speaker_id: str, workdir: str, max_sec: float = 10.0
) -> tuple[str, str | None]:
    """Cut a reference clip for speaker_id from `audio_path` (the separated vocals
    stem when available). Picks the speaker's longest segment as a clean-ish sample
    and returns (ref_audio_path, ref_text). The ref text is the source-language
    transcript of that segment — cross-lingual cloning handles the target language."""
    segs = [s for s in doc.segments if s.speaker_id == speaker_id and s.end_time > s.start_time]
    if not segs:
        raise ValueError(f"no segments to extract a reference for speaker {speaker_id!r}")
    best = max(segs, key=lambda s: s.end_time - s.start_time)
    start = best.start_time
    duration = min(best.end_time - start, max_sec)
    Path(workdir).mkdir(parents=True, exist_ok=True)
    out = str(Path(workdir) / f"ref_{speaker_id}.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-i", audio_path,
         "-t", str(duration), "-ac", "1", "-ar", "24000", out],
        check=True,
    )
    return out, best.text


def resolve_voices(
    doc: Doc,
    engine: TTSEngine,
    manual: dict[str, Voice] | None = None,
    workdir: str | None = None,
) -> dict[str, VoiceHandle]:
    """Build a VoiceHandle per speaker_id. Manual override wins; a single manual
    voice covers all speakers; otherwise auto-extract a reference per speaker from
    the separated vocals stem (cross-lingual clone). Prompts are cached so each
    distinct voice is built once."""
    manual = manual or {}
    cache: dict[tuple, VoiceHandle] = {}

    def handle_for(voice: Voice) -> VoiceHandle:
        ref_text = _resolve_ref_text(voice)
        key = (voice.ref_audio, ref_text)
        if key not in cache:
            cache[key] = engine.build_voice(voice.ref_audio, ref_text)
        return cache[key]

    # A single provided voice is the default for every speaker.
    default = handle_for(next(iter(manual.values()))) if len(manual) == 1 else None

    speakers = {s.speaker_id for s in doc.segments}
    handles: dict[str, VoiceHandle] = {}
    for sp in speakers:
        if sp in manual:
            handles[sp] = handle_for(manual[sp])
        elif default is not None:
            handles[sp] = default
        elif doc.vocals_audio:
            ref_audio, ref_text = extract_ref(
                doc.vocals_audio, doc, sp, workdir or str(Path(doc.vocals_audio).parent / "refs")
            )
            cache_key = (ref_audio, ref_text)
            if cache_key not in cache:
                cache[cache_key] = engine.build_voice(ref_audio, ref_text)
            handles[sp] = cache[cache_key]
        else:
            raise ValueError(
                f"no voice for speaker {sp!r}: provide a manual voice "
                "(a single voice applies to all speakers) or enable separation for auto-extract"
            )
    return handles
