# Session Handoff — 2026-06-25

> 브랜치: ccut-1.0.4-step9
> 직전 상태: BLOCK B 분석층 복구 완료. origin: 1f36fa0 (push 완료).

---

## 최종 커밋 이력 (이번 세션)

| SHA | 메시지 | 파일 |
|---|---|---|
| 1f36fa0 | fix(semantic): B-3 기존 SF_ fragment 재계산 + force_reanalyze | semantic_engine.py, main.py |
| d9c8b28 | fix(semantic): BLOCK B 분석층 복구 (B-1/B-2) | semantic_engine.py |
| 07ba2f8 | feat(pipeline): BLOCK A 데이터 입력층 복구 | main.py, pipeline_watchdog.py |
| 699fe89 | config(ai): pipeline 섹션 추가 | ai/config.yaml |
| 075b30e | fix(playback): 조각 전환 플리커 수리 | CenterPanel.tsx |

---

## 이번 세션 핵심 수정

### BLOCK B — 분석층 복구 (SHA: d9c8b28 + 1f36fa0)

**B-1** `calculate_continuity` — `sentiment_continuity` 하드코딩 0.5 → 실계산
- `_has_text` + `confidence` 기반: 텍스트+자신감 높으면 1.0, 텍스트만 0.7, 없으면 0.3

**B-2** `calculate_edit_value` — `evidence_refs` 미매칭 시 `return 0.5` → `all_evidences` motion/audio fallback

**B-3** `reanalyze_existing_fragments()` 신규 추가 (semantic_engine.py)
- 기존 SF_ fragment에 B-1/B-2 재적용 (DB 직접 업데이트)
- 배치 실행: `POST /semantic-fragments/{source_id}` × 113개 소스
- **placeholder 0% 달성: 1179/1179 실분석**

**force 파라미터** `/generate-fragments?force=true` 추가 (main.py)
- has_semantic=True여도 dedupe 우회 강제 재분석 가능

**AUDIT 확인:**
- `/generate-fragments` dedupe(FINGERPRINT_CACHE_HIT) → semantic 재분석 없음 (가짜 성공)
- `POST /semantic-fragments/{source_id}` → `gen.generate(source_id)` 직접 호출 (실제 재분석)
- 두 경로 차이 증명 완료

### BLOCK A — 데이터 입력층 복구 (SHA: 07ba2f8 + 699fe89)
- pipeline_watchdog.py, /pipeline/status, startup watchdog, ai/config.yaml pipeline 섹션
- CODE PASS. PRODUCT PASS: 신규 업로드 후 subtitles/quick_scan 채워지면 확인

---

## 미완료 / 미확인 항목

### [최우선] Electra sourceEntries 문제
- `GET /proposals/project/proj_94d203092cd7/sources` → `status: "NO_SEMANTIC_DATA"`
- Index.tsx `data.status === "OK"` 조건 미충족 → setSourceEntries 미실행
- 수정 방향: 백엔드 status "OK" 통일 또는 프론트 gate 완화

### G1+ 조각 빠짐
- proposal A/B 모두 G_clips=0 → proposal 재생성 필요

### PRODUCT PASS 대기
- 내보내기 (R3), 편집 상태 복원, 플리커, subtitles/quick_scan 실채움
- placeholder 0% → 브라우저에서 fragment 품질 확인 필요

---

## 다음 세션 1순위

**Electra `data.status = "NO_SEMANTIC_DATA"` 원인 확인**
```
GET http://127.0.0.1:8000/proposals/project/proj_94d203092cd7/sources
```
→ 백엔드에서 해당 status 반환하는 코드 위치 찾아 "OK"로 수정

---

## 환경
- Branch: ccut-1.0.4-step9
- origin: 1f36fa0 (push 완료)
- Backend: uvicorn (D:\CCUT1.0.4\ccut_backend) — 재시작 필요 (새 코드 반영)
- Frontend: Vite dev (localhost:5173)
