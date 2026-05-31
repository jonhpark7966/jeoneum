"""Voice profile registry — reuse the same voice for the same person across videos.

Maps a speaker fingerprint (embedding) to a stored reference clip / profile, so a
recurring speaker gets a consistent cloned voice. Storage form and the match
threshold are open (docs/spec.md §11.2).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VoiceProfile:
    profile_id: str
    ref_audio: str
    ref_text: str | None = None


class VoiceRegistry(ABC):
    @abstractmethod
    def match(self, embedding) -> VoiceProfile | None:
        """Return an existing profile if embedding is within threshold, else None."""

    @abstractmethod
    def add(self, embedding, ref_audio: str, ref_text: str | None = None) -> VoiceProfile:
        """Register a new voice profile and return it."""
