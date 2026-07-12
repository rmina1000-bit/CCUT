# CONCEPT ↔ CODE MAP — 개념 통일 대장 (MASTER CONCEPT §16-1단계)

> MASTER CONCEPT 1.0의 각 층이 현재 코드 어디에 사는지, 통일이 끝났는지의 단일 대장.
> 새 코드는 반드시 이 표의 개념 이름을 쓴다. 갱신 책임: 해당 층을 만지는 커밋.

| 개념 (MASTER CONCEPT §6) | 현재 코드 | 통일 상태 |
|---|---|---|
| **Source Asset** | `sources` 테이블 (source_id, file_path, duration, fps, …) — 원본 무변경 | ✅ 일치 |
| **Evidence Span** | 분산: `subtitles`(ASR·word ms), `evidence_board`(VF·audio_energy), `semantic_fragments`(좌표), `fragment_index`(visual_desc) | ⚠ 분산 — 읽기 계층(Ledger read API)이 조립. 물리 통합은 후속 협의 |
| **Ledger Span** | `ledger_span_id = LSPAN_{hash(source_id, anchor_start_ms, anchor_end_ms)}` (v1.1 패치 3, 결정론·저장 불필요) — Ledger R0 read API가 발급 | 🔨 A트랙 R0에서 구현 |
| **Fragment** | `semantic_fragments` / `fragment_index` (조각 후보 — 세분/병합 가능, 원본 좌표 유지) | ✅ 존재 (D8 fid 재발급 유의 — 좌표가 진실) |
| **Timeline Item** | `timeline_item_id` (사용본 단위, fragment_edit_state.timeline_item_id + occurrence) — B0 시대 결정론 발급식 | ✅ B0 스키마 반영 (발급 배선은 게이트 ON) |
| **Story Document** | 미구현 — 3단계(스토리 구성). ui_state.proposalsKeyFragments가 전신 | 🕐 후속 |
| **Edit Intent** | 채팅 종업원 v2 (intent router) — understand 우선 | ✅ 존재 (별도 트랙) |
| **Edit Plan** | 부분: proposal_reason / PBE Receipt 반환 — 자연어 제시층 미완 | 🕐 후속 |
| **Edit State** | **`fragment_edit_state` (B0 신규 테이블, 유일 권위)** — trim·excluded_ranges·removed·revision | ✅ B0-IMPL-1/2a 구현·검증 |
| **Render Span** | **`compile_spans()` 출력 (Py/TS 동등) — 저장 안 함, Preview/Export만 소비** | ✅ B0-IMPL-1 구현 (소비 배선 = IMPL-2b) |
| **Receipt** | normalize() receipt + `vault_events(event_kind='edit_command')` detail(before/after ms·origin) | ✅ B0-IMPL-2a 구현·검증 |

## 실행 원칙 대응 (§14)

| 원칙 | 현재 상태 |
|---|---|
| Job Conductor 단일 지휘 | ⚠ 미구현 — `_fragment_job_registry`(main.py)가 부분 전신. 1단계 잔여 과제 |
| worktree writer lock | ⚠ 규율로만 존재(R-a/R-b) — 코드 잠금 미구현. UNATTRIBUTED-WRITER-01 사건이 필요성 실증 |
| GPU 작업 직렬 큐 | ⚠ ASR/VL 부분적 — 통합 큐 미구현 |
| 재분석 최소화 캐시 | ⚠ 부분(subtitles 캐시 존재) — (hash, version) 키 체계 미통일 |

## PBE 재정의 (§11) 반영

PBE = 예외 정밀 감독창. B트랙 IMPL-2b의 5곳 교체는 "PBE 중심화"가 아니라
**PBE의 예외 수정이 Edit State 한 곳에 안전하게 저장·복원되게 만드는 배관 공사**다.
사용자 주 동선은 원고(①)·이야기(②)·결과(③) — A트랙 Ledger R0가 ①의 첫 구현.
