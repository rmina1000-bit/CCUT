# CCUT1.0.4 다음 방 전달문 (PBE 수리 & Narrative Bridge 연동 완료)

작성일: 2026-05-28  
이전 세션 작업자: Antigravity

---

## 1. 시작 및 검수 명령

다음 방 시작 시, 아래 명령어로 현재 저장소 상태가 깨끗하게 반영되어 있는지 점검하십시오.

```powershell
cd D:\CCUT1.0.4

# git 상태 점검
git status --short
git diff --stat
git log --oneline -5
git rev-parse HEAD

# 백엔드 서버 수동 테스트 및 4대 로그 확인
python scratch/verify_director_bridge.py
```

---

## 2. 이번 방에서 해결 및 완료된 사항

이번 세션에서는 사용자의 편집 사용성 극대화를 위한 **PBE(조각맵 편집기) 오차 수정 및 상태 영속화** 작업과, 감독/엔지니어 계층을 완벽히 분리하는 **STEP 10-L: External Narrative Director Bridge** 연동을 완료했습니다.

### 2.1 PBE 및 편집기 오차 수리 완료
1. **프레임 단위 Accurate Seek 적용 (썸네일 싱크 교정)**
   - **현상**: PBE 조각맵의 Panorama 썸네일 이미지 프레임과 비디오 재생 위치가 1~3초 가량 미세하게 일치하지 않음.
   - **수리**: [video_engine.py](file:///d:/CCUT1.0.4/ccut_backend/engine/video_engine.py) 내 `extract_panorama_frames` 및 `extract_thumbnail`의 FFmpeg 명령어 매개변수 중 `-ss`(Seek) 옵션을 입력 파일 `-i` 파라미터 **이후**로 이동시켜 빠른 키프레임 탐색(Fast Seek) 대신 정확한 프레임 탐색(Accurate Seek)이 이루어지도록 교정.
2. **A/B안 클릭 토글 및 수정한 조각맵 플레이어 미반영 문제 교정**
   - **현상**: B안(User)을 선택하여 조각맵의 길이를 늘리고 재생(Play)하면 기존 제안 조각들만 나오고 수정 사항이 무시됨. 탭을 클릭하여 A/B안을 왕복하면 수정한 내용이 초기화되는 문제 발생.
   - **수리**: [proposalFragmentResolver.ts](file:///d:/CCUT1.0.4/ccut_frontend/src/utils/proposalFragmentResolver.ts)의 `resolveProposalFragments`에서 사용자가 임의로 지정한 start_frame/end_frame 영역 수동 편집 데이터가 존재할 경우, 원본 semantic fragment의 정적 바운더리로 덮어쓰지 않고 최우선 유지하도록 변경.
3. **DB 저장 중 sqlite3 UNIQUE 제약조건 충돌 에러 교정**
   - **현상**: 조각맵에서 자르기(Trim)를 수행할 때 DB 레벨에서 `UNIQUE constraint failed: fragments.fragment_id` 에러와 함께 편집 내역 저장이 중단됨.
   - **수리**: [pbeBoundaryOps.ts](file:///d:/CCUT1.0.4/ccut_frontend/src/features/pbe/pbeBoundaryOps.ts)의 `applySingleTrim` 함수에서 조각이 좌/우측으로 나누어질 때 생성되는 신규 fragment_id에 `_L`, `_R` 접미사를 보강하여 항상 고유성이 유지되도록 수정.

### 2.2 STEP 10-L: External Narrative Director Bridge 연동 완료
* **목적**: 외부 초거대 AI(Claude/GPT/Gemini)가 연출/편집 감독의 연출 판단 및 미학 방향만 도출하고, CCUT 엔진은 이를 가중치 번역을 통해 Proposal 생성 스코어링 Heuristic에 dynamic scoring modifier로 실시간 연동하는 안전 계층 구축.

```text
CCUT Analysis (Metadata 추출)
→ Qwen Local Orchestrator (컨텍스트 메타데이터 압축)
→ External Narrative Director (어댑터 / 15초 제한 및 3회 재시도)
→ Narrative Directing Response (연출 판단 가이드)
→ Qwen Translator (Executable Constraints 가중치 변환)
→ CCUT Proposal Engine (edit_score 동적 점수 변환 및 조각 선별)
→ Render & Timeline
```

* **신규 생성 파일 및 역할**:
  - [cinematic_language_registry.json](file:///d:/CCUT1.0.4/ccut_backend/ai/narrative/cinematic_language_registry.json): 영화/다큐 편집 문법 매칭 템플릿.
  - [narrative_director_contract.py](file:///d:/CCUT1.0.4/ccut_backend/ai/narrative/narrative_director_contract.py): `NarrativeDirection` 계약 스키마.
  - [external_narrative_adapter.py](file:///d:/CCUT1.0.4/ccut_backend/ai/narrative/external_narrative_adapter.py): 메타데이터 전달 엄격 제한, API 15초 타임아웃, 3회 재시도 로직 내포.
  - [qwen_narrative_translator.py](file:///d:/CCUT1.0.4/ccut_backend/ai/narrative/qwen_narrative_translator.py): 연출 지침을 CCUT 가중치(`reduce_scenery_ratio`, `prefer_reaction_fragments` 등)로 변환.
* **수정 및 연동**:
  - [proposal_engine.py](file:///d:/CCUT1.0.4/ccut_backend/engine/proposal_engine.py): `_create_user_proposal` 내부에서 어댑터와 번역기를 연동하고 `edit_score` 내에서 리액션 가중치(1.35x), 풍경 컷 감점, 가변 듀레이션 페이싱에 가중치 자동 연산.
* **필수 런타임 로그**:
  - 백엔드 런타임 상에서 Proposals 생성 시 아래 4대 로그가 완벽하게 출력되도록 로깅 체계를 완성하고 100% 통과 확인.
    - `[NARRATIVE_DIRECTOR_REQUEST]`
    - `[NARRATIVE_DIRECTOR_RESPONSE]`
    - `[NARRATIVE_TRANSLATION]`
    - `[PROPOSAL_CINEMATIC_SCORE]`

---

## 3. 다음 방에서 유지할 절대 규칙
- **기존 렌더 파이프라인 및 ExportInput 스키마**: 절대 변경 금지.
- **External LLM 역할 고정**: 절대 외부 AI가 ffmpeg 명령어나 직접 컷 타임라인을 생성하게 해서는 안 되며, 오직 연출 정책만을 지시하고 실행 엔진은 CCUT로 고정해야 함.
- **TypeScript 타입 체크 완벽성 유지**: 프론트엔드 작업 완료 후 반드시 `npx tsc --noEmit`을 돌려 컴파일 패스 여부를 확인할 것.
