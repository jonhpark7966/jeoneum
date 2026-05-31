"""Canonical interchange schema (extends chalna's segment JSON).

Every pipeline stage reads/writes a `Doc`. chalna's original fields
(index, start_time, end_time, text, speaker_id, confidence) are preserved;
jeoneum adds target-language and synthesis fields keyed by language code.
See docs/spec.md §4.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Voice(BaseModel):
    mode: Literal["auto", "manual"] = "auto"
    ref_audio: Optional[str] = None
    ref_text: Optional[str] = None
    profile_id: Optional[str] = None  # voice-registry key, if reused across videos


class Segment(BaseModel):
    index: int
    start_time: float
    end_time: float
    speaker_id: str
    text: str                                   # source language
    confidence: Optional[float] = None
    # populated downstream, keyed by target language code:
    text_target: dict[str, str] = Field(default_factory=dict)
    audio: dict[str, str] = Field(default_factory=dict)
    fitted_speedup: dict[str, float] = Field(default_factory=dict)
    overran: dict[str, bool] = Field(default_factory=dict)


class Source(BaseModel):
    media: str
    language: Optional[str] = None
    duration: Optional[float] = None


class Doc(BaseModel):
    source: Source
    target_languages: list[str] = Field(default_factory=list)
    background_audio: Optional[str] = None      # Instrumental stem (preserved)
    vocals_audio: Optional[str] = None          # Vocals stem (for ref extraction)
    voices: dict[str, Voice] = Field(default_factory=dict)  # speaker_id -> Voice
    segments: list[Segment] = Field(default_factory=list)
