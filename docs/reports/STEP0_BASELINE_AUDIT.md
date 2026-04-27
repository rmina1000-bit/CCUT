# STEP 0 기준선 확보 보고서

## 1. 기준 문서 확인
- v3.2.1 문서팩 (MASTER_SPEC.md, PROJECT_NAVIGATION.md 등) 확인 완료.
- 핵심 흐름 `영상 → Proxy/Segment → Evidence Board → Semantic Fragment → Proposal(JSON) → ExportInput → Render`를 작업 기준으로 설정함.

## 2. Git 상태
- **결과**: `FAIL (Status Unavailable)`
- **상세**: 루트 디렉토리 및 `ccut_backend`에서 `.git` 인식이 불가함. `ccut_frontend`에 `.git` 폴더가 존재하나 표준 `git status` 명령이 워크트리 오류로 실행되지 않음. 환경 특성상 얕은 복제 또는 가상화된 트리로 추정됨.

## 3. Frontend Build 결과
- **결과**: **PASS**
- **명령**: `npm run build` (in `ccut_frontend`)
- **내용**: Vite v5.4.21 기반 빌드 성공. 에러 없음.

## 4. Backend Run 결과
- **결과**: **PASS**
- **명령**: `uvicorn main:app --host 0.0.0.0 --port 8000` (in `ccut_backend`)
- **내용**: AI PD Engine 및 Pipeline 정상 초기화. `http://localhost:8000`에서 정상 응답 확인.

## 5. Browser 확인 결과
- **URL**: `http://localhost:8080` (Frontend), `http://localhost:8000` (Backend)
- **Frontend**: **PASS** (보완 완료). 
    - 이전 `ERR_CONNECTION_REFUSED`는 Vite dev server의 네트워크 바인딩 설정 이슈였음. 
    - `npx vite --host 0.0.0.0` 실행 후 정상 진입 확인.
    - **화면 상태**: "새 프로젝트 시작" 및 원본/조각/보류맵 정상 표시.
    - **콘솔 로그**: `LeftNav.tsx`에서 `button` 중첩 경고(`validateDOMNesting`) 외 특이점 없음.
- **Backend**: **PASS**. Swagger UI (`/docs`) 정상 로드 확인.

## 6. Git Root 확인 결과
- **현재 작업 경로**: `d:\CCUT1.0.4`
- **확인 결과**: **Root Repo 아님**.
- **상세**:
    - `d:\CCUT1.0.4` 경로에는 `.git` 폴더가 존재하지 않음.
    - `d:\CCUT1.0.4\ccut_frontend` 경로에만 별도의 `.git` 폴더가 존재함.
    - 이는 본 프로젝트가 통합 레포지토리가 아닌 개별 모듈 단위로 관리되거나, 단순 코드 복사본 상태임을 시사함.

## 7. 구조 결함 목록 (v3.2.1 기준)

| 항목 | 현재 상태 | 기준상 문제 | 후속 단계 |
|---|---|---|---|
| proposal_engine | heuristic-only | Semantic 없이 Proposal 생성 위험 (데이터 무결성 결여) | STEP 6 |
| proposal_api | fragments 직접 입력 | Evidence/Semantic 검증 단계 누락 | STEP 6 |
| mock_fragments.json | mock 데이터 잔존 | UI 선행 및 휴리스틱 의존 위험 | STEP 0 격리 계획 |
| Resource Governor | 미구현 | CPU/GPU 자원 통제 및 스케줄링 부재 | STEP 8 |
| confidence/fallback_reason | 데이터 필드 없음 | v3.2.1 기술적 투명성 산출물 기준 미충족 | 각 단계별 반영 |

## 8. CCUT_1.0.3 경로 오염 목록

| 파일 | 라인 | 내용 | 위험도 | 조치 후보 |
|---|---:|---|---|---|
| `ccut_backend/engine/blackbox.py` | 8 | `d:/CCUT_1.0.3/ccut_backend/storage/blackbox.log` | 높음 | ENV `CCUT_STORAGE_DIR`로 변경 |
| `ccut_backend/engine/export_engine.py` | 12 | `D:/CCUT_1.0.3/ccut_backend/storage/exports` | 높음 | Path.join(STORAGE_DIR, "exports") |
| `ccut_backend/engine/export_engine.py` | 49 | `D:/CCUT_1.0.3/ccut_backend/storage/uploads/test_video.mp4` | 보통 | 테스트 코드 격리 |
| `ccut_backend/engine/video_engine.py` | 9 | `d:/CCUT_1.0.3/ccut_backend/storage` | 높음 | 생성자 인자 기본값 수정 |
| `tools/test_vulkan.py` | 6-8 | `D:/CCUT_1.0.3/...` (Model paths) | 보통 | 도구 옵션으로 경로 주입 |
| `frontend/vite.config.ts...mjs` | 6 | `var __vite_injected_original_dirname = ".../CCUT_1.0.3/..."` | 낮음 | 빌드 시 재생성 권장 |

## 9. Mock / Demo / Random / Legacy 목록

| 유형 | 파일 | 내용 | 현재 사용 여부 | 조치 후보 |
|---|---|---|---|---|
| Mock Data | `ccut_frontend/src/pages/Index.tsx` | `mockA`, `mockB` 더미 데이터 | UI 표시용 사용 중 | STEP 1 이후 삭제 |
| Random Logic | `ccut_frontend/src/services/proposalService.ts` | `reverse or random` 제안 로직 | 제안 생성 시 활용 | Proposal Engine 연동 시 제거 |
| Simulation | `ccut_backend/engine/processor.py` | `random.uniform(3.0, 15.0)` 기반 컷 생성 | 백엔드 테스트용 사용 중 | Evidence/Semantic 로직으로 교체 |
| Bak Files | `ccut_backend/main.py.bak` | 이전 버전 백엔드 코드 | 미사용 | `archive/legacy` 폴더로 이동 |
| Log Data | `ccut_backend/storage/blackbox.log` | 1.0.3 시절의 분석 로그 잔존 | 로그 표시용 | 파일 초기화 권장 |

## 10. 유지 자산 확인

| 자산 | 존재 여부 | 위치 | 현재 사용 여부 | 판단 |
|---|---|---|---|---|
| `scene_detector` | 존재 | `engine/signal_processor.py` (`_detect_scenes`) | 사용 중 | 유지 / 1.0.4 Evidence 연동 필요 |
| `audio_detector` | 존재 | `engine/signal_processor.py` (`_detect_silence`) | 사용 중 | 유지 / 1.0.4 Evidence 연동 필요 |
| `boundary_merge` | 존재 | `engine/boundary_editor.py` | 사용 중 | PBE 용 자산으로 유지 |
| `render_engine` | 존재 | `engine/export_engine.py` | 사용 중 | 유지 / FFmpeg 필터 로직 보존 |
| `decision_log` | 존재 | `engine/blackbox.py` | 사용 중 | 유지 / 1.0.4 추적용으로 확장 |
| `ai/interface.py` | 존재 | `ai/interface.py` | 사용 중 | 유지 / Adapter Interface 기준 |
| `qwen3_asr` | 존재 | `ai/adapters/qwen3_asr_adapter.py` | 사용 중 | 유지 / 핵심 ASR 자산 |
| `llama_server` | 존재 | `ai/runtimes/llama_server.py` | 사용 중 | 유지 / GGUF 추론기 |

## 11. 격리 계획
1.  **경로 격리**: 하드코딩된 `D:/CCUT_1.0.3` 경로를 `os.getenv("CCUT_STORAGE_DIR")`로 일괄 치환하고, `./.env` 파일을 통해 현재 경로를 주입한다.
2.  **Mock/Demo 격리**: 프론트엔드의 `mockA`, `mockB` 데이터를 `src/data/mock/` 폴더로 분리하고 `Index.tsx`에서 조건부 로딩하도록 변경한다.
3.  **랜덤 로직 봉인**: `Math.random()` 또는 `random.uniform()`이 쓰인 모든 분석 로직에 `[LEGACY_SIMULATION]` 주석을 추가하고, STEP 2(Evidence) 완료 시 해당 함수를 `DEPRECATED` 처리한다.
4.  **백업 파일 정리**: 모든 `.bak`, `.filterbak` 파일을 루트의 `_archive/legacy_baks/`로 이동시켜 프로젝트 가독성을 확보한다.


## 12. PASS / FAIL 판정
- **판정**: **PASS**
- **이유**: 프런트엔드 접속 이슈가 해결되었으며, Git 상태 및 구조적 결함 사항이 규격서 v3.2.1 기준으로 모두 목록화됨.
- **후속 작업**: STEP 1 (Proxy + Segment Partitioning) 착수에 문제 없음.

## 13. 다음 단계 매핑 (STEP 1 ~ STEP 10)
- **STEP 1**: Proxy 생성 및 지문(Fingerprint) 확보.
- **STEP 2**: Evidence Board 스키마 정의 및 병합 로직 구현.
- **STEP 4**: Semantic Fragment 3계층 구조 구현 (Step 6의 Proposal Engine 개선과 연계).
- **STEP 8**: Resource Governor 구현을 통한 안정성 확보.

