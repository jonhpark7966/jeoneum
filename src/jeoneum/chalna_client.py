"""Client for the chalna service (stages 1 transcribe + 2 translate).

chalna runs as a separate REST service on the compose network. jeoneum health-checks
it and brings it up via docker compose if it is not already running (docs/spec.md §2).

NOTE: chalna's translate endpoint is a chalna-side TODO (spec §11.5). The transcribe
contract mirrors chalna's existing /transcribe; translate is a placeholder until the
chalna API is finalized.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx

from .schema import Doc, Segment, Source


class ChalnaClient:
    def __init__(
        self,
        base_url: str | None = None,
        compose_service: str = "chalna",
        health_path: str = "/docs",
        auto_start: bool = True,
    ):
        # On the compose network use http://chalna:7861 (CHALNA_URL); the localhost
        # default is for host-side runs only.
        self.base_url = (base_url or os.environ.get("CHALNA_URL", "http://localhost:7861")).rstrip("/")
        self.compose_service = compose_service
        self.health_path = health_path
        self.auto_start = auto_start

    # -- lifecycle -----------------------------------------------------------
    def is_up(self) -> bool:
        try:
            # require a real 200 — `< 500` wrongly treats 404 as healthy (codex P1-11)
            return httpx.get(f"{self.base_url}{self.health_path}", timeout=2.0).status_code == 200
        except httpx.HTTPError:
            return False

    def ensure_up(self, timeout_s: float = 120.0) -> None:
        # Already running -> just use it; only auto-start when down (and allowed).
        if self.is_up():
            return
        if not self.auto_start:
            raise RuntimeError(f"chalna not reachable at {self.base_url} (auto_start disabled)")
        # NOTE: auto-start assumes a host-side run with a compose project present;
        # inside a container, rely on compose `depends_on` instead.
        subprocess.run(["docker", "compose", "up", "-d", self.compose_service], check=True)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.is_up():
                return
            time.sleep(2.0)
        raise RuntimeError(f"chalna did not become healthy at {self.base_url}")

    # -- diagnostics ---------------------------------------------------------
    def doctor(self) -> dict:
        """Return chalna's /doctor report (setup checks: codex, ffmpeg, gpu, ...)."""
        r = httpx.get(f"{self.base_url}/doctor", timeout=15.0)
        r.raise_for_status()
        return r.json()

    # -- stages --------------------------------------------------------------
    def transcribe(
        self,
        audio_path: str,
        *,
        language: str | None = None,
        context: str | None = None,
        include_speaker: bool = True,
        use_alignment: bool = True,
        use_llm_refinement: bool = True,
        timeout: float = 1200.0,
    ) -> Doc:
        """Transcribe + diarize via chalna /transcribe (json). Maps to a Doc."""
        data = {
            "output_format": "json",
            "include_speaker": str(include_speaker).lower(),
            "use_alignment": str(use_alignment).lower(),
            "use_llm_refinement": str(use_llm_refinement).lower(),
        }
        if language:
            data["language"] = language
        if context:
            data["context"] = context
        with open(audio_path, "rb") as fh:
            files = {"file": (Path(audio_path).name, fh)}
            r = httpx.post(f"{self.base_url}/transcribe", data=data, files=files, timeout=timeout)
        r.raise_for_status()
        return self._to_doc(audio_path, r.json())

    @staticmethod
    def _to_doc(audio_path: str, payload: dict) -> Doc:
        meta = payload.get("metadata", {})
        segments = [
            Segment(
                index=s["index"],
                start_time=s["start_time"],
                end_time=s["end_time"],
                speaker_id=str(s.get("speaker_id", "0")),
                text=s["text"],
                confidence=s.get("confidence"),
            )
            for s in payload.get("segments", [])
        ]
        return Doc(
            source=Source(media=audio_path, language=meta.get("language"), duration=meta.get("duration")),
            segments=segments,
        )

    def translate(self, doc: Doc, target_languages: list[str]) -> Doc:
        # Hard dependency on chalna (no jeoneum fallback). chalna has no /translate
        # endpoint yet — this is the chalna-side TODO (spec §11.4).
        raise NotImplementedError("chalna /translate not implemented yet (chalna-side TODO)")
