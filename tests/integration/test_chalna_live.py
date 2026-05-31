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


@pytest.mark.parametrize("clip", ["voice_2spk.wav", "voice_1spk.wav"])
def test_transcribe_returns_doc(client, clip):
    path = ASSETS / clip
    if not path.exists():
        pytest.skip(f"missing test clip {path}")
    doc = client.transcribe(str(path), use_llm_refinement=False)
    assert len(doc.segments) >= 1
    assert doc.source.duration and doc.source.duration > 0
    assert all(s.speaker_id for s in doc.segments)
    # segments are time-ordered and non-degenerate
    assert all(s.end_time >= s.start_time for s in doc.segments)
