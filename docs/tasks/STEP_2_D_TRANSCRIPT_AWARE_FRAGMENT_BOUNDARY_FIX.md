# CCUT STEP 2-D — Transcript-Aware Semantic Fragment Boundary Fix 작업지시서

## 목적

현재 CCUT은 ASR 오염 차단과 A/B diversity 정책까지 일부 해결했다.
그러나 브라우저 검증에서 다음 문제가 확인되었다.

- A/B가 각 1개 조각만 선택되는 경우가 있음
- 조각의 끝점과 대화 문장이 끝나는 지점이 맞지 않음
- 조각이 문장 중간에서 끊길 가능성이 있음

이번 작업의 목표는 “진짜 편집 조각”을 만들기 위한 경계 보정이다.

## 핵심 원칙

조각은 단순 시간 구간이 아니다.

조각은 다음 기준을 만족해야 한다.

1. 문장이 끝나는 지점에서 끝난다.
2. 의미 단락이 완결된다.
3. 너무 짧거나 너무 길지 않다.
4. audio energy / silence / scene cut과 충돌하지 않는다.
5. ProposalEngine이 바로 편집 재료로 쓸 수 있다.

## 수정 금지

- Frontend 수정 금지
- CenterPanel.tsx 수정 금지
- Preview Render 수정 금지
- ASR Guard 수정 금지
- ProposalEngine 추가 수정 금지
- Factory Matrix 구현 금지
- random 사용 금지
- mock 데이터 사용 금지

## 1단계: 감사 먼저 수행

수정 전에 반드시 감사 보고서를 먼저 만든다.

산출물:

`docs/reports/STEP_2_D_TRANSCRIPT_FRAGMENT_BOUNDARY_AUDIT.md`

감사 대상:

- `semantic_fragments`
- `evidence_board.text`
- `fragments.intelligence.transcript`
- ASR/Whisper segment 저장 위치
- `ccut_backend/engine/semantic_engine.py`
- `ccut_backend/main.py`

확인 항목:

1. transcript segment가 DB 어디에 저장되는지 확인
2. word timestamp 또는 segment timestamp가 존재하는지 확인
3. semantic_fragments.start/end가 어떤 기준으로 계산되는지 확인
4. semantic fragment end가 문장 끝과 얼마나 차이 나는지 확인
5. fragment end가 문장 중간인지 판정
6. scene/audio/silence 정보가 boundary에 반영되는지 확인

## 필수 SQL

```sql
SELECT id, source_id, start, end, semantic_json, structural_json
FROM semantic_fragments
ORDER BY updated_at DESC
LIMIT 20;
SELECT fragment_id, source_id, start, end, text, worker_sources
FROM evidence_board
WHERE LENGTH(COALESCE(text,'')) > 0
ORDER BY last_updated DESC
LIMIT 20;
SELECT fragment_id, source_id,
       JSON_EXTRACT(intelligence,'$.transcript') AS transcript
FROM fragments
WHERE LENGTH(COALESCE(JSON_EXTRACT(intelligence,'$.transcript'),'')) > 0
ORDER BY rowid DESC
LIMIT 20;
```

## 2단계: Boundary Rule 설계

감사 후 다음 정책을 설계한다.

Rule 1. Sentence End Snap

문장 종료 기호:

.
?
!
요.
다.
죠.
네.
습니다.
자연스러운 침묵 구간

조각 end가 문장 중간이면 가장 가까운 sentence end로 이동한다.

Rule 2. Silence Snap

문장 끝 근처에 silence 구간이 있으면 silence 지점으로 end를 보정한다.

우선순위:

sentence end
silence
scene cut
fixed time fallback

Rule 3. Minimum / Maximum Duration

기본값:

min duration: 3초
preferred duration: 5~20초
max duration: 30초

단, 문장 완결을 위해 약간 초과는 허용.

Rule 4. No Mid-Sentence Cut

대화 문장이 끝나기 نشده 않았는데 조각을 끊지 않는다.

예:

잘못된 조각:
"그래서 내가 그때 밥을 먹으려고"

올바른 조각:
"그래서 내가 그때 밥을 먹으려고 했는데, 갑자기 전화가 왔어."

## 3단계: 코드 수정 후보

감사 후 수정 대상 후보:

ccut_backend/engine/semantic_engine.py

추가 후보 함수:

def snap_fragment_boundary_to_sentence(fragment, transcript_segments, audio_events):
    ...
def detect_sentence_end_candidates(text, segment_start, segment_end):
    ...
def choose_best_boundary(sentence_candidates, silence_candidates, scene_candidates):
    ...

## 검증 기준

### CODE PASS
- compile 성공
- semantic_engine.py 단독 또는 최소 파일 수정
- 기존 ASR Guard / Proposal Preview / Render 깨지지 않음

### RUNTIME PASS 후보
- semantic_fragments.end가 sentence end와 가까워짐
- 문장 중간에서 끝나는 조각 감소
- A/B Proposal이 기존처럼 생성됨
- Preview mp4 생성됨

### PRODUCT HOLD
- 문장 중간 끊김이 남아 있음
- A/B가 여전히 각 1개만 생성됨
- fragment end와 transcript end 차이가 큼
- preview 생성 실패

## 보고 형식

보고서에는 아래 항목을 포함한다.

1. 감사 대상 source_id
2. transcript 저장 위치
3. word/segment timestamp 존재 여부
4. 기존 fragment boundary 문제 사례
5. sentence end와 fragment end 차이
6. 수정 대상 함수
7. 수정 후 boundary 개선 결과
8. proposal sequence_count
9. preview 생성 여부
10. 판정

## 한 줄 목표

문장이 끝나지 않았는데 조각이 끝나는 문제를 제거하고,
CCUT의 semantic fragment를 실제 편집 가능한 조각으로 바꾼다.
