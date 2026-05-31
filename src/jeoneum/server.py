"""jeoneum REST API + WebUI (FastAPI). See docs/spec.md §9.

Mirrors chalna's job pattern: POST /dub creates a job, GET /jobs/{id} polls it,
GET /jobs/{id}/result/{lang} downloads the per-language dubbed wav.

Concurrency: a single daemon worker thread consumes a queue.Queue (FIFO). The
GPU-bound, synchronous pipeline.dub runs there with a SHARED, LAZILY-created
Qwen3 engine, so the event loop stays free to serve status polls. The engine is
NEVER loaded at import/startup or in /health — only the worker creates it, right
before calling dub().
"""
from __future__ import annotations

import os
import queue
import shutil
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .pipeline import dub
from .schema import Voice

# =============================================================================
# App Setup
# =============================================================================

app = FastAPI(title="jeoneum", version="0.0.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_STATIC_DIR = Path(__file__).parent / "static"
_STATIC_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_DIR = Path(
    os.environ.get(
        "JEONEUM_RESULTS_DIR",
        str(Path(__file__).resolve().parents[2] / "results"),
    )
)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# Module-level state
# =============================================================================

_jobs: dict[str, "Job"] = {}                 # in-memory job store
_job_queue: "queue.Queue[str]" = queue.Queue()
_engine = None                               # shared lazy Qwen3 engine
_engine_lock = threading.Lock()
_worker_thread: Optional[threading.Thread] = None


def get_engine():
    """Get-or-create the shared Qwen3 engine. Called ONLY by the worker."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from .tts.qwen3 import Qwen3Engine
                _engine = Qwen3Engine()
    return _engine


# =============================================================================
# Models
# =============================================================================

class Job(BaseModel):
    job_id: str
    status: str = "queued"                    # queued | running | done | error
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    target_languages: list[str] = Field(default_factory=list)
    source_name: str = ""
    stage: Optional[str] = None
    error: Optional[str] = None
    outputs: dict[str, dict] = Field(default_factory=dict)
    # Internal (excluded from API responses):
    workdir: str = ""
    source_path: str = ""                      # uploaded file path OR url
    voice: Optional[dict] = None               # {"ref_audio": str, "ref_text": str|None}
    keep_background: bool = True
    duck: bool = False
    duck_db: float = -12.0
    subs_translated: bool = False
    max_speedup: float = 1.3


class JobResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    target_languages: list[str]
    stage: Optional[str] = None
    source_name: str
    error: Optional[str] = None
    outputs: dict[str, dict] = Field(default_factory=dict)


def _job_response(job: "Job") -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        target_languages=job.target_languages,
        stage=job.stage,
        source_name=job.source_name,
        error=job.error,
        outputs=job.outputs,
    )


# =============================================================================
# Static Files (Web UI)
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def web_ui():
    """Serve the built-in Web UI."""
    index_path = _STATIC_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return HTMLResponse("<h1>jeoneum API</h1><p><a href='/docs'>API Docs</a></p>")


# =============================================================================
# Endpoints
# =============================================================================

@app.get("/health")
async def health() -> dict:
    """Fast health check. Never loads the TTS engine."""
    gpu = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
    except Exception:
        gpu = None

    return {
        "status": "ok",
        "version": app.version,
        "engine_loaded": _engine is not None,
        "gpu": gpu,
    }


@app.post("/dub", response_model=None)
async def create_dub(
    file: UploadFile = File(None),
    url: Optional[str] = Form(None),
    target_languages: str = Form(...),
    voice_sample: UploadFile = File(None),
    ref_text: Optional[str] = Form(None),
    keep_background: bool = Form(True),
    duck: bool = Form(False),
    duck_db: float = Form(-12.0),
    subs_translated: bool = Form(False),
    max_speedup: float = Form(1.3),
) -> dict:
    """Create a dubbing job. Persists uploads, enqueues, returns immediately."""
    has_file = file is not None and bool(file.filename)
    has_url = bool(url and url.strip())

    if has_file == has_url:  # neither or both
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of 'file' (upload) or 'url'.",
        )

    langs = [s.strip() for s in target_languages.split(",") if s.strip()]
    if not langs:
        raise HTTPException(status_code=400, detail="target_languages must yield at least one language.")

    job_id = str(uuid.uuid4())
    workdir = RESULTS_DIR / job_id
    workdir.mkdir(parents=True, exist_ok=True)

    # Resolve source
    if has_file:
        ext = Path(file.filename).suffix or ".bin"
        source_path = workdir / f"source{ext}"
        with source_path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        source = str(source_path)
        source_name = file.filename
    else:
        source = url.strip()
        source_name = url.strip()

    # Resolve voice sample (applies to ALL speakers)
    voice: Optional[dict] = None
    if voice_sample is not None and voice_sample.filename:
        vext = Path(voice_sample.filename).suffix or ".wav"
        voice_path = workdir / f"voice{vext}"
        with voice_path.open("wb") as f:
            shutil.copyfileobj(voice_sample.file, f)
        rtext = ref_text.strip() if (ref_text and ref_text.strip()) else None
        if rtext:
            # Sidecar so voices._resolve_ref_text picks it up too.
            (workdir / "voice.txt").write_text(rtext, encoding="utf-8")
        voice = {"ref_audio": str(voice_path), "ref_text": rtext}
    # If ref_text given without voice_sample: silently ignored.

    job = Job(
        job_id=job_id,
        status="queued",
        created_at=datetime.utcnow(),
        target_languages=langs,
        source_name=source_name,
        workdir=str(workdir),
        source_path=source,
        voice=voice,
        keep_background=keep_background,
        duck=duck,
        duck_db=duck_db,
        subs_translated=subs_translated,
        max_speedup=max_speedup,
    )
    _jobs[job_id] = job
    _job_queue.put(job_id)

    return {"job_id": job_id, "status": "queued", "target_languages": langs}


@app.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_response(job)


@app.get("/jobs", response_model=None)
async def list_jobs() -> dict:
    """Optional convenience listing, newest first."""
    jobs = sorted(_jobs.values(), key=lambda j: j.created_at, reverse=True)
    return {"jobs": [_job_response(j).model_dump(mode="json") for j in jobs]}


@app.get("/jobs/{job_id}/result/{lang}")
async def get_result(job_id: str, lang: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "done" or lang not in job.outputs:
        raise HTTPException(status_code=404, detail="Result not available")

    path = RESULTS_DIR / job_id / "out" / f"dub_{lang}.wav"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Result file missing")

    return FileResponse(
        str(path),
        media_type="audio/wav",
        filename=f"dub_{lang}.wav",
    )


# =============================================================================
# Worker
# =============================================================================

def _run_job(job_id: str) -> None:
    job = _jobs.get(job_id)
    if job is None:
        return

    job.status = "running"
    job.started_at = datetime.utcnow()
    job.stage = "dubbing"

    try:
        manual_voices = None
        ref_text = None
        if job.voice:
            ref_text = job.voice.get("ref_text")
            manual_voices = {
                "0": Voice(
                    mode="manual",
                    ref_audio=job.voice["ref_audio"],
                    ref_text=ref_text,
                )
            }

        outdir = str(Path(job.workdir) / "out")
        outputs = dub(
            job.source_path,
            job.target_languages,
            outdir,
            subs_translated=job.subs_translated,
            keep_background=job.keep_background,
            manual_voices=manual_voices,
            engine=get_engine(),
            max_speedup=job.max_speedup,
            duck=job.duck,
            duck_db=job.duck_db,
        )
    except Exception as e:
        job.status = "error"
        job.error = str(e)
        job.completed_at = datetime.utcnow()
        job.stage = None
        traceback.print_exc()
        return

    # Record outputs
    job.outputs = {
        lang: {
            "lang": lang,
            "result_url": f"/jobs/{job_id}/result/{lang}",
            "filename": Path(p).name,
        }
        for lang, p in outputs.items()
    }
    job.status = "done"
    job.completed_at = datetime.utcnow()
    job.stage = None


def _worker_loop() -> None:
    while True:
        job_id = _job_queue.get()
        try:
            _run_job(job_id)
        except Exception:
            traceback.print_exc()
        finally:
            _job_queue.task_done()


@app.on_event("startup")
async def startup() -> None:
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        _worker_thread.start()
    print(f"jeoneum worker started; results dir: {RESULTS_DIR}")


# Mount AFTER routes so it does not shadow /health, /dub, /jobs/...
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
