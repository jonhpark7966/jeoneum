"""TTSEngine abstraction. Batch synthesis is first-class (see docs/spec.md §6/§10):
one GPU = one model instance; segments across languages are batched, not
parallelized across instances. Online concurrent serving (vLLM-Omni) is not yet
GA, so the contract is batch-oriented and an online backend can be added later.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import numpy as np


class VoiceHandle:
    """Opaque, engine-specific handle for a prepared (cloned) voice."""

    def __init__(self, payload: Any):
        self.payload = payload


@dataclass
class SynthItem:
    text: str
    language: str
    voice: VoiceHandle


class TTSEngine(ABC):
    @abstractmethod
    def build_voice(self, ref_audio: Any, ref_text: str | None = None) -> VoiceHandle:
        """Prepare a reusable voice from a reference clip (cross-lingual ok)."""

    @abstractmethod
    def synthesize_batch(self, items: list[SynthItem]) -> list[tuple[np.ndarray, int]]:
        """Synthesize a batch. Returns one (waveform, sample_rate) per item, in order."""
