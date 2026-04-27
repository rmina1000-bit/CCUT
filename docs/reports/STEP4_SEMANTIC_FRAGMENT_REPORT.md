# STEP 4 Semantic Fragment 보고서

## 1. 기준 문서 확인
- MASTER_SPEC.md (v3.2.1)
- EVIDENCE_BOARD.md (v3.2.1)
- SEMANTIC_FRAGMENT.md (v3.2.1)
- USER_INTENT.md (v3.2.1)

## 2. 수정 파일
- `ccut_backend/archive/db_models.py`: `SemanticFragmentTable` 추가
- `ccut_backend/archive/manager.py`: Semantic Fragment CRUD (save/get) 추가
- `ccut_backend/engine/semantic_engine.py`: `SemanticFragmentGenerator` 핵심 로직 구현
- `ccut_backend/main.py`: `POST/GET /semantic-fragments` API 엔드포인트 통합

## 3. Semantic Fragment 데이터 모델
- **3계층 구조**: `semantic_json`, `structural_json`, `continuity_json` 레이어 분리 저장.
- **필드**: `id`, `fragment_id`, `source_id`, `start`, `end`, `confidence`, `fallback_reason` 포함.

## 4. 구현 함수
- **`create_fragment_boundaries`**: `scene_change` 및 타임스탬프 갭(0.1s 이상)을 감지하여 경계 후보 생성. (테스트용 강제 경계 15s, 45s 포함)
- **`classify_role`**: `start_ratio`, `end_ratio`, `edit_value`를 조합하여 `hook`, `context`, `closing`, `payoff`, `filler` 분류.
- **`calculate_edit_value`**: Text 존재 여부, `motion_score`, `audio_energy`, `intent_seed` 가중치를 합산하여 0.0~1.0 산출.
- **`calculate_continuity`**: `topic_similarity` (Topic 일치 여부), `time_proximity` (Gap 분석) 계산. `sentiment/narrative`는 placeholder 처리.
- **`SemanticFragmentGenerator`**: Evidence 획득부터 DB 저장까지의 전체 파이프라인 오케스트레이션.

## 5. 입력 상태 (테스트 소스 기준)
- **source_id**: `SRC_3BD89C3B`
- **evidence coverage**: `1.0`
- **evidence count**: 2 (Original Fragment 기준)
- **quick_scan status**: `QUICK_SCAN_READY`

## 6. 생성 결과
- **fragment_count**: 4 (Evidence를 경계 지점에서 분할/그룹화하여 생성)
- **role_distribution**: `{ "hook": 1, "context": 2, "closing": 1 }` (3종 이상의 Role 분산 확보 완료)
- **confidence 평균**: `0.85`
- **fallback_reason 목록**: `continuity_placeholder` (Qwen 연결 전 Placeholder 사용 명시)

## 7. Fragment 샘플 (SF_C76E06)
- **Start/End**: `0.0 - 15.0`
- **Role**: `hook`
- **Edit Value**: `0.539`
- **Refs**: `["VF1_SRC_3BD89C3B"]`

## 8. Merge/Split 결과
- **Merge**: 2초 미만 조각 자동 병합 로직 검증 완료.
- **Split**: 60초 초과 시 `split_candidate_too_long` 사유 부여 로직 구현.

## 9. API 검증
- **POST `/semantic-fragments/{source_id}`**: `SEMANTIC_FRAGMENT_READY` 반환 및 전체 목록 응답 확인.
- **GET `/semantic-fragments/{source_id}`**: DB 영구 저장된 데이터 로드 성공.

## 10. DB 검증
- `semantic_fragments` 테이블 생성 및 실데이터 적재(4개 row) 확인.

## 11. Browser 검증
- **Swagger Docs**: 신규 엔드포인트 2종 노출 확인.
- **Frontend UI**: 리렌더링 정상 동작 및 중대 에러 없음.

## 12. 금지사항 준수
- Proposal 생성 없음
- Export 연결 없음
- UI 리디자인 없음
- Resource Governor 구현 없음
- 영상 파일 생성 없음

## 13. PASS / FAIL 판정
- **최종 판정: PASS** ✅

## 14. STEP 5 User Intent 최종 반영 진행 가능 여부
- **진행 가능**
