# Jeoneum — Spec & Architecture

> ⏸️ Status: **보류(WIP) — 2026-06-02.** 이 스펙은 구현까지 완료되었으나, **더빙 음성 품질이 실사용 기준에 미달**(크로스링구얼 클론 억양, 다화자 붕괴)하여 프로젝트를 일단락했습니다. 아래 §1b 및 [README의 WIP 섹션](../README.md) 참조. 이하 "Decided" 등은 **역사적 설계 기록**으로 보존합니다.
>
> ⏸️ **WIP / 보류 (2026-06-02).** 기능 구현은 동작하나 출력 품질 미달로 보류. 재작업 방향은 §1b 및 README WIP 섹션 참조.

## 1. Goal

영상/오디오/자막을 입력받아 **화자별 목소리를 보존하며 다른 언어로 더빙**하는 범용 파이프라인.
1차 검증: 한국어 YouTube → 영어. 산출물 = 원본 타임라인에 정렬된 **더빙 오디오 트랙**(보존 배경음 믹스 포함).

jeoneum은 본질적으로 **오케스트레이터**: 전사·번역은 **chalna**(서비스)에 위임하고, 음원분리·TTS합성·타이밍정렬·믹스를 담당한다.

## 1b. 상태 / 보류 사유 & 재작업 방향 (2026-06-02)

파이프라인은 끝까지 동작하지만 **출력 품질이 실사용 기준에 미달**하여 보류한다.

**마지막 테스트 결과**
- **1인 발화 / 단일 화자** (본인 레퍼런스, `out_extra1`): 한국인 화자 ref → 영어 합성 시 **중국어 억양이 섞인 영어**. 깨끗한 본인 샘플로도 억양·명료도 미달.
- **2인 대화**: 결과 **완전 붕괴**. 화자 분리 → 화자별 ref 추출 → 보이스 매칭 경로가 신뢰성 있게 동작하지 않음.

**근본 원인**
- TTS 엔진(현행 Qwen3-TTS)의 **크로스링구얼 보이스 클론 품질**이 핵심 병목.
- 다화자 시 **화자→레퍼런스 매칭**이 자동만으로는 신뢰 불가.

**재작업 방향 (재개 시)**
1. 분리된 **각 화자에 레퍼런스 오디오를 직접 매칭하는 UI**(자동 추출에만 의존하지 않음).
2. 화자별로 음성을 생성하는 **화자 단위 합성 API**.
3. **더 나은 TTS 엔진**이 나오면 그 위에서 재설계 — 엔진 교체 가능 구조(§2, submodule)는 이를 염두에 둔 것.

## 2. Decided (인터뷰 확정)

- **범용 다국어** 툴 — 언어/입력 추상화, 하드코딩 금지.
- **chalna = 별도 서비스, REST API로 호출**. 같은 **docker compose** 망에 상주. jeoneum이 chalna 헬스체크 → **이미 떠 있으면 그대로 호출, 미기동일 때만 자동 기동**.
- **전사 + 번역 모두 chalna가 구현/수행**. jeoneum은 호출만. (번역 엔진은 chalna 내부 Codex CLI, 길이 인식.)
  - chalna `/translate`는 **필수 외부 계약(블로킹 의존)**. jeoneum 자체 번역 폴백은 두지 않음 (codex P0-3). chalna-side TODO: 타깃어 번역 엔드포인트 구현.
- **다중 타깃 언어 = 1회 실행 N언어**. chalna가 1회 전사로 원어 SRT 생성 → 언어별 (번역+더빙) 팬아웃.
- **TTS = 교체 가능 엔진**(submodule + 추상 인터페이스). 1차 = Qwen3-TTS, submodule = **upstream `QwenLM/Qwen3-TTS`**.
  - **jeoneum 프로세스 내 in-process** 로드 (별도 서비스 아님).
  - 동시성: **GPU 1 = 모델 인스턴스 1**, 세그먼트(언어 무관)를 **배치로 묶어** 처리. 온라인 동시서빙 서버는 미GA → 백엔드 추상화만 열어둠(§10).
- **화자 보이스 = 자동 클론(원본 분리 음성에서 화자별 ref 추출) + 수동 오버라이드**.
  - **보이스 프로필 레지스트리 처음부터 포함** — 영상 간 동일 화자 보이스 재사용.
- **배경음 보존** → 음원 분리 단계 포함. 도구 = **`audio-separator`(nomadkaraoke)**, BS-Roformer 모델. Instrumental stem=배경음 보존, Vocals stem=화자 ref 추출.
  - **Ducking은 기본 OFF**(배경음 그대로). 옵션(`--duck`)으로 켜고 **감쇠 비율(`--duck-db`) 조정** 가능.
- **타이밍 = 시작점 동기화** + 피치 유지 타임스트레치 + 무음 패딩.
  - 충돌(다음 cue 침범) 시: **압축(`max_speedup`) 후 잔여 겹침 허용**. TTS는 발화 길이를 정확히 못 맞춰 "절대 비겹침"이 원천 불가하므로 드문 겹침은 수용.
- **입력 진입점**: 로컬 영상/오디오, YouTube URL, 기존 자막(SRT/JSON). 자막은 **원어** 또는 **이미 번역된** 것 모두 허용. 번역본 여부는 **명시 플래그**(`--subs-translated`).
- **출력 = 더빙 오디오 트랙**. 영상 먹싱·YT 업로드는 후순위 확장.
- **인터페이스 = CLI + REST + WebUI**.
- **License = PolyForm Noncommercial 1.0.0**.

## 3. Pipeline & Stage Contracts

각 단계는 캐노니컬 JSON(§4)을 읽고/쓰며 단계별 캐시·재개 가능.

| # | Stage | In | Out | 실행 주체 |
|---|-------|----|-----|-----------|
| 0 | **ingest** | video/audio/URL | 표준 wav | jeoneum (ffmpeg/yt-dlp) |
| 1 | **transcribe** | wav | segments(원어, speaker_id, ts) | **chalna API** |
| ⓿ | **separate** | wav | `vocals.wav`(=ref 추출), `background.wav`(=Instrumental, 보존) | jeoneum (audio-separator/BS-Roformer) |
| 2 | **translate** | segments + tgt langs | + `text_target`(언어별) | **chalna API** |
| 3 | **voice-map** | segments + vocals | speaker_id→voice_ref (+레지스트리) | jeoneum |
| 4 | **synthesize** | segments + voice_ref | 세그먼트별 클립 (배치) | jeoneum + TTS engine |
| 5 | **align** | 클립 + ts | 정렬된 보이스 트랙 | jeoneum |
| 6 | **mix** | 보이스 트랙 + background | 언어별 더빙 오디오 트랙 | jeoneum (mix; ducking 옵션, 기본 OFF) |

**진입 분기**
- video/audio/URL → stage 0~1부터.
- 원어 SRT/JSON → stage 2(번역)부터. (단, separate를 위해 원본 오디오가 있으면 ⓿도 수행; 없으면 배경음 보존 불가 → 전체교체 폴백.)
- 이미 번역된 SRT → stage 2 생략, stage 4부터. (`--subs-translated` 또는 언어 감지.)

**팬아웃**: transcribe/separate는 1회. 이후 `target_languages`마다 translate→synthesize→align→mix를 팬아웃하되, synthesize는 언어 교차 배치로 GPU 효율화.

## 4. Canonical Data Schema (chalna JSON 확장)

```jsonc
{
  "source": { "media": "input.mp4", "language": "ko", "duration": 612.3 },
  "target_languages": ["en", "ja"],            // 다중 타깃
  "background_audio": "background.wav",         // ⓿ (없으면 전체교체 폴백)
  "voices": {                                   // 화자→보이스 (§7)
    "0": { "mode": "auto",   "ref_audio": "refs/spk0.wav", "ref_text": "...",
           "profile_id": "spkprof_abc" },       // 레지스트리 키(있으면 재사용)
    "1": { "mode": "manual", "ref_audio": "my_voice.wav",  "ref_text": "..." }
  },
  "segments": [
    {
      "index": 1, "start_time": 10.92, "end_time": 15.56,
      "speaker_id": "0",
      "text": "원어 원문",
      "text_target": { "en": "translated", "ja": "翻訳" },  // ② 언어별
      "audio": { "en": "seg/en/0001.wav" },                 // ④ 언어별
      "fitted_speedup": { "en": 1.08 }, "overran": { "en": false }
    }
  ]
}
```

chalna 원형 필드(`index,start_time,end_time,text,speaker_id,confidence`) 보존 + 상위 필드 추가 → chalna 출력과 호환.

## 5. Package Layout (제안, chalna 답습)

```
jeoneum/
├── src/jeoneum/
│   ├── cli.py            # typer app, entry: `jeoneum`
│   ├── server.py         # FastAPI: REST + WebUI
│   ├── pipeline.py       # 단계 오케스트레이션 + 캐시 + 팬아웃
│   ├── schema.py         # 캐노니컬 모델 (pydantic)
│   ├── ingest.py         # ffmpeg/yt-dlp
│   ├── chalna_client.py  # chalna REST 클라이언트 + 헬스체크/자동기동
│   ├── separate.py       # 음원 분리 어댑터 (Separator; audio-separator/BS-Roformer)
│   ├── voices.py         # 화자→보이스 매핑 + ref 추출 + 레지스트리
│   ├── registry.py       # 보이스 프로필 영속 저장 (fingerprint→ref)
│   ├── tts/
│   │   ├── base.py       # TTSEngine ABC (배치 우선)
│   │   ├── qwen3.py      # Qwen3-TTS 구현 (in-process 배치)
│   │   └── vllm_omni.py  # (옵션) vLLM-Omni offline 백엔드
│   ├── align.py          # 타이밍 정렬 (dub_from_srt PoC 발전)
│   └── mix.py            # ducking 믹스
├── external/             # submodules
│   ├── chalna/           # github.com/jonhpark7966/chalna
│   └── Qwen3-TTS/        # github.com/QwenLM/Qwen3-TTS (upstream)
├── docker-compose.yml    # jeoneum + chalna 서비스
├── docs/spec.md
├── LICENSE.md / README.md / pyproject.toml   # hatch, scripts: jeoneum = "jeoneum.cli:app"
```

## 6. 핵심 인터페이스 (제안)

```python
# tts/base.py — 배치를 1급으로
class TTSEngine(ABC):
    @abstractmethod
    def build_voice(self, ref_audio, ref_text: str | None) -> VoiceHandle: ...
    @abstractmethod
    def synthesize_batch(self, items: list[SynthItem]) -> list[tuple[np.ndarray, int]]: ...
    # SynthItem = (text, language, voice)

class Separator(ABC):
    @abstractmethod
    def separate(self, wav_path: str) -> tuple[str, str]: ...  # (vocals, background)

# chalna_client.py
class ChalnaClient:
    def ensure_up(self) -> None: ...                 # 헬스체크 → 미기동 시 compose로 기동
    def transcribe(self, wav, **opts) -> Doc: ...
    def translate(self, doc: Doc, targets: list[str]) -> Doc: ...
```

## 7. 화자별 보이스 (자동 + 수동 + 레지스트리)

- **자동**: 분리된 `vocals.wav`에서 각 `speaker_id`의 가장 길고 깨끗한(겹침 없는) 구간을 ref로 추출 → 크로스링구얼 클론.
- **수동**: config(`--voice 0=my_voice.wav`)로 화자별 지정 보이스/프리셋 오버라이드.
- **레지스트리**: speaker fingerprint(임베딩) → 저장된 ref/profile. 신규 영상의 화자가 기존 프로필과 매칭되면 동일 보이스 재사용. (저장소 형태/매칭 임계값은 Open.)

## 8. 타이밍 정렬

PoC(`Qwen3-TTS/examples/dub_from_srt.py`) 정책 계승: cue `start_time` 배치, 사이 무음, 다음 cue 충돌 시에만 피치 유지 압축(`max_speedup` 기본 1.3 상한, 초과분 겹침 허용), 초과 세그먼트는 메타에 표시 → 번역 재압축 후보.

## 9. 인터페이스 표면

- **CLI**: `jeoneum dub <input> --to en,ja [--voice 0=ref.wav] [--keep-background] [--subs-translated] -o out/`
- **REST**: `POST /dub`(job), `GET /jobs/{id}`; chalna server 패턴 재사용.
- **WebUI**: 업로드 → 진행 → 화자별 보이스 지정/레지스트리 매칭 확인 → 언어별 결과 재생/다운로드.
- **Compose**: `jeoneum`(+GPU TTS) ↔ `chalna` 서비스. jeoneum이 chalna 헬스체크/자동기동.

## 10. 리스크 / 메모

- **TTS 동시성 현황**: vLLM-Omni가 Qwen3-TTS day-0 지원하나 **현재 offline 배치만**, online serving 미GA. → 설계는 **배치 합성** 중심, online 서버 백엔드는 추후 플러그인. (H100서 1.7B 8-stream near-RT 보고, 동시성 TTFB 개선 RFC 진행 중.)
- ~~upstream Qwen3-TTS 로컬 버그픽스 누락~~ **(해소됨)**: 검증 결과 로컬 `../Qwen3-TTS` HEAD == upstream `main` (`022e286`), `origin/main..HEAD` 비어있음. 즉 finetuning/tokenizer 패딩 fix는 **이미 upstream에 반영**되어 있고 로컬 전용 커밋은 없음(uncommitted 실험물만 존재). upstream submodule 사용에 품질 리스크 없음.
- TTS는 발화 길이 직접 제어 불가 → 타이밍 후처리 의존(겹침 원천 차단 불가).
- 화자 겹침 구간 ref 품질 / 배경음 분리 품질.
- **chalna `/translate` 하드 의존**: 미구현 시 파이프라인 진행 불가(블로킹). chalna-side 우선 구현 필요.
- **GPU 환경 공존 충돌**: `audio-separator[gpu]`(onnxruntime-gpu) + Qwen3-TTS(torch/transformers)가 동일 GPU/파이썬 환경에 공존 → CUDA 11/12 라이브러리 버전 충돌 가능. compose 이미지에서 핀 고정/검증 필요. 최악의 경우 separate를 별도 step/컨테이너로 분리(단, TTS는 in-process 유지).

## 11. Codex 리뷰 반영 (gpt-5.5 xhigh)

**즉시 수정됨 (코드/문서):**
- P0-1 분리/보이스 디커플링: `keep_background`와 무관하게 **자동 보이스에 vocals 필요 시 분리 수행**(`pipeline.py`).
- P0-2 타임라인 truncation: `align_track(floor_sec=source.duration)` + `mix`가 voice/배경 중 **긴 쪽에 앵커** → 아웃트로 보존.
- P1-6 KeyError/메타 미기록: 누락 번역 사전 검증 + `fitted_speedup/overran` doc에 write-back.
- P1-11 chalna 헬스체크: `==200` 판정, `auto_start` 옵션, compose/host URL 구분.
- P1-8 라우드니스: align은 headroom(0.97)에서만 스케일다운, mix는 클리핑만 방지(정밀 LUFS는 §12).
- P2-12/13/14: README separator 표기 통일, 상태/업로드 문구 정정, REST `DubRequest` 필드 정합, 잉여 코드펜스 제거.

**확정 (확정 라운드):**
1. **오디오 포맷 = 단일 24k mono** (단순성 우선). ingest가 24k mono로 고정하고 분리/ref/TTS/믹스 전부 동일 SR·채널. 트레이드오프 **수용**: 배경음 모노·고역 손실, 분리 입력도 24k mono(품질 다소 저하). → `ingest.TARGET_SR/CH` 유지, 포맷 매트릭스 불필요.
2. **순수 SRT 진입 = 단일 보이스 강제 + 수동 지정**: speaker_id·원본 오디오가 없으면 자동 클론 불가 → 모든 세그먼트를 **하나의 지정 보이스**(프리셋/수동 ref)로 합성. 수동 보이스 미지정 시 에러.
3. **캐노니컬 스키마 = 세그먼트 레벨만**: word 타임스탬프/추가 메타는 보존하지 않음(현행 유지).
4. **번역 = chalna 하드 의존, 폴백 전무**: jeoneum에 어떤 번역 폴백도 두지 않음. 테스트는 chalna 응답을 **mock/픽스처**로 대체.

**남은 Open (구현 시 결정):**
5. **TTS 합성 스케줄러** (P1-7): (language, segment) 큐, 최대 배치, GPU 백프레셔, REST job 직렬화.
6. **보이스 레지스트리** (P1-9): 저장 형태, fingerprint 임베딩 모델/임계값, ref 최소/최대 길이·SNR, 충돌 UX, consent.
7. **GPU 의존성 전략**: audio-separator(onnxruntime-gpu)+torch 핀 검증, 충돌 시 separate 별도 컨테이너.
8. **submodule 디렉토리** `external/` 확정 / **프로젝트명** `jeoneum`(전음) 한자.
