"""End-to-end pipeline test (GPU + live chalna).

Full dub: ingest -> chalna transcribe (early-EOS coverage) -> chalna translate
(codex) -> Qwen3-TTS voice clone (committed sample) -> start-time align -> mix.
Background separation is skipped (keep_background=False) so the run needs only
chalna + Qwen3-TTS. Validates real audio out at roughly the source duration.

Run locally:  python -m pytest tests/integration/test_pipeline_e2e.py -q
(Needs a GPU, `pip install -e external/Qwen3-TTS`, and a live chalna.)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

pytestmark = [pytest.mark.gpu, pytest.mark.integration]

ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "assets" / "voice_1spk.wav"
SAMPLE = ROOT / "tests" / "voice_samples" / "jb_english_instant_voice_clone.wav"


def test_dub_voice1_to_english(tmp_path):
    from jeoneum.chalna_client import ChalnaClient
    from jeoneum.pipeline import dub
    from jeoneum.schema import Voice

    if not ChalnaClient().is_up():
        pytest.skip("chalna not reachable")
    for p in (SOURCE, SAMPLE):
        if not p.exists():
            pytest.skip(f"missing {p}")

    outputs = dub(
        str(SOURCE),
        ["English"],
        str(tmp_path),
        keep_background=False,
        manual_voices={"0": Voice(mode="manual", ref_audio=str(SAMPLE))},
    )

    assert set(outputs) == {"English"}
    wav, sr = sf.read(outputs["English"])
    duration = len(wav) / sr
    assert 20.0 < duration < 45.0                      # ~ source (31s) + alignment tail
    assert float(np.sqrt(np.mean(wav ** 2))) > 1e-3    # real audio, not silence
