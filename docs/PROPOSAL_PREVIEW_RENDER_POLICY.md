# PROPOSAL_PREVIEW_RENDER_POLICY.md

> 작성일: 2026-05-10  
> 상태: CONFIRMED — PRODUCT PASS

---

## 1. 문제 배경

CCUT 1.0.4 A/B 제안 preview 재생 시 조각이 누적 재생되는 증상이 지속됐다.

기존 구조:
```
proposal key_fragments
→ fragment.video_url = 원본 uploads/*.mp4
→ video.currentTime = startSec
→ onTimeUpdate에서 endSec 감지
→ 다음 조각으로 이동
```

---

## 2. 실패한 currentTime Seek 방식

### 증상
- 조각이 원본 앞부분(0초)부터 누적 재생됨
- 중간 멈춤 발생
- A/B player 동시 재생으로 에코 발생
- A 소리 + B 화면 media state 꼬임
- progress bar와 실제 조각 흐름 불일치

### 실패한 접근 목록
- currentTime seek 보정 → FAIL
- seeked listener 추가 → FAIL
- loadedMetadata pending seek → FAIL
- !v.seeking guard → FAIL
- A/B dual play guard → FAIL
- fragment preview clip 반쪽 적용 → FAIL

### 근본 원인
브라우저 `<video>`는 편집 타임라인 플레이어가 아니다.  
moov atom이 파일 끝에 있으면 seek 후 currentTime=0으로 복귀.  
source 변경, loadedMetadata, seeked, onTimeUpdate, A/B dual player,
progress bar가 모두 비동기적으로 꼬이는 구조적 문제였다.

---

## 3. 최종 해결 — Proposal Preview Render 구조

```
Proposal A/B sequence (key_fragments)
→ backend: proposal_preview_engine.ensure_proposal_preview()
→ 각 clip: ffmpeg -ss {start} -to {end} -vf scale=-2:720,fps=30 -c:v libx264 -preset veryfast
→ concat demuxer로 A/B 각 하나의 preview mp4 생성
→ -movflags +faststart
→ storage/proposal_previews/PREV_{proposal_id}_{variant}.mp4
→ API 응답 preview_url 주입
→ Frontend: video.src = preview_url, currentTime = 0, play()
→ seek 없음
```

---

## 4. 핵심 변경 파일

| 파일 | 변경 내용 |
|---|---|
| `ccut_backend/engine/proposal_preview_engine.py` | 신규 — clips → re-encode → concat → faststart mp4 생성 |
| `ccut_backend/main.py` | `inject_proposal_previews()` 추가, `/proposals/project`, `/proposals/{source_id}` 응답에 주입 |
| `ccut_frontend/src/proposal/proposalTypes.ts` | `Proposal` 타입에 `preview_url?`, `preview_duration?` 추가 |
| `ccut_frontend/src/pages/Index.tsx` | proposal 매핑 시 `preview_url`, `preview_duration` 보존 |
| `ccut_frontend/src/components/CenterPanel.tsx` | `previewUrlA/B` 계산, onClick에서 preview_url → `src=preview_url, currentTime=0, play()` |

---

## 5. 검증 증거

```
1. npm run build PASS (1700 modules, built in 2.80s)
2. py_compile PASS (proposal_preview_engine.py, main.py)
3. storage/proposal_previews/PREV_PROP_A_*.mp4 생성 확인
4. storage/proposal_previews/PREV_PROP_B_*.mp4 생성 확인
5. Console [PROPOSAL_PREVIEW_PLAY] A/B 로그 확인
6. preview_url = /static/proposal_previews/PREV_PROP_*.mp4 API 응답 확인
7. 사용자 체감: 조각 누적 재생 해결됨
```

---

## 6. PASS 기준

| 단계 | 기준 | 상태 |
|---|---|---|
| CODE PASS | npm build 성공, py_compile 성공 | ✅ |
| RUNTIME PASS | PREV_*.mp4 실제 생성, API preview_url 응답 | ✅ |
| BROWSER PASS | Network: /static/proposal_previews/PREV_*.mp4 요청, Console: [PROPOSAL_PREVIEW_PLAY] | ✅ |
| PRODUCT PASS | 조각 누적 없음, 에코 없음, 중간 멈춤 없음 | ✅ |

---

## 7. 금지사항

```
- video.currentTime = startSec 방식으로 proposal preview 재생 금지
- proposal preview 재생 시 video_url(원본) fallback 금지
- onTimeUpdate/endSec 감지 기반 조각 전환 금지 (preview mode에서)
- preview_url 없을 때 playFrag/startSeq 호출을 default로 사용 금지
- 시뮬레이션 PASS를 RUNTIME PASS로 표현 금지
- 자동 커밋 금지
```

---

## 8. 향후 확장 원칙

### Artifact-First 원칙
```
코드가 있는가?          → 부족
실제로 호출되는가?      → 필요
산출물이 생기는가?      → 필요
API로 전달되는가?       → 필요
프론트가 실제로 쓰는가? → 필요
브라우저에서 확인되는가? → 필요
사용자가 체감하는가?    → 최종 PASS
```

### PASS 등급 구분
```
DESIGN PASS    — 설계 문서 완료
SIMULATION PASS — 시뮬레이션 결과
CODE PASS      — compile/build 성공
RUNTIME PASS   — 실제 artifact 생성
BROWSER PASS   — Network/Console 증거
PRODUCT PASS   — 사용자 체감 확인
```

### 신규 preview artifact 추가 시
1. `ensure_proposal_preview()` 재사용 (idempotent — 존재 시 캐시)
2. 파일은 `storage/proposal_previews/` 에 저장
3. API 응답에 `preview_url` 필드 필수
4. Frontend는 `preview_url` 없으면 재생 버튼 비활성화 (fallback 금지)

### faststart 필수
모든 mp4는 `-movflags +faststart` 적용.  
도구: `tools/apply_faststart.ps1`

---

## 9. 관련 파일

```
storage/proposal_previews/          — 생성된 A/B preview mp4
tools/apply_faststart.ps1           — uploads 일괄 faststart 적용
ccut_backend/engine/render_engine.py — 기존 Export Render (proposal_preview와 별도)
docs/RENDER_ENGINE.md               — Export 렌더 정책
docs/RENDER_QA_RULES.md             — Render QA 규칙
```
