"""Pluggable TTS engines. Default: Qwen3-TTS (in-process)."""
from .base import SynthItem, TTSEngine, VoiceHandle

__all__ = ["TTSEngine", "VoiceHandle", "SynthItem"]
