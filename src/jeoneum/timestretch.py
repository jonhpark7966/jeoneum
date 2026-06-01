"""Pitch-preserving time compression (WSOLA) for timing alignment.

Qwen3-TTS has no native speaking-rate control (the Base clone model is a pure
autoregressive codec LM with no speed/duration token and no instruction channel,
and it ignores the reference clip's tempo — QwenLM/Qwen3-TTS#290), so clips whose
translated speech runs longer than their slot must be compressed after synthesis.

We use **WSOLA** (audiotsm): time-domain, transient-preserving, and good for
speech — unlike a phase vocoder (e.g. librosa) which smears transients into a
"reverby" artifact. WSOLA is accurate at the pipeline's 24 kHz.

TODO: Rubber Band (`rubberband-cli` + `pyrubberband`) is higher quality still;
add it as an optional preferred backend when the CLI is available.
"""
from __future__ import annotations

import numpy as np


def time_compress(wav: np.ndarray, sr: int, rate: float) -> np.ndarray:
    """Speed speech up (rate>1 => shorter), pitch preserved, via WSOLA.
    Returns the input unchanged for rate<=1."""
    wav = np.asarray(wav, dtype=np.float32)
    if rate <= 1.0 or wav.size == 0:
        return wav

    from audiotsm import wsola
    from audiotsm.io.array import ArrayReader, ArrayWriter

    reader = ArrayReader(wav.reshape(1, -1))
    writer = ArrayWriter(channels=1)
    wsola(channels=1, speed=float(rate)).run(reader, writer)
    out = writer.data.flatten().astype(np.float32)
    return out if out.size else wav
