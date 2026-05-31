"""Real Qwen3-TTS smoke test (GPU, real model + tolerance).

Decided strategy: validate the actual engine, not a fake one, asserting loose
invariants (returns audio of plausible length at the model sample rate) rather
than exact waveforms — TTS output is non-deterministic.

Runs only with a GPU and `pip install -e external/Qwen3-TTS`.
Reference clip is provided via the JEONEUM_TEST_REF env var (path/URL); skipped if unset.
"""
from __future__ import annotations

import os

import numpy as np
import pytest

pytestmark = pytest.mark.gpu

REF = os.environ.get("JEONEUM_TEST_REF")


@pytest.mark.skipif(not REF, reason="set JEONEUM_TEST_REF to a reference audio path/URL")
def test_synthesize_batch_returns_audio():
    from jeoneum.tts.base import SynthItem
    from jeoneum.tts.qwen3 import Qwen3Engine

    engine = Qwen3Engine()
    voice = engine.build_voice(ref_audio=REF, ref_text=None)   # x-vector-only is fine for a smoke test
    items = [
        SynthItem(text="This is a short dubbing test.", language="English", voice=voice),
        SynthItem(text="Another sentence to dub.", language="English", voice=voice),
    ]
    results = engine.synthesize_batch(items)

    assert len(results) == 2
    for wav, sr in results:
        assert isinstance(wav, np.ndarray) and wav.ndim == 1
        assert sr > 0
        assert 0.2 < len(wav) / sr < 30.0          # plausible duration (loose tolerance)
