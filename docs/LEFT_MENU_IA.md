# Left Menu Information Architecture (IA)

본 문서는 CCUT 좌측 메뉴의 각 항목이 가지는 역할(Label, Type, Target View, Preserve Policy)을 고정합니다.

좌측 메뉴는 크게 3개의 기능 계층으로 나뉩니다:
1. **Global Navigation**: 서비스의 큰 레벨 이동
2. **Workspace Manager**: 현재 및 최근 작업 목록 관리
3. **Account / System**: 환경/사용자/설정

---

## 1. Global Navigation

| Label | Type | Target View | Preserve Policy | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| 영상 업로드 | action / nav | upload (overlay or view) | 현재 작업 유지 (Preserve) | 새로운 영상을 업로드하여 현재 Workspace에 반영하거나 새로운 Workspace를 생성. |
| Archive | nav | archive | 현재 작업 유지 (Preserve) | 완료작업 / 휴지통 / 보관함을 조회하는 뷰. 다른 Workspace의 작업 상태에 영향을 주지 않음. |
| SNS 홍보 공유 | nav | share | 편집 완성 전 제한 | 배포 및 공유를 위한 뷰. 현재 프로젝트의 편집 완성본이 있어야만 진입 가능. |
| Reports | nav | reports | 현재 작업 유지 (Preserve) | 분석 요약, 작업 로그, 결정 기록 등을 보여주는 리포트 대시보드. |

---

## 2. Workspace Manager

| Label | Type | Target View | Preserve Policy | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| 새 프로젝트 | action | workspace | 기존 작업실 상태 보존 | 새로운 빈 Workspace ID를 발급하고, 해당 Workspace로 전환. 기존 편집 상태는 메모리에 저장됨. |
| [프로젝트 항목] | workspace-item | workspace | 복원 (Restore) | 클릭 시 해당 Workspace의 마지막 편집 상태 및 영상, 분석 결과(Proposals 등) 전체 복원. |

---

## 3. Account / System

| Label | Type | Target View | Preserve Policy | 설명 |
| :--- | :--- | :--- | :--- | :--- |
| [demo_user] | section | account | 현재 작업 유지 (Preserve) | 계정 설정 및 프로필. |
| Settings | nav | settings | 현재 작업 유지 (Preserve) | 앱 전역 설정(Global Settings). |
