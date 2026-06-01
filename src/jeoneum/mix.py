"""Stage 6 — mix the dubbed voice track over the preserved background.

By default the background (Instrumental stem) plays unchanged under the dubbed
voice. Ducking is OPT-IN (`duck=True`) with an adjustable attenuation (`duck_db`):
when enabled, the background is lowered while the dubbed voice is active so speech
stays intelligible. A more refined sidechain compressor is a later refinement
(docs/spec.md §6).
"""
from __future__ import annotations

import numpy as np
import soundfile as sf
import soxr


def _voice_envelope(voice: np.ndarray, sr: int, win_ms: float = 50.0) -> np.ndarray:
    win = max(1, int(sr * win_ms / 1000))
    energy = np.convolve(np.abs(voice), np.ones(win) / win, mode="same")
    peak = float(energy.max()) or 1.0
    return energy / peak                              # 0..1 activity


def mix(
    voice: np.ndarray,
    sr: int,
    background_path: str | None,
    *,
    duck: bool = False,
    duck_db: float = -12.0,
) -> np.ndarray:
    """Return voice mixed over the background.

    duck=False (default): background plays unchanged under the voice.
    duck=True: background is attenuated by `duck_db` while the voice is active.
    """
    if not background_path:
        return voice                                 # full-replacement fallback

    bg, file_sr = sf.read(background_path, dtype="float32", always_2d=False)
    if bg.ndim > 1:
        bg = bg.mean(axis=1)
    if file_sr != sr:
        bg = soxr.resample(bg, file_sr, sr).astype(np.float32)
    bg = bg.astype(np.float32)
    # Anchor to the FULL timeline: keep the longer of the two so trailing
    # background (outro/music after the last spoken segment) is preserved.
    n = max(len(voice), len(bg))
    voice = np.pad(voice, (0, n - len(voice)))
    bg = np.pad(bg, (0, n - len(bg)))

    if duck:
        ducked = 10 ** (duck_db / 20.0)              # gain while voice is active
        act = _voice_envelope(voice, sr)
        bg_gain = 1.0 - (1.0 - ducked) * act         # 1.0 in silence -> ducked under speech
    else:
        bg_gain = 1.0                                # default: background unchanged

    out = voice + bg * bg_gain
    # NOTE: loudness/limiter policy (LUFS target, true-peak) is an open item
    # (spec §11) — for now only protect against hard clipping.
    peak = float(np.max(np.abs(out))) or 1.0
    if peak > 1.0:
        out /= peak
    return out
