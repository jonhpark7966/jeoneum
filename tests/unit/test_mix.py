"""Tests for jeoneum.mix — background preservation, length anchoring, ducking."""
from __future__ import annotations

import numpy as np
import soundfile as sf

from jeoneum.mix import mix

SR = 8000


def _bg_file(tmp_path, seconds: float, amp: float = 0.3) -> str:
    p = tmp_path / "bg.wav"
    sf.write(p, np.full(int(seconds * SR), amp, dtype=np.float32), SR)
    return str(p)


def test_no_background_returns_voice_unchanged():
    voice = np.full(1000, 0.4, dtype=np.float32)
    out = mix(voice, SR, None)
    assert np.array_equal(out, voice)


def test_anchors_to_longer_background(tmp_path):
    voice = np.full(SR, 0.5, dtype=np.float32)      # 1.0s
    out = mix(voice, SR, _bg_file(tmp_path, 2.0))   # bg 2.0s
    assert len(out) == 2 * SR                       # trailing background kept


def test_duck_off_leaves_background_unchanged(tmp_path):
    voice = np.concatenate([np.zeros(SR, np.float32), np.full(SR, 0.5, np.float32)])  # silent then active
    out = mix(voice, SR, _bg_file(tmp_path, 2.0, amp=0.3), duck=False)
    # silent region: only the unchanged background
    assert float(np.mean(out[: SR // 2])) == _approx(0.3, tol=0.02)
    # active region: voice + full background
    assert float(np.mean(out[SR + SR // 4 : SR + SR // 2])) == _approx(0.8, tol=0.05)


def test_duck_on_attenuates_background_under_voice(tmp_path):
    voice = np.concatenate([np.zeros(SR, np.float32), np.full(SR, 0.5, np.float32)])
    bg = _bg_file(tmp_path, 2.0, amp=0.3)
    active = slice(SR + SR // 2, SR + SR // 2 + 100)
    out_off = mix(voice, SR, bg, duck=False)
    out_on = mix(voice, SR, bg, duck=True, duck_db=-12.0)
    assert float(np.mean(out_on[active])) < float(np.mean(out_off[active]))


def test_no_hard_clipping(tmp_path):
    voice = np.full(SR, 0.9, dtype=np.float32)
    out = mix(voice, SR, _bg_file(tmp_path, 1.0, amp=0.9), duck=False)
    assert float(np.max(np.abs(out))) <= 1.0 + 1e-6


class _approx:
    def __init__(self, val, tol):
        self.val, self.tol = val, tol

    def __eq__(self, other):
        return abs(other - self.val) <= self.tol
