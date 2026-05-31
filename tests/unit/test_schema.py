"""Canonical schema round-trip + per-language field behavior."""
from __future__ import annotations

from jeoneum.schema import Doc, Segment, Source, Voice


def test_doc_roundtrip_preserves_per_language_fields():
    doc = Doc(
        source=Source(media="in.mp4", language="ko", duration=12.3),
        target_languages=["en", "ja"],
        voices={"0": Voice(mode="auto", ref_audio="r.wav")},
        segments=[
            Segment(
                index=1, start_time=0.5, end_time=2.0, speaker_id="0", text="안녕",
                text_target={"en": "Hi", "ja": "やあ"},
                fitted_speedup={"en": 1.1}, overran={"en": False},
            )
        ],
    )
    restored = Doc.model_validate_json(doc.model_dump_json())
    assert restored == doc
    assert restored.segments[0].text_target["ja"] == "やあ"


def test_build_doc_from_chalna_response(chalna_response):
    """The recorded chalna fixture maps cleanly onto segment-level fields."""
    segs = [Segment(**s) for s in chalna_response["result"]["segments"]]
    assert [s.speaker_id for s in segs] == ["0", "0", "1"]
    assert segs[0].text_target == {}                 # not yet translated
