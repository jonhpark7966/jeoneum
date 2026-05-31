"""Stage ⓿ — source separation (vocals / background).

Background (Instrumental stem) is preserved for the final ducked mix; the Vocals
stem feeds per-speaker reference extraction. Uses audio-separator (nomadkaraoke)
with a BS-Roformer model. See docs/spec.md §10 for the GPU/onnxruntime coexistence risk.

Install:  pip install ".[gpu]"   (or ".[cpu]")
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

DEFAULT_MODEL = "model_bs_roformer_ep_317_sdr_12.9755.ckpt"


class Separator(ABC):
    @abstractmethod
    def separate(self, wav_path: str, outdir: str) -> tuple[str, str]:
        """Return (vocals_path, background_path)."""


class AudioSeparator(Separator):
    def __init__(self, model_filename: str = DEFAULT_MODEL):
        self._model_filename = model_filename
        self._sep = None

    def _ensure(self, outdir: str):
        if self._sep is None:
            from audio_separator.separator import Separator as _S

            self._sep = _S(output_dir=outdir)
            self._sep.load_model(model_filename=self._model_filename)

    def separate(self, wav_path: str, outdir: str) -> tuple[str, str]:
        Path(outdir).mkdir(parents=True, exist_ok=True)
        self._ensure(outdir)
        outputs = [str(Path(outdir) / f) for f in self._sep.separate(wav_path)]
        vocals = next(p for p in outputs if "(Vocals)" in p)
        background = next(p for p in outputs if "(Vocals)" not in p)  # Instrumental
        return vocals, background
