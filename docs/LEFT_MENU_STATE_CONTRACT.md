# Left Menu State Contract

본 문서는 좌측 메뉴(Left Menu) 클릭 시 어떠한 상태가 유지(Preserve)되고, 어떠한 상태가 교체(Replace)되는지 정의합니다.
이 계약은 CCUT가 작업 중인 편집 상태를 잃지 않고 언제든 복원 가능하도록 하는 핵심 기반입니다.

---

## 1. App UI State
App UI State는 전역적(Global)인 어플리케이션 계층의 라우팅/설정 상태입니다.
어떤 프로젝트(Workspace)에 종속되지 않습니다.

- **activeView**: 현재 중앙/우측 패널에 떠 있는 뷰. (기본: `workspace`, 그 외 `upload`, `archive`, `share`, `reports`, `settings`)
- **selectedWorkspaceId**: 현재 활성화되어 배경에서 동작 중인, 또는 포커스된 프로젝트 ID.
- **isLeftPanelCollapsed**: 좌측 메뉴 접힘/펼침 여부.

**상태 전이 규칙:**
Global Navigation 트리 아래의 메뉴(Archive, Reports 등)를 클릭할 경우 **오직 `activeView`만 변경**됩니다.
이때 `selectedWorkspaceId`는 변하지 않으며 진행 중이던 편집 작업은 모두 숨겨진 채 보존됩니다.

---

## 2. Workspace State
하나의 영상 클립과 그에 따른 제안(Proposals), 편집 상태를 관장하는 거대한 상태 몽땅(Chunk)입니다.
 UI 네비게이션이 편집 데이터를 오염시키지 않도록, 메타데이터와 실제 작업 데이터는 반드시 분리(Separate)되어 저장됩니다.

- **workspaceList (Metadata)**: 좌측 프로젝트 리스트용 최소 정보.
  - `id`, `name`, `createdAt`, `updatedAt`, `hasVideo`, `status`
- **workspaceDataMap (Editing Data)**: 무거운 실제 편집 데이터. (workspaceId를 키로 가짐)
  - `fragments`, `proposals`, `boardItems`, `chatMessages`, `panoramaState`, `rightPanelState`
- **selectedWorkspaceId**: 현재 포커스된 프로젝트 ID.

**상태 전이 규칙:**
Workspace Manager의 다른 프로젝트를 클릭하면:
1. 기존의 `workspaceDataMap[oldId]`는 최신 상태로 `localStorage` 객체에 Auto-Save 됩니다.
2. `WorkspaceContext`가 `selectedWorkspaceId`를 변경하고, `workspaceDataMap[newId]`에서 데이터를 꺼내어 화면을 복원(Restore)합니다.
3. UI 패널들은 복원 주체가 아니며, 오직 `WorkspaceContext`가 제공하는 상태의 읽기 전용(Read-only) 소비자로 동작합니다.

**상태 전이 규칙:**
Workspace Manager의 다른 프로젝트를 클릭하면:
1. 기존의 `Workspace State`는 `workspaceStore` (메모리 또는 localStorage) 객체에 저장됩니다. (Auto-Save)
2. 선택된 프로젝트 ID를 가진 백업 `Workspace State`에서 완전히 새로운 상태를 꺼내어 화면을 복원(Restore)합니다.

---

## 3. Session State (System Preservation)
새로고침을 하거나 브라우저를 껐다 켰을 때 CCUT가 마지막 상황을 기억하기 위한 계약입니다.

- `localStorage.getItem('ccut_last_workspace_id')`
- `localStorage.getItem('ccut_workspaces')`
- `localStorage.getItem('ccut_active_view')`

이 상태들은 시스템이 부팅될 때 가장 먼저 로드되어 **Fail-Silent** 원칙 아래 안정적으로 어제 작업하던 화면을 띄워줍니다.
