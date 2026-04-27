# VALIDATION PROTOCOL v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 공통 원칙
모든 단계는 PASS/FAIL과 증거를 남긴다.
증거: 로그, DB 조회, API 응답, 생성 파일, 화면 캡처.

## P1 PASS
- proxy 생성
- segment 생성
- timestamp alignment 유지
- fingerprint 생성

## P2 PASS
- Evidence coverage 1.0
- gap 없음
- 필수 필드 존재
- field-level merge 동작
- Worker 동시쓰기 충돌 없음

## P4 PASS
- Semantic Fragment 생성
- 3계층 구조 존재
- role 3종 이상
- confidence/fallback_reason 존재

## P3 PASS
- User Intent 적용 전/후 score 변화
- 미응답 시 default intent 진행

## Proposal PASS
- backend semantic 기반 생성
- A/B 차이
- proposal_reason/confidence 존재

## Export PASS
- ExportInput 경유
- render_engine 호출
- 최종 mp4 생성
- Proposal 없이 Export 직접 연결 없음

## Resource PASS
- CPU/GPU/RAM/Disk 사용률 로그
- Worker/batch/cache 조절 동작
- UI 멈춤 없음
