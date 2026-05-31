"""Jeoneum (전음) — speaker-preserving multilingual dubbing pipeline.

Orchestrates: chalna (transcribe + translate) -> source separation ->
per-speaker voice-cloned TTS -> start-time alignment -> background-ducked mix.
See docs/spec.md for the full architecture.
"""

__version__ = "0.0.1"
