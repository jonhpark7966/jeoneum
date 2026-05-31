"""Real Qwen3-TTS smoke test (GPU, real model + tolerance).

Validates the actual engine (not a fake one), asserting loose invariants — TTS
output is non-deterministic, so we check plausible audio length, not waveforms.
Uses the committed voice sample (tests/voice_samples/) as the clone reference.

Runs only with a GPU and `pip install -e external/Qwen3-TTS`.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.gpu

SAMPLE = Path(__file__).parents[1] / "voice_samples" / "jb_english_instant_voice_clone.wav"


def test_voice_clone_synthesize_batch():
    from jeoneum.tts.base import SynthItem
    from jeoneum.tts.qwen3 import Qwen3Engine
    from jeoneum.voices import _resolve_ref_text
    from jeoneum.schema import Voice

    if not SAMPLE.exists():
        pytest.skip(f"missing voice sample {SAMPLE}")

    ref_text = _resolve_ref_text(Voice(ref_audio=str(SAMPLE)))  # from sidecar .txt
    engine = Qwen3Engine()
    voice = engine.build_voice(ref_audio=str(SAMPLE), ref_text=ref_text)
    items = [
        SynthItem(text="This is a short dubbing test.", language="English", voice=voice),
        SynthItem(text="Another sentence to dub, a bit longer than the first.", language="English", voice=voice),
    ]
    results = engine.synthesize_batch(items)

    assert len(results) == 2
    for wav, sr in results:
        assert isinstance(wav, np.ndarray) and wav.ndim == 1
        assert sr > 0
        assert 0.2 < len(wav) / sr < 30.0          # plausible duration (loose tolerance)
