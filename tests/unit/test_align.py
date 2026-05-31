"""Deterministic tests for timing alignment (jeoneum.align)."""
from __future__ import annotations

import numpy as np

from jeoneum.align import align_track, fit_clip

SR = 8000


def test_fit_clip_short_is_untouched(tone):
    clip = tone(0.5, SR)
    fitted, overran = fit_clip(clip, SR, slot_sec=1.0, max_speedup=1.3)
    assert overran is False
    assert np.array_equal(fitted, clip)            # no stretch when it already fits


def test_fit_clip_compresses_within_cap(tone):
    clip = tone(1.2, SR)                            # needs 1.2x -> under cap
    fitted, overran = fit_clip(clip, SR, slot_sec=1.0, max_speedup=1.3)
    assert overran is False
    assert len(fitted) / SR == _approx(1.0, tol=0.05)   # ~fits the 1.0s slot


def test_fit_clip_caps_and_flags_overrun(tone):
    clip = tone(2.0, SR)                            # needs 2.0x -> exceeds 1.3 cap
    fitted, overran = fit_clip(clip, SR, slot_sec=1.0, max_speedup=1.3)
    assert overran is True
    assert len(fitted) / SR == _approx(2.0 / 1.3, tol=0.05)   # only compressed to the cap


def test_align_places_clips_at_start_times(seg, tone):
    segs = [seg(1, 0.0, 1.0), seg(2, 2.0, 3.0)]
    clips = [tone(0.5, SR), tone(0.5, SR)]
    track, meta = align_track(segs, clips, SR, max_speedup=1.3)

    assert _energy(track, 0.0, 0.5, SR) > 0         # clip 1 at 0.0s
    assert _energy(track, 0.6, 1.9, SR) == _approx(0.0, tol=1e-6)   # silent gap
    assert _energy(track, 2.0, 2.5, SR) > 0         # clip 2 at 2.0s
    assert all(m["overran"] is False for m in meta)


def test_align_floor_anchors_total_length(seg, tone):
    segs = [seg(1, 0.0, 1.0)]
    clips = [tone(0.5, SR)]
    track, _ = align_track(segs, clips, SR, floor_sec=5.0)
    assert len(track) >= 5 * SR                     # trailing timeline preserved


def test_align_overrun_flag_on_collision(seg, tone):
    segs = [seg(1, 0.0, 1.0), seg(2, 1.0, 2.0)]     # 1.0s slot for clip 1
    clips = [tone(2.0, SR), tone(0.5, SR)]          # clip 1 is 2.0s -> collides
    _, meta = align_track(segs, clips, SR, max_speedup=1.3)
    assert meta[0]["overran"] is True


def test_align_never_clips_above_headroom(seg, tone):
    segs = [seg(1, 0.0, 1.0), seg(2, 0.0, 1.0)]     # fully overlapping -> additive sum
    clips = [tone(1.0, SR, amp=0.9), tone(1.0, SR, amp=0.9)]
    track, _ = align_track(segs, clips, SR, headroom=0.97)
    assert float(np.max(np.abs(track))) <= 0.97 + 1e-6


# -- helpers --
class _approx:
    def __init__(self, val, tol):
        self.val, self.tol = val, tol

    def __eq__(self, other):
        return abs(other - self.val) <= self.tol


def _energy(track, t0, t1, sr):
    a, b = int(t0 * sr), int(t1 * sr)
    return float(np.sum(np.abs(track[a:b])))
