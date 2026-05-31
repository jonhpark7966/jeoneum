"""End-to-end orchestration (docs/spec.md §3).

transcribe + separate run once; then translate -> synthesize -> align -> mix
fan out per target language. Synthesis batches segments (across languages) to use
the single in-process GPU TTS instance efficiently.

This is the skeleton wiring; cross-repo stages (chalna_client, voices) raise
NotImplementedError until their contracts are finalized. Implemented and validated
here: align + mix; functional: ingest, separate, Qwen3 TTS batch.
"""
from __future__ import annotations

from pathlib import Path

import soundfile as sf

from . import align, ingest, mix
from .chalna_client import ChalnaClient
from .schema import Doc, Voice
from .separate import AudioSeparator
from .tts.base import SynthItem, TTSEngine
from .tts.qwen3 import Qwen3Engine
from .voices import resolve_voices


def dub(
    source: str,
    target_languages: list[str],
    outdir: str,
    *,
    subs_translated: bool = False,
    keep_background: bool = True,
    manual_voices: dict[str, Voice] | None = None,
    engine: TTSEngine | None = None,
    max_speedup: float = 1.3,
    duck: bool = False,
    duck_db: float = -12.0,
) -> dict[str, str]:
    """Run the pipeline. Returns {language: output_wav_path}."""
    work = Path(outdir)
    work.mkdir(parents=True, exist_ok=True)
    chalna = ChalnaClient()
    engine = engine or Qwen3Engine()

    # --- once: ingest + transcribe + separate ---
    is_subs = source.lower().endswith((".srt", ".json"))
    if is_subs:
        raise NotImplementedError("load Doc from subtitle file (source/translated per --subs-translated)")
    wav = ingest.ingest(source, str(work / "ingest"))
    chalna.ensure_up()
    doc: Doc = chalna.transcribe(wav)
    doc.target_languages = target_languages

    # Separation is needed for background preservation AND for auto voice cloning
    # (vocals stem -> per-speaker ref). Decouple the two (codex review P0-1).
    manual = manual_voices or {}
    # A single manual voice covers all speakers (see voices.resolve_voices), so no
    # vocals stem is needed in that case.
    single_voice = len(manual) == 1
    need_vocals = not single_voice and any(s.speaker_id not in manual for s in doc.segments)
    if keep_background or need_vocals:
        vocals, background = AudioSeparator().separate(wav, str(work / "sep"))
        doc.vocals_audio = vocals
        if keep_background:
            doc.background_audio = background

    if not subs_translated:
        doc = chalna.translate(doc, target_languages)

    # --- per speaker: voices ---
    voices = resolve_voices(doc, engine, manual=manual_voices)

    # Anchor output length to the original timeline so trailing music/outro after
    # the last spoken segment is preserved (codex review P0-2).
    floor_sec = doc.source.duration or 0.0

    # --- fan out per language (synthesis batched across the doc) ---
    outputs: dict[str, str] = {}
    for lang in target_languages:
        missing = [s.index for s in doc.segments if lang not in s.text_target]
        if missing:
            raise ValueError(f"missing {lang} translation for segments {missing[:5]}...")
        items = [SynthItem(text=s.text_target[lang], language=lang, voice=voices[s.speaker_id]) for s in doc.segments]
        results = engine.synthesize_batch(items)
        clips = [w for w, _ in results]
        sr = results[0][1] if results else 24000

        track, meta = align.align_track(doc.segments, clips, sr, max_speedup=max_speedup, floor_sec=floor_sec)
        for m, seg in zip(meta, doc.segments):     # write alignment metadata back to the doc
            seg.fitted_speedup[lang] = m["speedup"]
            seg.overran[lang] = m["overran"]
        final = mix.mix(track, sr, doc.background_audio if keep_background else None, duck=duck, duck_db=duck_db)

        out_path = str(work / f"dub_{lang}.wav")
        sf.write(out_path, final, sr)
        outputs[lang] = out_path
    return outputs
