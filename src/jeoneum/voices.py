"""Stage 3 — speaker -> voice mapping.

For each chalna speaker_id: use a manual override if given, else auto-extract a
clean reference clip from the separated Vocals stem and clone it (cross-lingual).
A single provided voice is applied to every speaker (useful while diarization is
unreliable, or for plain-SRT single-voice input). See docs/spec.md §7.

A reference clip may carry its transcript in a sidecar `.txt` of the same basename
(e.g. ref.wav + ref.txt); it is loaded automatically when Voice.ref_text is unset.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

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
    audio_path: str, doc: Doc, speaker_id: str, workdir: str,
    target_sec: float = 8.0, max_segments: int = 5,
) -> tuple[str, str | None]:
    """Build a per-speaker reference clip from `audio_path` (the separated vocals
    stem when available, else the original audio) by concatenating that speaker's
    longest cues up to ~target_sec, with the matching transcript. Cross-lingual
    cloning handles the target language. Returns (ref_audio_path, ref_text)."""
    segs = [s for s in doc.segments if s.speaker_id == speaker_id and (s.end_time - s.start_time) > 0.4]
    if not segs:
        raise ValueError(f"no usable segments to extract a reference for speaker {speaker_id!r}")
    segs.sort(key=lambda s: s.end_time - s.start_time, reverse=True)
    chosen, total = [], 0.0
    for s in segs:
        chosen.append(s)
        total += s.end_time - s.start_time
        if total >= target_sec or len(chosen) >= max_segments:
            break
    chosen.sort(key=lambda s: s.start_time)   # natural order for the concatenated clip

    audio, sr = sf.read(audio_path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)
    clips = [audio[int(s.start_time * sr): int(s.end_time * sr)] for s in chosen]
    ref = np.concatenate([c for c in clips if len(c)])

    Path(workdir).mkdir(parents=True, exist_ok=True)
    out = str(Path(workdir) / f"ref_{speaker_id}.wav")
    sf.write(out, ref, sr)
    return out, " ".join(s.text for s in chosen)


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
        elif doc.vocals_audio or doc.audio_path:
            src_audio = doc.vocals_audio or doc.audio_path   # clean vocals if separated, else original
            ref_audio, ref_text = extract_ref(
                src_audio, doc, sp, workdir or str(Path(src_audio).parent / "refs")
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
