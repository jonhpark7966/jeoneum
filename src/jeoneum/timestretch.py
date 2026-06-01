"""Pitch-preserving time compression for timing alignment.

Qwen3-TTS has no native speaking-rate control (the Base clone model is a pure
autoregressive codec LM with no duration/speed token and no instruction channel,
and it ignores the reference clip's tempo — QwenLM/Qwen3-TTS#290). So clips that
run longer than their slot must be compressed after synthesis. librosa's phase
vocoder smears transients and adds a phasey/"reverby" artifact on speech, so we
prefer a higher-quality backend:

  Rubber Band  (best; needs the `rubberband` CLI: `apt install rubberband-cli`)
  -> WSOLA     (audiotsm; pip-only, time-domain, good for speech)
  -> librosa   (phase vocoder; last-resort fallback)
"""
from __future__ import annotations

import numpy as np


def _rubberband(wav: np.ndarray, sr: int, rate: float) -> np.ndarray:
    import pyrubberband

    return np.asarray(pyrubberband.time_stretch(wav, sr, rate), dtype=np.float32)


def _wsola(wav: np.ndarray, sr: int, rate: float) -> np.ndarray:
    from audiotsm import wsola
    from audiotsm.io.array import ArrayReader, ArrayWriter

    reader = ArrayReader(wav.reshape(1, -1).astype(np.float32))
    writer = ArrayWriter(channels=1)
    wsola(channels=1, speed=float(rate)).run(reader, writer)
    return writer.data.flatten().astype(np.float32)


def _librosa(wav: np.ndarray, sr: int, rate: float) -> np.ndarray:
    import librosa

    return librosa.effects.time_stretch(wav.astype(np.float32), rate=float(rate))


_BACKENDS = (_rubberband, _wsola, _librosa)


def time_compress(wav: np.ndarray, sr: int, rate: float) -> np.ndarray:
    """Speed speech up (rate>1 => shorter), pitch preserved, via the best available
    backend. Returns the input unchanged for rate<=1."""
    wav = np.asarray(wav, dtype=np.float32)
    if rate <= 1.0 or wav.size == 0:
        return wav
    for backend in _BACKENDS:
        try:
            out = backend(wav, sr, rate)
            if out is not None and len(out) > 0:
                return out.astype(np.float32)
        except Exception:
            continue
    return wav


def active_backend() -> str:
    """Name of the backend that would be used (for diagnostics/health)."""
    probe = np.zeros(2048, dtype=np.float32)
    for backend in _BACKENDS:
        try:
            backend(probe, 24000, 1.2)
            return backend.__name__.lstrip("_")
        except Exception:
            continue
    return "none"
