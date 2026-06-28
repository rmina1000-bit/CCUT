import { useCallback } from "react";
import { videoService } from "@/services/videoService";

interface UseAppNavigationParams {
  // setters (stable)
  setSelectedProposalId: (v: any) => void;
  setCommittedProposalId: (v: any) => void;
  setProposals: (v: any) => void;
  setDirectionSnapshot: (v: any) => void;
  resetAnalysisFlow: () => void;
  setActiveNavItem: (v: string) => void;
  setNavCollapsed: (updater: (prev: boolean) => boolean) => void;
  setProjects: (updater: (prev: any[]) => any[]) => void;
  // live values (uiSnap / 분기용)
  activeNavItem: string | null;
  appState: string;
  reservedFragments: any[];
  holdPositions: Record<string, { x: number; y: number }>;
  committedProposalId: any;
  selectedProposalId: any;
  activeSource: string;
  deletedFragments: any[];
  proposals: any;
}

export function useAppNavigation({
  setSelectedProposalId,
  setCommittedProposalId,
  setProposals,
  setDirectionSnapshot,
  resetAnalysisFlow,
  setActiveNavItem,
  setNavCollapsed,
  setProjects,
  activeNavItem,
  appState,
  reservedFragments,
  holdPositions,
  committedProposalId,
  selectedProposalId,
  activeSource,
  deletedFragments,
  proposals,
}: UseAppNavigationParams) {
  const resetAnalysisState = useCallback(() => {
    // [REFACTOR-01] proposal 4개(useProposalState 소유) 먼저, 그 뒤 analysis 13개(useAnalysisFlow). 원본 호출순서·빈 deps 보존.
    setSelectedProposalId(null);
    setCommittedProposalId(null);
    setProposals(null);
    setDirectionSnapshot(null);
    resetAnalysisFlow();
  }, []);

  // [HOME] CCUT 로고(펼친 상태) → 첫 화면. 편집상태 리셋 + 네비 projects.
  const onHome = useCallback(() => {
    resetAnalysisState();
    setActiveNavItem("projects");
  }, [resetAnalysisState, setActiveNavItem]);

  // 매 렌더 재생성(기존 인라인 화살표와 동일 의미) — useCallback 미적용으로 stale closure 회피. 본문 verbatim.
  const onItemClick = (newId: string) => {
    // [B-5d] 전환 직전: 현재 프로젝트 UI 스냅샷 저장 (백그라운드, non-blocking)
    if (activeNavItem && activeNavItem.startsWith("proj_") && appState === "complete") {
      const uiSnap = {
        reservedFragments,
        holdPositions,
        committedProposalId,
        selectedProposalId,
        activeSource,
        deletedFragments,
        proposalsKeyFragments: proposals ? {
          A: (proposals as any).A?.key_fragments,
          B: (proposals as any).B?.key_fragments,
        } : undefined,
        proposalsCustomFragments: proposals ? {
          A: (proposals as any).A?.customEditFragments,
          B: (proposals as any).B?.customEditFragments,
        } : undefined,
      };
      videoService.saveProjectState(activeNavItem, { ui_state: JSON.stringify(uiSnap) }).catch(() => {});
    }
    // [FIX-LIST-ORDER] 프로젝트를 '여는(클릭) 것'은 조회이므로 목록 순서를 바꾸지 않는다.
    // (Claude 채팅 사이드바 방식: 열람으로는 순서 불변, 실제 활동에서만 최상단으로)
    setActiveNavItem(newId);
  };

  const onToggleCollapse = () => setNavCollapsed((prev) => !prev);

  const onRenameProject = (id: string, newName: string) => {
    setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name: newName } : p)));
    fetch(`${videoService.API_BASE_URL}/programs/${id}/name`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: newName }),
    }).catch((e) => console.error("[rename]", e));
  };

  const onDeleteProject = (id: string) => {
    videoService.deleteProject(id).catch(() => {});
    setProjects((prev) => prev.filter((p) => p.id !== id));
    if (activeNavItem === id) {
      setActiveNavItem("__new__");
    }
  };

  const onNewProject = () => {
    // [B-5d] + 버튼도 전환으로 취급: 현재 프로젝트 스냅샷 저장 후 빈 화면으로
    if (activeNavItem && activeNavItem.startsWith("proj_") && appState === "complete") {
      const uiSnap = {
        reservedFragments,
        holdPositions,
        committedProposalId,
        selectedProposalId,
        activeSource,
        deletedFragments,
        proposalsKeyFragments: proposals ? {
          A: (proposals as any).A?.key_fragments,
          B: (proposals as any).B?.key_fragments,
        } : undefined,
        proposalsCustomFragments: proposals ? {
          A: (proposals as any).A?.customEditFragments,
          B: (proposals as any).B?.customEditFragments,
        } : undefined,
      };
      videoService.saveProjectState(activeNavItem, { ui_state: JSON.stringify(uiSnap) }).catch(() => {});
    }
    // [B-5b-v2] '+' → DB 즉시 생성 없음. 빈 상태 전환만 (업로드 시 createProject 실행)
    resetAnalysisState();
    setActiveNavItem("__new__");
  };

  return { resetAnalysisState, onHome, onItemClick, onToggleCollapse, onRenameProject, onDeleteProject, onNewProject };
}
