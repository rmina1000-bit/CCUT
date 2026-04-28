# EXECUTION PLAN v3.2.1

> 기준: CCUT 1.0.4 PROJECT NAVIGATION v3.2.1  
> 핵심: 영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render  
> 절대 원칙: Evidence 없이 Semantic 금지 / Semantic 없이 Proposal 금지 / Proposal 없이 Export 금지  
> **현재 기준 SHA:** `9bb6faf2be16c4d5d8ea2ef456a06d3853f1aabf`

## STEP 0. 기준선 확보 ✅ PASS

목적: 1.0.3 복사 코드의 오염과 legacy를 목록화한다.
- git status / build / backend run 확인
- `CCUT_1.0.3` 경로 전체 검색
- mock/demo/random/legacy 목록화
- 삭제 금지, 격리 계획만 작성

## STEP 1. Proxy + Segment Partitioning ✅ PASS

- 분석용 proxy 생성
- segment 10~30초 단위 분할
- overlap 0.5초
- fingerprint 생성

## STEP 2. Evidence Board ✅ PASS

- Worker 결과를 buffer에 수집
- 1초 또는 10 segment 단위 batch flush
- field-level merge
- coverage 100% 검증

## STEP 3. Quick Scan + Hypothesis ✅ PASS

- 대표 이미지 3~7개
- 짧은 영상 요약
- AI 가설 생성: 영상 성격 / 핵심 / 편집 방향
- 사용자 미응답 시 default intent로 계속 진행

## STEP 4. Semantic Fragment ✅ PASS

- Evidence 30% 이상 + transcript 10% 이상 확보 시 partial 생성
- semantic / structural / continuity 3계층 생성
- merge/split 적용
- confidence/fallback_reason 기록

## STEP 5. User Intent 최종 반영 ✅ PASS

- must_keep / avoid / tone / target_length 반영
- edit_value 재계산
- Proposal 전 re-score 완료

## STEP 6. Proposal Engine ✅ PASS

- backend semantic 기반 A/B 생성
- A: Market Mode
- B: User Mode
- proposal_reason / confidence / fallback_reason 포함
- frontend heuristic 생성 금지

## STEP 7. ExportInput 생성 ✅ PASS

- Proposal → ExportInput 변환
- clips / total_duration / status=EXPORT_INPUT_READY
- API: POST /export-input/{proposal_id}
- 스펙: `docs/EXPORT_INPUT.md`
- 보고서: `docs/reports/STEP7_EXPORT_INPUT_REPORT.md`

## STEP 8. Render Engine / Export 실행 ✅ PASS

- ExportInput 기반 ffmpeg render
- clips order/start/end/duration 처리
- source_id → sources.file_path 동적 조회
- output_url = /static/exports/...
- API: POST /render/{export_input_id}, GET /render-result/{export_input_id}
- 스펙: `docs/RENDER_ENGINE.md`
- 보고서: `docs/reports/STEP8_RENDER_ENGINE_REPAIR_REPORT.md`

## STEP 9. UI 최소연동 ✅ PASS

- 업로드 → Quick Scan → Semantic Fragment → Proposal → ExportInput → Render → mp4 표시/다운로드
- UI 리디자인 금지. API 응답 확인용 최소 표시만 허용.
- Mojibake 수정 완료 (Index.tsx)
- localhost 하드코딩 제거 완료 (CenterPanel.tsx)

## STEP 10. 최종 안정화 / 회귀 테스트 (예정)

- E2E: upload → evidence → semantic → proposal → export PASS
- Resource Governor 연동 (설계 단계)
- 회귀 테스트 시나리오 작성
