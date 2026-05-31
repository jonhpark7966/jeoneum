"""Qwen3-TTS engine (in-process). Wraps the qwen-tts package from the
`external/Qwen3-TTS` submodule. Voice cloning is cross-lingual: a Korean
reference clip can drive English (or any supported language) output.

Install the engine:  pip install -e external/Qwen3-TTS
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .base import SynthItem, TTSEngine, VoiceHandle

DEFAULT_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"


class Qwen3Engine(TTSEngine):
    def __init__(self, model: str = DEFAULT_MODEL, device: str = "cuda:0", dtype: str = "bfloat16"):
        import torch
        from qwen_tts import Qwen3TTSModel

        self._model = Qwen3TTSModel.from_pretrained(
            model,
            device_map=device,
            dtype=getattr(torch, dtype),
            attn_implementation="eager",
        )

    def build_voice(self, ref_audio: Any, ref_text: str | None = None) -> VoiceHandle:
        # ref_text=None -> x-vector-only mode (lower quality, no transcript needed)
        item = self._model.create_voice_clone_prompt(
            ref_audio=ref_audio,
            ref_text=ref_text,
            x_vector_only_mode=ref_text is None,
        )[0]
        return VoiceHandle(item)

    def synthesize_batch(self, items: list[SynthItem]) -> list[tuple[np.ndarray, int]]:
        if not items:
            return []
        wavs, sr = self._model.generate_voice_clone(
            text=[it.text for it in items],
            language=[it.language for it in items],
            voice_clone_prompt=[it.voice.payload for it in items],
        )
        return [(np.asarray(w, dtype=np.float32), sr) for w in wavs]
