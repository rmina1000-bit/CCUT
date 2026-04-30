# Free Form UI Component Map (V1.0)

UI 개발 시 필요한 핵심 컴포넌트 목록과 각각의 역할 정의입니다.

## 1. 좌측 영역 (Sidebar Components)
- **ProjectSidebar**: 사이드바 전체 컨테이너.
- **NewProjectButton**: 새 프로젝트 시작 버튼. (High Emphasis, Mono)
- **ProjectList**: 최근 작업한 프로젝트 목록.
- **NavigationMenu**: 아카이브, 보고서 등 시스템 메뉴.

## 2. 중앙 영역 (Form Components)
- **FreeEditFormPanel**: 무료 편집 폼 전체 감싸기.
- **FormOptionGroup**: 개별 질문 항목 (예: 영상 목적, 길이).
- **FormOptionChip**: 개별 선택지 버튼 (Pill Button).
- **CCUTHelperCard**: 사용자가 고민할 때 나타나는 AI 추천 가이드 카드.
- **ActionSubmitButton**: "편집안 생성" 메인 실행 버튼.

## 3. 우측 영역 (Working Area Components)
- **OriginalPanorama**: 원본 영상의 전체 흐름을 보여주는 타임라인 뷰.
- **FragmentBoard**: 추천/선택된 조각들의 리스트 보드.
- **FragmentCard**: 개별 조각 카드 (썸네일, 텍스트, 시간 정보 포함).
- **FragmentActionBar**: 조각 카드 내에서 수행하는 액션(살리기, 빼기 등) 버튼 그룹.
- **PreviewOutputPanel**: 비디오 플레이어 및 출력 제어부.
- **RenderActionButtons**: mp4 출력 및 렌더링 시작 버튼.

## 4. 공통 영역 (Shared Components)
- **FooterStatusBar**: 시스템 상태 및 진행률 표시줄.
- **ModalContainer**: 안내 및 설정용 팝업 창.

## 5. 컴포넌트 상세 명세 (샘플)
| 컴포넌트 명 | 역할 | 주요 입력 (I) | 주요 출력 (O) | 우선순위 |
|-------------|------|--------------|--------------|----------|
| **NewProjectButton** | 신규 업로드 트리거 | 없음 | File Open Dialog 호출 | P0 |
| **FormOptionChip** | 옵션 선택 | Label, Value | onClick(Value) | P0 |
| **FragmentActionBar**| 조각 상태 조작 | FragmentID | Update Instruction | P1 |
| **FooterStatusBar** | 시스템 모니터링 | Governor Logs | UI Display | P2 |
