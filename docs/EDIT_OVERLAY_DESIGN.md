# EDIT_OVERLAY_DESIGN v1.0

BETA_EDITING_BACKBONE_SPEC v1.0 §15 구현 설계. C-0 AUDIT 관례 raw 근거.
이 문서는 설계안이다. 코드 0. 국장+ChatGPT 검토 확정(2026-06-07).

## 1. edit_overlay 테이블 목적
- 사용자 편집 결과(trim·exclude·split)를 원본과 분리해 영속.
- 원본 semantic_fragments(start/end)는 불가침. overlay가 그 위에 "사용자 결정"을 얹음.
- 읽는 쪽(조각맵·정밀편집·재생·Preview)은 원본+overlay를 합쳐 effective range로 본다.

## 2. 테이블명
- edit_overlay (소문자 스네이크, sources/proposals/export_input과 동일 톤)

## 3. PK 방식 + overlay_id 생성 규칙 (확정: String 단일 PK)
- overlay_id = Column(String, primary_key=True, index=True)
- 생성 규칙:
  - 단순 trim overlay: OVL_{fragment_id}
  - split overlay: OVL_{derived_fragment_id}  (derived = SF_001#A 등)
  - _copy_ 조각: OVL_{copy_fragment_id}  (copy = ..._copy_{ts} 또는 ..._copy_{ts}#A)
- db_models.py 계열 String PK 관례에 맞춤.

## 4. source_id / fragment_id 매핑 (확정: FK 안 검, index만)
- source_id = Column(String, index=True)
- fragment_id = Column(String, index=True)
- fragment_id에는 화면/Proposal에서 실제로 쓰는 조각 ID를 저장(파생/복사 id 포함).
- FK 제약 미설정 — 분할 파생 조각(#A/#X/#B)은 semantic_fragments에 없는 새 id라 FK 시 무결성 예외. 논리적 연관은 root/parent 필드로(§10).

## 5. effective_start_sec / effective_end_sec (확정)
- effective_start_sec = Column(Float)
- effective_end_sec = Column(Float)
- 초(秒) 단위. frame 없음(SPEC §6 단일화). 이 조각의 살아있는 시작·끝(초).

## 6. excluded (1차 후보 Boolean, 구현 전 raw 확인)
- 1차 후보: excluded = Column(Boolean, default=False, nullable=False)
- 단, C-0 raw에서 Boolean import·사용 전례는 확인되지 않음(확인된 import: Column, String, Float, DateTime, JSON, ForeignKey).
- ★구현 전 read-only로 Boolean import 및 기존 사용 여부 확인. Boolean 전례가 없거나 import 추가 범위가 크면 String("true"/"false") 또는 Integer(0/1) 대안 검토.

## 7. edit_type (확정)
- edit_type = Column(String, index=True)  # "TRIM" | "EXCLUDE" | "SPLIT_KEEP" | "SPLIT_EXCLUDE"
- learning_models decision_type(String index) 관례 차용.

## 8. derived fragment 식별자 규칙 + 필드 역할 (개념)
- 파생 조각은 새 fragment_id를 갖되 root_fragment_id로 원본 추적.
- fragment_id = 화면/Proposal에서 실제 쓰는 조각 ID(파생·복사 포함).
- root_fragment_id = 원본(최상위) 추적 ID.
- 단순 trim(분할 없음)은 파생 id 없이 원본 fragment_id 그대로 + overlay 1건.
- split(가운데 제거)만 파생 id 생성(§9).

## 9. #A/#X/#B 파생 ID 규칙 (확정)
- 원본 SF_001 가운데 제거 시 셋 분할:
  SF_001#A  앞   excluded=false  edit_type=SPLIT_KEEP
  SF_001#X  가운데 excluded=true   edit_type=SPLIT_EXCLUDE
  SF_001#B  뒤   excluded=false  edit_type=SPLIT_KEEP
- 규칙: {원본fragment_id}#{A|X|B}. 구분자 # 1개.
- 2차 분할(재분할): 베타 미지원. 프론트 UI에서 차단. 1단계 분할(최대 3조각)만 공식 지원. (확정)
- _copy_ 조각 분할: 허용. 파생 id = {fragment_id}_copy_{timestamp}#A 형태로 유일성 보장. (확정)

## 10. parent/root fragment 관계 (확정)
- root_fragment_id = Column(String, index=True)  # 최상위 원본 조각 id
- parent_fragment_id = Column(String, nullable=True)  # 직전 조각(1단계면 root와 동일)
- 프론트 Fragment 타입에 root_fragment_uid/parent_fragment_uid 존재 → 프론트 보유, overlay에 저장만.

## 11. created_at / updated_at (확정)
- created_at = Column(DateTime, default=datetime.datetime.now)
- updated_at = Column(DateTime, default=datetime.datetime.now)

## 12. metadata_json (확정)
- metadata_json = Column(JSON, default=dict)  # orig_start_sec/orig_end_sec 백업, 편집 이력 등 확장용.

## 13. 기존 테이블 불변 원칙 (확정)
- semantic_fragments / proposals / export_input / sources / fragments 스키마 변경 0.
- edit_overlay만 신규 추가. 읽는 시점에 overlay를 원본에 합쳐 effective 생성.
- archive_fragments / save_fragments / save_edit 경로 미수정(별도 API).

## 14. API 초안 (개념)
- POST /edit-overlay — body: {source_id, fragment_id, effective_start_sec, effective_end_sec, excluded, edit_type, root_fragment_id, parent_fragment_id?}. upsert(같은 overlay_id면 갱신).
- GET /edit-overlay/{source_id} — 그 소스의 overlay 전체 반환(프론트가 원본에 합침).
- 기존 /save_edit: 호환 위해 유지하되 편집 영속엔 미사용. 정밀편집 저장/복원은 /edit-overlay만. (확정)
- 백엔드 신규 작업이므로 STEP F에서 구현, 그 전 read-only AUDIT 선행.

## 15. 정의 위치 (확정: db_models.py)
- edit_overlay는 archive/db_models.py에 정의. (학습 격리 영역 learning_models 아님 — 편집 상태는 아카이브·렌더 직결 핵심 데이터)
- manager.py L9 Base.metadata.create_all(bind=engine)로 서버 가동 시 자동 생성.
- ★구현 전 확인: learning_models의 Base와 db_models의 database.Base가 동일 Base인지, create_all 시점이 신규 테이블을 잡는지 read-only 1줄 확인.

## 16. PASS 기준
- DESIGN PASS: 이 설계 국장+ChatGPT 본문 검토 통과.
- 이후 구현 STEP D~H에서 각각 CODE/RUNTIME/BROWSER/PRODUCT PASS.
- 설계 검증 케이스(개념): trim 1건 저장→조회 effective 반영 / split 3분할 id #A·#X·#B / excluded=true 재생 제외 / 원본 테이블 무변경 / b5cee91 회귀 없음.

## 확정 사항 (2026-06-07, 국장+ChatGPT)
1. PK = overlay_id String 단일 PK. 생성규칙 OVL_{fragment_id}(파생/복사 id 반영).
2. fragment_id FK 안 검, index만. fragment_id=실사용 id, root_fragment_id=원본 추적. 연관은 root/parent 필드.
3. excluded = Boolean 1차 후보. 구현 전 Boolean 전례 read-only 확인, 없으면 String/Integer 대안.
4. 2차 분할 미지원(1단계만), 프론트 차단.
5. _copy_ 조각 분할 허용, id {fragment_id}_copy_{ts}#A.
6. /save_edit 유지하되 편집 영속 미사용, /edit-overlay만.
7. 정의 위치 db_models.py. Base/create_all 경로 구현 전 확인.
