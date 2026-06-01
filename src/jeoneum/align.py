"""Stage 5 — start-time alignment.

Policy (docs/spec.md §8): place each clip at its segment start; gaps stay silent.
A clip is compressed (pitch-preserved) only when it would collide with the next
segment's start, capped at `max_speedup`; any remainder is allowed to overlap.
TTS cannot hit an exact target duration, so collision-free output is not
guaranteed by construction — rare overlaps are accepted.

Ported from the validated PoC: Qwen3-TTS/examples/dub_from_srt.py.
"""
from __future__ import annotations

import numpy as np

from .schema import Segment
from .timestretch import time_compress


def fit_clip(wav: np.ndarray, sr: int, slot_sec: float, max_speedup: float) -> tuple[np.ndarray, bool]:
    """Compress wav to fit slot_sec (capped at max_speedup). Never stretches a short clip."""
    clip_sec = len(wav) / sr
    if slot_sec <= 0 or clip_sec <= slot_sec:
        return wav, False
    needed = clip_sec / slot_sec               # >1 => must speed up
    rate = min(needed, max_speedup)            # rate>1 -> faster/shorter
    fitted = time_compress(wav.astype(np.float32), sr, rate)
    return fitted, needed > max_speedup


def align_track(
    segments: list[Segment],
    clips: list[np.ndarray],
    sr: int,
    max_speedup: float = 1.3,
    tail_sec: float = 1.0,
    floor_sec: float = 0.0,
    headroom: float = 0.97,
) -> tuple[np.ndarray, list[dict]]:
    """Lay clips on one track by segment start_time. Returns (track, per-segment meta).

    `floor_sec` keeps the track at least this long (anchor to the original media
    duration so trailing music/outro is preserved by the later mix). `headroom`
    normalizes only when the additive overlap clips, leaving room for the mix.
    """
    if len(clips) != len(segments):
        raise ValueError(f"clip/segment count mismatch: {len(clips)} clips vs {len(segments)} segments")
    placements, meta = [], []
    for i, (seg, wav) in enumerate(zip(segments, clips)):
        next_start = segments[i + 1].start_time if i + 1 < len(segments) else None
        slot = (next_start - seg.start_time) if next_start is not None else float("inf")
        fitted, overran = fit_clip(wav, sr, slot, max_speedup)
        placements.append((seg.start_time, fitted))
        meta.append({"index": seg.index, "speedup": len(wav) / max(len(fitted), 1), "overran": overran})

    clip_end = max((p[0] + len(p[1]) / sr for p in placements), default=0.0) + tail_sec
    total_sec = max(clip_end, floor_sec)
    track = np.zeros(int(total_sec * sr) + 1, dtype=np.float32)
    for start, fitted in placements:
        off = int(round(start * sr))
        end = off + len(fitted)
        if end > len(track):
            track = np.concatenate([track, np.zeros(end - len(track), dtype=np.float32)])
        track[off:end] += fitted               # additive mix tolerates slight overlap

    peak = float(np.max(np.abs(track))) if track.size else 0.0
    if peak > headroom:
        track *= headroom / peak               # only scale down on clipping, keep headroom
    return track, meta
