# ANALYSIS PIPELINE v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 목적
원본 영상을 반복 분석하지 않고, 분석용 Proxy와 segment 기반 Worker 구조로 raw signal을 생성한다.

## 입력
- source_video
- metadata: duration, fps, resolution, audio info

## 출력
- proxy_video
- segments
- transcript_chunks
- audio_rms
- silence_events
- scene_changes
- motion_scores
- keyframes
- fingerprint

## Proxy 규칙
- Proxy는 사용자 표시용이 아니라 AI 분석용 경량 영상이다.
- timestamp alignment 필수.
- 원본 duration과 ±0.1초 이내 일치해야 한다.

## Segment Partitioning
- 기본 원칙: 10~30초 동적 분할 (Dynamic Partitioning)
- 60초 이하: 10~30초 (컨텐츠 밀도에 따라 가변)
- 60초 이상: 15~30초
- overlap 0.5초
- Segment 범위: `[start, end)`

## Worker
- Whisper Worker: text/timestamp
- Audio Worker: rms/silence
- Scene Worker: scene_change
- Motion Worker: motion_score
- Keyframe Worker: keyframe path

## Fail-Safe
- Worker 실패 시 전체 중단 금지
- fallback value + fallback_reason 기록
