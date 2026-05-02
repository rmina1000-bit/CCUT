# CODEX REQUEST: STEP 10-I.5.21 Pipeline Audit

## 1. 목적
현재 안정화된 CCUT 1.0.4 분석 및 제안 생성 파이프라인의 **코드 구조, 성능 병목, 데이터 정합성**을 전수 감사하여 향후 최적화 방향을 설정함.

## 2. 주요 감사 대상 파일
### Backend
- `ccut_backend/main.py` (API 오케스트레이션)
- `ccut_backend/engine/semantic_engine.py` (의미 분석 로직)
- `ccut_backend/engine/proposal_engine.py` (제안 생성 로직)
- `ccut_backend/engine/signal_processor.py` (시그널 가공)
- `ccut_backend/archive/manager.py` (데이터 영속성)

### Frontend
- `ccut_frontend/src/pages/Index.tsx` (메인 상태 관리)
- `ccut_frontend/src/utils/proposalFragmentResolver.ts` (조각 매핑 알고리즘)
- `ccut_frontend/src/components/FragmentMap.tsx` (타임라인 렌더링)
- `ccut_frontend/src/components/FragmentTile.tsx` (개별 조각 표시)

## 3. Codex 감사 질문 (Key Questions)
1. **성능 병목**: 현재 분석 파이프라인에서 가장 큰 시간을 잡아먹는 구간은 어디이며, 비동기 처리가 최적으로 이루어지고 있는가?
2. **분할 타당성**: 133개의 Semantic Fragment 분할은 실제 의미 단위로서 적절한가, 아니면 단순한 시간 기반 split의 결과인가?
3. **ID 체계**: Recursive ID suffix (`_S_S_S`) 구조가 시스템 안정성이나 DB 조회 성능에 악영향을 줄 가능성이 있는가?
4. **썸네일 누락**: `main.py` 및 `manager.py`의 썸네일 업데이트 로직 중 어디서 유실이 발생하는가?
5. **상태 단순화**: 프론트엔드의 `raw`, `semantic`, `proposal`, `resolved` 데이터 흐름을 더 단일화된 SSOT(Single Source of Truth)로 개편할 수 있는가?
6. **로깅 정책**: 터미널과 콘솔의 디버그 로그를 정리하기 위한 표준 로깅 수준 제안.
7. **우선순위**: 위 문제들을 해결하기 위한 향후 5개 작업의 우선순위 제안.

## 4. 제약 사항
- 이번 단계에서는 **코드를 수정하지 않음**.
- 오직 코드 분석과 현재 상태 진단만을 수행함.
- 대용량 데이터나 외부 API 호출 없이 로직 위주로 감사함.
