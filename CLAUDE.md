CCUT 1.0.2 — Claude Code 작업 기준 문서

이 문서의 목적
Claude Code가 CCUT 프로젝트를 처음 열 때 반드시 읽어야 할 맥락 문서다. 새 대화를 시작해도 이 문서를 기준으로 판단하고 작업한다.

제품 한 문장 정의
CCUT은 채팅형 영상 편집 제안 프로그램이다. 사용자는 영상을 올리고, AI가 두 가지 러프컷 안(A/B)을 제안하며, 사용자는 선택하거나 채팅으로 수정 지시하거나 비례바로 조각을 미세 조정한다. 대부분의 사용자는 제안을 선택하고 SNS에 바로 올린다.

실제 사용 흐름
1. 영상 업로드
2. AI가 Proposal A / B 두 안 제안
3. 사용자가 하나 선택
4. 대부분 → 바로 내보내기 (SNS용)
5. 더 손보고 싶으면 → 채팅으로 편집 지시
6. 조각 경계 조정 → 비례바 편집창 열어서 프레임 단위 조정

현재 코드베이스 상태 (Codex 감사 결과 2026-03-21)

핵심 문제
* 활성 앱(ui/src/)은 "fragment structure editor" — 직접 편집 도구
* 바이블이 원하는 건 "proposal A/B 채팅형 앱"
* 두 구조가 충돌 중

활성 앱 경로
ui/index.html → ui/main.jsx → ui/src/pages/Index.tsx

Legacy (비활성) 경로
ui/App.jsx, ui/context/WorkspaceContext.jsx — 현재 마운트 안 됨

Keep / Revise / Drop / Hold 기준

Keep (건드리지 말 것)
* ccut_core/proposal_engine/proposal_engine.py — backend A/B 엔진
* ui/src/ 전체 구조 — 핵심 자산, 버리지 않음

Revise (고쳐야 할 것)
* ui/src/pages/Index.tsx — proposal/workspace SSOT 연결 필요
* ui/src/components/CenterPanel.tsx — A/B 제안이 주인공이 되도록
* ui/src/components/LeftNav.tsx — 조용한 서랍으로 재정의
* ui/src/components/FragmentMap.tsx — 편집 affordance 줄이기

Drop (제거 대상 — 확인 후 삭제)
* ui/App.jsx
* ui/context/WorkspaceContext.jsx
* ui/layout/MainLayout.jsx (Proposal C/D 포함)
* ui/right_panel.jsx (board/trash/raw player 포함)
* ui/left_panel.jsx
* ui/chat_ui.jsx
* ui/panorama_engine.js

Hold (보류 — 아직 건드리지 말 것)
* /generate-fragments, /generate-proposals backend routes
* flattened mp4 export

절대 금지 사항
* direct editing 복구 금지
* Proposal C/D 추가 금지
* board / trash 복구 금지
* 우측 패널을 편집창으로 바꾸기 금지
* 대시보드형 Home 복구 금지
* 기능 확장 금지 — 지금은 polish 단계

화면 구조 목표

좌측
조용한 서랍. 아카이브, SNS 업로드, 편집 트래커, 사용자ID, 설정만.

중앙
A/B 제안이 주인공.
* 빈 상태: 영상 업로드 유도
* 업로드 후: 분석 중
* 분석 완료: Proposal A / B 카드 나란히
* 선택 후: 재제안 유도 또는 상세편집 버튼

우측
기본 닫힘. 원본 파노라마 + 조각 그리드 + 보류함. 읽기 전용 구조맵. 편집 조작 없음.

작업 원칙
1. 먼저 읽기 전용으로 파일 확인
2. 변경 전 반드시 Keep/Revise/Drop/Hold 판정
3. 한 번에 하나씩 작업
4. 기능 추가 전에 "이게 더 쉬워지는가?" 먼저 물을 것
5. 배워야 하는 툴이 되면 실패한다
