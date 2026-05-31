# jeoneum 사용법 (Usage)

전음(傳音)은 영상·오디오를 **화자별 목소리를 유지한 채 다른 언어로 더빙**하는 오케스트레이터입니다.
세 가지 인터페이스를 제공합니다: **CLI**, **REST API**, **WebUI**.

> **사전 요구사항**
> - **GPU 필수.** TTS는 Qwen3-TTS(GPU)를 사용합니다. 모델 가중치는 첫 요청 시 HuggingFace에서 자동 다운로드되어 캐시됩니다 — 첫 실행은 느립니다.
> - **chalna 서비스가 기동 중이어야 합니다.** jeoneum은 전사·번역을 직접 하지 않고 chalna REST API에 위임합니다. chalna는 `/transcribe`와 `/translate`를 제공해야 하며, 도달 불가 시 더빙 잡이 실패합니다(폴백 없음).

---

## 1. 빠른 시작 (Quickstart)

### CLI 한 줄

```bash
# 별도 터미널에서 chalna 기동(또는 docker compose 사용) 후:
jeoneum dub video.mp4 --to en,ja
# -> [en] out/dub_en.wav
#    [ja] out/dub_ja.wav
```

### REST + WebUI

```bash
jeoneum serve            # http://localhost:7870 (WebUI), /docs (API 문서)
```

브라우저로 `http://localhost:7870/` 접속.

### Docker Compose

```bash
docker compose up --build
```

`jeoneum`(:7870, GPU) + `chalna`(:7861)를 함께 띄웁니다.

---

## 2. CLI 레퍼런스

### `jeoneum dub`

```bash
jeoneum dub <source> --to <langs> \
  [-o, --out <dir>] \
  [--voice <speaker=ref.wav>]... \
  [--keep-background | --replace-audio] \
  [--duck | --no-duck] [--duck-db <float>] \
  [--subs-translated] \
  [--max-speedup <float>]
```

| 인자/플래그 | 기본값 | 설명 |
|------------|--------|------|
| `<source>` | (필수) | 로컬 영상/오디오 파일, YouTube/HTTP URL, 또는 기존 자막(`.srt`/`.json`). 자막은 원어 또는 번역본 모두 가능. |
| `--to` | (필수) | 타깃 언어, 쉼표 구분. 예: `en,ja`. |
| `--out`, `-o` | `out` | 출력 디렉터리. 결과는 `<out>/dub_<lang>.wav`. |
| `--voice` | (없음) | 수동 화자 보이스. `speaker_id=ref.wav` 형식, 반복 지정 가능. 같은 basename의 `ref.txt` 사이드카가 있으면 대본으로 자동 로드. |
| `--keep-background` / `--replace-audio` | `--keep-background` | 원본 배경음(BGM/SFX) 보존 / 더빙 음성만 출력. |
| `--duck` / `--no-duck` | `--no-duck` | 음성 구간에서 배경음 더킹(감쇠). 기본 OFF. |
| `--duck-db` | `-12.0` | 더킹 시 배경음 감쇠량(dB). |
| `--subs-translated` | `false` | 입력 자막이 이미 타깃 언어로 번역됨 → 번역 단계 생략. |
| `--max-speedup` | `1.3` | 타이밍 정렬 시 허용 최대 압축(속도) 배율. |

출력은 언어별 한 줄씩 `[lang] path`:

```
[en] out/dub_en.wav
[ja] out/dub_ja.wav
```

#### 입력 모드별 예시

```bash
# 1) 로컬 파일 → 영어 + 일본어 (배경음 보존)
jeoneum dub video.mp4 --to en,ja -o results/

# 2) YouTube URL → 영어, 수동 보이스 + 더킹
jeoneum dub "https://youtu.be/XXXX" --to en --voice 0=me.wav --duck --duck-db -10

# 3) 원어 SRT 입력 → 영어 (jeoneum이 chalna로 번역)
jeoneum dub talk.ko.srt --to en --voice 0=me.wav

# 4) 이미 번역된 SRT → 영어 더빙 (번역 생략)
jeoneum dub talk.en.srt --to en --subs-translated --voice 0=me.wav

# 5) 배경음 없이 더빙 음성만
jeoneum dub video.mp4 --to en --replace-audio
```

### `jeoneum serve`

```bash
jeoneum serve [--host 0.0.0.0] [--port 7870]
```

REST API + WebUI를 기동합니다. 기본 호스트 `0.0.0.0`, 포트 `7870`. (`uvicorn jeoneum.server:app`을 실행하는 것과 동등.)

---

## 3. REST API 레퍼런스

기본 베이스 URL: `http://localhost:7870`. 작업은 비동기이며 단일 백그라운드 워커가 FIFO로 처리합니다.

상태 전이: `queued → running → done | error`.

### `GET /health`

엔진을 로드하지 않고 즉시 응답합니다.

```bash
curl http://localhost:7870/health
```

```json
{ "status": "ok", "version": "0.0.1", "engine_loaded": false, "gpu": "NVIDIA H100" }
```

- `engine_loaded`: 공유 Qwen3 엔진이 한 번이라도 인스턴스화되면 `true`.
- `gpu`: `torch.cuda.get_device_name(0)` 결과, 사용 불가 시 `null`.

### `POST /dub` — 잡 생성

`multipart/form-data` (JSON 아님 — 업로드가 필요).

| 필드 | 타입 | 필수 | 기본 | 설명 |
|------|------|------|------|------|
| `file` | 파일 | file/url 중 하나 | — | 소스 영상/오디오/.srt/.json 업로드. |
| `url` | 문자열 | file/url 중 하나 | `null` | YouTube/HTTP URL. `file`이 없을 때만 사용. |
| `target_languages` | 문자열 | 예 | — | CSV, 예: `en,ja`. 빈 값이면 400. |
| `voice_sample` | 파일 | 아니오 | `null` | 단일 참조 보이스. **모든 화자**에 적용. |
| `ref_text` | 문자열 | 아니오 | `null` | `voice_sample` 대본. `voice_sample` 없으면 무시(에러 아님). |
| `keep_background` | bool | 아니오 | `true` | 배경음 보존. |
| `duck` | bool | 아니오 | `false` | 배경음 더킹. |
| `duck_db` | float | 아니오 | `-12.0` | 더킹 감쇠(dB). |
| `subs_translated` | bool | 아니오 | `false` | 입력 자막이 이미 번역됨. |
| `max_speedup` | float | 아니오 | `1.3` | 최대 압축 배율. |

검증 실패 시 HTTP 400 `{"detail": "..."}`:
- `file`(비어 있지 않은 파일명)와 `url` 중 **정확히 하나**만 제공.
- `target_languages`가 1개 이상의 언어를 산출해야 함.

성공 (HTTP 200):

```json
{ "job_id": "uuid4-string", "status": "queued", "target_languages": ["en", "ja"] }
```

```bash
curl -F file=@video.mp4 \
     -F target_languages=en,ja \
     -F voice_sample=@me.wav \
     -F ref_text="안녕하세요, 테스트입니다." \
     -F keep_background=true \
     http://localhost:7870/dub
```

URL 입력 예:

```bash
curl -F url="https://youtu.be/XXXX" -F target_languages=en http://localhost:7870/dub
```

### `GET /jobs/{job_id}` — 상태 조회

잡이 없으면 404 `{"detail":"Job not found"}`. 그 외 200:

```bash
curl http://localhost:7870/jobs/<id>
```

상태별 JSON 예시:

**queued**

```json
{
  "job_id": "uuid4",
  "status": "queued",
  "created_at": "2026-06-01T12:00:00.000000",
  "started_at": null,
  "completed_at": null,
  "target_languages": ["en", "ja"],
  "stage": null,
  "source_name": "video.mp4",
  "error": null,
  "outputs": {}
}
```

**running**

```json
{
  "job_id": "uuid4",
  "status": "running",
  "created_at": "2026-06-01T12:00:00.000000",
  "started_at": "2026-06-01T12:00:01.000000",
  "completed_at": null,
  "target_languages": ["en", "ja"],
  "stage": "dubbing",
  "source_name": "video.mp4",
  "error": null,
  "outputs": {}
}
```

**done**

```json
{
  "job_id": "uuid4",
  "status": "done",
  "created_at": "2026-06-01T12:00:00.000000",
  "started_at": "2026-06-01T12:00:01.000000",
  "completed_at": "2026-06-01T12:03:00.000000",
  "target_languages": ["en", "ja"],
  "stage": null,
  "source_name": "video.mp4",
  "error": null,
  "outputs": {
    "en": { "lang": "en", "result_url": "/jobs/<id>/result/en", "filename": "dub_en.wav" },
    "ja": { "lang": "ja", "result_url": "/jobs/<id>/result/ja", "filename": "dub_ja.wav" }
  }
}
```

**error**

```json
{
  "job_id": "uuid4",
  "status": "error",
  "created_at": "2026-06-01T12:00:00.000000",
  "started_at": "2026-06-01T12:00:01.000000",
  "completed_at": "2026-06-01T12:00:05.000000",
  "target_languages": ["en"],
  "stage": null,
  "source_name": "video.mp4",
  "error": "ChalnaClient: connection refused",
  "outputs": {}
}
```

- `outputs`는 `status=done` 이전에는 `{}`.
- 모든 datetime은 ISO-8601, 미설정 시 `null`.
- URL 입력의 경우 `source_name`은 URL 문자열.

### `GET /jobs/{job_id}/result/{lang}` — wav 다운로드

- 잡이 없거나, `done`이 아니거나, `lang`이 outputs에 없으면 404.
- 그 외에는 wav를 `audio/wav`로 스트리밍(`Content-Disposition` 파일명 `dub_<lang>.wav`).
- `<audio src>` 및 다운로드 링크로 그대로 사용 가능.

```bash
curl -o dub_en.wav http://localhost:7870/jobs/<id>/result/en
```

### `GET /` — WebUI

자체 완결형 단일 페이지 HTML을 서빙합니다(§4 참조).

---

## 4. WebUI

`jeoneum serve` 후 `http://localhost:7870/` 접속. 외부 라이브러리/폰트/CDN 없는 단일 자체 완결형 페이지입니다.

좌측 **입력** 패널:
1. **소스** — 파일 드롭존 업로드 또는 YouTube/URL 입력(둘은 상호 배타적; 하나를 채우면 다른 쪽이 비워짐).
2. **타깃 언어** — 쉼표 구분, 기본 `en`.
3. **화자 보이스 샘플(선택)** — 단일 참조 보이스, 모든 화자에 적용.
4. **보이스 샘플 대본(선택)** — 클론 품질 향상용.
5. **옵션** — 배경음 보존 / 배경음 더킹 / 더킹 감쇠(dB) / 입력 자막 번역됨 / 최대 압축 배율.
6. **더빙 시작** — 소스가 지정되면 활성화.

우측 **결과** 패널: idle → progress → result/error로 전환됩니다.
- progress: 단계(`stage`) 레이블과 경과 시간 표시. UI는 `/jobs/{id}`를 **2초마다 폴링**.
- result: 언어별 카드에 `<audio>` 플레이어와 다운로드 링크(`result_url` 직접 사용).
- error: 잡의 `error` 메시지 표시.

---

## 5. 잡 모델 & 수명주기

- **인메모리 잡 저장소.** DB 없음 — 서버 재시작 시 잡 정보 손실(설계상 허용).
- **단일 백그라운드 워커 스레드** + `queue.Queue`로 FIFO 직렬 처리. GPU 1개 = 모델 인스턴스 1개이므로 동시 더빙은 직렬화됨.
- **공유 지연 로딩 엔진.** Qwen3 엔진은 워커가 첫 `dub` 직전에 한 번만 생성하여 잡 간 공유합니다. 서버 부팅과 `/health`는 절대 엔진을 로드하지 않습니다.
- **잡별 작업 디렉터리**: `JEONEUM_RESULTS_DIR/<job_id>/`(기본 `<repo>/results/<job_id>/`).
  - 업로드 소스: `source<ext>`
  - 보이스 샘플: `voice<ext>` (+ `ref_text` 지정 시 `voice.txt` 사이드카)
  - 출력: `out/dub_<lang>.wav`
- 출력은 다운로드 가능하도록 보존됩니다(워크디렉터리 자동 삭제 없음).

---

## 6. 보이스 처리

- WebUI/REST 경로: 단일 `voice_sample`(+ 선택 `ref_text`)을 **모든 화자**에 적용합니다(`jeoneum.voices.resolve_voices`). 내부적으로 `{"0": Voice(mode="manual", ref_audio=..., ref_text=...)}` 형태로 전달됩니다.
- CLI `--voice speaker=ref.wav`로 화자별 수동 매핑이 가능합니다. ref 대본은 같은 basename의 `.txt` 사이드카로 자동 로드됩니다(`Voice.ref_text` 미설정 시).
- 음원 분리 기반 **자동 화자별 클론**은 비-WebUI(다중 화자) 경로입니다.

---

## 7. Docker 서빙

```bash
docker compose up --build
```

- `jeoneum`(:7870, GPU 필요) + `chalna`(:7861)를 기동.
- jeoneum은 `CHALNA_URL=http://chalna:7861`로 chalna에 접근.
- 결과는 `./results`(컨테이너 `/data/results`)에 저장, HF 가중치는 `jeoneum-models` 명명 볼륨에 캐시.
- **첫 `/dub`는 느립니다** — 가중치 다운로드 + 엔진 로드. 이후 요청은 빠릅니다.
- chalna는 별도 설정(codex 인증 등)이 필요합니다 — `external/chalna` 참조.

---

## 8. 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CHALNA_URL` | `http://localhost:7861` | chalna 전사/번역 서비스 주소. |
| `JEONEUM_RESULTS_DIR` | `<repo>/results` | 잡 작업/출력 디렉터리 루트. |
| `HF_HOME` | (시스템 기본) | HuggingFace 캐시 경로(모델 가중치). |

---

## 9. 트러블슈팅

- **잡이 즉시 `error`가 되고 chalna 연결 오류** — chalna가 기동·도달 가능해야 하며 `/translate`를 구현해야 합니다(하드 의존, 폴백 없음). `CHALNA_URL`을 확인하세요.
- **첫 요청이 매우 느림** — 정상입니다. Qwen3-TTS 가중치 다운로드 + 엔진 로드 때문이며, 이후 요청은 빠릅니다.
- **CUDA/GPU 오류** — GPU가 필수입니다. Docker 사용 시 `--gpus all`(compose에 NVIDIA 디바이스 예약 포함)이 필요합니다.
- **재시작 후 잡이 사라짐** — 인메모리 저장소라 정상 동작입니다(DB 없음). 출력 wav는 `JEONEUM_RESULTS_DIR/<job_id>/out/`에 남아 있습니다.
</content>
</invoke>
