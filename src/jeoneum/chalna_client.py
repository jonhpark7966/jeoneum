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

import httpx

from .schema import Doc


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

    # -- stages --------------------------------------------------------------
    def transcribe(self, wav_path: str, **opts) -> Doc:
        raise NotImplementedError("wire to chalna /transcribe; map segments -> Doc")

    def translate(self, doc: Doc, target_languages: list[str]) -> Doc:
        raise NotImplementedError("wire to chalna translate endpoint (chalna-side TODO)")
