# CCUT 다음 방 전달문 — 2026-06-14

> branch `ccut-1.0.4-step9` · 직전 작업: 영상 파이프라인 + 아카이브 + 조각 검색 토대
> 상세 보고서: `docs/reports/SESSION_REPORT_2026-06-14_video_archive.md`

---

## 0. 다음 방 첫 작업 — 단계 5·6 (놀라움을 결정하는 작업)

국장 평: *"5,6은 또 다른 차원의 작업. CCUT이 사람들에게 그냥 그렇게 보이냐, 놀라움을 주느냐를 결정한다."*

### 단계 6 — 전체 조각 인덱싱 (선행 권장)
- 현재 `fragment_index`에 **28개만** (curated 일부). 검색이 작동하나 범위가 좁음.
- 전체 fragment(812개 중 의미있는 것) 인덱싱 → "영국 비 중년 아저씨" 검색이 실제로 풍부해짐.
- 실행: `cd ccut_backend && python -m engine.fragment_indexer` (또는 `fragment_indexer.index_fragments(use_vl=True, only_curated=False)`)
- VL 6s/장 × 수백 개 = 수십 분~1시간. 백그라운드 + 진행 로그.
- **주의:** Ollama(qwen3-vl:4b) 가동 필수. 키프레임 ffmpeg 추출 → VL → 임베딩.

### 단계 5 — 제안 고급화 (curated 가중치)
- 검색으로 찾은/자주 쓰인 조각에 가중치 → proposal_engine이 더 좋은 제안 생성.
- `engine/proposal_engine.py` + `fragment_index.usage_count`/`is_curated` 활용.

---

## 1. 환경 / 실행

- **백엔드:** `python ccut_backend/main.py` (포트 8000, reload 없음 → 코드 수정 후 수동 재시작 필수)
- **프론트:** `cd ccut_frontend && npx vite --host 127.0.0.1` (포트 5173)
  - ⚠️ `--host 127.0.0.1` 중요: 안 주면 IPv6(`[::1]`)에만 바인딩되어 `localhost` 접속 실패
- **Ollama:** qwen3-vl:4b, qwen3:4b 등 가동 중 (조각 검색/VL에 필요)
- **임베딩 모델:** `~/.cache/huggingface/hub`에 paraphrase-multilingual-MiniLM-L12-v2 캐시됨

---

## 2. 반드시 지킬 규율 (국장 지시)

1. commit/push는 **국장 승인 후에만**. self-commit 금지
2. `git add .` / `git add -A` 금지 — 선택적 add만
3. `backend_err.log` add 금지 (추적 중이나 커밋 제외)
4. `stash@{2}` (PBE 2450줄 Temp) — pop 금지, 건드리지 마라
5. 보고는 원시출력 우선, 해석 분리. "PASS/성공/완벽"은 증거 아님 — git/DB/로그 원시출력만 채택
6. 수정 전 read-only 감사 먼저. 감사와 수술 한 턴 합치기 금지
7. **백엔드 코드 수정 후 항상 자동 재시작 + 검증까지 완료 후 보고**
8. 한 번에 한 단계, 완료 후 국장 확인 대기

---

## 3. 영상 파이프라인 함정 (재발 방지 — 메모리에도 기록됨)

`docs/reports/SESSION_REPORT_2026-06-14_video_archive.md` §2 참조. 핵심:
- **concat은 반드시 재인코딩** (`-c copy` 금지) — SPS/PPS 경계 불일치로 Chrome이 멈춤
- 모든 출력 mp4에 `-movflags +faststart` + `-g 30`(keyframe 1초)
- export는 `ccut_backend/storage/`, uploads 원본은 루트 `storage/` — `_resolve_static_path`가 양쪽 탐색
- 재렌더 후 캐시: output_url `?v={mtime}` 캐시버스터로 자동 무력화

---

## 4. 현재 dirty 상태 (이번 커밋에 미포함)

이번 세션과 무관한 이전 작업 변경이 남아있음 (커밋하지 않음, 별도 처리 필요):
- `ccut_frontend/src/components/FragmentMap.tsx`, `OriginalPanorama.tsx`, `pages/Index.tsx`(일부), `lib/fragmentIdentity.ts`
- `ccut_frontend/e2e/pbe_thumbnail_fix.spec.ts`, `vite.config.ts`
- `scratch/db_inspect.py`, `db_sample.py`
- `backend_err.log` (규율상 영구 제외)

PBE 트랙(stash@{0},{1},{2})은 미착수. 로드맵 `docs/CCUT_진행상황_및_완성_로드맵.md` PBE 섹션 참조.

---

## 5. 알려진 미해결

- `export_input.clips`에 start/end=null인 비정상 데이터(예: EXP_89932EE6) — 생성 단계 검증 필요
- 고아 export 5개 (export_input 소실, 재렌더 불가) — SNS 최신 표시엔 무해
- fragment_index 전체 인덱싱 미완 (단계 6)
