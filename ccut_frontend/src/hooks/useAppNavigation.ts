import { useCallback } from "react";
import { videoService } from "@/services/videoService";

interface UseAppNavigationParams {
  // setters (stable)
  setSelectedProposalId: (v: any) => void;
  setCommittedProposalId: (v: any) => void;
  setProposals: (v: any) => void;
  setDirectionSnapshot: (v: any) => void;
  // [PROJECT-SWITCH-RESET 2026-08-01] 채팅 원고도 프로젝트 수명이다.
  //   useProposalState 는 이미 "storyPlan과 동일 수명"이라 적고 proposalHistory 만
  //   비우고 있었다 — 정작 storyPlan 은 아무도 비우지 않았다.
  setStoryPlan: (v: any) => void;
  resetAnalysisFlow: () => void;
  setActiveNavItem: (v: string) => void;
  setNavCollapsed: (updater: (prev: boolean) => boolean) => void;
  setProjects: (updater: (prev: any[]) => any[]) => void;
  // 분기용 값
  activeNavItem: string | null;
  appState: string;
  // uiSnap 단일 빌더 (STEP 2 dedup)
  buildUiSnapshot: () => any;
  // [#30 merge-저장] "모르는 것을 지우지 않는다" — Index의 saveUiStateMerged 주입
  saveUiState: (programId: string, snapshot: any) => Promise<any>;
}

export function useAppNavigation({
  setSelectedProposalId,
  setCommittedProposalId,
  setProposals,
  setDirectionSnapshot,
  setStoryPlan,
  resetAnalysisFlow,
  setActiveNavItem,
  setNavCollapsed,
  setProjects,
  activeNavItem,
  appState,
  buildUiSnapshot,
  saveUiState,
}: UseAppNavigationParams) {
  const resetAnalysisState = useCallback(() => {
    // [REFACTOR-01] proposal 4개(useProposalState 소유) 먼저, 그 뒤 analysis 13개(useAnalysisFlow). 원본 호출순서·빈 deps 보존.
    setSelectedProposalId(null);
    setCommittedProposalId(null);
    setProposals(null);
    setDirectionSnapshot(null);
    // [PROJECT-SWITCH-RESET 2026-08-01] 채팅 원고. 지우고 나면 그 프로젝트로 돌아왔을 때
    //   서버 타임라인이 되살린다 — 그 길은 1d4e84ba 에서 복구했다(그전엔 끊겨 있었다).
    setStoryPlan(null);
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
      saveUiState(activeNavItem, buildUiSnapshot()).catch(() => {}); // [#30] merge-저장
    }
    // [PROJECT-SWITCH-RESET 2026-08-01] 프로젝트 → 프로젝트 전환에는 초기화가 **아예 없었다.**
    //   onHome·onNewProject·onDeleteProject 는 셋 다 resetAnalysisState() 를 부르는데
    //   정작 가장 잦은 경로인 이 클릭만 빠져 있었다. 그래서 A 의 채팅·story.fids·보류가
    //   B 위에 그대로 남고, 하이드레이션이 B 데이터를 덮은 뒤에도 B 에 없는 것은 A 것이
    //   살아남았다. STORY-WRITE-GUARD 의 "외래 원고 / fids 8.9배 급증" REJECT 가 그것이다.
    //   (가드는 끄지 않는다 — 지금 제 일을 하고 있고, 이 수리로 발동할 일이 없어져야 맞다.)
    //   새 초기화 로직을 만들지 않고 기존 3곳과 같은 함수를 쓴다.
    //   순서: 초기화 → setActiveNavItem → 하이드레이션 effect([activeNavItem]).
    //   buildUiSnapshot() 는 위에서 이미 동기로 값을 떠갔으므로 A 의 저장 payload 는 무사하다.
    if (newId !== activeNavItem) {
      resetAnalysisState();
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
      // [LAB-48] 화면 잔재 정리 — 구판은 activeNavItem 만 __new__ 로 바꾸고 분석 상태를
      //   그대로 뒀다. 그래서 지운 프로젝트의 조각맵·채팅이 빈 작업실 위에 남아
      //   '유령 화면'이 됐다. onNewProject 는 이미 같은 자리에서 정리하고 있었다 —
      //   삭제도 같은 정리를 거친다. 다음 프로젝트를 대신 골라주지는 않는다
      //   (시스템이 앞서가지 않는다 — 빈 작업실로 두고 사용자가 고른다).
      resetAnalysisState();
      setActiveNavItem("__new__");
    }
  };

  const onNewProject = () => {
    // [B-5d] + 버튼도 전환으로 취급: 현재 프로젝트 스냅샷 저장 후 빈 화면으로
    if (activeNavItem && activeNavItem.startsWith("proj_") && appState === "complete") {
      saveUiState(activeNavItem, buildUiSnapshot()).catch(() => {}); // [#30] merge-저장
    }
    // [B-5b-v2] '+' → DB 즉시 생성 없음. 빈 상태 전환만 (업로드 시 createProject 실행)
    resetAnalysisState();
    setActiveNavItem("__new__");
  };

  return { resetAnalysisState, onHome, onItemClick, onToggleCollapse, onRenameProject, onDeleteProject, onNewProject };
}
