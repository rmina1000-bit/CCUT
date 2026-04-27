# EVIDENCE BOARD v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 정의
모든 분석 데이터를 통합한 Timeline 기반 SSOT다.

```text
Video → Proxy → Segment Partitioning → Worker 병렬 분석 → Evidence Board
```

## Segment Partitioning
- 구간 길이: 10~30초 동적 조정
- overlap: 0.5초
- 모든 Worker는 segment 단위로 독립 수행
- 결과는 timestamp 기준 병합
- `[start, end)` exclusive end 기준

## Evidence Segment Schema
```json
{
  "segment_id": "seg_001",
  "start": 0.0,
  "end": 1.0,
  "text": "transcription",
  "audio_rms": 0.5,
  "silence": false,
  "motion_score": 0.7,
  "scene_change": false,
  "keyframe": "frames/abc123_0000.jpg",
  "confidence": 0.95,
  "fallback_reason": null,
  "worker_sources": {
    "text": "whisper_worker_1",
    "audio_rms": "audio_worker_1",
    "motion_score": "motion_worker_1"
  },
  "timestamp": "2026-04-26T02:50:00.123Z"
}
```

## Write Rule
Worker는 DB에 직접 쓰지 않는다.
```text
Worker → 독립 Memory Buffer → 1초 batch 누적 → field-level merge → DB flush
```

## Field-Level Merge
Segment 전체 overwrite 금지.
- text: Whisper 결과
- audio_rms/silence: Audio 결과
- scene_change: Scene 결과
- motion_score: Motion 결과
- keyframe: Keyframe 결과
동일 필드 충돌 시 confidence 높은 값 선택. confidence 동일 시 최신 timestamp 선택.

## Coverage
```text
coverage = covered_duration / total_duration
```
- overlap은 1회만 포함
- gap 없음
- 목표 coverage = 1.0

## Adaptive Window
- speech_density 높음: 0.5초
- 일반: 1초
- 침묵/정적: 2~3초

## Fail-Safe
- Whisper 실패: text="", confidence=0.3
- Motion 실패: motion_score=0.5, confidence=0.4
- Scene 실패: scene_change=false, confidence=0.4
- Keyframe 실패: keyframe=null, confidence=0.2

## PASS
- coverage 100%
- gap 없음
- 필수 필드 존재
- confidence 존재
- Worker 동시 쓰기 충돌 없음
