# CCUT EDIT LAB / 관리자 AI / API 키 통합 작업 보고서

작성일: 2026-07-29
작업 위치: `D:\CCUT1.0.4`
현재 HEAD: `4bd805a3 add flagged ollama chat role path`
상태: **구현 미커밋 / Anthropic API 개통 HOLD / 결제 없음**

## 1. 결론

EDIT LAB 감사기와 능력지도, 관리자 전용 외부 AI 경로, API 키 통합 화면까지 구현했다.
관리자 AI는 제품 화면의 로컬 Qwen 경로와 분리되어 Anthropic API만 사용하며, 키가 없거나
API를 사용할 수 없을 때 로컬 모델로 조용히 폴백하지 않는다.

실제 Anthropic 키의 저장과 인증은 확인했다. 그러나 계정의 API 크레딧 잔액이 0이어서
실제 관리자 질의는 `API 크레딧 잔액 부족`으로 실패한다. Anthropic 결제 화면에서는
필수 주소와 카드가 입력되고 한때 세금과 총액까지 표시됐음에도 최종 구매 버튼이
활성화되지 않았다는 국장 실증이 있다. 현재 화면에서는 세금과 총액이 다시 `$--`로
표시된다. 최종 비활성 원인은 **UNKNOWN**이다.

따라서 이번 작업은 다음 상태로 닫는다.

```text
EDIT LAB 감사/지도       구현됨, 미커밋
관리자 Anthropic 경로    구현됨, 미커밋
API 키 저장/보안         구현됨, 실제 키 저장됨
Anthropic 인증           확인됨
Anthropic 실제 질의      HOLD: API 크레딧 잔액 부족
Anthropic 결제           HOLD: 최종 구매 버튼 비활성 원인 UNKNOWN
로컬 AI 대체             금지/미실행
commit / push            없음
```

## 2. 작업 범위와 결정

### 2.1 유지한 경계

- 관제실 11개 탭의 관리자 AI만 Anthropic API를 사용한다.
- CCUT 제품 화면의 로컬 Qwen 경로는 수정하지 않았다.
- EDIT LAB 진입만으로 LLM을 호출하지 않는다.
- EDIT LAB AI 질의는 `admin_ai_runs`, `admin_audit_log`에 기록하지 않는다.
- 기존 10개 관리자 탭은 기존 기록 정책을 유지한다.
- 원본 영상, 프레임, 얼굴, 전사 전문, 로컬 절대경로, 사용자 원문은 Anthropic에 보내지 않는다.
- `.env`의 키 원문을 화면, API 응답, 콘솔, 보고서에 반환하지 않는다.
- 실패 시 로컬 Qwen 폴백을 하지 않는다.

### 2.2 공급자 판정

코드에서 실제로 도달 가능한 외부 API 키 사용처를 조사한 결과 관리자 API 키 페이지에
등록할 공급자는 Anthropic 하나였다.

- 실제 사용: `ANTHROPIC_API_KEY`
- 제외: `EXTERNAL_AI_API_KEY`
  - 어댑터 파일은 존재하지만 호출/등록 경로가 확인되지 않아 미사용 공급자로 판정했다.
- 제외: YouTube OAuth
  - API 키가 아니라 OAuth client/token 파일 경로다.
- 제외: OpenAI/GPT
  - 현재 관리자 AI의 실제 호출 경로가 없다.

공급자 메타데이터는
`ccut_backend/config/admin_api_providers.json` 한 곳에 둔다.

등록 URL:

- 키 발급: `https://platform.claude.com/settings/keys`
- 문서: `https://platform.claude.com/docs/en/api/overview`

## 3. LAB-0: EDIT LAB 기반 구현

### 3.1 백엔드 감사기

신규 감사기:

- `ccut_backend/lab/audit.py`
- `ccut_backend/config/lab_audit.json`

엔드포인트:

- `GET /lab/audit`
- `POST /lab/audit/run`

감사기는 mock이나 설계 예시 숫자를 사용하지 않고 운영 DB와 현재 config/registry를 읽는다.

확인된 실데이터:

```text
운영 DB 조각             670
word_timestamps          77
재료                     7종
하드룰 선언              12
검사기 registry          6
선언/registry 교집합     0
편집기법 선언            31
실제 배선                2 (as_is, punch_in)

motion                   534/670, distinct 533
audio_beat               15/256, distinct 15
audio_energy             256/256, distinct 136
word_timestamps          77/77, distinct 77
face_size                0/670
shot_size                0/670
emotion_score            0/670
```

설계 예시와 실제값이 달랐던 항목:

- 기법 선언: 예상 30이 아니라 실제 31
- motion: 예상 670/670이 아니라 실제 534/670
- word_timestamps: 특정 13조각이 아니라 운영 DB 전체 기준 77/77

숫자를 설계 예시에 맞춰 보정하지 않았다.

### 3.2 관리자 탭

경로:

- `/admin/edit-lab`

관리자 왼쪽 탐색에 11번째 `편집연구실` 탭을 추가했다.

주요 프론트 파일:

- `ccut_frontend/src/components/admin/AdminEditLabPanel.tsx`
- `ccut_frontend/src/components/admin/AdminLeftNav.tsx`
- `ccut_frontend/src/components/admin/AdminShell.tsx`
- `ccut_frontend/src/pages/AdminIndex.tsx`

기존 관리자 탭 10개의 동작은 유지했다.

## 4. LAB-1: 능력지도

기존 표를 삭제하지 않고 감사 결과를 5열 능력지도로 확장했다.

열:

```text
재료 -> 측정/판단 -> 하드룰 -> 편집기법 -> 결과검증
```

간선은 선언 또는 실제 코드 참조 근거가 있을 때만 생성한다. 이름 유사도나 기능 추정으로
간선을 만들지 않는다.

API 확장:

- `materials[].producers`
- `materials[].consumers`
- `rules[]`
- `techniques[]`
- `edges[]`

간선 상태:

```text
LIVE          7
LOCKED        4
BROKEN        4
UNDECLARED    0
합계          15
```

결과검증 열은 LAB-2 범위이므로 전부 `미측정`으로 표시하며 가짜 GREEN을 만들지 않았다.

## 5. LAB-1.5: 관리자 AI 경로 분리

### 5.1 공급자와 모델

```text
provider      anthropic
model env     CCUT_ADMIN_LLM_MODEL
model string  claude-fable-5
endpoint      https://api.anthropic.com/v1/messages
```

환경변수 이름:

```text
CCUT_ADMIN_LLM_PROVIDER
CCUT_ADMIN_LLM_MODEL
ANTHROPIC_API_KEY
```

`.env.example`에는 이름과 빈 값만 둔다. 실제 키가 있는
`ccut_backend/.env`는 add/commit 금지 대상이다.

### 5.2 EDIT LAB context

EDIT LAB은 화면과 동일한 `/lab/audit` 산출물을 재사용한다. 별도 계산 경로를 만들지 않았다.

전송 대상:

- 재료 ID/라벨/non-null/total/distinct/producers/consumers
- 하드룰 config ID와 registry ID
- 선언/registry 교집합
- 기법 ID/wired/requires_materials/requires_rules
- edges from/to/kind/status/evidence
- 상태 요약과 미배선 기법 수

전송 금지:

- 원본 영상/프레임
- 얼굴 원본
- 전사 전문
- 로컬 절대경로
- 사용자 원문 데이터

답변 규율:

- 감사 데이터에 없는 값은 `감사 데이터에 없음`
- 결론 -> 근거 수치 -> 다음 후보 행동
- 화면 이름만 되받는 공허한 답변 금지

키 미설정 상태 실측:

```text
INPUT {너는 누구인가}
OUTPUT {관리자 AI 미설정}
```

## 6. LAB-1.6: API 키 통합 화면

### 6.1 UI 위치와 현재 흐름

새 최상위 관리자 탭을 만들지 않고 기존 `AI 운영실` 안에 API 키 영역을 편입했다.

프론트:

- `ccut_frontend/src/components/admin/AdminAIOpsPanel.tsx`

초기 구현은 다음 버튼을 분리했다.

```text
발급 페이지 열기 / 연결 테스트 / 저장 / 연결 해제
```

국장 실사용에서 단계가 많고 테스트와 저장의 차이가 불명확하다는 문제가 확인됐다.
이를 다음 흐름으로 단순화했다.

```text
미설정:
  발급 페이지 열기 -> 키 붙여넣기 -> 연결하고 저장

연결 후:
  상태/모델/확인시각 표시 -> 키 변경 또는 연결 해제
```

`연결하고 저장`은 서버에서 다음 순서를 원자적으로 수행한다.

```text
복호화 -> 최소 API 호출로 유효성 확인 -> 성공할 때만 .env 저장 -> os.environ 즉시 반영
```

검증 실패 키는 `.env`에 저장하지 않는다.

### 6.2 API

`ccut_backend/main.py` 관리자 라우터에 추가:

- `GET /admin/api-keys`
- `GET /admin/api-keys/public-key`
- `POST /admin/api-keys/{provider_id}/test`
- `POST /admin/api-keys/{provider_id}/save`
- `POST /admin/api-keys/{provider_id}/connect`
- `DELETE /admin/api-keys/{provider_id}`

기존 test/save는 호환을 위해 남아 있지만 현재 화면의 기본 경로는 `connect` 하나다.

백엔드 구현:

- 상태/마스킹: `ccut_backend/admin/service.py:44`, `:119`
- 공개키: `ccut_backend/admin/service.py:63`
- `.env` 단일 저장 경로: `ccut_backend/admin/service.py:95`
- 결합 검증/저장: `ccut_backend/admin/service.py:249`
- 연결 해제: `ccut_backend/admin/service.py:288`

### 6.3 키 전송 보안

브라우저는 서버의 일회성 프로세스 공개키를 받아 WebCrypto RSA-OAEP/SHA-256으로 키를
암호화한다.

프론트 위치:

- 암호화: `AdminAIOpsPanel.tsx:52`
- 결합 호출: `AdminAIOpsPanel.tsx:115`

전송 본문은 다음 필드 하나만 갖는다.

```json
{"ciphertext":"..."}
```

실측:

```text
BODY_KEYS=['ciphertext']
PLAINTEXT_PRESENT=False
```

서버 응답은 키 원문을 반환하지 않으며 상태 응답은 마스킹만 제공한다.
보고서에는 마스킹 값도 기록하지 않았다.

### 6.4 즉시 반영

저장 함수는 기존 `ccut_backend/.env`의 해당 이름만 교체하고 `os.environ`도 갱신한다.
키 저장 뒤 백엔드 재기동 없이 관리자 AI가 새 값을 읽는 구조다.

## 7. 실제 Anthropic 실증

### 7.1 확인된 것

- 실제 키가 생성됐다.
- 키가 CCUT 관리자 화면에 저장됐다.
- 키 원문은 보고서, API 응답, 콘솔에 출력하지 않았다.
- 잘못된 키는 `401 인증 실패`로 표시됐다.
- 실제 키로 최소 인증 호출이 통과해 키 자체의 유효성은 확인됐다.
- 관리자 화면 진입 전후 `admin_ai_runs`, `admin_audit_log`가 증가하지 않았다.

### 7.2 실제 질의 결과

```text
INPUT {너는 누구인가}
OUTPUT {API 크레딧 잔액 부족}
```

Anthropic 원응답 의미:

```text
API credit balance is too low.
```

관리자 UI는 현재 다음을 동시에 표시한다.

```text
오류
키는 저장됐지만 관리자 AI를 사용할 수 없습니다.
API 크레딧 잔액 부족
```

하단 관리자 AI 카드도 더 이상 `ready`라고 모순되게 표시하지 않고 같은 오류를 표시한다.

## 8. 결제 장애

### 8.1 관측 사실

- Anthropic Billing 페이지 접근 가능
- 조직 역할은 Admin
- 크레딧 잔액 `US$0.00`
- 최소 구매금액 `US$5`
- 결제 카드 선택됨
- 청구지 필수 항목 입력됨
- 사업자등록번호는 사업자인 경우에만 입력하는 선택 항목
- 국장 실증상 한때 세금과 총 결제금액이 표시됨
- 그 상태에서도 최종 구매 버튼 비활성
- 현재 재진입 상태에서는 세금/총액이 `$--`로 돌아가며 버튼 비활성

### 8.2 판정

주소 미입력 또는 세금 미계산 하나를 원인으로 확정할 수 없다.
국장 실증이 해당 가설을 반증했다.

최종 판정:

```text
Anthropic 결제 버튼 비활성 원인 = UNKNOWN
```

가능성 추정은 보고서 결론으로 사용하지 않는다. 동일 입력 반복, 카드 재등록, 추가 결제 시도는
이번 차수에서 중단했다.

### 8.3 관리자 페이지 내장 가능성

Anthropic 결제/키 페이지 응답 헤더 실측:

```text
X-Frame-Options: SAMEORIGIN
Content-Security-Policy: frame-ancestors 'self'
```

따라서 CCUT 관리자 페이지의 iframe 안에 Anthropic 로그인/결제/키 화면을 삽입할 수 없다.
가능한 UX는 외부 탭을 열고 CCUT로 돌아왔을 때 상태를 재확인하는 수준이다.

국장 결정:

```text
관리자 페이지는 로컬 AI로 대체하지 않는다.
외부 API 경로를 유지한다.
이번 차수는 결제 장애 상태에서 마무리한다.
```

## 9. 검증 결과

### 9.1 정적/빌드

```text
Python py_compile       PASS
git diff --check        PASS
npm run build           PASS
TypeScript 신규 오류    0
```

기존 TypeScript 오류 7건은 유지되며 이번 변경에서 새로 만들지 않았다.

기존 오류 파일:

- `src/pages/Index.tsx`
- `src/services/proposalService.ts`
- `src/utils/proposalFragmentResolver.ts`

### 9.2 런타임

보고서 작성 시점:

```text
backend port    8011
backend PID     20032
frontend port   5173
admin route     /admin/ai
EDIT LAB route  /admin/edit-lab
```

### 9.3 UI

확인된 UI:

- 관리자 탭 11개
- EDIT LAB 능력지도 렌더
- API 키 Anthropic 한 행
- 발급 페이지 새 탭 열기
- 미설정 시 `연결하고 저장` 단일 행동
- 연결 후 키 입력칸 숨김
- `키 변경`, `연결 해제`
- 키 원문 미표시
- 크레딧 부족 오류 배지와 관리자 AI 카드 상태 일치

## 10. 변경 파일과 소유권 주의

### 10.1 이번 LAB 계열 핵심 파일

```text
ccut_backend/lab/audit.py
ccut_backend/config/lab_audit.json
ccut_backend/config/admin_api_providers.json
ccut_backend/admin/service.py
ccut_backend/main.py
ccut_backend/.env.example
ccut_frontend/src/components/admin/AdminEditLabPanel.tsx
ccut_frontend/src/components/admin/AdminAIOpsPanel.tsx
ccut_frontend/src/components/admin/AdminAIPanel.tsx
ccut_frontend/src/components/admin/AdminLeftNav.tsx
ccut_frontend/src/components/admin/AdminShell.tsx
ccut_frontend/src/pages/AdminIndex.tsx
```

### 10.2 절대 add 금지

```text
ccut_backend/.env
키 포함 파일
DB / WAL / SHM / backup
scratch/*
*.timestamp
*.bak_*
```

### 10.3 기존 dirty와 혼동 금지

현재 `git diff --stat` 전체에는 LAB 외 사용자 작업이 섞여 있다. 다음 파일은 이번 API 키 작업
범위로 간주하거나 자동 staging하면 안 된다.

```text
ccut_frontend/src/components/CenterPanel.tsx
ccut_frontend/src/components/FragmentMiniPlayer.tsx
ccut_frontend/src/components/LeftNav.tsx
ccut_frontend/src/components/SettingsPanel.tsx
ccut_frontend/src/components/SnsUploadPanel.tsx
ccut_frontend/src/components/TrashPanel.tsx
ccut_frontend/src/components/admin/AdminRevenuePanel.tsx
```

`git add .`, `git add -A`는 금지한다. 커밋 승인 시 파일별 diff를 다시 확인하고 경로 지정
add만 사용해야 한다.

## 11. 미완료와 재개 조건

### 11.1 현재 미완료

- Anthropic 크레딧 구매
- 실제 관리자 AI 정상 응답
- LAB-1.5의 3개 감사 질의 실증
- 없는 데이터 함정 질의 실증
- 기존 관리자 탭 외부 AI 정상 응답 회귀
- 국장 최종 화면 PASS
- commit
- push

### 11.2 재개 조건

아래 중 하나가 확보된 뒤에만 재개한다.

1. 현재 Anthropic 조직에 API 크레딧이 실제 반영됨
2. Anthropic 지원을 통해 구매 버튼 비활성 문제가 해소됨
3. 국장이 다른 외부 API 공급자 통합을 별도 승인함

재개 후 첫 검증:

```text
GET /admin/api-keys
INPUT {너는 누구인가}
EDIT LAB 3문항
없는 데이터 함정 1문항
진입 전후 runs/audit
기존 탭 1건 runs 증가
키/주소/결제정보 누출 검사
build / tsc / diff check
```

## 12. 롤백

현재 변경은 미커밋이다. 롤백이 필요하면 LAB 관련 파일만 선별해야 하며 기존 dirty 파일을
건드리면 안 된다.

주의:

- `git reset --hard` 금지
- `git checkout -- .` 금지
- 전체 worktree 일괄 복구 금지
- 실제 키 제거가 필요하면 먼저 관리자 화면의 `연결 해제` 또는 승인된 서버 경로를 사용
- `.env`를 커밋/보고서/로그로 노출하지 말 것

## 13. 최종 상태

```text
LAB 감사 기능             구현 완료
LAB 능력지도              구현 완료
관리자 Anthropic 분리     구현 완료
API 키 통합/보안          구현 완료
사용 흐름 단순화          구현 완료
실제 외부 AI              HOLD
HOLD 원인                 Anthropic API 크레딧 0
결제 버튼 비활성 원인     UNKNOWN
국장 결제                 미실행
commit                    없음
push                      없음
```
