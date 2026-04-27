# CCUT 1.0.4 MASTER SPEC v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 1. 정의
CCUT은 영상 데이터를 의미 데이터로 변환하는 로컬 AI 시스템이다. 핵심은 단순 속도가 아니라 **실행 가능한 의미 데이터 구조**다.

## 2. 핵심 철학
1. 사용자 결정 우선: AI는 제안만 한다.
2. 로컬 자원 적극 활용: CPU/GPU/RAM/Disk를 Resource Governor로 통제한다.
3. 의미 중심: Evidence → Semantic → Proposal.
4. Fragment 기반 편집: 편집/Proposal 단계에서는 영상 없이 JSON 조합으로 처리한다.
5. 데이터 재사용: Multi-Layer Cache와 fingerprint를 사용한다.

## 3. 영상 사용 원칙
```text
분석 단계: 최소한의 영상 접근 허용
- Proxy 생성
- Keyframe 추출
- Motion/Scene 분석
- 원본 접근은 필요한 경우 허용하되 반복 분석 금지

편집/Proposal 단계: 영상 로딩 금지
- Semantic Fragment JSON 조합
- A/B Proposal JSON 생성

Preview/Export 단계: 영상 사용 허용
- Preview 로딩
- 원본 기반 최종 렌더 1회
```

## 4. 실행 순서
```text
P1: Proxy 생성 + Segment Partitioning
P2: Evidence Board 생성
P3-pre: Quick Intent Seed
P4: Semantic Fragment 생성
P3-post: User Intent 최종 반영
P5: Proposal 생성
P6: ExportInput 생성 및 Export
```

## 5. GPU/CPU 실행 규칙
GPU 인코딩은 벤더별로 선택한다.
- NVIDIA: NVENC
- AMD: AMF
- Intel: QSV
- GPU 불가: CPU x264 fast fallback

Whisper/Qwen/VLM은 GPU 가능 시 GPU를 사용하고, 불가능하면 CPU 또는 rule-based fallback을 사용한다.
GPU 우선순위는 고정이 아니라 phase별 동적 조정이다.
- 초기: Proxy / Keyframe 우선
- Evidence 30% 이후: Qwen Semantic 우선순위 상승
- Preview/Export 전: Render 우선

## 6. Worker Conflict 원칙
Segment 전체 overwrite 금지. **field-level merge**를 기본으로 한다.
- text → Whisper Worker
- audio_rms/silence → Audio Worker
- scene_change → Scene Worker
- motion_score → Motion Worker
- keyframe → Keyframe Worker
동일 필드 충돌 시 confidence 높은 값 선택. confidence 동일 시 최신 timestamp 선택.

## 7. Coverage 규칙
- Segment 범위는 `[start, end)` exclusive end 모델을 사용한다.
- overlap 구간은 merge 후 1회만 coverage에 포함한다.
- `coverage = covered_duration / total_duration`
- 목표 coverage는 1.0이다.

## 8. 필수 산출물
- analysis_bundle
- evidence_board
- semantic_fragments
- user_intent
- proposals
- proposal_qa
- export_input
- archive decision records

## 9. 완료 판정
아래가 모두 가능해야 한다.
```text
Upload → Proxy → Evidence → Semantic → Intent → Proposal → ExportInput → Export
```
