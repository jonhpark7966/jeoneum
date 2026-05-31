"""jeoneum REST API + WebUI (FastAPI). Skeleton — see docs/spec.md §9.

Mirrors chalna's job pattern: POST /dub creates a job, GET /jobs/{id} polls it.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="jeoneum", version="0.0.1")


class DubRequest(BaseModel):
    source: str
    target_languages: list[str]
    keep_background: bool = True
    subs_translated: bool = False
    # keep in sync with cli.py / pipeline.dub (codex P2-13)
    manual_voices: dict[str, str] = {}              # speaker_id -> ref audio path/url
    duck: bool = False
    duck_db: float = -12.0
    max_speedup: float = 1.3


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/dub")
def create_dub(req: DubRequest) -> dict:
    raise NotImplementedError("enqueue job -> run pipeline.dub in worker; return job_id")


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    raise NotImplementedError("return job status + per-language output paths")
