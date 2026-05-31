# jeoneum — speaker-preserving multilingual dubbing orchestrator.
# NOTE: GPU runtime required; model weights download from HuggingFace at first /dub call.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    JEONEUM_RESULTS_DIR=/data/results \
    HF_HOME=/models/huggingface \
    TORCH_HOME=/models/torch

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      build-essential ca-certificates curl ffmpeg git libsndfile1 \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Engine first (heavy, cached layer). qwen-tts is editable from the submodule.
COPY external/Qwen3-TTS /app/external/Qwen3-TTS
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -e /app/external/Qwen3-TTS

# jeoneum metadata + deps. README.md is COPYed because pyproject readme = "README.md".
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install -e /app
# RUN pip install -e ".[gpu]"  # optional: source separation (BS-Roformer); verify CUDA pins

RUN mkdir -p /data/results /models

EXPOSE 7870

CMD ["uvicorn", "jeoneum.server:app", "--host", "0.0.0.0", "--port", "7870"]
