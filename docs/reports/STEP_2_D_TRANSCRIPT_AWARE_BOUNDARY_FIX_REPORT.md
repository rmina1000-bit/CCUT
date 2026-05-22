# STEP 2-D Transcript-Aware Boundary Fix Audit Report

## Phase 1 — 사전 감사 결과

### 1-A. semantic_fragments start/end 생성 위치 파악

| 기능 | 위치 (라인 번호) | 설명 |
|------|-----------------|------|
| 경계 후보 생성 | `semantic_engine.py:103-143` | `whisper_segments`, `scene_change`, `silence` 등을 `boundaries` 리스트에 수집 |
| 경계 필터링 | `semantic_engine.py:151-162` | 0.8초 미만 간격의 경계를 병합/제거 |
| Fragment 객체 생성 | `semantic_engine.py:170` | `boundaries` 리스트를 순회하며 `start`, `end`를 할당 |
| Merge 보정 | `semantic_engine.py:289, 317` | 3초 미만 조각 또는 개수 제한 초과 시 `end`를 확장하여 병합 |
| Split 보정 | `semantic_engine.py:377` | 20초 초과 조각 분할 시 `part_end`를 계산하여 `end`로 할당 |
| DB Write | `semantic_engine.py:84` | `self.bams.save_semantic_fragments` 호출을 통해 저장 |

### 1-B. ASR/transcript 텍스트 저장 위치 파악

| 데이터 | 저장 위치 | 형식 | 컬럼/키 |
|--------|----------|------|---------|
| 문장 세그먼트 | `evidence_board` | String | `text` (worker_name='whisper_segments' 일 때) |
| 단어별 타임스탬프 | `fragments` | JSON | `intelligence['words']` (리스트 형식) |
| 전체 텍스트 | `fragments` | JSON | `intelligence['transcript']` |
| 조각 요약 | `semantic_fragments` | JSON | `semantic_json['summary']` |

*참고: Qwen3-ASR 사용 시 word-level timestamp가 비어 있을 수 있음. 이 경우 `whisper_segments` 기반의 문장 경계 보정이 필수적임.*

### 1-C. Audit Tool 생성 결과

- **경로**: `tools/audit_transcript_fragment_boundary.py`
- **주요 로직**: 
    1. `whisper_segments` 중 마침표(`. ? !` 등)로 끝나는 세그먼트의 `end`를 문장 끝점 후보로 추출.
    2. `semantic_fragments`의 `end`와 가장 가까운 문장 끝점 사이의 `gap` 계산.
    3. `gap > 0.3s` 인 사례를 추출하여 보고.

### 1-D. 끊김 사례 보고 (Audit Tool 실행 결과 예상)

> **[IMPORTANT]** 현재 환경의 `run_command` 제약으로 인해 Antigravity가 직접 툴을 실행하지 못했습니다. 
> 작성된 `tools/audit_transcript_fragment_boundary.py`를 직접 실행해주시면, 해당 결과를 바탕으로 1-D 보고 및 Phase 2 구현에 착수하겠습니다.

---
*발행: Antigravity | Phase 1 감사 완료 보고*
