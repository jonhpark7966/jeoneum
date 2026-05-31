"""Load a subtitle file (SRT or chalna-style JSON) into a canonical Doc.

Used for the subtitle entry point (docs/spec.md §2/§3): a source `.srt`/`.json`
enters the pipeline at the translate stage (or straight to synthesis when the subs
are already in the target language). SRT cues may carry a `[speaker]` prefix
(chalna's format); otherwise all cues are speaker "0".
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .schema import Doc, Segment, Source

_TS = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{3})")
_SPK = re.compile(r"^\[([^\]]+)\]\s*")


def _ts_to_sec(ts: str) -> float:
    h, m, s, ms = _TS.match(ts).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(text: str) -> list[Segment]:
    segments: list[Segment] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if lines[0].strip().isdigit():
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        a, b = lines[0].split("-->")
        start, end = _ts_to_sec(a.strip()), _ts_to_sec(b.strip())
        body = " ".join(lines[1:]).strip()
        speaker = "0"
        m = _SPK.match(body)
        if m:
            speaker = m.group(1).strip()
            body = body[m.end():].strip()
        if body:
            segments.append(
                Segment(index=len(segments) + 1, start_time=start, end_time=end,
                        speaker_id=speaker, text=body)
            )
    return segments


def _segments_from_json(data: dict) -> list[Segment]:
    segs = data.get("segments") or data.get("result", {}).get("segments", [])
    return [
        Segment(
            index=s["index"], start_time=s["start_time"], end_time=s["end_time"],
            speaker_id=str(s.get("speaker_id", "0")), text=s["text"],
            confidence=s.get("confidence"),
        )
        for s in segs
    ]


def _sec_to_ts(t: float) -> str:
    ms_total = int(round(max(t, 0.0) * 1000))   # round once, then split — no 00:00:60 spillover
    h, rem = divmod(ms_total, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1_000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list, path: str, text_for) -> str:
    """Write segments to an SRT file. `text_for(segment)` returns the cue text
    (skip the cue if it returns empty)."""
    blocks, idx = [], 1
    for seg in segments:
        txt = (text_for(seg) or "").strip()
        if not txt:
            continue
        blocks.append(f"{idx}\n{_sec_to_ts(seg.start_time)} --> {_sec_to_ts(seg.end_time)}\n{txt}\n")
        idx += 1
    Path(path).write_text("\n".join(blocks), encoding="utf-8")
    return path


def load_subtitle_doc(path: str) -> Doc:
    """Parse an SRT/JSON subtitle file into a Doc (no audio; duration = last cue end)."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        segments = _segments_from_json(json.loads(p.read_text(encoding="utf-8")))
    else:
        segments = parse_srt(p.read_text(encoding="utf-8-sig"))
    duration = max((s.end_time for s in segments), default=0.0)
    return Doc(source=Source(media=str(path), duration=duration), segments=segments)
