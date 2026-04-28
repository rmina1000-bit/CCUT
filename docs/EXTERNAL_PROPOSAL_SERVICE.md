# External Proposal Service

## 정의
로컬 CCUT이 만든 의미 데이터만 외부 AI에 전달하여 Proposal 방향/구성/QA 의견을 받는 선택적 보조 계층.

## 핵심 원칙
- **영상은 로컬에 남긴다.**
- 의미 데이터만 이동한다.
- Web AI는 조언만 한다.
- 최종 Proposal 채택/수정/폐기는 CCUT과 사용자가 결정한다.

## 이번 단계(CCUT 1.0.4) 구현 범위

### 허용 범위
- interface 초안
- request/response schema 문서화
- adapter 후보 파일명 정리
- fail-safe 정책 문서화

### 금지 범위
- 실제 API 호출 구현
- API key 저장
- 네트워크 호출 코드 추가
- UI 버튼 추가
- Render/ExportInput 연결

## 후보 파일명 (구조 제안)
- `ccut_backend/external_ai/contracts/web_ai_contract.py`
- `ccut_backend/external_ai/adapters/base_adapter.py`
- `ccut_backend/external_ai/services/external_proposal_service.py`
- `ccut_backend/external_ai/schemas/proposal_request.py`
- `ccut_backend/external_ai/schemas/proposal_response.py`

*참고: 이번 작업에서는 실제 파일을 생성하지 않고 문서로만 기록함.*
