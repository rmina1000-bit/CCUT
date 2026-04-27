# VIDEO USE SAFETY RULE v3.2.1
> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지

## 원칙
Video Use의 개념은 참고하지만 코드는 복사하지 않는다.

## 금지
- video-use 코드 직접 복사
- 동일 파일명/함수명/구조 재현
- timeline_view.py 직접 이식
- self-eval loop 동일 구현

## 허용
- 텍스트 우선 편집 아이디어 참고
- Proposal 전 가설 확인 UX 참고
- FFmpeg 표준 기법 사용
- 독자 구현

## CCUT 차별화
- 자동 확정이 아니라 사용자 결정
- Evidence/Semantic-first
- Local Resource Orchestration
- Archive/decision_log 기반 학습 데이터
