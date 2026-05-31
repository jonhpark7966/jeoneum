# Jeoneum (전음)

> 전음(傳音) — 소리를 다른 언어로 전한다. 원본의 타이밍과 목소리를 지키며 더빙한다.
> _(이름/한자 뜻은 가안입니다. 인터뷰에서 확정.)_

영상·오디오를 입력하면 **화자별 목소리를 유지한 채 다른 언어로 더빙**해 주는 엔드투엔드 파이프라인.
범용 다국어 더빙 툴을 지향하며, 한국어 YouTube 영상을 영어로 더빙하는 것이 1차 검증 시나리오.

> ⚠️ **Status: 스펙 확정 + 골격(skeleton) 단계.** `src/jeoneum/`에 모듈 골격이 있으며(검증된 align/mix는 실제 구현, 크로스레포 부분은 스텁), 본격 구현 전입니다. 상세 설계는 [`docs/spec.md`](docs/spec.md).

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

## License

[PolyForm Noncommercial License 1.0.0](LICENSE.md).
소스는 공개되며 **누구나 비영리 목적으로 자유롭게 사용·수정·배포**할 수 있습니다.
**상업적 이용 권리는 저작자에게 유보**됩니다 — 상업 라이선스는 저작자에게 문의.
(chalna에는 LICENSE 파일이 없어 본 프로젝트가 신규 채택. chalna 본체에도 동일 라이선스 추가는 별도 논의.)

---

## 인터뷰 진행 상황

확정 결정은 위 표와 [`docs/spec.md`](docs/spec.md)에 반영. 남은 오픈 이슈는 spec 문서의 "Open Questions" 참조.
