"""Integration tests against a LIVE chalna service (not mocked).

Run with chalna up (default CHALNA_URL=http://localhost:7861):
    python -m pytest -m integration -q
Skipped automatically if chalna is unreachable.
"""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from jeoneum.chalna_client import ChalnaClient

pytestmark = pytest.mark.integration

ASSETS = Path(__file__).parents[2] / "assets"


@pytest.fixture(scope="module")
def client():
    c = ChalnaClient()
    if not c.is_up():
        pytest.skip(f"chalna not reachable at {c.base_url}")
    return c


def test_doctor_reports_setup(client):
    try:
        report = client.doctor()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            pytest.skip("chalna /doctor not deployed yet — rebuild the chalna container")
        raise
    assert report["status"] in {"ok", "degraded", "error"}
    names = {c["name"] for c in report["checks"]}
    assert {"codex", "ffmpeg", "gpu"} <= names


# min_covered guards the early-EOS coverage fix: transcription must reach near the
# end of the clip (clips are ~17.1s and ~31.3s), not stop ~halfway.
@pytest.mark.parametrize("clip,min_covered", [("voice_2spk.wav", 15.0), ("voice_1spk.wav", 28.0)])
def test_transcribe_returns_doc(client, clip, min_covered):
    path = ASSETS / clip
    if not path.exists():
        pytest.skip(f"missing test clip {path}")
    doc = client.transcribe(str(path), use_llm_refinement=False)
    assert len(doc.segments) >= 1
    assert all(s.speaker_id for s in doc.segments)
    assert all(s.end_time >= s.start_time for s in doc.segments)
    assert doc.source.duration and doc.source.duration >= min_covered


def test_translate_fills_target(client):
    from jeoneum.schema import Doc, Segment, Source

    doc = Doc(
        source=Source(media="x", language="Korean"),
        segments=[
            Segment(index=1, start_time=0.0, end_time=1.0, speaker_id="0", text="안녕하세요"),
            Segment(index=2, start_time=1.0, end_time=2.0, speaker_id="0", text="감사합니다"),
        ],
    )
    doc = client.translate(doc, ["English"])
    assert all(s.text_target.get("English") for s in doc.segments)
