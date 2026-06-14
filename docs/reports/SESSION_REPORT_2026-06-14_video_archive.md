# CCUT 작업 보고서 — 영상 파이프라인 + 아카이브 + 조각 검색

> 작성: 2026-06-14 · branch `ccut-1.0.4-step9`
> 범위: 조각 자연어 검색 토대 / 영상 재생 6중 버그 해결 / 아카이브 전면 개편 / soft-delete

---

## 1. 조각 자연어 검색 (큐원VL + 임베딩) — CCUT의 C 이념 토대

채팅창에서 "영국에서 비오는날 찍었던 중년 아저씨를 찾아서 불러와줘" 같은 자연어로 조각을 검색하는 기능. 큐원(Qwen) 도입의 근본 목적.

| 구성 | 파일 | 내용 |
|------|------|------|
| DB | `archive/db_models.py` | `fragment_index` 테이블(23컬럼) + FTS5 `fragment_fts` |
| 마이그레이션 | `tools/migrate_fragment_index.py` | 테이블 + FTS5 + 동기화 트리거 생성 |
| 임베딩 | `engine/embedding_model.py` | paraphrase-multilingual-MiniLM-L12-v2 싱글톤(384d, 한↔영 cross-lingual) |
| VL 묘사 | `engine/fragment_vl_describer.py` | qwen3-vl:4b 키프레임 묘사 (num_predict 512 → 6s/장, 기존 32s 대비 5배) |
| 인덱서 | `engine/fragment_indexer.py` | 키프레임(ffmpeg)→VL묘사→임베딩→저장, curated 우선 |
| 검색 | `engine/fragment_search.py` | 시맨틱(numpy cosine) + FTS5 하이브리드 |
| 채팅 의도 | `engine/fragment_chat.py` | 검색 동사 룰베이스 분류 |
| API | `main.py` | `GET /fragment-search`, `POST /chat/fragment-search`, `GET /fragment-search-status` |
| 프론트 | `CenterPanel.tsx` | handleSendFull 검색 분기 + 결과 카드 |

**검증:** "도시 빌딩 야경" → 두바이 영상 0.613 (한국어 쿼리↔영어 VL묘사 cross-lingual 매칭 확인). 현재 28개(curated 일부) 인덱싱. **전체 인덱싱은 단계 6에서.**

---

## 2. 영상 재생 6중 버그 — 전부 해결

국장 화면에서 영상이 멈추던 문제. 6개의 독립적 원인이 겹쳐 있었음:

| # | 원인 | 해결 |
|---|------|------|
| 1 | **faststart 안 됨** (moov atom이 파일 끝) → 스트리밍 시 영상 멈춤 | render/preview 엔진에 `-movflags +faststart` |
| 2 | **이중 storage 경로** (export는 `ccut_backend/storage`, STORAGE_DIR은 루트) → 404 | `_resolve_static_path()` 양쪽 탐색 |
| 3 | **concat inpoint/outpoint** timestamp 손상 → 실제 1.357fps | 각 클립 `-ss/-to` 정밀 추출 + 30fps CFR 정규화 |
| 4 | **keyframe 부족** (ultrafast 긴 GOP) → 조각 경계 디코드 불가 | `-g 30 -keyint_min 30 -sc_threshold 0` (1초마다 keyframe) |
| 5 | **브라우저 캐시** (Cache-Control 없음) → 옛 영상 재생 | output_url에 `?v={mtime}` 캐시버스터 + `Cache-Control: no-cache` |
| 6 | **concat copy의 SPS/PPS 경계 불일치** (진짜 핵심) → Chrome 디코더가 첫 조각 경계에서 멈춤 | concat을 재인코딩(단일 stream)으로 변경 |

**핵심 교훈:** proposal_preview_engine은 원래 재인코딩 concat이라 멀쩡했고(제안 재생 정상), render_engine만 concat copy라 멈췄음. 이 대조가 6번 원인을 특정하는 단서였음.

**부수 효과:** veryfast 재인코딩으로 export 파일 크기 1/4 축소 (Mimosa 102MB→26MB).

**기존 export 일괄 재렌더:** `scratch/rerender_broken_exports.py`로 47개 재렌더(파일 덮어쓰기 → mtime 갱신 → 캐시버스터 자동). 고아 export(export_input 소실) 5개는 재렌더 불가하나 SNS는 프로젝트별 최신만 표시하므로 무해.

---

## 3. soft-delete + 강한 경고 (아카이브 신념: 흔적 불멸)

- DB: `programs.deleted_at` 컬럼 추가
- `DELETE /projects/{id}` → hard-delete 폐기, **status='DELETED' + deleted_at** (30일 보관)
- `POST /projects/{id}/restore`, `DELETE /projects/{id}/purge`, `GET /projects/trash` 신규
- `/projects` 목록: 30일 경과분 자동 완전삭제 + deleted 필터
- 프론트(LeftNav): 빨간 강한 경고 모달 ("30일 보관 후 영구삭제, 누구도 되살릴 수 없습니다")
- 검증: Sirius 삭제→휴지통30일→복원 왕복 (원상복구)

---

## 4. 아카이브 전면 개편

| 항목 | 내용 |
|------|------|
| `/archive/list` 보강 | proposals에 program_id/program_deleted, programs에 proposal_count/export_count/deleted_at, sources에 play_url |
| 프로젝트 관리 드릴다운 | [이력▾] → 원본/제안/내보내기 펼침 + **클릭 시 그 자리 인라인 재생** + [열기]/[복원] |
| 제안 즉석 렌더 | 모든 제안 [재생] — `POST /proposals/{id}/preview`로 on-demand 렌더(캐시 348개 즉시), proposal_preview_engine 활용 |
| 제안 프로젝트 귀속 | 프로젝트명 배지(직접/삭제), 클릭 이동은 제거(표시 전용), [열기] 버튼만 이동 |
| 원본 리스트 | 이름변경 + 재생 + **삭제 2-옵션**(원본만 삭제=노출위험영상/조각보존, 전체삭제) |
| SNS 버튼 정리 | 혼란스럽던 "SNS 업로드"(→프로젝트 이동) 중복 제거 |
| 로딩 지속 | complete 후 "이 프로젝트는~" 컨설팅 설명 뜰 때까지 로딩 유지 |

---

## 5. 변경 파일 목록

**백엔드:** `main.py`, `archive/db_models.py`, `archive/manager.py`, `engine/render_engine.py`, `engine/proposal_preview_engine.py`, `engine/embedding_model.py`(신규), `engine/fragment_{vl_describer,indexer,search,chat}.py`(신규 4), `tools/migrate_fragment_index.py`(신규)

**프론트:** `components/{ArchivePanel,CenterPanel,LeftNav,SnsUploadPanel}.tsx`, `services/videoService.ts`, `pages/Index.tsx`(prop 전달)

**DB 스키마 2건:** `fragment_index` 테이블+FTS5, `programs.deleted_at` 컬럼

---

## 6. 미해결 / 다음 단계

- **단계 5**: 제안 고급화 (curated 조각 가중치로 편집 품질 향상)
- **단계 6**: 전체 인덱싱 (28개 → 전체 fragment, ~11분, 검색 범위 확대)
- export_input.clips에 start/end=null인 비정상 데이터 존재 (생성 단계 검증 필요)
- 고아 export 5개 (export_input 소실, 재렌더 불가)
