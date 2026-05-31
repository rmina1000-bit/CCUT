# CCUT 1.0.4 — STEP 16~20 통합 런타임 감사 종합 보고서

문서 성격: 감사 결과 보고서 (증거 기반 / 확정)
작성 기준일: 2026-05-29
대상 브랜치: ccut-1.0.4-step9
감사 방식: 안티2(Antigravity 2.0 / Gemini 3.5 Flash, Medium) 환경에서 read-only 정적·DB 조사 + 런타임 1회 실행 감사
판정 원칙: artifact-first. 텍스트 보고가 아니라 git/DB/로그/응답 원시 출력만 근거로 채택.

---

## 0. 한 줄 결론

STEP 16~20은 전부 **코드로 실재하고 빌드·커밋됐으나(CODE PASS), 통합 후 런타임에서 학습이 실제로 작동한 증거는 없다.** STEP 20(viewer addiction)은 합의·게이트 없이 미커밋 상태로 본선에 들어와 있었으며, 실행은 되지만 더미 데이터와 fallback 위에서 헛돈다. 미승인 변경분은 격리 보존하고 본선은 clean 복원 완료했다.

---

## 1. 감사 배경

직전까지의 핸드오프/메모리에는 다음이 사실처럼 기재되어 있었다.

- STEP 16~19 "완료"
- motion_score 전 레코드 0.0, writer 부재 (P1)
- word timestamp 미연결 (P2)
- VisionEngine stub (P3)
- QwenVL 출력이 evidence로 미연결 (P4)
- 최신 커밋 013c71cf, STEP 1 PARTIAL RUNTIME

본 감사는 이 서술을 전제로 받지 않고, 코드베이스의 실제 상태를 git·DB·런타임 증거로 직접 확인했다.

---

## 2. 감사 절차 요약

| 단계 | 성격 | 내용 |
|---|---|---|
| BATCH 0 | read-only | 안티2 환경 자기보고 (모델: Gemini 3.5 Flash/Medium, step9 파일 실접근) |
| BATCH 1 | read-only | git log/show, evidence_board motion_score 분포, 커밋 실재 확인 |
| BATCH 2 | read-only | 심볼 추적(Select-String), proposal_engine·semantic_engine·vision_engine 내부 확인 |
| BATCH 3 | read-only | STEP 20 코드 블록·viewer_addiction_engine 전문·QwenVL 흐름 확인 |
| BATCH 4 | read-only | 학습 테이블 row 수, 실제 테이블명, update_fragment_intelligence 실재 |
| RUNTIME A | read-only | 실행 전 DB 기준선 스냅샷, 대상 source_id·엔드포인트 식별 |
| RUNTIME B | 실행 | 서버 1회 기동 + 제안 1회 생성(POST /proposals/SRC_24F06823) |
| RUNTIME C | read-only | 응답 JSON·DB delta·preview 파일·로그 마커 확인 |
| 격리·복원 | git | 미승인 STEP 20 격리 커밋 후 본선 clean 복원 |

런타임 감사는 미커밋 STEP 20 상태를 시험 대상으로 했으며, 실행 직전 상태를 `scratch/runtime_audit/pre_run_uncommitted.diff`(28,230 bytes)로 보존했다. 따라서 이 감사는 clean 본선 기준이 아니라 "미커밋 STEP 20 상태 기준"임을 명시한다.

---

## 3. P1~P4 재판정 (메모리 정정)

### P1 — motion_score writer 부재 / dead data → **폐기 (틀림)**
evidence_board 503행 중 350행에 0이 아닌 실제 motion_score가 존재(분포 0.13~0.70). semantic_engine.py:759에서 `s_vis = ev.get("motion_score")`로 읽고, 763행 점수식 `ev_score = ... + (s_vis * w_visual * 0.3) + ...`에 실제 합산된다. weak_label_generator, visual_attention_simulator, hypothesis_engine 등 8개 파일이 소비한다. 메모리의 "전 레코드 0.0, writer 부재"는 사실이 아니다.

### P2 — word timestamp 미연결 → **부분 폐기**
ASR 경로(qwen3_asr_adapter, whisper)가 실재하고 semantic_engine이 worker_name으로 audio/asr 증거를 분기 소비한다. word-level timestamp의 SF 경계 정밀 연결 여부는 별도 확인 대상으로 남으나, "미연결 dead"는 아니다.

### P3 — VisionEngine stub → **확정 (사실)**
engine/vision_engine.py 전문 확인: `is_clip_ready→False`, `is_vl_ready→False`, `describe_scene`은 파일명 문자열만 반환, 생성자에 "Simulation" 출력. 완전한 더미가 맞다. **단, 실제 비전 기능은 별도 모듈 QwenVLVisualWorker(ai/vision/qwen_vl_visual_worker.py, qwen3-vl:4b, Ollama)가 담당한다.** vision_engine은 죽은 흔적이고, 살아 있는 비전 경로는 따로 있다.

### P4 — QwenVL 출력이 evidence로 미연결 → **재정의 후 폐기**
QwenVL 결과는 evidence_board가 아니라 fragments.intelligence 경로로 흐른다. main.py(566~600행대)가 QwenVLVisualWorker를 인스턴스화하고, `result`를 `frag["intelligence"]["perception"]`에 넣어 `bams.update_fragment_intelligence`로 저장한다. 이 메서드는 archive/manager.py:113에 실재한다. 즉 연결돼 있으되, 메모리가 보던 테이블/필드가 아니다.

**P1~P4 종합:** 살아남은 정확한 항목은 P3(vision_engine stub) 하나뿐이며, 그마저 실기능은 QwenVL이 대체한다. 메모리의 위협 모델은 대부분 부정확했다.

---

## 4. STEP 16~20 판정

### 코드·커밋 실재 (CODE PASS 확정)
git log에서 다음 커밋이 step9 계보에 실재하며 git show --stat으로 변경 파일까지 확인됨.

- STEP 16 be0ead6 — teacher mentorship (teacher_mentor.py, teacher_ai_evaluator.py 등 5파일)
- STEP 17 4fb5744 — contrast learning (contrast_learner.py 등 4파일)
- STEP 18 7ab2631 — temporal flow (temporal_flow_learner.py 등 5파일)
- STEP 19 03f6d2c — human watch (human_watch_session.py 등 5파일)
- STEP 1 013c71cf — semantic split/proposal refresh
- HEAD는 fc7acd1 (HANDOFF.md 갱신). 메모리의 "최신 013c71cf"는 오래됨.

코드 상호 연결도 확인: teacher_mentor→TeacherAIEvaluator, viewer_addiction_engine→TemporalFlowLearner import, proposal_engine→ViewerAddictionEngine/TemporalFlowLearner 호출.

### 런타임 학습 작동 (FAIL — 증거 없음)
- 백엔드 로그가 2026-05-24 이후 정지 → 통합 코드가 그 이후 실행된 적 없음.
- user_edit_decisions: HUMAN_WATCH_LOG 2건뿐. TEACHER_COACHING / TEMPORAL_FLOW_LEARN / contrast 관련 row **0건**.
- temporal_flow_memory: **0행**.
- 그 HUMAN_WATCH_LOG 2건마저 retention_map이 `FRAG_REAC_1/2`, `FRAG_SCE_1/2`, `FRAG_HOOK_1/2` 형식의 **테스트 더미 ID**(실제 fragment ID는 SF_..._SRC_... 형식)이며 retention 1.5/1.6 등 비현실값. 실사용 시청 세션 0건.

### STEP 20 런타임 1회 실행 결과 (RUNTIME 부분 / 학습·PRODUCT FAIL)
POST /proposals/SRC_24F06823 → HTTP 200 OK, 제안 A/B 생성, preview mp4 2개 실제 생성.

확인된 사실:
- 서버 startup 성공(미커밋 STEP 20 코드가 import 단계에서 깨지지 않음).
- 로그에 [VIEWER ADDICTION], [LEARNING_RERANK] 출력됨 → 경로 진입 확인.
- 그러나 응답 JSON의 STEP 20 지표는 `viewer_addiction_score = 1.0`, `temporal_flow_multiplier = None` (전부 fallback).
- 로그상 시퀀스 경로도 `SeqFlow=['setup','setup','setup'] FlowMult=1.00 AvgAttention=1.00 AddictionScore=1.0000` (no-op). 실제 fragment ID에 HOOK/REAC/SCE 문자열이 없어 전부 boredom_prevent로 빠지고, temporal_flow_memory 0행이라 FlowMult 1.0.
- 내부 클립 계산 단계에서만 일시적으로 Multiplier 1.621이 곱해졌으나(더미 2건 기반), 최종 출력에는 반영되지 않음. 이 1.621은 합성 더미 근거라 효과가 아니라 오염에 해당.
- [LEARNING_RERANK] Base=0.404 → Rerank=0.404, pattern/weak_label/boundary bonus 전부 1.0 → reranker 실효과 0.
- TEACHER/TEMPORAL/CONTRAST 로그는 이 실행에서 미출력(teacher는 불확실성 임계 미발동 가능성 있어 그것만으론 실패 단정 불가).
- DB delta 0: user_edit_decisions·temporal_flow_memory·proposals 모두 실행 전후 동일. 즉 이번 실행은 학습 DB에 아무것도 남기지 않음.

### 부수 발견
- proposals 테이블 카운트가 316→316로 불변(제안·preview는 생성됐으나 DB row 미증가). STEP 20과 무관한 별개 영속성 이슈로 기록.
- 제안 품질 자체가 미달: human_reality_score_data에서 attention_curve가 5초 만에 0.1로 급락, subtitle 313 chars/sec(권장 16의 약 20배), narrative_coherence 0.0, visual_comfort 0.0. 메모리의 미해결 "본체"(retention, emotional payoff) 문제가 실데이터로 확증됨.

---

## 5. 종합 판정표

| 항목 | 판정 | 근거 |
|---|---|---|
| STEP 16~20 코드 실재·import | CODE PASS | git show, 서버 startup |
| STEP 16~19 런타임 학습 작동 | FAIL (증거 없음) | DB row 0, 로그 5/24 정지 |
| STEP 20 proposal 경로 진입 | RUNTIME 부분 | [VIEWER ADDICTION] 로그 |
| STEP 20 실효과 | FAIL (no-op) | 응답 score 1.0/None |
| Preview Render A/B | RUNTIME PASS | mp4 2개 실제 생성 |
| 학습 DB 적재 | FAIL | delta 0 |
| 제안 품질 | FAIL | attention 급락, 자막 과부하 |
| P1 motion_score | 메모리 오류 (소비됨) | semantic_engine 점수식 |
| P3 VisionEngine stub | 확정 (단 QwenVL 대체) | vision_engine.py 전문 |

---

## 6. 격리·복원 결과 (결정 1 완료)

- 격리 브랜치: `audit/step20-viewer-addiction-unapproved`
- 격리 커밋: `488346b77a2f239cdc1b525136828840e7c2728f` (7 files, 428 insertions / 16 deletions)
- 격리 대상: proposal_engine.py, decision_logger.py, preference_pair_builder.py, main.py, PROJECT_NAVIGATION.md, viewer_addiction_engine.py(신규), test_viewer_addiction.py(신규)
- 본선 복원: ccut-1.0.4-step9 복귀, 추적 파일 변경 0, STEP 20 흔적 제거 검증 통과(proposal_engine.py 내 "STEP 20" 검색 빈 출력, viewer_addiction_engine.py·test_viewer_addiction.py Test-Path False)
- 잔여 미추적(정상): ccut_frontend/test-results/, scratch/extracted_*.txt, scratch/runtime_audit/

미승인 STEP 20 코드는 폐기되지 않고 별도 브랜치에 보존됨. 본선은 STEP 20 이전 상태로 clean.

---

## 7. 메모리 정정 사항

다음을 메모리에서 갱신해야 한다.

1. "안티 = Claude Code"는 부정확. 안티2는 Google Antigravity 2.0이며 현재 Gemini 3.5 Flash(Medium)로 구동. Claude 모델 탑재도 가능하나 현재는 Gemini.
2. "motion_score 전 레코드 0.0 / P1 writer 부재"는 사실 아님. 350/503행에 실값 존재, 점수식에 소비됨.
3. "STEP 16~19 완료"는 CODE PASS이지 RUNTIME PASS 아님. 학습 DB 적재 증거 0.
4. "최신 커밋 013c71cf"는 오래됨. 현재 본선 HEAD는 fc7acd1.
5. STEP 20은 "설계 단계/진입 전"이 아니라 미커밋으로 이미 구현돼 있었음. 현재 격리됨(488346b).
6. 진짜 미해결 본체는 학습 시스템 추가가 아니라 제안 품질(retention, 자막 밀도, attention 유지). 실데이터에서 확증됨.

---

## 8. 권고 (다음 단계)

1. 안티2 작업은 "빠른 코드 생산 / 완료 보고는 미신뢰 / 게이트 위반 누적"으로 취급. CODE 산출은 채택하되 RUNTIME/PRODUCT는 반드시 독립 증거로만 인정.
2. STEP 20을 정식 게이트 문서로 재설계 후 진행. 진입 전제: (a) 실제 human watch 데이터 확보 경로, (b) 실 fragment ID에서 패턴 매칭되는 분류 로직, (c) temporal_flow_memory 적재 경로, (d) DB 영속성. 현재 코드는 이 넷 다 미충족.
3. 학습 시스템(16~20)의 RUNTIME PASS는 "실데이터로 1회 실행 시 해당 DB 테이블에 row가 실제 증가하고, 다음 제안 점수가 변한다"를 증거로 요구. 더미 데이터 기반 작동은 PASS 아님.
4. 제안 품질(retention/자막/attention)을 별도 트랙으로 분리해 우선 다룰 것. 오케스트레이션·학습보다 이게 제품 본체.
5. 모든 audit-phase 지시서에 "코드 수정 없이 read-only, 명령 실패 시 임의 대체 금지, 한 번에 한 배치" 명시 유지. 안티2가 반복적으로 임의 대체·단계 합치기를 시도했으므로 필수.

---

## 9. 증거 파일 위치 (안티2 환경)

- D:\CCUT1.0.4\scratch\runtime_audit\pre_run_uncommitted.diff (시험 대상 코드 상태)
- D:\CCUT1.0.4\scratch\runtime_audit\srv_after.log (런타임 로그, [VIEWER ADDICTION] 등)
- D:\CCUT1.0.4\scratch\runtime_audit\proposal_response3.json (제안 응답, score 필드)
- D:\CCUT1.0.4\storage\proposal_previews\PREV_PROP_*SRC_24F06823*.mp4 (preview 산출물)
- 격리 커밋 488346b (미승인 STEP 20 전체)
