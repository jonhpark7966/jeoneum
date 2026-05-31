"""SRT/JSON subtitle loading (deterministic, no GPU)."""
from __future__ import annotations

import json

from jeoneum.subtitles import load_subtitle_doc, parse_srt


def test_parse_srt_with_and_without_speaker():
    srt = (
        "1\n00:00:00,000 --> 00:00:02,200\n[2] Hello there.\n\n"
        "2\n00:00:02,500 --> 00:00:05,000\nNo speaker prefix here.\n"
    )
    segs = parse_srt(srt)
    assert len(segs) == 2
    assert segs[0].speaker_id == "2" and segs[0].text == "Hello there."
    assert segs[0].start_time == 0.0 and abs(segs[0].end_time - 2.2) < 1e-6
    assert segs[1].speaker_id == "0" and segs[1].text == "No speaker prefix here."
    assert [s.index for s in segs] == [1, 2]


def test_load_subtitle_doc_json(tmp_path):
    p = tmp_path / "subs.json"
    p.write_text(json.dumps({"segments": [
        {"index": 1, "start_time": 0.0, "end_time": 1.5, "text": "hi", "speaker_id": "1"},
    ]}), encoding="utf-8")
    doc = load_subtitle_doc(str(p))
    assert len(doc.segments) == 1
    assert doc.segments[0].speaker_id == "1"
    assert doc.source.duration == 1.5
