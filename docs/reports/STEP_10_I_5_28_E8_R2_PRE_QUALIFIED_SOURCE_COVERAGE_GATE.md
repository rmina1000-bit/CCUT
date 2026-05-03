# STEP 10-I.5.28-E8-R2-PRE Qualified Source Coverage Gate Design

## 1. 기준
- branch: ccut-1.0.4-step9
- HEAD: 78e48668e2e5ae61db38f8d88f55d66e1d690776 (E8-R1 적용 완료 상태)
- 코드 수정 여부: NO
- 작업 성격: 설계 문서화

## 2. 배경
- E8-R1(Lightweight Diversity Pass) 도입으로 적용 영상 범위가 개선되었으나, 여전히 고득점 조각 위주의 편중 현상이 잔존함.
- 모든 입력을 강제 사용하면 편집 품질이 저하될 위험이 있으므로, "자격 있는 소스"를 선별하는 논리적 관문(Gate)이 필요함.
- 사용자가 업로드한 영상은 일단 편집 의도가 있다고 간주하되, AI의 자동 제외 시에는 명확한 근거를 제시하고 사용자의 최종 결정(Override) 경로를 보장함.

## 3. 핵심 원칙
- **자율 선별**: 모든 영상을 무조건 쓰지 않고, 최소 품질/의미 조건을 충족하는 경우에만 A/B 제안에 반영 시도.
- **최종 결정권**: AI가 제외한 영상이라도 사용자가 원본맵(Source Map)에서 직접 조각을 조각맵에 삽입할 수 있는 Override 경로를 SSOT로 인정.
- **투명한 설명**: 자동 제안에서 제외된 영상에 대해서는 그 이유(예: 의미 조각 부족, 품질 저하 등)를 사용자에게 설명함.
- **성능 보존**: 무거운 프레임 재분석 대신 기존 Semantic Fragment 데이터를 활용한 O(n) 연산 우선.

## 4. Source Eligibility Status

다음 상태값을 통해 영상의 제안 적합성을 관리한다.

| 상태 | 정의 | 제안 반영 정책 |
| :--- | :--- | :--- |
| **USABLE** | 제안에 사용하기 적합함 | A/B 중 최소 하나에 반영 시도 |
| **WEAK** | 품질/의미는 약하지만 후보 존재 | B안(사용자친화형)에 우선 반영 시도 |
| **RISKY** | 사용 가능하나 품질 위험 있음 | 반영 시 경고 문구 포함 |
| **JUNK_SUSPECT** | 자동 제안 제외 권장 | 제외 사유 설명, 사용자 직접 삽입 권장 |
| **EXCLUDED** | 기술적 문제 또는 사용 불가 | 자동 제안 제외, 직접 삽입 시에도 경고 |

## 5. 최소 사용 가능성 데이터 후보 (Criteria)

### 기존 데이터 (Fast Path)
- `analyzed_fragment_count`: 분석된 의미 조각 수 (최소 2개 이상 권장)
- `best_fragment_confidence`: 최상위 조각의 신뢰도
- `market_value` / `edit_value`: 시장성 및 편집 가치 점수
- `role` 분포: hook, context, payoff 등 역할 부여 여부
- `duration`: 영상 길이 및 조각 길이 정합성

### 추가 분석 후보 (Deferred)
- Brightness / Blur / Sharpness
- Motion Score / Audio RMS (Energy)
- Silence Ratio / Transcript 존재 여부

## 6. v0 판정 기준 초안

- **USABLE**: 분석 조각 2개 이상 + confidence 0.7 이상 후보 존재 + 유효 역할(role) 1개 이상.
- **WEAK**: 분석 조각 1개 이상 + 역할은 모호하나 duration이 충분함.
- **JUNK_SUSPECT**: 의미 조각 거의 없음(0~1개) + confidence 매우 낮음 + 반복/무음/암흑 의심.
- **EXCLUDED**: 파일 손상, duration 0, 기술적 preview 불가 등.

## 7. User Override Flow

1. **자동 제안**: AI가 기준 미달 영상을 제외하고 사유를 `proposal_explanation`에 표시.
2. **사용자 요청**: 사용자가 "영상 H도 포함해"라고 입력하거나, **원본맵에서 직접 조각을 드래그**하여 삽입.
3. **수용**: 시스템은 AI 판단보다 사용자 결정을 우선시하여 조각을 수용하되, 품질 위험이 있는 경우 작은 UI 배지 등으로 표시.
4. **학습**: 사용자가 반복적으로 Override하는 기준은 향후 Gate 임계값 조정의 근거로 활용.

## 8. 원본맵 직접 조각 삽입과의 관계
- **SSOT**: 원본맵 직접 삽입은 사용자의 가장 강력한 의사 표시임.
- **Gate 역할**: Gate는 "폐기"가 아니라 "자동 선택 보조" 장치임. 자동 제안에서 빠졌더라도 원본맵에 존재하므로 사용자는 언제든 수동으로 수용 가능함.

## 9. 속도 설계 (Complexity)
- **Fast Gate**: 기존 데이터만 사용하므로 **O(n)**. 현재의 1분 미만 분석 속도에 영향 없음.
- **Coverage Pass**: B안 중심의 최소 1개 반영 시도. **O(n)**.
- **Deep Re-analysis**: 사용자가 강력 요청할 때만 수행하도록 설계하여 기본 경로의 속도 보존.

## 10. E8-R2 본구현 범위 제안
- **대상**: `proposal_engine.py` 내부 로직 개선.
- **기능**:
  - Source eligibility v0 판정 로직 추가.
  - B안에서 `USABLE/WEAK` 소스의 최소 1개 조각 반영 시도.
  - 제외된 소스에 대한 설명 문구 생성.
- **금지**: 프레임 재분석, 외부 AI 호출, DB/UI 스키마 변경.

## 11. 판정
**PASS**
- Gate 정책, 데이터 기준, 속도 단계, Override 흐름이 명확히 정의됨.
