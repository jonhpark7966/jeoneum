# Jeoneum (전음)

> 전음(傳音) — 소리를 다른 언어로 전한다. 원본의 타이밍과 목소리를 지키며 더빙한다.
> _(이름/한자 뜻은 가안입니다. 인터뷰에서 확정.)_

영상·오디오를 입력하면 **화자별 목소리를 유지한 채 다른 언어로 더빙**해 주는 엔드투엔드 파이프라인.
범용 다국어 더빙 툴을 지향하며, 한국어 YouTube 영상을 영어로 더빙하는 것이 1차 검증 시나리오.

> ✅ **Status: 동작하는 엔드투엔드 구현.** CLI · REST API · WebUI · Docker 서빙까지 구현·검증 완료.
> 상세 설계 [`docs/spec.md`](docs/spec.md), 사용법 [`docs/usage.md`](docs/usage.md).

## 구현 상태 (2026-06-01 기준)

**동작 확인됨**
- **풀 파이프라인**: 영상/오디오/URL/자막 → chalna 전사·번역 → (배경 보존 시 음원 분리) → Qwen3-TTS 화자별 보이스 클론 → 타이밍 정렬 → 믹스 → **더빙 오디오 + 원어 SRT(`transcript.srt`) + 번역 SRT(`dub_<lang>.srt`)**. 5분 클립 e2e 검증.
- **화자 보이스**: 단일 수동 보이스(모든 화자 적용) / **화자별 자동 클론**(원본 또는 분리 vocals에서 화자 구간 ref 추출, 크로스링구얼).
- **자막 입력**: SRT/JSON(원어 또는 번역본). 번역은 chalna 내부 codex(길이 인식).
- **인터페이스**: `jeoneum dub` CLI · REST(`POST /dub` 잡 + `GET /jobs` 모니터 + 음성/자막 다운로드) · **WebUI**(업로드/URL·화자 보이스·옵션·진행 단계·큐·완료 소요시간·다운로드) · **Docker compose 서빙**.
- **chalna**: `/transcribe`(조기 EOS 커버리지, duration 비례 패스) · `/translate`(codex) · `/doctor`(셋업 진단) · 컨테이너 내 codex(호스트 OAuth 인증 마운트).

**TODO / 한계**
- **배경음 보존 믹싱 품질 테스트** — audio-separator 분리 → ducking 믹스 음질 검증 미완.
- **화자 분리(diarization) 정확도** — chalna가 화자 수를 가끔 오판(짧은 클립).
- **audio-separator는 CPU** — onnxruntime-gpu가 CUDA-13 torch와 충돌해 CPU 사용, 5분+ 분리 느림.
- **다국어 동시 스케줄러 / 보이스 레지스트리(영상 간 일관성)** 미구현.

---

## 무엇을 하나

```
 영상 / 오디오 / YouTube URL / 기존 자막(SRT·JSON)
        │
        ▼  ① 전사 + 화자 분리 + 정밀 타임스탬프      ┌─ chalna (submodule)
   원어 세그먼트  [speaker_id, start, end, text]    ─┘  VibeVoice ASR + Qwen Forced Align
        │
        ├──────────────▶  ⓿ 음원 분리 (음성 / 배경)   ┌─ audio-separator (BS-Roformer)
        │                  배경음(BGM·SFX) 보존용     ─┘  Vocals=ref 추출, Instrumental=배경 보존
        │
        ▼  ② 길이 인식 번역 (원문 길이에 맞춰 압축)    ┌─ chalna (내부 Codex CLI)
   타깃어 세그먼트  [.. , text_target]              ─┘
        │
        ▼  ③ 화자별 보이스 매핑 + TTS 합성            ┌─ TTS Engine (submodule, 교체 가능)
   세그먼트별 음성 클립                               ─┘  Qwen3-TTS (1차 구현)
        │
        ▼  ④ 타이밍 정렬 (세그먼트 시작점 동기화 + 피치 유지 타임스트레치)
   더빙 보이스 트랙 (원본과 동일 타임라인)
        │
        ▼  ⑤ 믹스 (더빙 + 보존된 배경음; ducking은 옵션·기본 OFF)
   언어별 더빙 오디오 트랙   (YouTube 다국어 오디오로 활용 — 업로드 자동화는 후순위)
```

## 핵심 설계 결정 (인터뷰 확정)

| 항목 | 결정 |
|------|------|
| 스코프 | **범용 다국어 더빙 툴** (언어/입력 하드코딩 금지, 추상화) |
| 역할 | jeoneum = **오케스트레이터**. 전사·번역은 chalna에 위임 |
| chalna 연동 | **별도 서비스, REST API 호출** (docker compose). jeoneum이 헬스체크 → 미기동 시 자동 기동 |
| 전사·번역 | **chalna가 구현/수행** (번역도 chalna 내부 Codex CLI, 길이 인식). jeoneum은 호출만 |
| 다중 언어 | **1회 실행 N언어** — 전사 1회 후 언어별 (번역+더빙) 팬아웃 |
| TTS | **교체 가능 엔진** (submodule, 추상 인터페이스). 1차: **Qwen3-TTS (upstream QwenLM)**. GPU 1=인스턴스 1, **세그먼트 배치** 처리 |
| 화자 보이스 | **자동 클론 + 수동 오버라이드 + 보이스 프로필 레지스트리**(영상 간 동일 화자 재사용, 처음부터 포함) |
| 배경음 | **원본 BGM/SFX 보존** → 음원 분리(audio-separator) 단계 포함. ducking은 기본 OFF, 옵션·비율 조정 |
| 타이밍 | **세그먼트 시작점 동기화** + 타임스트레치 + 무음 패딩 |
| 입력 | **로컬 영상/오디오 · YouTube URL · 기존 자막(SRT/JSON, 원어 또는 번역본)** |
| 출력 | **더빙 오디오 트랙** (보존 배경음 믹스 포함). 영상 먹싱·YT 업로드는 후순위 |
| 인터페이스 | **CLI + REST + WebUI** (chalna 패턴 답습) |
| 라이선스 | **PolyForm Noncommercial 1.0.0** — 소스 공개, 누구나 비영리 사용, 상업 이용은 저작자만 |

## 구성 요소

| 구성 | 역할 | 형태 |
|------|------|------|
| **chalna** | 영상/오디오 → 화자분리 자막 **+ 번역** | git submodule + REST 서비스 (`github.com/jonhpark7966/chalna`) |
| **TTS engine** | 텍스트 → 음성 (보이스 클론), 배치 합성 | git submodule, 추상 인터페이스 뒤 (1차: Qwen3-TTS upstream) |
| **separator** | 음성/배경 분리 (배경음 보존) | 내부 모듈 (audio-separator / BS-Roformer) |
| **voices + registry** | 화자→보이스 매핑 + ref 추출 + 영속 프로필 | 내부 모듈 |
| **aligner** | 세그먼트 클립 → 타임라인 정렬 | 내부 모듈 |
| **mixer** | 더빙 트랙 + 배경음 ducking 믹스 | 내부 모듈 |

---

## 사용법 / Usage

세 가지 인터페이스를 제공합니다: **CLI**, **REST API**, **WebUI**. 자세한 안내는 [`docs/usage.md`](docs/usage.md) 참조.

> jeoneum은 전사·번역을 직접 하지 않습니다. **chalna 서비스가 반드시 기동 중이어야** 하며(`CHALNA_URL`, 기본 `http://localhost:7861`), `/translate`를 제공해야 합니다. TTS는 GPU에서 Qwen3-TTS를 사용하므로 **GPU가 필요**하고, 모델 가중치는 첫 요청 시 HuggingFace에서 자동 다운로드됩니다.

### CLI

#### `jeoneum dub` — 더빙 실행

```bash
jeoneum dub <source> --to en,ja \
  [-o out] \
  [--voice 0=ref.wav] \
  [--keep-background | --replace-audio] \
  [--duck | --no-duck] [--duck-db -12.0] \
  [--subs-translated] \
  [--max-speedup 1.3]
```

| 인자/플래그 | 기본값 | 설명 |
|------------|--------|------|
| `<source>` | (필수) | 입력 소스 — 로컬 영상/오디오 파일, YouTube/HTTP URL, 또는 기존 자막(`.srt`/`.json`, 원어 또는 번역본). |
| `--to` | (필수) | 타깃 언어. 쉼표 구분, 예: `en,ja`. |
| `--out`, `-o` | `out` | 출력 디렉터리. 결과는 `<out>/dub_<lang>.wav`. |
| `--voice` | (없음) | 수동 화자 보이스, `speaker=ref.wav` 형식. 반복 지정 가능. ref 대본은 `ref.txt` 사이드카로 자동 로드됨. |
| `--keep-background` / `--replace-audio` | `--keep-background` | 원본 배경음(BGM/SFX) 보존 여부. `--replace-audio`면 더빙 음성만 출력. |
| `--duck` / `--no-duck` | `--no-duck` | 음성 구간에서 배경음 더킹(감쇠) 여부. 기본 OFF. |
| `--duck-db` | `-12.0` | 더킹 시 배경음 감쇠량(dB). |
| `--subs-translated` | `false` | 입력 자막이 이미 타깃 언어로 번역되어 있음(번역 단계 건너뜀). |
| `--max-speedup` | `1.3` | 타이밍 정렬 시 허용 최대 압축(속도) 배율. |

출력은 언어별로 한 줄씩 `[lang] path` 형식으로 표준출력에 표시됩니다:

```
[en] out/dub_en.wav
[ja] out/dub_ja.wav
```

예시:

```bash
# 로컬 영상 → 영어 + 일본어, 배경음 보존
jeoneum dub video.mp4 --to en,ja

# YouTube URL → 영어, 수동 보이스 지정
jeoneum dub "https://youtu.be/XXXX" --to en --voice 0=me.wav

# 이미 번역된 SRT → 영어 더빙(번역 생략)
jeoneum dub subs.en.srt --to en --subs-translated --voice 0=me.wav
```

#### `jeoneum serve` — REST API + WebUI 기동

```bash
jeoneum serve [--host 0.0.0.0] [--port 7870]
```

`http://localhost:7870/` 에서 WebUI, `/docs` 에서 자동 생성 API 문서를 제공합니다. (기본 호스트 `0.0.0.0`, 포트 `7870`.)

### REST API

작업은 비동기입니다: `POST /dub`로 잡을 생성하고 `GET /jobs/{id}`를 폴링하여 상태를 확인한 뒤, 완료되면 `GET /jobs/{id}/result/{lang}`로 wav를 내려받습니다. 상태 값: `queued → running → done | error`.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/health` | 헬스체크. `{status, version, engine_loaded, gpu}`. 엔진을 로드하지 않으므로 즉시 응답. |
| `POST` | `/dub` | 더빙 잡 생성 (`multipart/form-data`). `{job_id, status, target_languages}` 반환. |
| `GET` | `/jobs/{job_id}` | 잡 상태/결과 조회 (JSON). |
| `GET` | `/jobs/{job_id}/result/{lang}` | 완료된 언어의 wav 다운로드 (`audio/wav`). |
| `GET` | `/` | WebUI (자체 완결형 HTML). |

**`POST /dub` multipart 필드**

| 필드 | 타입 | 필수 | 기본 | 설명 |
|------|------|------|------|------|
| `file` | 파일 | file/url 중 하나 | — | 소스 영상/오디오/.srt/.json 업로드. |
| `url` | 문자열 | file/url 중 하나 | `null` | YouTube/HTTP URL. `file`이 없을 때만 사용. |
| `target_languages` | 문자열 | 예 | — | CSV, 예: `en,ja`. 비어 있으면 400. |
| `voice_sample` | 파일 | 아니오 | `null` | 단일 참조 보이스. **모든 화자**에 적용. |
| `ref_text` | 문자열 | 아니오 | `null` | `voice_sample` 대본(클론 품질 향상). `voice_sample` 없으면 무시. |
| `keep_background` | bool | 아니오 | `true` | 배경음 보존. |
| `duck` | bool | 아니오 | `false` | 배경음 더킹. |
| `duck_db` | float | 아니오 | `-12.0` | 더킹 감쇠(dB). |
| `subs_translated` | bool | 아니오 | `false` | 입력 자막이 이미 번역됨. |
| `max_speedup` | float | 아니오 | `1.3` | 최대 압축 배율. |

curl 예시:

```bash
# 잡 생성
curl -F file=@video.mp4 \
     -F target_languages=en,ja \
     -F voice_sample=@me.wav \
     -F keep_background=true \
     http://localhost:7870/dub
# -> {"job_id":"...","status":"queued","target_languages":["en","ja"]}

# 상태 폴링
curl http://localhost:7870/jobs/<id>

# 결과 다운로드
curl -o dub_en.wav http://localhost:7870/jobs/<id>/result/en
```

`GET /jobs/{id}` 완료 응답 예:

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

### WebUI

`jeoneum serve` 후 브라우저에서 `http://localhost:7870/` 접속. 자체 완결형 단일 페이지로, 외부 의존성이 없습니다.

1. 좌측 **입력** 패널에서 소스 파일을 업로드하거나 YouTube/URL을 붙여넣습니다(둘은 상호 배타적).
2. 타깃 언어(쉼표 구분, 기본 `en`)를 입력합니다.
3. (선택) 화자 보이스 샘플과 그 대본을 지정합니다 — 모든 화자에 적용됩니다.
4. 옵션(배경음 보존/더킹/감쇠 dB/자막 번역됨/최대 압축 배율)을 설정합니다.
5. **더빙 시작**을 누르면 우측 **결과** 패널에서 진행 상황을 보여줍니다. UI는 `/jobs/{id}`를 **2초마다 폴링**합니다.
6. 완료되면 언어별 카드에서 바로 재생하거나 다운로드할 수 있습니다.

### Docker 서빙

```bash
docker compose up --build
```

`jeoneum`(:7870, GPU 필요)과 `chalna`(:7861)를 함께 띄웁니다. jeoneum은 `CHALNA_URL=http://chalna:7861`로 chalna에 접근합니다.

- **GPU 필수.** 첫 `/dub` 요청은 Qwen3-TTS 가중치를 HuggingFace에서 내려받고 엔진을 로드하므로 느립니다(가중치는 `jeoneum-models` 볼륨에 캐시되어 재시작 후에도 유지).
- 결과는 `./results`(컨테이너 내 `/data/results`, `JEONEUM_RESULTS_DIR`)에 저장됩니다.
- **chalna는 별도 설정(codex 인증 등)이 필요**합니다 — `external/chalna` 참조. chalna가 기동·도달 가능하지 않으면 더빙 잡은 실패합니다.

---

## License

[PolyForm Noncommercial License 1.0.0](LICENSE.md).
소스는 공개되며 **누구나 비영리 목적으로 자유롭게 사용·수정·배포**할 수 있습니다.
**상업적 이용 권리는 저작자에게 유보**됩니다 — 상업 라이선스는 저작자에게 문의.
(chalna에는 LICENSE 파일이 없어 본 프로젝트가 신규 채택. chalna 본체에도 동일 라이선스 추가는 별도 논의.)

---

## 인터뷰 진행 상황

확정 결정은 위 표와 [`docs/spec.md`](docs/spec.md)에 반영. 남은 오픈 이슈는 spec 문서의 "Open Questions" 참조.
