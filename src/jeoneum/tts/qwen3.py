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

# Qwen3-TTS expects language NAMES (e.g. "English"), not ISO codes ("en").
_LANG_NAMES = {
    "en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese",
    "de": "German", "fr": "French", "ru": "Russian", "pt": "Portuguese",
    "es": "Spanish", "it": "Italian",
}


def _normalize_language(language: str) -> str:
    """Map an ISO code to a Qwen3 language name; pass through names unchanged."""
    if not language:
        return "Auto"
    return _LANG_NAMES.get(language.strip().lower(), language)


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

    def synthesize_batch(self, items: list[SynthItem], batch_size: int = 8) -> list[tuple[np.ndarray, int]]:
        # Chunk so long inputs (many segments) don't OOM the GPU in one generate call.
        out: list[tuple[np.ndarray, int]] = []
        for i in range(0, len(items), batch_size):
            chunk = items[i : i + batch_size]
            wavs, sr = self._model.generate_voice_clone(
                text=[it.text for it in chunk],
                language=[_normalize_language(it.language) for it in chunk],
                voice_clone_prompt=[it.voice.payload for it in chunk],
            )
            out.extend((np.asarray(w, dtype=np.float32), sr) for w in wavs)
        return out
