"""Shared test fixtures.

Testing strategy (decided in interview):
- CI runs only fast, deterministic, mock-based tests (no GPU): `pytest -m 'not gpu and not integration'`.
- Real Qwen3-TTS / audio-separator tests are marked `@pytest.mark.gpu` and run locally.
- chalna is replayed from recorded JSON fixtures (httpx mocked), not a live service.
- Heavy TTS validation uses the real model with tolerance (not a fake engine).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from jeoneum.schema import Segment

FIXTURES = Path(__file__).parent / "fixtures"


def _has_cuda() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    """Auto-skip @gpu tests when no CUDA is present, so local CPU runs stay green."""
    if _has_cuda():
        return
    skip_gpu = pytest.mark.skip(reason="no CUDA GPU available")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip_gpu)


@pytest.fixture
def seg():
    """Factory for Segments."""
    def _make(index: int, start: float, end: float, speaker: str = "0", text: str = "x") -> Segment:
        return Segment(index=index, start_time=start, end_time=end, speaker_id=speaker, text=text)

    return _make


@pytest.fixture
def tone():
    """Factory for a constant-amplitude mono clip of a given duration."""
    def _make(seconds: float, sr: int = 8000, amp: float = 0.5) -> np.ndarray:
        return np.full(int(seconds * sr), amp, dtype=np.float32)

    return _make


@pytest.fixture
def chalna_response() -> dict:
    """A recorded chalna /transcribe-style response (diarized, segment-level)."""
    return json.loads((FIXTURES / "chalna_sample.json").read_text())
