# Video-use Adapter Policy (V1.0)

Video-use 프로젝트의 검증된 로직을 CCUT에 흡수하기 위한 어댑터 방식의 기술 이식 정책입니다.

## 1. 핵심 원칙
- **Direct Copy 금지**: Video-use 코드를 그대로 복사해서 붙여넣지 않습니다.
- **Structural Alignment**: CCUT의 Common Core 및 Matrix 구조에 맞게 재해석하여 구현합니다.
- **License Compliance**: 코드 이식 전 라이선스 및 저작권 범위를 명확히 확인합니다.
- **Separation of Concerns**: 품질 규칙(Logic)은 가져오되, 실행 프레임워크(Framework)는 CCUT의 것을 사용합니다.

## 2. 흡수 대상 (Import List)

### 2.1. 가져올 항목 (Adopt)
- **품질 알고리즘**: Word Timestamp 기반의 컷 경계 보정 로직.
- **사고방식**: EDL(Edit Decision List)을 단순한 리스트가 아닌 데이터 구조로 관리하는 방식.
- **Subtitle Logic**: 편집된 타임라인에 맞춘 자막 시간 재정렬 및 병합 알고리즘.
- **QA Criteria**: 결과물 검수 항목 및 자동 패스/실패 판정 기준.
- **Working Tree**: 작업방(Logical Room) 내에서 부산물(Proxy, Waveform, Cache)을 정리하는 개념.

### 2.2. 가져오지 않을 항목 (Reject)
- **외부 AI 의존 구조**: 특정 LLM이나 API에 강결합된 서비스 로직.
- **사용자 API Key 강제**: 사용자에게 직접 API Key 입력을 요구하는 인터페이스(CCUT Governor가 관리).
- **실행 흐름**: CCUT의 아카이브/의미조각 파이프라인과 충돌하는 Video-use의 순차적 실행 방식.

## 3. 구현 로드맵 (Adapter Strategy)

1. **Rule Adapter**: `VIDEO_USE_QUALITY_RULES_FOR_CCUT.md`의 규칙을 코드로 추상화.
2. **Data Adapter**: Video-use의 결과물(JSON)을 CCUT의 Semantic Fragment 형식으로 변환하는 모듈 개발.
3. **QA Adapter**: 렌더링 후 검수 로직을 CCUT Render Engine에 Plug-in 형태로 삽입.

## 4. 라이선스 및 법적 고지
- 실제 이식 단계 전, Video-use 프로젝트의 소유권 및 라이선스(MIT/Apache 등)를 재확인하고, 필요한 경우 라이선스 고지 문구를 소스 코드 상단에 포함합니다.
- 현재는 **"설계"** 단계이며, 실제 코드 이식은 라이선스 확인 후에만 진행합니다.
