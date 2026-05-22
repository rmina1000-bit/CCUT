# STEP 2-C Session Handoff — True Fragment Entry

## 상태

이번 세션은 CCUT1.0.4가 단순 분석/제안 단계를 넘어, 실제 편집 조각 품질 문제로 진입한 세션이다.

## 완료된 작업

### 1. ASR Text Quality Guard

Qwen3-ASR 및 ASR 결과에서 다음 오염을 차단했다.

- CJK/중국어 오인식
- 반복 환각
- 길이 초과 환각
- empty text

Runtime 재검증 결과 Evidence Board에 오염 텍스트가 들어가지 않는 것을 확인했다.

판정:

- CODE PASS
- RUNTIME PASS
- PRODUCT PASS 아님

### 2. Proposal max_frags 상한 수정

단일 source에서 `max_frags = source_count * 2`로 인해 최대 2개 조각만 선택되던 문제를 수정했다.

판정:

- CODE PASS
- 부분 RUNTIME PASS

### 3. A/B Split Logic 감사

A/B가 같은 semantic group을 홀수/짝수 조각처럼 나눠 갖는 구조를 확인했다.

예:

- A: P001, P003, P005
- B: P002, P004

이것은 코드 정책상 의도된 동작이나, 제품 관점에서는 A/B가 충분히 다른 제안이 아니므로 다음처럼 판정했다.

- CODE-AS-DESIGNED
- PRODUCT HOLD

### 4. Proposal Diversity Policy Fix

B안에 A와 다른 semantic group을 포함시키기 위한 diversity fallback을 구현했다.

긴 테스트 source에서는 다음 결과를 확인했다.

- A count = 3
- B count = 3
- B exclusive group 존재

그러나 새 브라우저 테스트에서는 다음 문제가 남았다.

- A/B가 각 1개 조각만 선택됨
- 문장 끝점과 조각 끝점이 맞지 않음

## 남은 핵심 문제

현재 문제는 ProposalEngine의 단순 조각 수 문제가 아니다.

핵심 문제는 다음이다.

1. Transcript 문장 경계와 semantic fragment 경계가 맞지 않는다.
2. 조각이 대화 중간에서 끝날 수 있다.
3. 문장 단위, 의미 단위, 편집 단위가 아직 통합되지 않았다.
4. 현재 조각은 “진짜 편집 조각”이 아니라 “분석 구간”에 가깝다.

## 다음 단계

다음 단계는 아래 작업으로 진행한다.

`STEP 2-D Transcript-Aware Semantic Fragment Boundary Fix`

목표:

- 문장 끝점을 기준으로 semantic fragment end를 보정한다.
- 대화 문장이 끝나기 전에 조각이 잘리지 않도록 한다.
- Whisper segment / transcript segment / audio energy / scene cut을 함께 고려한다.
- ProposalEngine은 보정된 semantic fragment를 사용해야 한다.

## 다음 방 시작 시 필수 확인

```powershell
cd D:\CCUT1.0.4
git status --short
git rev-parse HEAD
git diff --stat

확인 대상:

proposal_engine.py 미커밋 수정 여부
tools/audit_r4_result.py 존재 여부
docs/reports/STEP_2_C_R4_PROPOSAL_DIVERSITY_POLICY_FIX.md 상태
최신 source의 proposals.sequence_count
최신 source의 semantic_fragments start/end
transcript text와 fragment boundary 차이
판정

이번 세션의 최종 판정:

ASR Guard: RUNTIME PASS
Proposal selection cap: CODE PASS / 부분 RUNTIME PASS
A/B split audit: REPORT PASS
A/B diversity fix: 긴 source 기준 RUNTIME PASS 후보, 짧은 source 기준 HOLD
True fragment boundary: 다음 단계 핵심 과제
한 줄 결론

CCUT은 이제 “조각을 얼마나 고르느냐”가 아니라,
“문장과 의미가 끝나는 지점에서 조각을 끊는가”를 해결해야 한다.
