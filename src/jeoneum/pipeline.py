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

from . import align, ingest, mix, subtitles
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
    progress=None,
) -> dict[str, str]:
    """Run the pipeline. Returns {language: output_wav_path}.

    Also writes subtitles into `outdir`: `transcript.srt` (source language) and
    `dub_<lang>.srt` (translated) per target language. `progress` is an optional
    callback(stage: str) invoked at each stage for monitoring.
    """
    work = Path(outdir)
    work.mkdir(parents=True, exist_ok=True)
    chalna = ChalnaClient()
    engine = engine or Qwen3Engine()

    def _p(stage: str) -> None:
        if progress:
            progress(stage)

    # --- build the Doc: from a subtitle file, or by ingesting + transcribing audio ---
    manual = manual_voices or {}
    is_subs = source.lower().endswith((".srt", ".json"))
    if is_subs:
        # Subtitle entry (docs/spec.md §3): no audio -> no background; the voice must
        # be manual (a single voice covers all speakers).
        keep_background = False
        _p("loading subtitles")
        doc = subtitles.load_subtitle_doc(source)
        doc.target_languages = target_languages
        if subs_translated:
            if len(target_languages) != 1:
                raise ValueError(
                    "--subs-translated requires exactly one target language "
                    "(the language the subtitles are already written in)"
                )
            lang = target_languages[0]
            for s in doc.segments:
                s.text_target.setdefault(lang, s.text)
        else:
            chalna.ensure_up()
            _p("translating")
            doc = chalna.translate(doc, target_languages)
    else:
        _p("ingesting")
        wav = ingest.ingest(source, str(work / "ingest"))
        chalna.ensure_up()
        _p("transcribing")
        doc = chalna.transcribe(wav)
        doc.target_languages = target_languages

        # Separation is needed for background preservation AND for auto voice cloning
        # (vocals stem -> per-speaker ref). A single manual voice covers all speakers
        # (voices.resolve_voices), so no vocals stem is needed in that case.
        single_voice = len(manual) == 1
        need_vocals = not single_voice and any(s.speaker_id not in manual for s in doc.segments)
        if keep_background or need_vocals:
            _p("separating")
            vocals, background = AudioSeparator().separate(wav, str(work / "sep"))
            doc.vocals_audio = vocals
            if keep_background:
                doc.background_audio = background

        if not subs_translated:
            _p("translating")
            doc = chalna.translate(doc, target_languages)

    # Source-language transcript subtitle (e.g. Korean).
    subtitles.write_srt(doc.segments, str(work / "transcript.srt"), lambda s: s.text)

    # --- per speaker: voices ---
    _p("preparing voices")
    voices = resolve_voices(doc, engine, manual=manual, workdir=str(work / "refs"))

    # Anchor output length to the original timeline so trailing music/outro after
    # the last spoken segment is preserved (codex review P0-2).
    floor_sec = doc.source.duration or 0.0

    # --- fan out per language (synthesis batched across the doc) ---
    outputs: dict[str, str] = {}
    for lang in target_languages:
        missing = [s.index for s in doc.segments if lang not in s.text_target]
        if missing:
            raise ValueError(f"missing {lang} translation for segments {missing[:5]}...")
        # Translated subtitle for this language.
        subtitles.write_srt(doc.segments, str(work / f"dub_{lang}.srt"), lambda s: s.text_target.get(lang, ""))

        _p(f"synthesizing:{lang}")
        items = [SynthItem(text=s.text_target[lang], language=lang, voice=voices[s.speaker_id]) for s in doc.segments]
        results = engine.synthesize_batch(items)
        clips = [w for w, _ in results]
        sr = results[0][1] if results else 24000

        _p(f"aligning:{lang}")
        track, meta = align.align_track(doc.segments, clips, sr, max_speedup=max_speedup, floor_sec=floor_sec)
        for m, seg in zip(meta, doc.segments):     # write alignment metadata back to the doc
            seg.fitted_speedup[lang] = m["speedup"]
            seg.overran[lang] = m["overran"]
        _p(f"mixing:{lang}")
        final = mix.mix(track, sr, doc.background_audio if keep_background else None, duck=duck, duck_db=duck_db)

        out_path = str(work / f"dub_{lang}.wav")
        sf.write(out_path, final, sr)
        outputs[lang] = out_path
    return outputs
