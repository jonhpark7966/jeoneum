"""End-to-end pipeline test (GPU + live chalna). Scaffold.

Blocked until the chalna client stages (transcribe/translate) are wired against a
real chalna service. Until then this documents the intended e2e assertions and is
skipped. Run locally with a GPU, a live chalna, and a small real clip in assets/.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.gpu, pytest.mark.integration]


@pytest.mark.skip(reason="needs chalna_client.transcribe/translate wired (spec §11.4) + live chalna")
def test_dub_short_clip_keeps_timeline(tmp_path):
    from jeoneum.pipeline import dub

    outputs = dub("assets/sample_short.mp4", ["en"], str(tmp_path), keep_background=True)
    assert set(outputs) == {"en"}
    # intended invariants (real model + tolerance):
    # - output duration ~= source duration (timeline preserved, trailing audio kept)
    # - no hard clipping
    # - one track per requested language
