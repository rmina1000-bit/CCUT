import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import { toast } from "sonner";
import LeftNav from "@/components/LeftNav";
import CenterPanel from "@/components/CenterPanel";
import OriginalPanorama from "@/components/OriginalPanorama";
import FragmentMap from "@/components/FragmentMap";
import ReservedFragments from "@/components/ReservedFragments";
import LedgerPage from "@/pages/LedgerPage";
import FragmentMiniPlayer from "@/components/FragmentMiniPlayer";
import RoughCutStage from "@/components/RoughCutStage";
import type { RoughCutData, RoughCutSpan } from "@/components/RoughCutOutline";

// [DRAG-ONE 2026-08-02] 드래그바는 components/ResizeHandle.tsx 하나에서 관리한다.
//   폭·색·안쪽 선·커서가 전부 거기 있다 — 여기서 숫자를 다시 적지 않는다.
import ResizeHandle from "@/components/ResizeHandle";
// [dev ESM 안전] 타입 전용 import는 반드시 `import type` — 혼합 import는 esbuild가 못 벗겨
// 런타임에 존재하지 않는 named export(interface)를 요청해 모듈 에러가 난다(build는 통과).
import type { MiniPlayTarget } from "@/components/FragmentMiniPlayer";
import { useWorkspaceLayout } from "@/hooks/useWorkspaceLayout";
import { useProposalState } from "@/hooks/useProposalState";
import { useStoryGate, fetchStory } from "@/hooks/useStoryGate";
import { ArchivePanel } from "@/components/ArchivePanel";
import { SnsUploadPanel } from "@/components/SnsUploadPanel";
import { AccountPanel } from "@/components/AccountPanel";
import { TrashPanel } from "@/components/TrashPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { SingleFragmentEditor } from "@/components/SingleFragmentEditor";
import { AppDialog } from "@/components/AppDialog";
import { storyStageVisible, storyStageBadge } from "@/lib/storyMode";
import { fragmentTranscriptText } from "@/lib/fragmentText";
import { STORY_GATE_COPY } from "@/lib/storyGateCopy";
// [GHOST 소각 #4·5] 구 2조각 PBE(PrecisionBoundaryEditor) 완전 소각 — 타입·주석 렌더 포함. 복원은 git 이력.


import {
  Fragment,
  SelectionState,
  FragmentStatus,
  initialEditFragments,
  initialReservedFragments,
} from "@/data/fragmentData";
import { useAnalysisFlow } from "@/hooks/useAnalysisFlow";
import { useAppNavigation } from "@/hooks/useAppNavigation";
import type { SourceEntry } from "@/types";

import { assignShortDisplayIds, getUid, recalcDisplayIds, rangeDisplayName, registerSourceTitle } from "@/lib/fragmentIdentity";
import { videoService } from "@/services/videoService";

import { Direction, DirectionSnapshot, Proposal, StoryPlanPreview } from "@/proposal/proposalTypes";
import {
  createNextSnapshot,
} from "@/proposal/directionSnapshot";
// [GHOST#3 절단] generateProposals(strategyEngine 폴백)·createInitialSnapshot import 제거 — 가짜 제안 경로 소멸
import { collectFragmentAliases, resolveProposalFragments } from "@/utils/proposalFragmentResolver";
// [EDIT-CONTRACT-B0 IMPL-2b] 공통 편집 계약 클라이언트 — 게이트 OFF면 어디서도 호출되지 않는다
import {
  fetchEditStates,
  fetchGateEnabled,
  postEditState,
  segmentsToExcludedMs,
  timelineItemIdFor,
  type EditStateRow,
} from "@/utils/editContractClient";
// [R2] 조각맵 분할 표시 = 상태의 순수 파생 — Apply 경로와 재수화 경로가 같은 함수를 쓴다
import { rebuildFragmentTiles } from "@/utils/fragmentTiles";
import { rematchAnchor, toMs } from "@/utils/editContract";
import { buildExportClipsFromResolvedFragments, type PhysicalClip } from "@/utils/exportClipBuilder";
import { DEBUG_LOG } from "@/utils/debugFlags";
import { closeMirrorPendingForProject, recordMirrorEvent } from "@/utils/mirrorEventLog";
import {
  fetchSoundRoles,
  saveSoundRole,
  type SoundRole,
  type SoundRoleItem,
} from "@/utils/soundRoleClient";

type PbeContractState = Pick<
  EditStateRow,
  "anchor_start_ms" | "anchor_end_ms" | "trim_start_ms" | "trim_end_ms" | "excluded_ranges" | "removed"
>;

type RoughCutPlacement = {
  inputHash: string | null;
  selectedSpanIds: string[];
};

const pbeContractKey = (programId: string | null | undefined, fid: string) => `${programId ?? "local"}:${fid}`;

function proposalFidsForFlow(proposal: any): string[] {
  const keyFragments = Array.isArray(proposal?.key_fragments) ? proposal.key_fragments : [];
  if (keyFragments.length) return keyFragments.map(String).filter(Boolean);
  const sequence = Array.isArray(proposal?.sequence) ? proposal.sequence : [];
  if (sequence.length) {
    return sequence
      .map((item: any) => item?.fragment_id ?? item?.proposal_fragment_id ?? item?.fid ?? item?.id)
      .map(String)
      .filter(Boolean);
  }
  const aliases = Array.isArray(proposal?.resolved_aliases) ? proposal.resolved_aliases : [];
  return aliases
    .map((item: any) => item?.fragment_id ?? item?.proposal_fragment_id ?? item?.fid ?? item?.id)
    .map(String)
    .filter(Boolean);
}

function sameFlowFids(left: string[], right: string[]): boolean {
  return left.length === right.length && left.every((fid, index) => fid === right[index]);
}

function proposalPairMatchesFlowStory(pair: any, storyFids: string[]): boolean {
  if (!pair?.A || !pair?.B || storyFids.length === 0) return false;
  return (
    sameFlowFids(proposalFidsForFlow(pair.A), storyFids) &&
    sameFlowFids(proposalFidsForFlow(pair.B), storyFids)
  );
}

// Layout constants moved to useWorkspaceLayout.ts



const Index: React.FC = () => {
  const {
    containerRef,
    activeNavItem,
    setActiveNavItem,
    navCollapsed,
    setNavCollapsed,
    projects,
    setProjects,
    navWidth,
    isNavDragging,
    setIsNavDragging,
    centerWidth,
    isDragging,
    setIsDragging,
  } = useWorkspaceLayout();

  const [activeSource, setActiveSource] = useState("A");

  const {
    selectedFragment, setSelectedFragment,
    highlightedPanoramaFrag, setHighlightedPanoramaFrag,
    expandedFragment, setExpandedFragment,
    editFragments, setEditFragments,
    reservedFragments, setReservedFragments,
    deletedFragments, setDeletedFragments,
    appState, setAppState,
    sourceFragments, setSourceFragments,
    currentSourceId, setCurrentSourceId,
    currentVideoUrl, setCurrentVideoUrl,
    quickScanData, setQuickScanData,
    semanticFragments, setSemanticFragments,
    sourceEntries, setSourceEntries,
    resetAnalysisFlow,
  } = useAnalysisFlow();

  // [STORY-GATE P3] 승인 전에는 PBE(조각 정밀편집) 진입을 막는다 (S2).
  // 게이트 OFF면 awaitingApproval=false → 현행과 동일.
  // [LAB-21] activeNavItem 은 프로젝트 id 와 화면 이름("upload"·"archive"…)을 겸한다.
  //   가드 없이 넘기면 /api/story/upload 같은 요청이 나가 404 가 뜬다(콘솔 잡음).
  //   아래 137행이 이미 쓰는 것과 같은 조건이다.
  const storyGate = useStoryGate(
    activeNavItem?.startsWith("proj_") ? activeNavItem : null,
    appState === "complete",
  );
  const uiStateSaveRef = useRef<Promise<unknown> | null>(null);
  // [SAVE-SPINE 2-C] 직전 저장 버전 — 다음 저장의 부모가 된다(설계 ⑥: 부모/자식은 버전 사이).
  const lastSavedVersionIdRef = useRef<number | null>(null);
  // [LAYER-SPLIT 2026-08-04 ②] 저장된 버전 목록. 채팅 밖 자기 층이 이걸 그린다.
  const [savedVersions, setSavedVersions] = useState<Array<{
    version_id: number; name: string; item_count: number;
    parent_version_id: number | null; created_at: string;
  }>>([]);
  const [editVersions] = useState<Array<{ id: string; name: string }>>([]);
  const [activeVersionId, setActiveVersionId] = useState<number | null>(null);
  const [precisionPaneMode, setPrecisionPaneMode] = useState<"story" | "edit">("story");
  // [LAYER-FIX 3-A] 방금 복원한 버전의 fids. 급증 가드가 '이건 복원이다'를 알아보는 유일한 근거.
  //   ref 인 이유: 가드는 렌더 밖(saveUiStateMerged 안)에서 도므로 최신 값이 필요하다.
  const versionRestoreFidsRef = useRef<string[] | null>(null);
  const activeVersionIdRef = useRef<number | null>(null);
  activeVersionIdRef.current = activeVersionId;
  const [compositionNotice, setCompositionNotice] = useState<string | null>(null);
  const [appDialog, setAppDialog] = useState<{
    message: string;
    cancelText?: string;
    onConfirm?: () => void | Promise<void>;
  } | null>(null);
  // [#22 모든 편집 진입은 스토리로 2026-07-19] '다시 편집'(SNS·아카이브)로 들어온 프로젝트는
  // 이미 승인 상태여도 편집(A/B)으로 직행하지 않고 스토리 단계로 연다. 강제 story 모드는
  // '재편집 세션'이 지속되는 동안만 — (a) 다른 프로젝트로 이동, (b) 이후 사용자가 새로 승인,
  // (c) 재작업으로 실제 stale 전환(#8-a) 되면 해제. 재작업 시 승인 stale은 #8-a가 처리.
  const [reEditProgramId, setReEditProgramId] = useState<string | null>(null);
  const reEditSessionStartRef = useRef<number>(0);
  useEffect(() => {
    if (!reEditProgramId) return;
    if (reEditProgramId !== activeNavItem) { setReEditProgramId(null); return; }   // (a)
    const at = storyGate.story?.approved?.approved_at;
    if (at && new Date(at).getTime() > reEditSessionStartRef.current) setReEditProgramId(null); // (b) 새 승인
  }, [reEditProgramId, activeNavItem, storyGate.story?.approved?.approved_at]);
  const navigateToProject = useCallback((id: string, reEdit?: boolean) => {
    if (reEdit) { reEditSessionStartRef.current = Date.now(); setReEditProgramId(id); }
    setActiveNavItem(id);
  }, [setActiveNavItem]);
  useEffect(() => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return;
    const closePending = () => {
      closeMirrorPendingForProject(activeNavItem, "session_end");
    };
    window.addEventListener("pagehide", closePending);
    window.addEventListener("beforeunload", closePending);
    return () => {
      window.removeEventListener("pagehide", closePending);
      window.removeEventListener("beforeunload", closePending);
    };
  }, [activeNavItem]);

  // [STORY-TRACK-A A-1 · R8 유령 4호 2026-07-20] 우측창 스토리 모드 = 중앙(centerShowStory)과
  // '완전 동일한 식' storyStageVisible 하나. 판정·후단 조건이 유틸 안에 있어 분열 경로가 없다.
  const activeReEdit = reEditProgramId === activeNavItem;
  const rightStoryMode = storyStageVisible(storyGate.story, activeReEdit);
  const [modeGateOn, setModeGateOn] = useState(false);
  const [fragmentFace, setFragmentFace] = useState<"image" | "text">("image");
  useEffect(() => {
    let dead = false;
    fetch("/api/settings/gates")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (dead) return;
        const raw = d?.gates?.CCUT_MODE_GATE ?? import.meta.env.VITE_CCUT_MODE_GATE ?? "";
        setModeGateOn(String(raw).trim().toUpperCase() === "ON");
      })
      .catch(() => {
        if (!dead) setModeGateOn(String(import.meta.env.VITE_CCUT_MODE_GATE ?? "").trim().toUpperCase() === "ON");
      });
    return () => { dead = true; };
  }, []);
  // [GATE-LOOP-01 1번] modeEditLocked 폐기 — 승인 후에도 사용자를 잠그지 않는다.
  //   구판: 승인되면 보류맵을 숨기고 조각 편집 핸들러를 () => {} 로 죽였다.
  //         사용자가 "왜 안 되지"를 겪고, 화면이 임시 페이지처럼 보이던 원인.
  //   신판: 바꾸는 건 언제나 허용. 바꾸면 sequence_hash가 달라지고 → 백엔드 story_state가
  //         approved → review로 내려가고 → storyStageVisible이 참이 되어 스토리 단계로 복귀한다.
  //         A/B는 그때 stale이 되어 화면에서 물러날 뿐, 제안 데이터는 지우지 않는다.
  //   즉 잠금이 필요 없다. 상태기계가 스스로 되돌아온다 (복귀 루프).
  //   (단계 배지 storyStage는 committedProposalId 선언 뒤에서 계산 — TDZ 회피)

  // [STORY-TRACK-C C-3] 조각맵:보류맵 세로 분할 비율(조각맵 몫 0..1). 기존 ccut_center_width와
  // 동일 localStorage 방식. 편집 단계도 마지막 조정 존중(§9) — 값은 단계 무관 공유.
  const [mapHoldSplit, setMapHoldSplit] = useState<number>(() => {
    try { const v = parseFloat(localStorage.getItem("ccut_map_hold_split") || ""); if (v >= 0.15 && v <= 0.85) return v; } catch { /* 손상값 무시 */ }
    return 0.7;
  });
  useEffect(() => { try { localStorage.setItem("ccut_map_hold_split", String(mapHoldSplit)); } catch { /* quota 무시 */ } }, [mapHoldSplit]);
  const mapHoldAreaRef = useRef<HTMLDivElement>(null);
  const startMapHoldDrag = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    const area = mapHoldAreaRef.current;
    if (!area) return;
    const onMove = (ev: MouseEvent) => {
      const rect = area.getBoundingClientRect();
      if (rect.height <= 0) return;
      const ratio = (ev.clientY - rect.top) / rect.height;   // 조각맵 몫
      setMapHoldSplit(Math.max(0.15, Math.min(0.85, ratio)));
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "row-resize";
    document.body.style.userSelect = "none";
  }, []);

  // [GATE-LOOP-01 2-1] 승인 후 A/B 생성기. 선언 순서(TDZ) 때문에 ref로 늦게 채운다.
  const requestProposalsForApprovedStoryRef = useRef<(() => Promise<boolean>) | null>(null);
  const startApprovedStoryEditingBridgeRef = useRef<((source: "chat") => Promise<boolean>) | null>(null);
  const startApprovedStoryEditingFromChat = useCallback(
    async (source: "chat") => startApprovedStoryEditingBridgeRef.current?.(source) ?? false,
    [],
  );


  const handleReopenComposition = useCallback(async () => {
    setAppDialog({
      message: "편집값은 보존됩니다. 빠진 조각의 값은 남고, 이음매 값은 다시 확인이 필요할 수 있습니다.",
      cancelText: "Cancel",
      onConfirm: async () => {
        const result = await storyGate.reopen();
        if (result.ok) {
          reEditSessionStartRef.current = Date.now();
          setReEditProgramId(activeNavItem);
          await storyGate.reload();
        }
      },
    });
  }, [activeNavItem, storyGate, setAppDialog]);

  // [STORY-LAYER-01 A-1] 보류맵 좌표도 프로젝트 스코프 하나 (구판 제안별 {A,B} 폐기).
  const [holdPositions, setHoldPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [boundaryHighlightIds, setBoundaryHighlightIds] = useState<string[]>([]);
  // [GHOST 소각 #4] 구 2조각 PBE 상태(editorTarget·pbeWindow·editorOpen) 제거 — 소비자 전무 증명(STEP C)
  const [singleEditOpen, setSingleEditOpen] = useState(false);
  const [singleEditTarget, setSingleEditTarget] = useState<Fragment | null>(null);
  const [fragmentOverrides, setFragmentOverrides] = useState<Map<string, Fragment>>(new Map());

// selectedProposalId, committedProposalId moved to useProposalState

  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [analyzeMessage, setAnalyzeMessage] = useState("");
  const [analysisLogs, setAnalysisLogs] = useState<string[]>([]);
  const pushAnalysisLog = (line: string) => {
    setAnalysisLogs((prev) => [...prev.slice(-7), line]);
  };
  const [isSwitchingProject, setIsSwitchingProject] = useState(false);
  useEffect(() => {
    if (!isSwitchingProject) return;
    const timer = setTimeout(() => setIsSwitchingProject(false), 3000);
    return () => clearTimeout(timer);
  }, [isSwitchingProject]);

  // [PBE-PROGRESS] 분석 중 진행바가 멈춰 보이지 않도록 95%까지 천천히 전진(멈춤처럼 보이지 않게)
  useEffect(() => {
    if (appState !== "analyzing") return;
    const _pbeTick = setInterval(() => {
      setAnalyzeProgress((p) => (p < 95 ? Math.min(95, p + 1) : p));
    }, 600);
    return () => clearInterval(_pbeTick);
  }, [appState]);
  const [intelligenceOn, setIntelligenceOn] = useState(false);

  // ── [STORY-LAYER-01 A-1] live story = program 단위 하나 ──
  // storyFids       : 선택된 조각 + 순서 (사용자 결정 — INV-0. AI가 바꾸지 않는다)
  // storyFragments  : 그 스토리의 구성본(좌표·분할 포함 표시용) — 구판 customEditFragments 대체
  // 제안(A/B)은 이 하나의 스토리를 '어떻게 편집할지'이므로, 스토리를 소유하지 않는다.
  const [storyFids, setStoryFids] = useState<string[]>([]);
  const [storyFragments, setStoryFragments] = useState<Fragment[]>([]);

// proposals, directionSnapshot moved to useProposalState



  const {
    selectedProposalId,
    setSelectedProposalId,
    committedProposalId,
    setCommittedProposalId,
    proposals,
    setProposals,
    directionSnapshot,
    setDirectionSnapshot,
    storyPlan,
    setStoryPlan,
    handleProposalPreview,
    handleProposalCommit,
    handleReproposal,
    handleConsultation,
    logProposalPair,
    proposalHistory,
    activeProposalEntryId,
    restoreProposalEntry,
    hydrateProposalHistory
  } = useProposalState(
    sourceFragments,
    activeNavItem || "default_project",
    sourceEntries.length > 0
      ? sourceEntries.map(e => e.source_id)
      : currentSourceId ? [currentSourceId] : [],
    storyFids,
    {
      approvedStoryReady: storyGate.story?.story_state === "story_approved" && (storyGate.story?.item_count ?? 0) > 0,
      approvedStoryCount: storyGate.story?.item_count ?? storyFids.length,
      onStartApprovedStoryEditing: startApprovedStoryEditingFromChat,
    },
  );
  // [FLOW] 확정/선택 전에도 조각맵이 비지 않게 — 무대에 선 제안(기본 A)을 따라간다.
  // [STORY-LAYER-01 A-1] 이 값은 '표시 방식'(어느 편집안을 무대에 세울지)일 뿐이며,
  // 스토리(조각·순서·대사)를 가르지 않는다. 조각맵·전사·보류맵은 이 값을 참조하지 않는다.
  const displayProposalId = committedProposalId ?? selectedProposalId ?? (proposals ? "A" : null);

  // [GATE-LOOP-01 3번] 단계 배지 — 상태기계에서 파생만 한다 (배지가 자기 상태를 갖지 않는다).
  const hasCurrentProposalPair = proposalPairMatchesFlowStory(proposals, storyFids);
  const storyStage = storyStageBadge(
    storyGate.story?.story_state,
    committedProposalId,
    activeReEdit,
    hasCurrentProposalPair,
  );

  const appendStoryGateMessage = useCallback((idPrefix: string, text: string, extra?: Record<string, unknown>) => {
    setStoryPlan((prev: any) => {
      const messages = (prev?.messages) ?? [];
      const lastText = messages.length ? String(messages[messages.length - 1]?.text ?? "") : "";
      if (lastText === text) return prev;
      return {
        ...(prev ?? {
          story_plan_id: `STP_${Date.now()}`,
          source_count: sourceEntries.length,
          consultation_status: "draft_ready",
          confirmation_status: "pending",
          direction_options: [],
          detected_theme: "",
          selected_direction: undefined,
          messages: [],
        }),
        messages: [
          ...messages,
          {
            id: `${idPrefix}_${Date.now()}`,
            sender: "ai" as const,
            text,
            timestamp: Date.now(),
            ...(extra ?? {}),
          },
        ],
      };
    });
  }, [sourceEntries.length]);


  const [soundViewEnabled, setSoundViewEnabled] = useState(false);
  const [soundRoleItems, setSoundRoleItems] = useState<SoundRoleItem[]>([]);
  const [soundRoleLoading, setSoundRoleLoading] = useState(false);
  const [soundRoleError, setSoundRoleError] = useState(false);
  const [soundRoleSavingIds, setSoundRoleSavingIds] = useState<Set<string>>(new Set());
  const soundLoadSeqRef = useRef(0);
  const soundRoleSavingRef = useRef<Set<string>>(new Set());
  const editFlowProposalSigRef = useRef<string | null>(null);
  const soundProgramRef = useRef(activeNavItem);
  soundProgramRef.current = activeNavItem;
  const refreshSoundRoles = useCallback(async () => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) {
      setSoundRoleItems([]);
      return 0;
    }
    const seq = ++soundLoadSeqRef.current;
    setSoundRoleLoading(true);
    setSoundRoleError(false);
    try {
      const result = await fetchSoundRoles(activeNavItem);
      if (seq !== soundLoadSeqRef.current) return;
      setSoundRoleItems(result.items ?? []);
      const count = result.items?.length ?? 0;
      console.info("[SOUND-ROLE][EDIT-FLOW]", {
        program_id: activeNavItem,
        item_count: count,
        roles: (result.items ?? []).map((item) => ({
          ordinal: item.ordinal,
          fragment_id: item.fragment_id,
          detected: item.detected_role,
          effective: item.effective_role,
          reason: item.reason,
        })),
      });
      return count;
    } catch (error) {
      if (seq !== soundLoadSeqRef.current) return;
      console.warn("[SOUND-1] sound handling load failed", error);
      setSoundRoleItems([]);
      setSoundRoleError(true);
      return 0;
    } finally {
      if (seq === soundLoadSeqRef.current) setSoundRoleLoading(false);
    }
  }, [activeNavItem]);
  const handleSoundViewChange = useCallback((enabled: boolean) => {
    setSoundViewEnabled(enabled);
  }, []);
  const handleSoundRoleChange = useCallback(async (item: SoundRoleItem, role: SoundRole) => {
    if (!activeNavItem || soundRoleSavingRef.current.has(item.timeline_item_id)) return;
    const programId = activeNavItem;
    soundRoleSavingRef.current.add(item.timeline_item_id);
    setSoundRoleSavingIds(new Set(soundRoleSavingRef.current));
    try {
      const saved = await saveSoundRole(programId, item, role);
      if (soundProgramRef.current !== programId) return;
      setSoundRoleItems((current) => current.map((candidate) => (
        candidate.timeline_item_id === item.timeline_item_id
          ? {
              ...candidate,
              effective_role: saved.effective_role,
              overridden: saved.overridden,
              revision: saved.revision,
            }
          : candidate
      )));
    } catch (error) {
      if (soundProgramRef.current !== programId) return;
      console.warn("[SOUND-1] sound handling save failed", error);
      toast.error(STORY_GATE_COPY.sound.saveFailed);
      void refreshSoundRoles();
    } finally {
      soundRoleSavingRef.current.delete(item.timeline_item_id);
      setSoundRoleSavingIds(new Set(soundRoleSavingRef.current));
    }
  }, [activeNavItem, refreshSoundRoles]);
  useEffect(() => {
    soundLoadSeqRef.current += 1;
    soundRoleSavingRef.current.clear();
    setSoundViewEnabled(false);
    setSoundRoleItems([]);
    setSoundRoleError(false);
    setSoundRoleLoading(false);
    setSoundRoleSavingIds(new Set());
  }, [activeNavItem]);
  const soundStorySignature = useMemo(() => storyFids.join("|"), [storyFids]);
  useEffect(() => {
    if (soundViewEnabled) void refreshSoundRoles();
  }, [refreshSoundRoles, soundStorySignature, soundViewEnabled]);
  const [roughCutData, setRoughCutData] = useState<RoughCutData | null>(null);
  const [roughCutPlacement, setRoughCutPlacement] = useState<RoughCutPlacement | null>(null);

  const roughCutMapReady = storyStage.key !== "scanned" && roughCutData !== null;
  // [TIMELINE-PAGE 2026-08-02] 300행 절단 복구용 커서.
  //   서버는 limit 을 넘으면 has_more=true 와 함께 최신 N행만 준다(main.py:6467).
  //   구판은 이 사실을 DEBUG_LOG 문자열 안에서만 읽어 사용자에게 0으로 도달했다.
  //   oldest = 지금까지 받은 것 중 가장 오래된 entry_id — 다음 페이지의 before 커서.
  const [timelineHasMore, setTimelineHasMore] = useState(false);
  const [timelineOldestEntry, setTimelineOldestEntry] = useState<number | null>(null);
  const [timelineLoadingMore, setTimelineLoadingMore] = useState(false);
  // [TIMELINE-REF 2026-08-02] 전사가 대화 흐름에 등장한 시각 (원장의 transcript_ref 행).
  //   null 이면 아직 기록이 없다는 뜻이고, 그때는 종전대로 맨 위에 둔다(위치 변경 없음).
  const [transcriptRefTs, setTranscriptRefTs] = useState<number | null>(null);
  // 이 프로젝트의 ui_state 재수화가 끝났는가 (저장이 복원을 앞질러 덮는 것을 막는 문턱)
  const [uiRestoredFor, setUiRestoredFor] = useState<string | null>(null);

  // [GUARD-LEDGER 2026-08-01] 가드가 막은 사실을 원장에 신고한다. **판정은 건드리지 않는다.**
  //   가드는 이미 정확히 검출하는데 결과가 콘솔에만 남았다 — 콘솔은 devtools 를 연 사람에게만
  //   존재한다. 오늘 전사 84% 소실이 스물두 시간 숨어 있던 것과 같은 구조다.
  //   본선 무접촉: 실패해도 조용히 넘어가되(catch) 그 사실은 콘솔에 남긴다.
  //   서버도 200 + {ok:false} 로 답한다(500 이 가드 흐름 안에서 터지지 않게).
  const reportGuardReject = useCallback((errorCode: string, detail: Record<string, unknown>) => {
    void fetch("/api/failure-ledger", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        domain: "story",
        error_code: errorCode,
        program_id: (detail.program_id as string) ?? null,
        phase: "ui_state_save",
        detail,
      }),
    })
      .then((r) => r.json())
      .then((d) => { if (!d?.ok) console.warn("[GUARD-LEDGER] 신고 실패:", d?.error); })
      .catch((e) => console.warn("[GUARD-LEDGER] 신고 실패:", e));
  }, []);

  // ── [STORY-WRITE-GUARD-01] 스토리 쓰기 가드 ──────────────────────────────
  // 실측된 병소(재현 완료): 핸들러들이 `applyStory(editFragments 파생)`을 불러
  //   스토리(선택 9개)가 **조각 웅덩이 전체(330)** 로 치환됐다. 보류 이동 1회로 9 → 329.
  //   구판은 두 축을 분리해 다뤘다 — 구성본은 next(웅덩이 파생), 선택은 key_fragments.filter().
  //   A-1에서 그 둘을 next 하나로 합치며 웅덩이가 스토리로 승격됐다.
  // 가드 1 (축 분리): fids는 **반드시 명시**한다. 생략 시 구성본에서 파생하던 편의 기능을
  //   없앴다 — 그 편의가 정확히 사고의 통로였다. 호출부는 storyFidsRef에서 파생해야 한다.
  const storyFidsRef = useRef<string[]>([]);
  storyFidsRef.current = storyFids;
  const roughCutSaveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const roughCutExplicitSaveSigRef = useRef<string | null>(null);
  // 가드 2 (출처 표식): 저장은 '사용자 행위'로 만들어진 스토리만. 서버 폴백·씨앗·재수화로
  //   화면에 올라온 목록은 저장 경로에 진입하지 못한다 (2-1/2-2).
  const storyOriginRef = useRef<"none" | "ui_state" | "server" | "user">("none");

  /** 사용자 명시 행위로 스토리를 바꾼다 — 저장 허용 표식을 함께 세운다. */
  const applyStory = useCallback((frags: Fragment[], fids: string[]) => {
    setStoryFragments(frags);
    setStoryFids(fids);
    storyOriginRef.current = "user";
  }, []);
  /** 구성본(좌표·분할)만 갱신 — 선택·순서는 건드리지 않는다 (경계 편집 계열). */
  const applyStoryComposition = useCallback((frags: Fragment[]) => {
    setStoryFragments(frags);
  }, []);
  /** 선택 목록 파생 도우미 — 웅덩이가 아니라 **현재 스토리**에서만 뺀다/넣는다. */
  const storyFidsWithout = useCallback((uid: string) =>
    storyFidsRef.current.filter((id) => id !== uid), []);
  const storyFidsWith = useCallback((uid: string, insertAt?: number) => {
    const cur = storyFidsRef.current.filter((id) => id !== uid);
    const idx = insertAt !== undefined ? Math.min(Math.max(insertAt, 0), cur.length) : cur.length;
    return [...cur.slice(0, idx), uid, ...cur.slice(idx)];
  }, []);

  // [UI-③⑤] 업로드 문진 답변 — storyPlan 생성 시 story_intent/메시지에 주입
  const intakeRef = useRef<{
    videoNotes: Array<{ name: string; note: string; duration?: number; orientation?: string }>;
    aspectPreference: string;
    soundPreference: string;
  } | null>(null);

  // [STEP 10-I.5.27-E7] Timing measurement baseline
  const timingRef = useRef<Record<string, number>>({});
  const isTimingReportedRef = useRef(false);

  const markTiming = useCallback((key: string) => {
    if (!timingRef.current[key]) {
      timingRef.current[key] = performance.now();
    }
  }, []);

  const reportTiming = useCallback((backendTiming?: any) => {
    if (isTimingReportedRef.current) return;
    const t = timingRef.current;
    if (!t.user_selectable) return; // Wait until fully complete

    isTimingReportedRef.current = true;
    const diff = (end?: number, start?: number) => 
      (end && start ? Number(((end - start) / 1000).toFixed(2)) : null);

    const summary = {
      frontend: {
        upload_sec: diff(t.upload_done, t.upload_start),
        analysis_wait_sec: diff(t.analysis_complete, t.generate_fragments_requested),
        proposal_sec: diff(t.proposal_received, t.proposal_requested),
        ui_mapping_sec: diff(t.proposal_mapped_to_ui, t.proposal_received),
        perceived_total_sec: diff(t.user_selectable, t.upload_start),
      },
      backend: backendTiming || null
    };

    console.log("[PERCEIVED_TIMING]", summary);
  }, []);

// centerWidth, isDragging, containerRef moved to useWorkspaceLayout

  const toFullUrl = useCallback((path?: string | null) => {
    if (!path) return null;
    if (path.startsWith("http://") || path.startsWith("https://")) return path;
    // [FIX-THUMB-PREFIX] /api로 시작하는 경로는 이미 prefix 포함
    if (path.startsWith("/api/")) return path;
    return `${videoService.API_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;
  }, []);

  const appendUniqueByUid = useCallback((prev: Fragment[], nextFrag: Fragment) => {
    if (prev.some((f) => getUid(f) === getUid(nextFrag))) return prev;
    return [...prev, nextFrag];
  }, []);

  const removeByUid = useCallback((prev: Fragment[], target: Fragment) => {
    return prev.filter((f) => getUid(f) !== getUid(target));
  }, []);

  const mapFragments = useCallback((frags: any[], label: string) => {
    const mapped: Fragment[] = frags.map((f: any, idx: number) => {
      const fps = 30;
      const startSec = f.start_sec ?? f.start ?? f.start_time ?? f.semantic?.start_sec ?? f.structural?.start_sec ?? 0;
      const endSec = f.end_sec ?? f.end ?? f.end_time ?? f.semantic?.end_sec ?? f.structural?.end_sec ?? 
                     (startSec + (f.duration_sec || f.structural?.duration || f.duration || 5));
      
      const startFrame = Math.round(f.start_frame ?? (startSec * fps));
      const endFrame = Math.round(f.end_frame ?? (endSec * fps));
      const durationFrames = Math.max(1, endFrame - startFrame);
      const rawThumb = f.intelligence?.thumb_url || f.thumb || f.thumbnail_url;
      const fullThumbUrl = toFullUrl(rawThumb) ?? null;
      // [DISPLAY-NAME] 제목부 레지스트리 등록 — 과거 스냅샷 출신 조각의 렌더 시점 자가치유용
      registerSourceTitle(f.source_id || f.sourceId, f.display_name);

      // Populate global cache
      if (typeof window !== "undefined") {
        const cache = (window as any).__ccut_thumbnail_cache || {};
        if (!(window as any).__ccut_thumbnail_cache) {
          (window as any).__ccut_thumbnail_cache = cache;
        }
        if (f.fragment_id && fullThumbUrl) {
          cache[f.fragment_id] = fullThumbUrl;
        }
      }

      return {
        fragment_id: f.fragment_id,
        fragment_uid: f.fragment_id,
        root_fragment_uid: f.root_fragment_uid || f.fragment_id,
        display_id: f.display_id || f.fragment_id,
        // [DISPLAY-NAME] 백엔드 단일 권위가 실어준 주이름을 그대로 통과 (프론트 재조립 금지)
        display_name: f.display_name,
        dialogue: f.dialogue,
        stage_direction: f.stage_direction,
        original_text: f.original_text,
        transcript: f.transcript,
        description: f.description,
        selection_state: "S" as SelectionState,
        status: "committed" as FragmentStatus,
        source_video: label,
        source_id: f.source_id || f.sourceId,
        start_time: startSec,
        end_time: endSec,
        start_frame: startFrame,
        end_frame: endFrame,
        duration: durationFrames,
        thumbnail_hue: idx % 2 === 0 ? 211 : 30,
        thumbnail: {
          thumbnail_url: fullThumbUrl,
        },
        intelligence: {
          // [UNKNOWN-NOFAKE STEP1-0] 증거 없으면 null(UNKNOWN). ||→?? : 실측 0점이 0.5로 위장되던 버그 동반 수리.
          hook_score: f.intelligence?.hook_score ?? f.structural?.market_value ?? null,
          // [UNKNOWN-NOFAKE STEP1-1] 증거 없으면 null(UNKNOWN). "Main" 기본배역 위장 제거.
          role: f.intelligence?.role ?? f.structural?.role ?? null,
          description: f.intelligence?.description || f.intelligence?.visual_description || f.semantic?.summary || "",
        },
        preview_clip_url: f.preview_clip_url ?? null,
        // [PREVIEW-CUT STEP2] 백엔드 산출을 그대로 통과시킨다. mapFragments 는 새 객체를
        //   만들기 때문에 여기 적지 않은 필드는 조용히 사라진다 — STEP1-1 의 evidence 도
        //   응답에는 있었지만 이 지점에서 버려지고 있었다. 프론트는 계산하지 않고 읽기만 한다.
        evidence: f.evidence ?? null,
        evidence_status: f.evidence_status ?? null,
        recommend_tier: f.recommend_tier ?? null,
        recommended: f.recommended ?? null,
        recommend_reason: f.recommend_reason ?? null,
        recommend_status: f.recommend_status ?? null,
      } as any;
    });

    if (mapped.length > 0) {
      // [PERF-LOG 2026-08-01] THUMB_AUDIT_ALL_JSON 철거 — 소스마다 조각 전량을
      //   JSON.stringify(pretty) 해서 콘솔에 쏟았다. 40소스 프로젝트면 수만 줄이고,
      //   직렬화 비용은 devtools 를 닫아도 그대로 든다. 썸네일 감사는 끝났고
      //   지금 필요한 것은 이 값이 아니다 — 죽은 로그라 게이트가 아니라 삭제.
      // pushAnalysisLog 는 남긴다: 제품 화면(AnalysisLoadingView)이 읽는 값이다.
      pushAnalysisLog(`[mapFragments] ${label} (${mapped.length} frags)`);
    }
    return assignShortDisplayIds(recalcDisplayIds(mapped as any)) as any;
  }, [toFullUrl]);

// logProposalPair moved to useProposalState

  // [STORY-LAYER-01 A-1] 제안에서 '스토리 씨앗'(조각 순서열)을 뽑는다. 분석 직후 아직 스토리가
  // 없을 때 단 한 번 쓰인다 — 백엔드 resolve_sequence의 proposals 폴백과 같은 역할이다.
  // 씨앗이 심어진 뒤부터 진실원은 storyFids 하나이며, 제안은 스토리를 다시 건드리지 않는다.
  const proposalSeedFids = useCallback((proposal: any): string[] | undefined => {
    const rawSeq =
      Array.isArray(proposal?.resolved_aliases) && proposal.resolved_aliases.length > 0
        ? proposal.resolved_aliases
        : Array.isArray(proposal?.sequence) && proposal.sequence.length > 0
          ? proposal.sequence
          : null;
    const ids = rawSeq
      ?.map((item: any) => item?.fragment_id || item?.proposal_fragment_id || item?.id)
      .filter(Boolean);
    return ids && ids.length > 0 ? ids : proposal?.key_fragments;
  }, []);

  // [STORY-LAYER-01 A-1] 스냅샷도 program 단위 하나. 스토리(story.fids)와 그 구성본
  // (storyFragments), 보류·휴지통·좌표가 제안축 없이 저장된다. 백엔드 진실원과 같은 키다
  // (story_gate/service.py `read_story_fids`, ledger_r0.py `story.fids`/`storyFragments`).
  // [STORY-ANCHOR 2026-08-01] 원고를 좌표로도 앵커한다.
  //   확정된 사실: 편집 상태(fragment_edit_state)는 source_id + anchor_ms 로 앵커돼 있어
  //   재조각화(분절 경계 변경)에 면역이다 — 23/23 재연결 가능. 반면 원고는 fid 문자열만
  //   저장해 경계가 흔들리면 끊긴다 — 실측 754건 중 507건이 이미 현행 조각에 없다.
  //   fid 는 재발급되지 않는다(sha1(source_id|start_ds|end_ds)[:6], 결정론).
  //   바뀌는 것은 **분절 경계**이고 그래서 해시 입력이 달라진다. 좌표를 함께 저장하면
  //   경계가 흔들려도 다시 이을 수 있다.
  //   재조각화는 특별한 사건이 아니다 — 소스 88개 중 64개(72.7%)가 이미 여러 세대를 겪었고
  //   최대 12세대까지 갔다.
  //   ★ 병기 방식을 택한 이유: fids 배열을 객체 배열로 바꾸면 이 값을 읽는 기존 코드
  //   (ledger_r0._ordered_stringout_fids · 가드 · 서버 _strip_dead_ui_keys)가 전부 깨진다.
  //   fids 는 문자열 배열 그대로 두고 fidAnchors 를 옆에 둔다. 좌표가 없으면 예전과 똑같이 동작한다.
  //   ref 로 잇는 이유: 조각 풀(roughCutFragmentPool)은 이 아래에서 선언된다. deps 로 참조하면
  //   TDZ 로 렌더가 죽는다 — 위치를 옮기는 대신 ref 하나로 읽는다(값은 아래 effect 가 채운다).
  const roughCutFragmentPoolRef = useRef<Fragment[]>([]);
  // [STORY-ANCHOR] 복원된 원고의 좌표(하이드레이션이 채우고 치유 effect 가 읽는다).
  const storyFidAnchorsRef = useRef<Record<string, { source_id: string; anchor_start_ms: number; anchor_end_ms: number }> | null>(null);
  const fidAnchorsOf = useCallback((fids: string[]) => {
    const byId = new Map(roughCutFragmentPoolRef.current.map((f) => [getUid(f), f]));
    const out: Record<string, { source_id: string; anchor_start_ms: number; anchor_end_ms: number }> = {};
    for (const fid of fids) {
      const f: any = byId.get(fid);
      if (!f) continue;                       // 지금 못 찾는 조각의 좌표를 지어내지 않는다
      const sid = String(f.source_id ?? "");
      const s = Number(f.start_time ?? f.start ?? (f.start_frame ?? 0) / 30);
      const e = Number(f.end_time ?? f.end ?? (f.end_frame ?? 0) / 30);
      if (!sid || !Number.isFinite(s) || !Number.isFinite(e) || e <= s) continue;
      out[fid] = { source_id: sid, anchor_start_ms: toMs(s), anchor_end_ms: toMs(e) };
    }
    return out;
  }, []);

  const buildUiSnapshot = useCallback(() => ({
    story: { fids: storyFids, fidAnchors: fidAnchorsOf(storyFids) },
    storyFragments,
    reservedFragments,
    holdPositions,
    committedProposalId,
    selectedProposalId,
    activeSource,
    deletedFragments,
    roughCutPlacement,
    // [TRUTH-SINGLE-01 2번] proposalsIds 사본 폐기 — DB proposals가 진실이다.
    //   읽는 곳 0건(전수 조사)이었고 실측에서 이미 낡아 있었다:
    //   ui_state {A: PROP_A_E737A9…} vs DB {A: PROP_A_79716E…}.
  }), [storyFids, storyFragments, reservedFragments, holdPositions, committedProposalId, selectedProposalId, activeSource, deletedFragments, roughCutPlacement]);

  // [#30 merge-저장 — 원칙 "모르는 것을 지우지 않는다" (국장 승인 2026-07-17)]
  // 클라 소유 필드(아래 목록)는 스냅샷이 덮어쓰고, 그 외(서버 소유·미지 — 예: paperCutOrder)는
  // 저장 직전 서버 원본을 읽어 보존 병합한다. 경계: 클라가 의도적으로 비운 소유 필드를
  // merge가 되살리면 #1(스냅샷 부활)의 재림 — 소유 필드는 절대 병합하지 않는다.
  // [TRUTH-SINGLE-01 1번] 구판의 storyOrder(표시 순서 사본)는 폐기됐다 — 표시 순서는
  // story.fids에서 파생한다(ledger_r0._ordered_stringout_fids). story.fids는 조각맵·전사의
  // 사용자 결정이라 클라 소유. 서버는 저장 시 죽은 사본 키를 걷어낸다(main._strip_dead_ui_keys).
  const OWNED_UI_FIELDS = useMemo(() => new Set([
    "story", "storyFragments",
    "reservedFragments", "holdPositions", "committedProposalId", "selectedProposalId",
    "activeSource", "deletedFragments", "roughCutPlacement",
  ]), []);
  const saveUiStateMerged = useCallback(async (programId: string, snapshot: Record<string, any>) => {
    let unknown: Record<string, any> = {};
    let serverFidCount: number | null = null;
    try {
      const cur = await videoService.getProjectState(programId);
      if (cur?.ui_state) {
        const parsed = JSON.parse(cur.ui_state);
        for (const [k, v] of Object.entries(parsed)) {
          if (!OWNED_UI_FIELDS.has(k)) unknown[k] = v;
        }
        const prevFids = parsed?.story?.fids;
        if (Array.isArray(prevFids)) serverFidCount = prevFids.length;
      }
    } catch (e) {
      // [#43 (1)] 침묵 금지 — 병합 원본을 못 읽으면 미지 필드(예: paperCutOrder)가 이번 저장에서
      // 보존되지 못할 수 있다. 저장 자체는 차단하지 않되, 이유를 콘솔 + 지휘부 채팅에 남긴다 (헌장 §5).
      console.error("[UI_STATE_MERGE][READ_FAIL] 서버 상태를 읽지 못함 — 스냅샷 단독 저장 (미지 필드 미보존 위험)", e);
      setStoryPlan((prev: any) => {
        const text = "저장 중 서버 상태를 읽지 못해 일부 항목이 보존되지 않을 수 있습니다.";
        const msgs = prev?.messages ?? [];
        const last = msgs[msgs.length - 1];
        if (last?.sender === "ai" && last?.text === text) return prev;
        return {
          ...(prev ?? { story_plan_id: `STP_${Date.now()}` }),
          messages: [...msgs, { id: `ai_save_merge_fail_${Date.now()}`, sender: "ai" as const, text, timestamp: Date.now() }],
        };
      });
    }
    // [STORY-WRITE-GUARD-01 2-3] 급증 안전망 — 사용자 행위로 스토리가 3배 늘 일은 없다.
    //   실측된 사고: 보류 이동 1회로 9 → 329(조각 웅덩이 전체)로 치환됐다. 원인은 고쳤지만,
    //   같은 종류의 사고가 다시 나면 **DB에 닿기 전에** 여기서 멈춘다. 조용히 넘기지 않는다.
    const nextFids = Array.isArray(snapshot?.story?.fids) ? snapshot.story.fids : null;
    // [LAYER-FIX 3-A 2026-08-04] 저장된 버전으로 되돌리는 것은 '급증'이 아니다.
    //   5조각 버전에서 25조각 버전으로 옮기면 ratio 5.0x 라 가드가 막았다(실측 REJECT).
    //   ★가드를 없애지도, 임계값을 올리지도 않는다 — 그건 8/1 사고 방지 장치를 무르게 한다.
    //   대신 입력에 맥락을 준다: 방금 복원한 버전의 fids 와 ★정확히 일치할 때만 통과.
    //   길이만 보는 게 아니라 원소·순서까지 같아야 하므로, 버전 복원을 가장한 급증은 못 지나간다.
    const restoring = versionRestoreFidsRef.current;
    const isVersionRestore = !!(nextFids && restoring
      && restoring.length === nextFids.length
      && restoring.every((f, i) => f === nextFids[i]));
    if (isVersionRestore && nextFids && serverFidCount !== null
        && nextFids.length > serverFidCount * 3) {
      console.info(
        `[STORY-WRITE-GUARD][ALLOW] 저장된 버전 복원 — 급증 아님. `
        + `before=${serverFidCount} after=${nextFids.length} version=${activeVersionIdRef.current}`,
      );
    }
    if (!isVersionRestore
        && nextFids && serverFidCount !== null && serverFidCount > 0
        && nextFids.length > serverFidCount * 3) {
      console.error(
        `[STORY-WRITE-GUARD][REJECT] story.fids 급증 — 저장 거부. `
        + `program=${programId} before=${serverFidCount} after=${nextFids.length} `
        + `ratio=${(nextFids.length / serverFidCount).toFixed(1)}x origin=${storyOriginRef.current} `
        + `first3=[${nextFids.slice(0, 3).join(", ")}]`,
      );
      reportGuardReject("story_fids_surge", {
        program_id: programId,
        before: serverFidCount,
        after: nextFids.length,
        ratio: Number((nextFids.length / serverFidCount).toFixed(2)),
        origin: storyOriginRef.current,
        first3: nextFids.slice(0, 3),
      });
      return { status: "REJECTED_STORY_SPIKE" } as any;
    }
    // [FOREIGN-STORY-GUARD] 남의 원고 저장 차단 — 급증 안전망과 같은 자리, 조건만 하나 더.
    //   실측된 사고(2026-07-30): 신규 프로젝트 Marigold 가 직전 프로젝트의 원고 13조각을
    //   그대로 물려받아 저장했다. 그 13개는 이 프로젝트 소스(SRC_3111FA4F)와 교집합 0이라
    //   조각맵이 통째로 비었다(135개를 로드하고도 렌더 대상이 0).
    //   판정은 '전량 외래'일 때만 한다 — 분할(_cN)·재조각화로 일부 fid가 어긋나는 것은
    //   정상 상황이라 한 건이라도 걸치면 통과시킨다(정상 저장 회귀 방지).
    //   조각이 아직 안 실린 시점(editFragments 0)은 판정하지 않는다 — 모르는 것을 막지 않는다.
    if (nextFids && nextFids.length > 0 && editFragments.length > 0) {
      const known = new Set<string>();
      for (const fragment of editFragments) {
        for (const alias of collectFragmentAliases(fragment as any)) known.add(alias);
      }
      if (!nextFids.some((id: string) => known.has(id))) {
        // [GUARD-NAMING 2026-08-01] '외래'와 '세대 불일치'를 가른다.
        //   실측: REJECT 159 fids 중 자기 소스가 146(91.8%)이었다 — 대부분 남의 원고가 아니라
        //   자기 소스인데 분절 경계가 달라져 fid 가 어긋난 것이다. 한 이름으로 뭉쳐 두면
        //   원장이 사실과 다르게 말한다(오늘 하루 반복해서 잡은 그 모양).
        //   판정 기준은 fid 에 박힌 소스 토큰 — 이 프로젝트가 가진 소스인가.
        //   ★ 거부 여부는 바꾸지 않는다. 둘 다 그대로 거부한다(가드 판정 무접촉).
        //     이름과 error_code 만 사실에 맞춘다.
        const projectSources = new Set(
          editFragments.map((f: any) => String(f.source_id ?? "")).filter(Boolean),
        );
        const srcOf = (id: string) => {
          const m = /(SRC_[0-9A-Za-z]+)/.exec(id);
          return m ? m[1] : "";
        };
        const ownSource = nextFids.filter((id: string) => projectSources.has(srcOf(id))).length;
        const generationMismatch = ownSource === nextFids.length && projectSources.size > 0;
        const code = generationMismatch ? "story_fids_generation_mismatch" : "foreign_story_fids";
        console.error(
          `[STORY-WRITE-GUARD][REJECT] ${generationMismatch ? "세대 불일치(자기 소스인데 경계가 달라짐)" : "외래 원고(남의 소스)"} — 저장 거부. `
          + `program=${programId} fids=${nextFids.length} 이 프로젝트 조각=${editFragments.length} `
          + `교집합=0 자기소스 ${ownSource}/${nextFids.length} origin=${storyOriginRef.current} `
          + `first3=[${nextFids.slice(0, 3).join(", ")}]`,
        );
        reportGuardReject(code, {
          program_id: programId,
          fids: nextFids.length,
          own_source_fids: ownSource,
          project_fragments: editFragments.length,
          intersection: 0,
          origin: storyOriginRef.current,
          first3: nextFids.slice(0, 3),
        });
        return { status: "REJECTED_FOREIGN_STORY" } as any;
      }
    }
    return videoService.saveProjectState(programId, { ui_state: JSON.stringify({ ...unknown, ...snapshot }) });
  }, [OWNED_UI_FIELDS, setStoryPlan, editFragments, reportGuardReject]);

  const saveUiStateMergedTracked = useCallback((programId: string, snapshot: Record<string, any>) => {
    const p = saveUiStateMerged(programId, snapshot);
    uiStateSaveRef.current = p;
    p.finally(() => {
      if (uiStateSaveRef.current === p) uiStateSaveRef.current = null;
    });
    return p;
  }, [saveUiStateMerged]);

  // [SAVE-SPINE 2-C 2026-08-04] 이 자리는 이제 '저장'이다.
  //   주인은 프로젝트가 아니라 사용자가 저장한 버전이다(국장 확정 ③).
  //   승인 행은 저장의 부산물로 서버가 함께 적는다 — P4 배관(main.py:3122-3132)은 무접촉.
  //   ★버튼 위치·레이아웃은 그대로. 이름과 하는 일만 바뀐다.
  // [LAYER-SPLIT 2026-08-04 ②] 저장된 버전 목록을 다시 읽는다. 저장 직후·프로젝트 전환 시.
  const refreshVersions = useCallback(async (programId?: string | null) => {
    const pid = programId ?? activeNavItem;
    if (!pid?.startsWith("proj_")) { setSavedVersions([]); return; }
    try {
      const res = await videoService.listStoryVersions(pid);
      setSavedVersions(res?.versions ?? []);
    } catch (e) {
      console.warn("[LAYER-SPLIT] 버전 목록을 읽지 못했습니다", e);
      setSavedVersions([]);          // 못 읽은 것을 '없다'로 위장하지 않는다 — 위 경고가 이유를 남긴다
    }
  }, [activeNavItem]);

  useEffect(() => { void refreshVersions(); }, [refreshVersions]);

  // [LAYER-SPLIT 2026-08-04 ③] 버전 아이콘 클릭 -> 조각맵·전사 선택상태를 그 버전의 것으로.
  //   ★버전 클릭은 사용자 명시 행위다 — origin='user' 를 세워야 이 상태가 저장 경로에 진입한다.
  //   ★단방향: 여기서 조각맵을 바꾸고 끝. 조각맵이 다시 전사를 갱신하지 않는다(설계 ⑦ 순환 금지).
  const handleVersionPick = useCallback(async (versionId: number) => {
    try {
      const res = await fetch(`/api/story-version/detail/${versionId}`);
      const d = await res.json();
      if (!res.ok || !d?.ok) {
        toast.error("그 버전을 불러오지 못했습니다.");
        return;
      }
      storyOriginRef.current = "user";
      versionRestoreFidsRef.current = d.fids ?? [];   // [LAYER-FIX 3-A] 가드에 줄 맥락
      setStoryFids(d.fids ?? []);
      setRoughCutPlacement((prev) => ({
        inputHash: d.rough_cut_input_hash ?? prev?.inputHash ?? null,
        selectedSpanIds: d.selected_span_ids ?? [],
      }));
      setActiveVersionId(versionId);
      setPrecisionPaneMode("story");
      lastSavedVersionIdRef.current = versionId;
      appendStoryGateMessage("ai_story_returned", STORY_GATE_COPY.chat.storyReturned);
      console.info(`[LAYER-SPLIT] 버전 ${versionId} 적용 — 조각 ${(d.fids || []).length}개 `
        + `· 전사선택 ${(d.selected_span_ids || []).length}개`);
    } catch (e) {
      console.error("[LAYER-SPLIT] 버전 적용 실패", e);
      toast.error("그 버전을 불러오지 못했습니다.");
    }
  }, []);

  const handleSaveVersion = useCallback(async (options?: { askName?: boolean }) => {
    setCompositionNotice(null);
    const programId = activeNavItem;
    if (!programId?.startsWith("proj_")) return;

    // ★저장은 '사용자 명시 행위'다 — 화면의 원고를 서버 원고로 승격시킨다(국장 확정 ③).
    //   이 줄이 없으면 STORY-WRITE-GUARD(:819)가 origin=server 라며 ui_state 쓰기를 막고,
    //   서버는 여전히 폴백(조각 전량)을 원고로 본다. 실측: 화면 15조각을 저장했는데
    //   서버 원고는 135라 story_mismatch 로 편집안이 안 만들어졌다.
    //   저장 버튼을 누른 것 자체가 "이걸로 하겠다"는 사용자 결정이므로 표식을 세우는 게 맞다.
    storyOriginRef.current = "user";
    await saveUiStateMergedTracked(programId, buildUiSnapshot()).catch(() => {});

    // 저장 전에 ui_state 쓰기를 끝낸다. 서버는 '지금 서버가 보는 원고'와 대조하므로
    // 이게 안 끝나면 방금 고친 것이 아직 서버에 없어 문이 안 열린다.
    const pending = uiStateSaveRef.current;
    if (pending) await pending.catch(() => {});

    let name = `버전 ${new Date().toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}`;
    if (options?.askName) {
      const typed = window.prompt(STORY_GATE_COPY.actions.saveStoryPrompt, name);
      if (typed === null) return;              // 취소 — 아무것도 안 한다
      if (typed.trim()) name = typed.trim();
    }

    const result = await videoService.saveStoryVersion(programId, {
      name,
      fids: storyFids,
      selected_span_ids: roughCutPlacement?.selectedSpanIds ?? [],
      rough_cut_input_hash: roughCutPlacement?.inputHash ?? roughCutData?.input_hash ?? null,
      parent_version_id: lastSavedVersionIdRef.current,
    });

    if (!result.ok) {
      // 반쪽 저장은 없다 — 실패하면 아무것도 안 남았다는 뜻이다. 그대로 말한다.
      const msg = result.body?.message || "저장하지 못했습니다.";
      console.error("[SAVE-SPINE] 저장 실패", result.status, result.body);
      setCompositionNotice(msg);
      toast.error("저장하지 못했습니다.", { description: msg });
      return;
    }

    lastSavedVersionIdRef.current = result.body?.version_id ?? null;
    setActiveVersionId(result.body?.version_id ?? null);
    void refreshVersions(programId);
    console.info(`[SAVE-SPINE] 저장됨 version_id=${result.body?.version_id} `
      + `items=${result.body?.item_count} gate_opened=${result.body?.gate_opened}`);
    toast.success(`${STORY_GATE_COPY.toast.storySaved} — ${name}`, {
      description: `조각 ${result.body?.item_count ?? storyFids.length}개`,
    });
    appendStoryGateMessage(
      `ai_story_saved_${result.body?.version_id ?? Date.now()}`,
      STORY_GATE_COPY.chat.storySaved,
      { kind: "story_saved_prompt" },
    );

    recordMirrorEvent({
      event_kind: "accept",
      project_id: programId,
      approval_id: result.body?.approval_id,
      sequence_hash: result.body?.sequence_hash,
      item_count: result.body?.item_count,
    });
    await storyGate.reload();

    if (result.body?.gate_opened) {
      console.info("[EDIT-FLOW][AB-GENERATE][WAIT] 저장 완료 — 편집 시작 뒤 A/B 생성");
    } else {
      // 저장은 됐는데 문이 안 열렸다 — 왜인지 숨기지 않는다.
      console.warn(`[SAVE-SPINE] 편집안 생성 보류: ${result.body?.gate_reason}`);
      if (result.body?.gate_reason === "story_mismatch") {
        setCompositionNotice(
          `저장은 됐습니다(${result.body?.saved_item_count}조각). `
          + `다만 서버가 보는 원고는 ${result.body?.server_item_count}조각이라 편집안은 잠시 뒤에 만듭니다.`,
        );
      }
    }
  }, [activeNavItem, storyFids, roughCutPlacement, roughCutData?.input_hash, storyGate,
      saveUiStateMergedTracked, buildUiSnapshot]);


  const handleHoldPositionsCommit = useCallback((positions: Record<string, { x: number; y: number }>) => {
    setHoldPositions(positions);
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return;
    // 방금 확정한 좌표가 스냅샷의 (아직 갱신 전) 상태를 이기게 한다 — 프로젝트 스코프 하나.
    saveUiStateMergedTracked(activeNavItem, { ...buildUiSnapshot(), holdPositions: positions });
  }, [activeNavItem, buildUiSnapshot, saveUiStateMergedTracked, setHoldPositions]);

  // [#8-a STORY-GATE-SYNC 2026-07-19 · STORY-LAYER-01 A-1] 스토리가 바뀌면 ui_state를 즉시
  // 저장한다 — 기존엔 내보내기 완료 시점에만 저장돼 story-gate가 구 승인을 계속 유효로 보는
  // 구멍이 있었다(승인 없이 EDIT 진입). 트리거는 제안 채택이 아니라 **스토리 지문**이다:
  // 스토리가 program 단위 하나가 되면서 "어느 안을 골랐나"는 스토리 변경이 아니게 됐다.
  const storySnapshotSigRef = useRef<string | null>(null);
  useEffect(() => {
    if (storyFids.length === 0) return;   // 아직 씨앗 전 — 빈 스토리를 저장해 덮지 않는다
    // [저장 무결성] 재수화가 끝난 뒤에만 저장한다. 씨앗은 proposals 도착 직후 심어지는데
    // ui_state 복원은 그보다 늦게 끝나므로, 여기서 기다리지 않으면 아직 복원 전인
    // committedProposalId/activeSource를 null로 덮어써 사용자의 선택이 조용히 사라진다(실측).
    if (uiRestoredFor !== activeNavItem) return;
    // [STORY-WRITE-GUARD-01 2-2] 출처 가드 — 사용자 행위('user')이거나 이미 ui_state에
    // 있던 스토리('ui_state')만 저장한다. 서버 폴백/제안 파생('server')은 진입 금지.
    if (storyOriginRef.current !== "user" && storyOriginRef.current !== "ui_state") {
      console.info(`[STORY-WRITE-GUARD][SKIP] 저장 안 함 — origin=${storyOriginRef.current} (사용자 행위 아님)`);
      return;
    }
    // 지문에 표시 방식(committed/selected)도 넣는다. 스토리를 가르지는 않지만 '사용자가 고른
    // 편집안'이라 새로고침 후에도 남아야 한다 — 스토리만 보면 A/B 확정이 저장되지 않는다(실측).
    const sig = JSON.stringify([storyFids, committedProposalId, selectedProposalId, roughCutPlacement]);
    if (storySnapshotSigRef.current === sig) return;
    storySnapshotSigRef.current = sig;
    const roughCutSig = JSON.stringify([
      storyFids,
      roughCutPlacement?.selectedSpanIds ?? [],
    ]);
    if (roughCutExplicitSaveSigRef.current === roughCutSig) return;
    if (activeNavItem && activeNavItem.startsWith("proj_")) {
      saveUiStateMergedTracked(activeNavItem, buildUiSnapshot()).catch(() => {});
    }
  }, [storyFids, committedProposalId, selectedProposalId, roughCutPlacement, activeNavItem, uiRestoredFor, saveUiStateMergedTracked, buildUiSnapshot]);
  // 프로젝트가 바뀌면 지문 기준을 새로 잡는다 (다음 프로젝트의 첫 스토리가 저장되도록)
  // [FOREIGN-STORY-GUARD 2] 원고 상태도 함께 내린다 — 잔류가 새 프로젝트의 원고로 저장되던 뿌리.
  //   resetAnalysisFlow(useAnalysisFlow.ts:48)는 13개 state를 지우지만 story 계열은 목록에 없어,
  //   +버튼·삭제·전환 어느 경로로 와도 이전 프로젝트의 원고가 화면과 스냅샷에 그대로 남았다.
  //   출처(origin)도 함께 내린다 — 이전 프로젝트에서 얻은 'ui_state' 자격이 승계되면
  //   저장 가드(2-2)가 남의 원고를 사용자 결정으로 오인한다.
  //   지우기만 한다. 새 값은 서버 복원(ui_state → proposals → 조각)이 넣는다.
  useEffect(() => {
    storySnapshotSigRef.current = null;
    storyOriginRef.current = "none";
    // [STORY-RELOAD-FIX] ref 도 같은 자리에서 즉시 비운다.
    //   storyFidsRef 는 렌더 중에 state 를 미러링하는데(:349), setStoryFids([]) 는
    //   다음 렌더에야 반영된다. 같은 커밋에서 뒤이어 도는 서버 원고 적재 effect(:2400)가
    //   `storyFidsRef.current.length > 0` 가드에 걸려 재적재를 건너뛰었다.
    //   그 뒤로는 deps(activeNavItem·uiRestoredFor)가 다시 안 바뀌어 영영 안 돌아온다 —
    //   실측: 조각이 다 떴다가 사라진 뒤 복구되지 않던 증상(2026-07-31 Buttercup).
    storyFidsRef.current = [];
    setStoryFids([]);
    setStoryFragments([]);
    setRoughCutData(null);
    setRoughCutPlacement(null);
    setHoldPositions({});
    setPrecisionPaneMode("story");
  }, [activeNavItem]);

  const {
    resetAnalysisState,
    onHome,
    onItemClick: onNavItemClick,
    onToggleCollapse: onNavToggleCollapse,
    onRenameProject: onNavRenameProject,
    onDeleteProject: onNavDeleteProject,
    onNewProject: onNavNewProject,
  } = useAppNavigation({
    setSelectedProposalId, setCommittedProposalId, setProposals, setDirectionSnapshot,
    setStoryPlan,
    resetAnalysisFlow, setActiveNavItem, setNavCollapsed, setProjects,
    activeNavItem, appState, buildUiSnapshot,
    saveUiState: saveUiStateMergedTracked, // [#30] merge-저장 주입
  });

  // [B-5-FIX] 저장된 백엔드 proposals → UI proposals 형태 매핑 (복원용, 업로드 매핑과 동일 형태)
  const mapBackendProposals = useCallback((proposals: any[]) => {
    const out: Record<"A" | "B", any> = {} as any;
    (proposals || []).forEach((p: any) => {
      const mode = p.mode === "A" ? "A" : "B";
      const copy = STORY_GATE_COPY.abCards.variants[mode];
      out[mode] = {
        id: mode,
        proposal_id: p.proposal_id,
        mode: p.mode === "A" ? "market" : "user",
        title: copy.title,
        desc: copy.desc,
        score: String(Math.round((p.confidence ?? 0) * 100)) + "%",
        key_fragments: (p.sequence || []).map((s: any) => s.fragment_id),
        proposal_story: p.proposal_story,
        proposal_explanation: p.proposal_explanation,
        direction: {},
        snapshot_id: "R1",
        template_id: p.mode,
        slot_trace: [],
        preview_url: p.preview_url ?? null,
        preview_duration: p.preview_duration ?? 0,
      };
      if (out[mode].key_fragments.length > 0) {
        out[mode].resolved_aliases = (p.sequence || []).map((s: any) => ({
          proposal_fragment_id: s.fragment_id,
          source_id: s.source_id,
          source_fragment_id: s.fragment_id,
          display_id: s.display_id,
          start_sec: s.start,
          end_sec: s.end,
          thumbnail_url: s.thumbnail_url
        }));
      }
    });
    return out;
  }, []);

  // [GATE-LOOP-01 2-1] 승인된 스토리로 A/B를 만든다. 승인 직후 handleApproveComposition이 부른다.
  // 이 시점에만 백엔드 생성 게이트가 열린다(그 전엔 STORY_NOT_APPROVED로 거절).
  const requestProposalsForApprovedStory = useCallback(async () => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return false;
    const sourceIds = (sourceEntries ?? []).map((e) => e.source_id).filter(Boolean);
    if (sourceIds.length === 0) return false;
    const storySig = storyFids.map(String).filter(Boolean).join("|");
    if (storySig && proposalPairMatchesFlowStory(proposals, storyFids)) {
      console.info("[EDIT-FLOW][AB-GENERATE][SKIP] 현재 원고 A/B가 이미 준비됨", {
        story_count: storyFids.length,
      });
      return true;
    }
    if (storySig && editFlowProposalSigRef.current === storySig) {
      console.info("[EDIT-FLOW][AB-GENERATE][SKIP] 같은 원고 생성은 한 번만", {
        story_count: storyFids.length,
      });
      return true;
    }
    try {
      console.info("[EDIT-FLOW][AB-GENERATE][START]", {
        program_id: activeNavItem,
        story_count: storyFids.length,
      });
      const res: any = await videoService.requestProjectProposals(activeNavItem, sourceIds, 60.0);
      if (res?.status === "STORY_NOT_APPROVED") {
        console.warn("[PROPOSAL] 승인 직후인데 게이트가 아직 승인 전으로 봄 — 다음 승인에서 재시도", res);
        return false;
      }
      if (Array.isArray(res?.proposals) && res.proposals.length > 0) {
        setProposals(mapBackendProposals(res.proposals));
        editFlowProposalSigRef.current = storySig || null;
        console.info(`[PROPOSAL] 편집 시작 후 A/B 생성 완료 — ${res.proposals.length}건`);
        return true;
      } else {
        console.warn("[PROPOSAL] 승인 후 생성이 제안을 반환하지 않음", res?.status);
        return false;
      }
    } catch (e) {
      console.error("[PROPOSAL] 승인 후 A/B 생성 실패 — 승인은 유효합니다", e);
      return false;
    }
  }, [activeNavItem, sourceEntries, storyFids, proposals, mapBackendProposals, setProposals]);
  requestProposalsForApprovedStoryRef.current = requestProposalsForApprovedStory;

  // [STEP 10-I.5.27-E7-M2] Debug Log Guard
  const DEBUG_FRAGMENT_MAP = useMemo(() => 
    import.meta.env.DEV && localStorage.getItem("CCUT_DEBUG_FRAGMENT_MAP") === "1"
  , []);

  const debugFragmentMap = useCallback((...args: unknown[]) => {
    if (!DEBUG_FRAGMENT_MAP) return;
    console.log(...args);
  }, [DEBUG_FRAGMENT_MAP]);

  const handleStartAnalysis = useCallback(
    async (file?: File, extraFiles?: File[]) => {
      resetAnalysisState();
      timingRef.current = {}; // Reset timings
      isTimingReportedRef.current = false;
      markTiming("upload_start");

      setAppState("analyzing");
      setAnalyzeProgress(10);
      setAnalyzeMessage("영상을 업로드하는 중입니다...");

      try {
        const allFiles = [file, ...(extraFiles ?? [])].filter(Boolean) as File[];
        if (allFiles.length === 0) {
          throw new Error("선택된 파일이 없습니다.");
        }

        // [UI-②] 열려 있는 프로젝트에 기존 소스가 있으면 '추가' 모드 — 라벨 이어붙임, 기존 보존
        const priorEntries: SourceEntry[] =
          activeNavItem && activeNavItem.startsWith("proj_") ? [...sourceEntries] : [];
        const labelOffset = priorEntries.length;
        if (labelOffset > 0) console.log(`[UI-②] append mode: 기존 ${labelOffset}개 + 신규 ${allFiles.length}개`);

        // [UI-⑨] 엑셀식 라벨: A..Z, AA, AB... (26 초과 시 기호로 새던 문제 수리)
        const labelFromIndex = (idx: number) => {
          let n = idx, s = "";
          do { s = String.fromCharCode(65 + (n % 26)) + s; n = Math.floor(n / 26) - 1; } while (n >= 0);
          return s;
        };

        const collectedEntries: SourceEntry[] = [];
        let firstSourceId: string | null = null;

        for (let i = 0; i < allFiles.length; i++) {
          const label = labelFromIndex(i + labelOffset);
          setAnalyzeMessage(
            allFiles.length === 1
              ? "영상 파일을 서버에 전송하는 중입니다..."
              : `영상 ${label} 업로드 중... (${i + 1}/${allFiles.length})`
          );

          const uploadData = await videoService.uploadVideo(allFiles[i]);
          const sid = uploadData.source_id;
          const vurl = toFullUrl(uploadData.static_url) ?? "";

          if (i === 0) {
            firstSourceId = sid;
            setCurrentSourceId(sid);
            setCurrentVideoUrl(vurl);
          }

          console.log(`[UPLOAD] ${label}: source_id=${sid}`);
          pushAnalysisLog(`[UPLOAD] ${label}: source_id=${sid}`);

          markTiming("generate_fragments_requested");
          const data = await videoService.generateFragments(sid);
          const initialFrags = mapFragments(data.fragments || [], label);

          collectedEntries.push({
            source_id: sid,
            label,
            title: allFiles[i].name,
            video_url: vurl,
            fragments: initialFrags,
            file_size_bytes: allFiles[i].size,
            duration_sec: initialFrags.length > 0 ? initialFrags[initialFrags.length - 1].end_frame / 30 : 0
          });

          console.log(`[N-01] ${label}: ${initialFrags.length}개 초벌 조각 완료`);
        }
        markTiming("upload_done");

        // [서사층 §2.1] 말의 원장 — 문진에서 들려준 말을 소스 원장에 영구 귀속
        // (대화에만 표류하지 않게. 실패해도 업로드 흐름은 계속 — 노트는 재전송 멱등)
        if (intakeRef.current?.videoNotes?.length) {
          const byName = new Map(collectedEntries.map((e) => [e.title, e.source_id]));
          const notes = intakeRef.current.videoNotes
            .filter((v) => v.note && byName.get(v.name))
            .map((v) => ({ target_kind: "source", target_id: byName.get(v.name)!, text: v.note, origin: "intake" }));
          if (notes.length) {
            videoService.addNarrativeNotes(notes)
              .then((r) => console.log(`[NARRATIVE] 문진 노트 원장 귀속: +${r?.added}`))
              .catch((e) => console.warn("[NARRATIVE] 노트 귀속 실패 (비차단):", e));
          }
        }

        const today = new Date();
        const dateStrYYMMDD = `${today.getFullYear().toString().slice(2)}${String(today.getMonth() + 1).padStart(2, "0")}${String(today.getDate()).padStart(2, "0")}`;
        const fileCount = allFiles.length;
        const dateStr = String(today.getMonth() + 1) + "/" + String(today.getDate()) + " " + String(today.getHours()).padStart(2, "0") + ":" + String(today.getMinutes()).padStart(2, "0");
        const uploadedSourceIds = collectedEntries.map(e => e.source_id).filter(Boolean);
        console.log("[N-01] 분석 대상 source_ids:", uploadedSourceIds);
        pushAnalysisLog(`[N-01] 분석 대상 source_ids: ${String(uploadedSourceIds)}`.slice(0, 120));

        // [B-5d] 기존 프로젝트(proj_ prefix)면 귀속. 아니면(새 프로젝트 또는 레거시) 지금 DB 생성.
        let projectId: string;
        if (activeNavItem && activeNavItem.startsWith("proj_")) {
          projectId = activeNavItem;
          setProjects((prev) => prev.map((p) => (p.id === projectId ? { ...p, count: labelOffset + fileCount } : p)));
          // [UI-②] 기존 프로젝트에 신규 소스 연결 (project_sources) — 복원 시 유실 방지
          try {
            await fetch(`${videoService.API_BASE_URL}/projects/${projectId}/sources`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ source_ids: uploadedSourceIds }),
            });
          } catch (e) {
            console.warn("[UI-②] project_sources link failed:", e);
          }
        } else {
          const newRes = await fetch(`${videoService.API_BASE_URL}/projects`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name: null, source_ids: uploadedSourceIds }),
          }).then((res) => {
            if (!res.ok) throw new Error(`프로젝트 생성 실패: ${res.status}`);
            return res.json();
          });
          projectId = newRes.program_id;
          // [FIX-HYD-EMPTY] 업로드-생성 프로젝트 표식 → hydration fetch-전 클리어 스킵(분석 세션 보존)
          justCreatedProjectRef.current = projectId;
          setActiveNavItem(projectId);
          setProjects((prev) => [{ id: projectId, name: newRes.name, date: dateStr, count: fileCount }, ...prev]);
        }


        setSourceEntries([...priorEntries, ...collectedEntries]);
        setActiveSource(priorEntries.length > 0 ? collectedEntries[0]?.label ?? "A" : "A");

        const firstEntry = collectedEntries[0];
        if (!firstEntry) throw new Error("첫 번째 원본 처리 실패");

        setEditFragments(firstEntry.fragments);
        setSourceFragments(firstEntry.fragments);
        setAnalyzeProgress(80);
        setAnalyzeMessage("의미분석(Whisper) 진행 중입니다...");
        setAppState("analyzing");

        let pollCount = 0;
        const MAX_POLLS = 100;
        const sourceStatusMap: Record<string, string> = {};
        const completedSourceIds: string[] = [];
        const failedSourceIds: string[] = [];

        const pollInterval = setInterval(async () => {
          try {
            pollCount++;
            
            // 모든 업로드 소스에 대해 상태 체크
            for (const sid of uploadedSourceIds) {
              if (completedSourceIds.includes(sid) || failedSourceIds.includes(sid)) continue;
              
              const statusData = await videoService.getFragmentStatus(sid);
              // [PROGRESS-VOICE 2] 백엔드가 이미 주는 stage·progress 를 화면에 흘린다
              //   (새 계측 없음 — /generate-fragments/status 응답 그대로).
              //   구판은 status 만 보고 나머지를 버려서, 사용자는 도는지 멈췄는지 알 수 없었다.
              //   폴마다 찍으면 로그가 넘치므로 값이 바뀔 때만 남긴다.
              const _mark = `${statusData.status}/${statusData.stage ?? "-"}/${statusData.progress ?? "-"}`;
              if (sourceStatusMap[sid] !== _mark) {
                const _label = collectedEntries.find((e) => e.source_id === sid)?.label ?? sid;
                pushAnalysisLog(
                  `[분석] ${_label} ${statusData.stage ?? statusData.status}`
                  + (statusData.progress != null ? ` ${statusData.progress}%` : "")
                );
              }
              sourceStatusMap[sid] = _mark;

              if (statusData.status === "ANALYSIS_COMPLETE") {
                completedSourceIds.push(sid);
                console.log(`[analysis-status] ${sid}: ANALYSIS_COMPLETE`);
              } else if (statusData.status === "FAILED") {
                failedSourceIds.push(sid);
                console.error(`[analysis-status] ${sid}: FAILED - ${statusData.error}`);
              }
            }

            // [PBE-PROGRESS] 분석 진행 상황 실시간 표시(멈춘 것처럼 보이지 않게)
            const _settledCount = completedSourceIds.length + failedSourceIds.length;
            if (_settledCount < uploadedSourceIds.length) {
              setAnalyzeMessage(`영상 의미 분석 중... (${_settledCount}/${uploadedSourceIds.length} 완료)`);
            }
            const allSettled = (completedSourceIds.length + failedSourceIds.length) === uploadedSourceIds.length;
            const isTimeout = pollCount >= MAX_POLLS;

            if (allSettled || isTimeout) {
              clearInterval(pollInterval);
              markTiming("analysis_complete");
              
              if (completedSourceIds.length === 0) {
                setAnalyzeMessage("모든 영상 분석 실패 또는 시간 초과");
                setAppState("complete");
                return;
              }

              setAnalyzeMessage("의미 조각 수집 및 제안 생성 중...");
              
              // 1. 모든 완료된 소스에서 Semantic Fragments 수집
              const semanticResults: Record<string, any[]> = {};
              const sourceLabels = collectedEntries.reduce((acc, e) => ({ ...acc, [e.source_id]: e.label }), {} as Record<string, string>);

              let _semIdx = 0;
              for (const sid of completedSourceIds) {
                _semIdx++;
                setAnalyzeMessage(`의미 조각 수집 중... (${_semIdx}/${completedSourceIds.length})`);
                try {
                  const semanticRes = await fetch(`${videoService.API_BASE_URL}/semantic-fragments/${sid}`, { method: "POST" });
                  if (semanticRes.ok) {
                    const semanticData = await semanticRes.json();
                    semanticResults[sid] = semanticData.fragments || [];
                  }
                } catch (err) {
                  console.error(`[semantic-source] ${sid} fetch error:`, err);
                }
              }
              markTiming("semantic_loaded");

              // 2. 소스 엔트리 업데이트 (Semantic으로 교체)
              let finalEditFragments: Fragment[] = [];
              const updatedEntries = collectedEntries.map(entry => {
                const sid = entry.source_id;
                const rows = semanticResults[sid] || [];
                
                if (rows.length > 0) {
                  // [STEP 10-K-C1-R29] 초벌 조각 메타데이터 보존을 위한 매핑
                  const baseById = new Map(entry.fragments.map((f: any) => [f.fragment_id, f]));

                  const toFrameFromUnknown = (value: any, fps = 30): number | null => {
                    if (value === undefined || value === null) return null;
                    const n = Number(value);
                    if (!Number.isFinite(n)) return null;
                    return Math.round(n);
                  };

                  const resolveSfFrameRange = (sf: any, fps = 30) => {
                    const directStartFrame = toFrameFromUnknown(sf.start_frame, fps);
                    const directEndFrame = toFrameFromUnknown(sf.end_frame, fps);
                    if (directStartFrame !== null && directEndFrame !== null) {
                      return { startFrame: directStartFrame, endFrame: directEndFrame, unitSource: "start_frame/end_frame" };
                    }
                    const startSec = Number(sf.start_time ?? sf.start ?? 0);
                    const endSec = Number(sf.end_time ?? sf.end ?? 0);
                    return { startFrame: Math.round(startSec * fps), endFrame: Math.round(endSec * fps), unitSource: "seconds_to_frames" };
                  };

                  const findParentVFByTimeOverlap = (sf: any, baseFragments: any[], fps = 30) => {
                    const { startFrame, endFrame, unitSource } = resolveSfFrameRange(sf, fps);
                    const sfSourceId = sf.source_id ?? sf.sourceId;
                    const candidates = baseFragments.filter((vf) => {
                      const vfSourceId = vf.source_id ?? vf.sourceId;
                      const sameSource = vfSourceId === sfSourceId || vf.fragment_id?.includes(sfSourceId);
                      const vfStart = Number(vf.start_frame ?? 0);
                      const vfEnd = Number(vf.end_frame ?? 0);
                      return sameSource && startFrame >= vfStart && startFrame < vfEnd;
                    });
                    return { parentVF: candidates[0] ?? null, startFrame, endFrame, unitSource };
                  };

                  console.log(
                    `[R41_SF_LINEAGE_AUDIT] ${entry.label}\n` +
                    JSON.stringify(
                      rows.map((row: any) => {
                        const { parentVF, startFrame, endFrame, unitSource } = findParentVFByTimeOverlap(row, entry.fragments);
                        return {
                          semantic_fragment_id: row.fragment_id,
                          semantic_source_id: row.source_id,
                          resolved_start_frame: startFrame,
                          resolved_end_frame: endFrame,
                          unit_source: unitSource,
                          parent_vf_found: !!parentVF,
                          parent_vf_id: parentVF?.fragment_id,
                          parent_vf_range: parentVF ? [parentVF.start_frame, parentVF.end_frame] : null,
                          raw_fields: {
                            start: row.start,
                            end: row.end,
                            start_time: row.start_time,
                            end_time: row.end_time,
                            start_frame: row.start_frame,
                            end_frame: row.end_frame,
                          }
                        };
                      }),
                      null,
                      2
                    )
                  );

                  const enrichedRows = rows.map((row: any) => {
                    const { parentVF, startFrame, endFrame, unitSource } = findParentVFByTimeOverlap(row, entry.fragments);
                    
                    if (!parentVF) return {
                      ...row,
                      start_frame: startFrame,
                      end_frame: endFrame,
                      start_time: row.start_time ?? row.start,
                      end_time:   row.end_time   ?? row.end,
                      lineage_match_method: "time_overlap_failed",
                      lineage_unit_source: unitSource
                    };

                    return {
                      ...row,
                      // [R41] Lineage 보존
                      start_frame: startFrame,
                      end_frame: endFrame,
                      start_time: row.start_time ?? row.start,
                      end_time:   row.end_time   ?? row.end,
                      parent_vf_id: parentVF.fragment_id,
                      lineage_match_method: "source_id_time_overlap",
                      lineage_unit_source: unitSource,
                      
                      // 썸네일 보존 (R42 이전까지는 VF 썸네일 사용)
                      thumbnail_url:
                        row.thumbnail_url ||
                        parentVF.thumbnail?.thumbnail_url ||
                        parentVF.thumbnail_url ||
                        parentVF.intelligence?.thumb_url,
                      thumb:
                        row.thumb ||
                        parentVF.thumbnail?.thumbnail_url ||
                        parentVF.thumbnail_url ||
                        parentVF.intelligence?.thumb_url,
                      intelligence: {
                        ...(row.intelligence || {}),
                        ...(parentVF.intelligence || {}),
                        thumb_url:
                          row.intelligence?.thumb_url ||
                          parentVF.thumbnail?.thumbnail_url ||
                          parentVF.thumbnail_url ||
                          parentVF.intelligence?.thumb_url,
                      },
                    };
                  });

                  const mapped = mapFragments(enrichedRows, entry.label);
                  finalEditFragments = [...finalEditFragments, ...mapped];
                  return { ...entry, fragments: mapped };
                }
                // Semantic 없는 경우 경고 (R1 정책에 따라 Skip되겠지만 프론트에서도 표시 유지)
                return entry;
              });

              setSourceEntries([...priorEntries, ...updatedEntries]); // [UI-②] 기존 소스 보존

              // 3. 제안 생성 요청
              let generatedProposals: Record<"A" | "B", any> = {} as any;
              let proposalData: any = null;
              let proposalError: string | null = null;  // [GHOST#3] 실패 이유 — 화면 표시용 (침묵 금지)
              markTiming("proposal_requested");

              try {
                // [B-5-FIX] 단일/멀티 모두 프로젝트(program_id) 경로로 일원화 — program_id 저장돼야 복원 가능
                const orderedSourceIds = [
                  ...priorEntries.map((e) => e.source_id), // [UI-②] 기존 소스 포함해 전체 재제안
                  ...uploadedSourceIds.filter(id => completedSourceIds.includes(id)),
                ];
                setAnalyzeMessage("편집 제안(A·B)을 생성하는 중입니다... 잠시만 기다려 주세요.");
                proposalData = await videoService.requestProjectProposals(projectId, orderedSourceIds, 60.0);
                console.log("[proposal-project] Diagnostics:", {
                  project_id: proposalData.project_id,
                  source_ids: proposalData.source_ids,
                  source_usage: proposalData.source_usage,
                  warnings: proposalData.warnings,
                  completed: completedSourceIds,
                  failed: failedSourceIds
                });
                markTiming("proposal_received");

                if (proposalData && proposalData.proposals) {
                  proposalData.proposals.forEach((p: any) => {
                    const mode = p.mode === "A" ? "A" : "B";
                    const copy = STORY_GATE_COPY.abCards.variants[mode];
                    generatedProposals[mode] = {
                      id: mode,
                      proposal_id: p.proposal_id,
                      mode: p.mode === "A" ? "market" : "user",
                      title: copy.title,
                      desc: copy.desc,
                      score: String(Math.round(p.confidence * 100)) + "%",
                      key_fragments: p.sequence.map((s: any) => s.fragment_id),
                      proposal_story: p.proposal_story,
                      proposal_explanation: p.proposal_explanation,
                      direction: {},
                      snapshot_id: "R1",
                      template_id: p.mode,
                      slot_trace: [],
                      // [PROPOSAL_PREVIEW] 백엔드 preview_url 보존
                      preview_url: p.preview_url ?? null,
                      preview_duration: p.preview_duration ?? 0,
                    };
                    
                    if (generatedProposals[mode].key_fragments.length > 0) {
                      generatedProposals[mode].resolved_aliases = p.sequence.map((s: any) => ({
                        proposal_fragment_id: s.fragment_id,
                        source_id: s.source_id,
                        source_fragment_id: s.fragment_id, // FIX: s.source_id -> s.fragment_id
                        display_id: s.display_id,
                        start_sec: s.start,
                        end_sec: s.end,
                        thumbnail_url: s.thumbnail_url
                      }));
                    }
                  });
                }
              } catch (pErr) {
                console.error("[proposal-orchestration] error:", pErr);
                proposalError = pErr instanceof Error ? pErr.message : String(pErr);
              }

              // 4. 최종 상태 적용
              // [GHOST#3 절단] 백엔드 제안 부재/실패 시 프론트 임의 생성(strategyEngine 가짜 제안) 금지
              // — 헌장 §5 거짓말 금지·침묵 실패 금지. 분석 결과(조각)는 그대로 보존하고
              //   실패 이유를 화면에 표시한다. 재시도는 사용자가 결정한다.
              const proposalsEmpty = Object.keys(generatedProposals).length === 0;
              // [PROPOSAL-TRUTH] 승인 전에 A·B를 만들지 않는 것은 실패가 아니라 설계다
              //   (main.py:GATE-LOOP-01 2-1 — 제안은 '승인된 스토리를 어떻게 편집할지'다).
              //   백엔드는 status=STORY_NOT_APPROVED 와 안내 문구까지 실어 보내는데,
              //   구판은 proposals 배열이 빈 것만 보고 '생성 실패'라고 화면에 적었다.
              //   정상 동작을 실패로 보고하는 것도 거짓말이다 — 백엔드가 준 말을 그대로 쓴다.
              const storyNotApproved = proposalData?.status === "STORY_NOT_APPROVED";
              const proposalNotice = storyNotApproved
                ? (proposalData?.message || "원고를 먼저 저장해 주세요. 저장하면 편집안(A·B)을 만듭니다.")
                : null;

              setEditFragments(finalEditFragments);
              setSourceFragments(updatedEntries[0]?.fragments || []);
              if (!proposalsEmpty) setProposals(generatedProposals);
              markTiming("proposal_mapped_to_ui");
              markTiming("story_visible"); // Set at same time as proposals are mapped
              setSemanticFragments(Object.values(semanticResults).flat());

              // [STORY-RESYNC] 분석이 새 세대 조각을 냈으면, 사용자 원고가 아닌 화면 원고는
              //   새 세대로 다시 세운다. 실측(2026-07-31 Dubhe): 분석 초반에 STORY-LOAD 가
              //   1세대 id 135개를 실었는데 품질 재분석이 2세대로 갈아타, 원고↔조각 교집합이
              //   0이 되며 조각맵이 통째로 비었다(새로고침 전까지 복구 불가).
              //   사용자가 만든 원고(user/ui_state)는 절대 덮지 않는다 — 서버 폴백 표시분만.
              if (storyOriginRef.current !== "user" && storyOriginRef.current !== "ui_state") {
                const freshFids = finalEditFragments
                  .map((f: any) => String(f.fragment_id ?? ""))
                  .filter(Boolean);
                if (freshFids.length > 0) {
                  setStoryFids(freshFids);
                  storyFidsRef.current = freshFids;   // 가드(:2403)가 다음 렌더 전에 읽어도 새 세대
                  storyOriginRef.current = "server";  // 표시용 — 저장 자격 없음(가드 2-2 그대로)
                  console.info(`[STORY-RESYNC] 분석 완료 — 원고를 새 세대 ${freshFids.length}조각으로 재동기 (출처=server · 저장 금지)`);
                }
              }

              setAnalyzeProgress(100);
              setAnalyzeMessage(
                proposalNotice
                  ? `분석 완료 — ${proposalNotice}`
                  : proposalsEmpty
                  ? `분석은 끝났지만 편집 제안 생성에 실패했습니다 — ${proposalError ?? "백엔드가 제안을 반환하지 않았습니다"}. 조각은 보존되어 있으니 다시 시도해 주세요.`
                  : (failedSourceIds.length > 0 ? `일부 분석 실패 (${failedSourceIds.length}개), 제안 생성 완료` : "모든 영상 분석 및 제안 완료")
              );
              if (proposalsEmpty && !proposalNotice) {
                // 분석 배너는 complete 전환과 함께 사라지므로, 지속 표면(지휘부 채팅)에 이유를 남긴다.
                // 제안 실패 시엔 storyPlan 골격 effect(:1169, proposals 필수)가 못 태어나므로
                // 여기서 null-안전하게 최소 골격을 세운다 — 침묵 화면 금지.
                const failMsg = {
                  id: `ai_proposal_fail_${Date.now()}`,
                  sender: "ai" as const,
                  text: `분석은 끝났지만 편집 제안(A·B) 생성에 실패했습니다 — ${proposalError ?? "백엔드가 제안을 반환하지 않았습니다"}. 조각은 그대로 보존되어 있습니다. 잠시 후 다시 말씀해 주시면 재시도하겠습니다.`,
                  timestamp: Date.now(),
                };
                setStoryPlan((prev: any) => ({
                  ...(prev ?? {
                    story_plan_id: `STP_${Date.now()}`,
                    source_count: updatedEntries.length,
                    consultation_status: "draft_ready",
                    confirmation_status: "pending",
                    direction_options: [],
                    detected_theme: "",
                    selected_direction: undefined,
                    messages: [],
                  }),
                  messages: [...((prev?.messages) ?? []), failMsg],
                }));
              } else {
                // [PROGRESS-VOICE 3] 끝났다는 말을 화면에 남긴다. 분석 배너는 complete 전환과
                //   함께 사라지므로, 지속 표면(채팅)에 결과를 한 줄로 남겨야 사용자가
                //   "끝난 건가?"를 다시 묻지 않는다. 실패 경로(위)와 같은 골격을 쓴다.
                const _fragCount = Object.values(semanticResults).flat().length;
                const _failNote = failedSourceIds.length > 0
                  ? ` (영상 ${failedSourceIds.length}개는 분석 실패)` : "";
                // [LAYER-FIX2 2026-08-04 국장 지시] 절차를 통보하지 않는다.
                //   "원고를 먼저 저장해 주세요"는 사용자가 아직 하지도 않은 일을 재촉하는 말이었다.
                //   지금 할 수 있는 일을 권하는 문장으로 바꾼다.
                const _tail = "전사를 보면서 쓸 장면을 골라 보세요. 마음에 들면 저장해 두면 됩니다.";
                const _doneMsg = {
                  id: `ai_analysis_done_${Date.now()}`,
                  sender: "ai" as const,
                  text: `영상에서 장면 ${_fragCount}개를 찾았어요${_failNote}. ${_tail}`,
                  timestamp: Date.now(),
                };
                setStoryPlan((prev: any) => ({
                  ...(prev ?? {
                    story_plan_id: `STP_${Date.now()}`,
                    source_count: updatedEntries.length,
                    consultation_status: "draft_ready",
                    confirmation_status: "pending",
                    direction_options: [],
                    detected_theme: "",
                    selected_direction: undefined,
                    messages: [],
                  }),
                  messages: [...((prev?.messages) ?? []), _doneMsg],
                }));
              }
              setAppState("complete");
              markTiming("user_selectable");

              reportTiming(proposalData?.timing_summary);
            }
          } catch (err) {
            console.error("[Index] Multi-source polling error:", err);
            if (err instanceof Error && (err.message.includes("Failed to fetch") || err.message.includes("NetworkError"))) {
              clearInterval(pollInterval);
              setAnalyzeMessage("백엔드 서버 연결이 끊겼습니다.");
              setAppState("empty");
            }
          }
        }, 2000);

        return true;
      } catch (e: any) {
        console.error("[N-01] 분석 중단 오류:", e);
        const errorMsg = e.message || "분석 중 알 수 없는 오류가 발생했습니다.";
        setAnalyzeMessage(errorMsg);
        setAnalyzeProgress(0);
        
        // 중요: 로딩 상태를 해제하여 사용자가 다시 시도할 수 있게 함
        setAppState("empty");
        
        // 사용자에게 알림 (Toast 등이 있다면 좋겠지만 여기서는 alert로 우선 처리하거나 UI에 메시지 유지)
        setAppDialog({ message: `[분석 실패] ${errorMsg}` });
        return false;
      }
    },
    [logProposalPair, resetAnalysisState, toFullUrl, activeNavItem, sourceEntries]
  );

  // [GHOST 소각 #4] triggerPBEMock(#debug-hydrate Playwright 어댑터) 제거 — 구 2조각 PBE 진입 유일 경로였음

  // [B-5c] 백엔드 프로젝트 목록 로드 (재기동/새로고침/휴지통 복원 후에도 영속)
  const reloadProjects = useCallback(async () => {
    try {
      const res = await videoService.listProjects();
      if (!res || !Array.isArray(res.projects)) return;
      const mapped = res.projects.map((p: any) => {
        const raw = p.last_updated_at || p.created_at;
        const d = raw ? new Date(raw) : null;
        const dateStr = d ? (String(d.getMonth() + 1) + "/" + String(d.getDate()) + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0")) : "";
        return { id: p.program_id, name: p.name, date: dateStr, count: p.source_count ?? 0 };
      });
      setProjects(mapped);
    } catch (e) {
      console.warn("[B-5c] 프로젝트 목록 로드 실패", e);
    }
  }, [setProjects]);

  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash === "#debug-hydrate") return;
    reloadProjects();
  }, [reloadProjects]);

  // [FIX-HYD-A] 마지막으로 하이드레이션한 프로젝트 id. 진짜 '프로젝트 전환'과
  // '신규 업로드로 막 생성된 프로젝트(첫 하이드레이션)'를 구분하기 위한 기준점.
  const previousHydratedProjectRef = useRef<string | null>(null);
  // [FIX-HYD-EMPTY] 방금 업로드로 생성한 프로젝트 id. 분석 중 신규 프로젝트로 진입할 때
  // hydration의 fetch-전 클리어가 갓 만든 세션을 비우지 않도록 1회 표식(소비형).
  const justCreatedProjectRef = useRef<string | null>(null);

  // [CCUT1.0.4 PROPOSALS PROJECT SOURCES HYDRATION]
  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash === "#debug-hydrate") {
      DEBUG_LOG && console.log("[Hydration] Skipping backend hydration because #debug-hydrate is active");
      return;
    }
    const savedActiveProject = typeof window !== "undefined" ? localStorage.getItem("ccut_active_project_id") : null;
    if (!savedActiveProject || savedActiveProject === "projects" || !activeNavItem || activeNavItem === "projects" || activeNavItem === "default_project" || activeNavItem === "__new__" || activeNavItem === "settings") {
      // [FIX-RUNTIME-1b] 'settings'(환경진단 화면) 전환은 프로젝트 hydration 트리거가 아님 → 세션 보존.
      // [#32 침묵 제거 ①] 프로젝트를 향했는데 localStorage 게이트가 복원을 막는 경우만 정직 표기 (§5).
      if (activeNavItem && activeNavItem.startsWith("proj_")) {
        console.warn(`[HYDRATION][GATE_SKIP] 프로젝트 복원 게이트 차단 — activeNavItem=${activeNavItem}, saved=${savedActiveProject}`);
      }
      return;
    }

    // [FIX-HYD-A] '진짜 프로젝트 전환'만 클리어 대상. 첫 하이드레이션(마운트/업로드 직후
    // 신규 프로젝트로 activeNavItem 최초 진입)은 전환이 아니므로 방금 분석한 세션을 보존한다.
    const previousProjectId = previousHydratedProjectRef.current;
    const isRealProjectSwitch =
      previousProjectId !== null &&
      previousProjectId !== activeNavItem;
    // [FIX-HYD-EMPTY] 방금 업로드로 생성한 프로젝트면 fetch-전 클리어 스킵(분석 세션 보존). 표식은 1회 소비.
    const isJustCreated = justCreatedProjectRef.current === activeNavItem;
    if (isJustCreated) justCreatedProjectRef.current = null;
    if (isRealProjectSwitch && !isJustCreated) {
      closeMirrorPendingForProject(previousProjectId, "project_switch");
    }
    previousHydratedProjectRef.current = activeNavItem;
    if (isRealProjectSwitch && !isJustCreated) setIsSwitchingProject(true);

    let isMounted = true;
    let debounceTimer: ReturnType<typeof setTimeout> | null = null;

    const hydrateProjectSources = async () => {
      // [FIX-HYD-A] fetch 전 클리어 — 다른 프로젝트로 '전환'할 때만 수행.
      // [FIX-HYD-EMPTY] 단, 업로드-생성 직후(분석 중) 프로젝트는 제외 — 갓 만든 세션 보존.
      if (isRealProjectSwitch && !isJustCreated) {
        setSourceEntries([]);
        setEditFragments([]);
        setSourceFragments([]);
        setProposals(null);
        setCommittedProposalId(null);
        setSelectedProposalId(null);
        // [STORY-LAYER-01 A-1] 프로젝트 전환 클리어 — 스토리·보류·휴지통 모두 program 스코프 하나
        setStoryFids([]);
        setStoryFragments([]);
        setReservedFragments([]);
        setHoldPositions({});
        setDeletedFragments([]);
        setCurrentSourceId(null);
        setCurrentVideoUrl(null);
        setSingleEditOpen(false);
        setSingleEditTarget(null);
        setAppState("empty");
        setStoryPlan(null);
        setAnalyzeMessage("");
        setAnalysisLogs([]);
      }

      try {
        DEBUG_LOG && console.log(`[Hydration] Loading sources for project: ${activeNavItem}`);
        pushAnalysisLog(`[Hydration] Loading sources for project: ${activeNavItem}`.slice(0, 120));
        const data = await videoService.getProjectSources(activeNavItem);
        if (!isMounted) return;

        // 2. API 응답 project_id 가 요청 projectId와 다르면 hydration skip
        if (!data || data.project_id !== activeNavItem) {
          // [#32 침묵 제거 ②] 응답 프로젝트 불일치 — 복원 중단을 정직 표기 (§5)
          console.warn(`[HYDRATION][ID_MISMATCH] 복원 중단 — 요청=${activeNavItem}, 응답=${data?.project_id}`);
          return;
        }

        // 3. 응답 sources.length === 0
        //    NO_PROPOSALS_FOUND 는 "아직 제안 없음(분석 중)"일 수 있으므로,
        //    [FIX-HYD-A] 세션에 이미 소스가 있으면 업로드 화면으로 내리지 않고 그대로 유지한다.
        //    세션이 진짜 비어 있을 때만 empty 처리(빈 프로젝트 → 업로드 화면).
        if (!data.sources || data.sources.length === 0) {
          if (sourceEntries.length === 0) {
            // [#32 침묵 제거 ③] 빈 소스 → 업로드 화면 강하도 상시 표기
            console.info(`[HYDRATION][EMPTY_SOURCES] ${activeNavItem}: 소스 0 + 세션 비어있음 → 업로드 화면`);
            pushAnalysisLog("[Hydration] sources=0, session empty → upload screen");
            setSourceEntries([]);
            setSourceFragments([]);
            setEditFragments([]);
            setCurrentSourceId(null);
            setCurrentVideoUrl(null);
            setSemanticFragments([]);
            setSelectedFragment(null);
            setHighlightedPanoramaFrag(null);
            setExpandedFragment(null);
            setAppState("empty");  // [B-5-FIX] 빈 프로젝트 → 업로드 화면 (FAILURE 아님)
          } else {
            console.info(`[HYDRATION][EMPTY_SOURCES_KEPT] ${activeNavItem}: 소스 0이나 세션 보존 (제안 생성 대기 추정)`);
            pushAnalysisLog("[Hydration] sources=0 but session kept (proposals pending)");
          }
          return;
        }

        if (data.status === "OK" && Array.isArray(data.sources)) {
          const restoredEntries: SourceEntry[] = data.sources.map((src: any) => {
            const label = src.label;
            const mappedFrags = mapFragments(src.fragments || [], label);
            return {
              source_id: src.source_id,
              label: label,
              title: src.title,
              display_name: src.display_name ?? null,
              video_url: src.video_url,
              fragments: mappedFrags,
              file_size_bytes: src.file_size_bytes || 0,
              duration_sec: src.duration_sec || (mappedFrags.length > 0 ? mappedFrags[mappedFrags.length - 1].end_frame / 30 : 0)
            };
          });

          if (restoredEntries.length > 0) {
            setSourceEntries(restoredEntries);
            setActiveSource("A");
            
            const firstEntry = restoredEntries[0];
            // [#23 수리 — 국장 승인 2026-07-17] 원료 웅덩이(editFragments)에 전 소스 조각 합집합 적재.
            // 구판(첫 소스만)은 사용자가 원본맵에서 추가한 타 소스 조각이 재진입 시 조용히 증발하던
            // 병소(§5) — 시퀀스 매칭분만 렌더되므로 조각맵 표시 수는 불변. 분석(업로드) 경로는
            // 원래 전 소스 누적(:659·:776)이라 무접촉.
            setEditFragments(restoredEntries.flatMap((e) => e.fragments));
            setSourceFragments(firstEntry.fragments);
            
            setCurrentSourceId(firstEntry.source_id);
            setCurrentVideoUrl(firstEntry.video_url);

            // [B-5-FIX] 저장된 A/B 제안 복원 → 돌아오면 하던 그대로
            // [GATE-LOOP-01 2-2] appState 의존 방향 교정 — proposals가 아니라 story를 본다.
            //   구판: `data.proposals.length > 0 ? complete : empty`
            //         제안이 곧 '작업 화면이 있는가'의 판정이었다. 그래서 (a) 제안이 생기기
            //         전에는 작업 화면이 없고, (b) 제안이 화면의 주인이 됐다. 승인 관문이
            //         제안 뒤에 서게 된 뿌리다.
            //   신판: 재료(조각)와 story_state가 결정한다. 제안은 있으면 무대에 세울 뿐이다.
            if (data.proposals && data.proposals.length > 0) {
              setProposals(mapBackendProposals(data.proposals));
            }
            const hasMaterial = restoredEntries.some((e) => (e.fragments?.length ?? 0) > 0);
            const storyInfo = await fetchStory(activeNavItem);
            const storyAlive = !!storyInfo && storyInfo.story_state !== "scanned";
            setAppState(hasMaterial || storyAlive ? "complete" : "empty");
            console.info(
              `[APPSTATE] ${activeNavItem}: material=${hasMaterial} story_state=${storyInfo?.story_state ?? "none"} `
              + `items=${storyInfo?.item_count ?? 0} → ${hasMaterial || storyAlive ? "complete" : "empty"}`,
            );

            // [B-5d] ui_state 스냅샷 복원 (단일 스냅샷 패턴)
            try {
              const stateRes = await videoService.getProjectState(activeNavItem);
              // [TIMELINE 2026-07-05] append-only 타임라인 복원 — 상용 채팅 동형 구조.
              // 행 단위 사건 로그를 시간순으로 되살린다 (v1 chat_state blob은 서버가
              // 첫 조회 때 행으로 자동 이관). 복원분 id는 synced에 등록해 재전송 방지.
              syncedTimelineIdsRef.current = new Set();
              try {
                const tl = await videoService.getTimeline(activeNavItem, 300);
                if (tl?.entries?.length && isMounted) {
                  const msgs: any[] = [];
                  const gens: any[] = [];
                  let refTs: number | null = null;
                  for (const en of tl.entries) {
                    syncedTimelineIdsRef.current.add(en.client_id);
                    // [C 증발 방어] 재수화 메시지는 항상 확정 상태 — 혹 isInterpreting=true가
                    // 실린 payload가 있어도(중단 세션 잔재) 스피너로 숨지 않게 강제 해제.
                    if (en.kind === "message" && en.payload) msgs.push({ ...en.payload, isInterpreting: false });
                    else if (en.kind === "generation" && en.payload) gens.push(en.payload);
                    // [TIMELINE-REF 2026-08-02] 전사가 대화의 '언제'였는지 — 참조 사건 하나.
                    //   가장 이른 것을 쓴다. 재생성으로 행이 늘어도 최초 등장 자리는 안 밀린다.
                    else if (en.kind === "transcript_ref") {
                      refTs = refTs === null ? en.ts : Math.min(refTs, en.ts);
                    }
                  }
                  if (msgs.length) {
                    // [TIMELINE-RACE] 스켈레톤이 이미 지나간 뒤 복원이 도착하면(HTTP가
                    // setProposals보다 느린 보통의 경우) ref는 영영 소비되지 않는다 —
                    // storyPlan이 있으면 직접 병합(id 중복 제외, 과거이므로 앞에).
                    setStoryPlan((prev: any) => {
                      // [CHAT-RESTORE-NULLSAFE 2026-08-01] 구판은 여기서 `if (!prev) return prev`
                      //   로 복원분을 통째로 버렸다. 대비책이라던 restoredTimelineRef 는
                      //   **write-only** 였다 — 선언 1곳·대입 1곳·비움 2곳, 읽는 곳 0곳.
                      //   "스켈레톤이 승계"라는 주석만 있고 승계하는 스켈레톤이 코드에 없다.
                      //   그래서 storyPlan 이 없는 순간 서버 타임라인이 조용히 사라졌고,
                      //   07-31 시도1의 "재방문 시 채팅 영영 빔"이 정확히 이 줄이었다.
                      //   (방어는 있는데 도달 불가 — 오늘 rematch_anchor·whisper 임계값과 같은 계열)
                      //   이제 prev 가 없으면 골격을 만들어 복원분을 담는다. 골격 모양은
                      //   STAGE-VOICE(:3043)와 동일 — consultation_status 를 confirmed 로
                      //   올리지 않으므로 방향 선택 UI(:2278)가 임의로 열리지 않는다.
                      if (!prev) {
                        return {
                          story_plan_id: `STP_${Date.now()}`,
                          source_count: restoredEntries.length,
                          consultation_status: "draft_ready",
                          confirmation_status: "pending",
                          direction_options: [],
                          detected_theme: "",
                          selected_direction: undefined,
                          messages: msgs,
                        };
                      }
                      const have = new Set((prev.messages ?? []).map((m: any) => String(m.id)));
                      const texts = new Set((prev.messages ?? []).map((m: any) => m.text));
                      // 재열기 시 fresh 개략(같은 id)이 매번 맨 아래로 재인사하지 않게 —
                      // 복원분의 원래 시각을 승계해 역사 위치에 놓는다
                      const restoredTs = new Map(msgs.map((m: any) => [String(m.id), m.timestamp]));
                      const base = (prev.messages ?? []).map((m: any) => {
                        const ts = restoredTs.get(String(m.id));
                        return typeof ts === "number" && ts > 0 && ts < m.timestamp ? { ...m, timestamp: ts } : m;
                      });
                      // 개략(ai_init)은 결정론 id 도입 전 열 때마다 새 id로 쌓인 레거시가
                      // 있다 — 같은 텍스트의 개략은 화면에서 1개로 접는다 (복원분끼리 포함)
                      const olds = msgs.filter((m: any) => {
                        if (have.has(String(m.id))) return false;
                        if (String(m.id).startsWith("ai_init_")) {
                          if (texts.has(m.text)) return false;
                          texts.add(m.text);
                        }
                        return true;
                      });
                      return { ...prev, messages: [...olds, ...base] };
                    });
                  }
                  if (gens.length) hydrateProposalHistory(gens);
                  // [TIMELINE-PAGE 2026-08-02] has_more 를 콘솔이 아니라 사용자에게 도달시킨다.
                  //   구판은 이 값을 DEBUG_LOG 안에서만 읽었다 — 서버가 "더 있다"고 말하는데
                  //   듣는 코드가 0이었고, 그래서 Merope 614행 중 314행이 도달 불가였다.
                  //   커서는 이번 페이지의 ★최소 entry_id (서버가 entry_id 오름차순으로 준다).
                  setTranscriptRefTs(refTs);
                  setTimelineHasMore(!!tl.has_more);
                  setTimelineOldestEntry(
                    tl.entries.reduce((mn: number, en: any) =>
                      (mn === 0 || en.entry_id < mn ? en.entry_id : mn), 0) || null);
                  DEBUG_LOG && console.log(`[TIMELINE] 복원: 메시지 ${msgs.length} · 세대 ${gens.length}` +
                    (tl.has_more ? " (이전 페이지 더 있음)" : ""));
                }
              } catch (e) {
                // [#32 침묵 제거 ④] 타임라인/상태 재수화 실패 상시 표기 (§5)
                console.warn("[HYDRATION][TIMELINE_RESTORE_FAIL] 복원 실패 — 새 흐름으로 시작", e);
              }
              if (stateRes && stateRes.ui_state && isMounted) {
                const snap = JSON.parse(stateRes.ui_state);
                // [STORY-LAYER-01 A-1] 복원도 program 스코프 하나. 배열/평면 Record만 받는다.
                // 구판 {A,B} 버킷은 스토리를 갈랐던 폐기 모델이라 읽지 않는다 — 그 형태로 저장된
                // 프로젝트는 보류·좌표가 비어서 열린다(국장 승인: 기존 프로젝트 이전 불필요).
                const asFrags = (v: any): Fragment[] | null => (Array.isArray(v) ? v : null);
                const asPos = (v: any): Record<string, { x: number; y: number }> | null =>
                  v && typeof v === "object" && !Array.isArray(v) && v.A === undefined && v.B === undefined ? v : null;
                const rf = asFrags(snap.reservedFragments);
                if (rf) setReservedFragments(rf);
                const hp = asPos(snap.holdPositions);
                if (hp) setHoldPositions(hp);
                if (snap.committedProposalId) setCommittedProposalId(snap.committedProposalId);
                if (snap.selectedProposalId) setSelectedProposalId(snap.selectedProposalId);
                if (snap.activeSource) setActiveSource(snap.activeSource);
                const df = asFrags(snap.deletedFragments);
                if (df) setDeletedFragments(df);
                if (snap.roughCutPlacement && Array.isArray(snap.roughCutPlacement.selectedSpanIds)) {
                  setRoughCutPlacement({
                    inputHash: typeof snap.roughCutPlacement.inputHash === "string"
                      ? snap.roughCutPlacement.inputHash
                      : null,
                    selectedSpanIds: snap.roughCutPlacement.selectedSpanIds.map(String),
                  });
                }
                // 스토리 복원 — 진실원 하나(story.fids + storyFragments).
                // [STORY-WRITE-GUARD-01 2-2] 출처 표식: ui_state에서 온 스토리만 저장 자격이 있다.
                //   서버 폴백(조각 시간순)·제안 파생으로 화면에 오른 목록은 'server'로 찍어
                //   저장 경로 진입 자체를 막는다(사용자가 손대면 그때 'user'로 승격).
                const snapFids = Array.isArray(snap.story?.fids) ? snap.story.fids.map(String) : null;
                const snapFrags = asFrags(snap.storyFragments);
                if (snapFids && snapFids.length > 0) {
                  setStoryFids(snapFids);
                  if (snapFrags) setStoryFragments(snapFrags);
                  storyOriginRef.current = "ui_state";
                  // [STORY-ANCHOR] 좌표를 들고 온다. 조각 풀이 아직 안 실렸을 수 있으므로
                  //   여기서 잇지 않고 ref 에 담아 두고, 풀이 준비된 뒤 아래 치유 effect 가 잇는다.
                  storyFidAnchorsRef.current = (snap.story?.fidAnchors ?? null) as any;
                }
              }
            } catch (_) {}

            DEBUG_LOG && console.log(`[Hydration] Successfully hydrated ${restoredEntries.length} sources, ${(data.proposals || []).length} proposals for project: ${activeNavItem}`);
            pushAnalysisLog(`[Hydration] hydrated ${restoredEntries.length} sources, ${(data.proposals || []).length} proposals`);
          }
        }
      } catch (err) {
        console.error("[Hydration] Failed to hydrate project sources:", err);
      } finally {
        // 성공·실패·조기반환 무엇이든 '이 프로젝트의 복원 시도는 끝났다' — 이 문턱이 열린 뒤에만
        // 스토리 저장이 허용된다(복원 전 저장이 committedProposalId를 null로 덮던 병소).
        if (isMounted) {
          setUiRestoredFor(activeNavItem);
          setIsSwitchingProject(false);
        }
      }
    };

    debounceTimer = setTimeout(() => {
      if (isMounted) hydrateProjectSources();
    }, 150);

    return () => {
      isMounted = false;
      if (debounceTimer) clearTimeout(debounceTimer);
    };
  }, [activeNavItem, mapFragments]);


  // [TIMELINE 2026-07-05] append-only 동기화 — 상용 채팅 동형 구조.
  // 새로 생긴 메시지만 골라 사건 발생 즉시 기록(유실 창 ~0). client_id 멱등이라
  // 재전송·멀티탭에 안전하고, 과거 행은 불변이라 역사 파괴가 구조적으로 불가능.
  // 해석중(isInterpreting) 임시 메시지는 최종 문구로 교체된 뒤에 기록.
  // 제안 세대는 4초 숙성 후 저장 — 프리뷰 URL 주입까지 끝난 완성 스냅샷을 남긴다.
  // [CHAT-RESTORE-NULLSAFE 2026-08-01] restoredTimelineRef 철거 — write-only 였다.
  //   대입 1곳뿐이고 읽는 곳이 0곳이라 '스켈레톤이 승계'는 일어난 적이 없다.
  //   복원은 이제 setStoryPlan 안에서 골격을 직접 만들어 담는다(:1543).
  const syncedTimelineIdsRef = useRef<Set<string>>(new Set());
  const genSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // [TIMELINE-PAGE 2026-08-02] 잘린 옛 기록을 커서로 이어 붙인다.
  //   ★서버·서비스 계층 무수정 — before 인자는 이미 있었고(videoService.ts:154,
  //     main.py:6467) 부르는 사람만 없었다. 호출처만 잇는다.
  //   ★옛것은 ★위에★ 붙인다. entry_id 오름차순이 원장의 순서이고, ts 로 정렬하지 않는다.
  //   ★복원분 client_id 는 synced 에 등록 — 되받은 것을 다시 보내지 않는다(중복 0).
  const loadOlderTimeline = useCallback(async () => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return;
    if (!timelineOldestEntry || timelineLoadingMore) return;
    setTimelineLoadingMore(true);
    try {
      const tl = await videoService.getTimeline(activeNavItem, 300, timelineOldestEntry);
      const entries: any[] = tl?.entries ?? [];
      if (!entries.length) { setTimelineHasMore(false); return; }
      const msgs: any[] = [];
      const gens: any[] = [];
      for (const en of entries) {
        syncedTimelineIdsRef.current.add(en.client_id);
        if (en.kind === "message" && en.payload) msgs.push({ ...en.payload, isInterpreting: false });
        else if (en.kind === "generation" && en.payload) gens.push(en.payload);
      }
      if (msgs.length) {
        setStoryPlan((prev: any) => {
          const base = prev?.messages ?? [];
          const have = new Set(base.map((m: any) => String(m.id)));
          const olds = msgs.filter((m: any) => !have.has(String(m.id)));
          if (!prev) {
            // 복원 경로(:1646)와 같은 골격 — 대화가 없다고 옛 기록을 버리지 않는다.
            return {
              story_plan_id: `STP_${Date.now()}`,
              source_count: 0,
              consultation_status: "draft_ready",
              confirmation_status: "pending",
              direction_options: [],
              detected_theme: "",
              selected_direction: undefined,
              messages: olds,
            };
          }
          return { ...prev, messages: [...olds, ...base] };
        });
      }
      if (gens.length) {
        // ★hydrateProposalHistory 는 통째로 갈아끼운다(useProposalState.ts:205).
        //   옛 세대만 넘기면 새 세대가 지워지므로 합쳐서 넘긴다. 마지막 원소는
        //   여전히 최신이라 activeProposalEntryId 는 움직이지 않는다.
        const seen = new Set(proposalHistory.map((g: any) => String(g.id)));
        const merged = [...gens.filter((g: any) => !seen.has(String(g.id))), ...proposalHistory];
        if (merged.length !== proposalHistory.length) hydrateProposalHistory(merged as any);
      }
      setTimelineHasMore(!!tl.has_more);
      setTimelineOldestEntry(
        entries.reduce((mn: number, en: any) =>
          (mn === 0 || en.entry_id < mn ? en.entry_id : mn), 0) || timelineOldestEntry);
      DEBUG_LOG && console.log(`[TIMELINE-PAGE] 이전 페이지 +${entries.length}행 ` +
        `(메시지 ${msgs.length} · 세대 ${gens.length}) has_more=${!!tl.has_more}`);
    } catch (e) {
      console.warn("[TIMELINE-PAGE] 이전 기록 불러오기 실패 — 다시 눌러 재시도", e);
    } finally {
      setTimelineLoadingMore(false);
    }
  }, [activeNavItem, timelineOldestEntry, timelineLoadingMore,
      proposalHistory, hydrateProposalHistory, setStoryPlan]);

  // [TIMELINE-REF 2026-08-02] 전사가 대화에 등장한 사건을 원장에 한 번만 남긴다.
  //   ★원문은 복제하지 않는다 — payload 는 참조뿐이다(ref_kind·ref_id·payload_version).
  //     전사 본문의 진실은 계속 ui_state.roughCut 하나다(무접촉).
  //   ★client_id 는 결정론: tref_<input_hash>. Date.now() 를 쓰면 프로젝트를 열 때마다
  //     한 행씩 쌓인다 — STAGE-DUP 이 정확히 그 함정이었다(ai_stage_*_${Date.now()}).
  //     input_hash 는 전사 내용의 지문이라, 같은 전사면 몇 번을 열어도 같은 client_id 이고
  //     uq_timeline_client 가 두 번째부터 조용히 막는다(added=0).
  //   ★복원이 끝난 뒤에만 쓴다(uiRestoredFor) — 이미 있는 기록을 못 보고 새로 쓰면
  //     최초 등장 시각이 오늘로 덮인다.
  useEffect(() => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return;
    if (uiRestoredFor !== activeNavItem) return;      // 복원 전에는 판단하지 않는다
    if (transcriptRefTs !== null) return;             // 이미 원장에 있다
    const inputHash = roughCutData?.input_hash;
    if (!inputHash) return;                           // 전사(원고)가 아직 없다
    const cid = `tref_${inputHash}`;
    if (syncedTimelineIdsRef.current.has(cid)) return;
    syncedTimelineIdsRef.current.add(cid);
    const ts = Date.now();
    videoService.appendTimeline(activeNavItem, [{
      kind: "transcript_ref", client_id: cid, ts,
      payload: { ref_kind: "rough_cut", ref_id: inputHash, payload_version: 1 },
    }])
      .then((r) => {
        // added=0 이면 이미 있던 사건이다 — 그때는 복원이 준 시각을 그대로 쓴다.
        if (r?.added) setTranscriptRefTs(ts);
        DEBUG_LOG && console.log(`[TIMELINE-REF] transcript_ref ${cid} (added=${r?.added})`);
      })
      .catch((err) => {
        syncedTimelineIdsRef.current.delete(cid);
        DEBUG_LOG && console.warn("[TIMELINE-REF] append 실패 — 다음 변경 시 재시도", err);
      });
  }, [activeNavItem, uiRestoredFor, transcriptRefTs, roughCutData?.input_hash]);
  useEffect(() => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return;
    if (isSwitchingProject) return;

    const newMsgs: any[] = [];
    for (const m of (((storyPlan as any)?.messages) ?? [])) {
      const cid = String(m?.id ?? `m_${m?.timestamp}`);
      if (!m || m.isInterpreting || syncedTimelineIdsRef.current.has(cid)) continue;
      newMsgs.push({ kind: "message", client_id: cid, ts: m.timestamp ?? Date.now(), payload: m });
    }
    if (newMsgs.length) {
      newMsgs.forEach((e) => syncedTimelineIdsRef.current.add(e.client_id));
      videoService.appendTimeline(activeNavItem, newMsgs)
          .then((r) => DEBUG_LOG && console.log(`[TIMELINE] +${newMsgs.length} message (server added=${r?.added})`))
        .catch((err) => {
          newMsgs.forEach((e) => syncedTimelineIdsRef.current.delete(e.client_id));
          DEBUG_LOG && console.warn("[TIMELINE] message append 실패 — 다음 변경 시 재시도", err);
        });
    }

    const hasPendingGen = proposalHistory.some((g) => !syncedTimelineIdsRef.current.has(`gen_${g.id}`));
    if (hasPendingGen) {
      if (genSaveTimerRef.current) clearTimeout(genSaveTimerRef.current);
      genSaveTimerRef.current = setTimeout(() => {
        const gens = proposalHistory
          .filter((g) => !syncedTimelineIdsRef.current.has(`gen_${g.id}`))
          .map((g) => ({ kind: "generation", client_id: `gen_${g.id}`, ts: g.ts, payload: g }));
        if (!gens.length) return;
        gens.forEach((e) => syncedTimelineIdsRef.current.add(e.client_id));
        videoService.appendTimeline(activeNavItem, gens)
          .then((r) => DEBUG_LOG && console.log(`[TIMELINE] +${gens.length} generation (server added=${r?.added})`))
          .catch((err) => {
            gens.forEach((e) => syncedTimelineIdsRef.current.delete(e.client_id));
            DEBUG_LOG && console.warn("[TIMELINE] generation append 실패 — 다음 변경 시 재시도", err);
          });
      }, 4000);
    }
  }, [activeNavItem, isSwitchingProject, storyPlan, proposalHistory]);

  // handleProposalPreview, handleProposalCommit moved to useProposalState

// handleReproposal moved to useProposalState

  const handleExport = useCallback(async (projectId: string) => {
    try {
      const res = await fetch(
        videoService.API_BASE_URL + "/export/final?project_id=" + projectId,
        { method: "POST" }
      );
      return await res.json();
    } catch (e) {
      console.error("내보내기 실패:", e);
      return { status: "ERROR", message: "서버 연결 오류" };
    }
  }, []);

  // Resize effect moved to useWorkspaceLayout

  // [STORY-TRACK-B] 조각 단위 공용 미니 플레이창 상태·핸들러 — handleEditFragmentClick보다
  // 먼저 선언(TDZ 방지: 아래 useCallback이 이걸 deps로 참조). A/B 듀얼 무접촉, sec canonical.
  const [miniTarget, setMiniTarget] = useState<MiniPlayTarget | null>(null);

  const handleEditFragmentClick = useCallback(
    (f: Fragment) => {
      setFragmentFocusOrigin("user");   // [PLAYSTABILITY-FIX-01 1번] 클릭은 시야로 따라간다
      // [TOGGLE-RESTORE 2026-08-01] `!modeGateOn &&` 제거 — 07-25 d86ccf8f 이 붙였고,
      //   게이트가 켜진 뒤로 재클릭 해제가 통째로 죽어 선택이 단방향이 됐다(퇴행).
      //   그 커밋("UI 정리 + 보류맵 원본 복원 + 대사 에디터 재연결")은 이 조건을 왜 걸었는지
      //   메시지·주석 어디에도 남기지 않았다 — 지키려던 것을 알 수 없어 **07-25 이전 동작을
      //   그대로 되돌린다**. 새 토글을 만들지 않는다(두 벌 금지).
      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
        setHighlightedPanoramaFrag(null);
        setExpandedFragment(null);
        setMiniTarget(null);  // [B-2] 재클릭 해제 시 미니 창도 닫는다
      } else {
        setSelectedFragment(f);
        // [LAYER-FIX3 2026-08-04 국장 지시] 원본맵이 그 소스로 갈아타야 조각이 화면에 있고,
        //   그래야 "나 여기 있어요"가 보인다. f.source_video 는 ★문자 라벨뿐이고 비어 있을 수
        //   있다(STATE-DRIFT 수리 때 source_id 폴백을 뺐다) — 비면 원본맵이 안 움직인다.
        //   실측: 텍스트조각은 일어나는데 이미지조각은 안 일어났다. 차이가 여기였다.
        //   handleCenterStoryFragmentFocus 와 같은 방식으로 source_id 로 라벨을 찾아 쓴다.
        const _label = (sourceEntries ?? []).find(
          (e) => e.source_id === (f as any).source_id,
        )?.label || f.source_video;
        if (_label) setActiveSource(_label);
        const highlightId = String((f as any).fragment_id ?? getUid(f));
        setHighlightedPanoramaFrag(highlightId);
        window.setTimeout(() => setHighlightedPanoramaFrag(highlightId), 0);
        setExpandedFragment(null);
      }
    },
    [modeGateOn, selectedFragment, sourceEntries]
  );

  // [2-2b] 조각편집 진입 (단일 조각 1개).
  const handleSingleFragmentEdit = useCallback(
    (f: Fragment) => {
      setSingleEditTarget(f);
      setSingleEditOpen(true);
      void refreshSoundRoles();
    },
    [refreshSoundRoles]
  );

  // [UI-②] 분석 후 영상 추가/제거 (모든 상태 선언 이후에 위치해야 TDZ 안전)
  const appendInputRef = useRef<HTMLInputElement>(null);
  const handleAnalyzeRef = useRef<((f?: File, ex?: File[]) => Promise<boolean>) | null>(null);
  useEffect(() => { handleAnalyzeRef.current = handleStartAnalysis; }); // 항상 최신 인스턴스
  const handleAppendFiles = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    e.target.value = "";
    if (files.length === 0) return;
    await handleAnalyzeRef.current?.(files[0], files.slice(1)); // append 모드는 handleAnalyze가 자동 감지
  }, []);

  const handleRemoveSource = useCallback(async (source: any) => {
    const label = source.label || source.source_id;
    setAppDialog({
      message: `영상 ${label}을(를) 이 프로젝트에서 빼시겠어요?\n(원본 파일과 조각은 보존됩니다)`,
      cancelText: "Cancel",
      onConfirm: async () => {
        try {
          if (activeNavItem && activeNavItem.startsWith("proj_")) {
            await fetch(`${videoService.API_BASE_URL}/projects/${activeNavItem}/sources/${source.source_id}`, { method: "DELETE" });
          }
          setSourceEntries((prev) => {
            const next = prev.filter((s) => s.source_id !== source.source_id);
            if (activeSource === label && next.length > 0) {
              setActiveSource(next[0].label);
              setSourceFragments(next[0].fragments);
              setEditFragments(next[0].fragments);
            }
            return next;
          });
          console.log(`[UI-?? source removed from project: ${source.source_id}`);
        } catch (err) {
          console.error("[UI-?? remove source failed:", err);
        }
      },
    });
  }, [activeNavItem, activeSource, setSourceEntries, setSourceFragments, setEditFragments, setActiveSource, setAppDialog]);

  const handleRenameSource = useCallback(async (source: SourceEntry, name: string) => {
    if (!source?.source_id) return;
    const res = await videoService.renameSource(source.source_id, name);
    if (res?.status !== "SUCCESS") return;
    const displayName = res.display_name ?? name ?? null;
    setSourceEntries((prev) => prev.map((s) => (
      s.source_id === source.source_id ? { ...s, display_name: displayName } : s
    )));
  }, [setSourceEntries]);

  // [EDIT-CONTRACT-B0 IMPL-2b] EDIT_CONTRACT_V2 게이트 — OFF면 아래 전 분기 기존 경로 그대로 (쓰기 0)
  const [editContractV2, setEditContractV2] = useState(false);
  const [editStatesList, setEditStatesList] = useState<EditStateRow[]>([]);
  const [localPbeContractStates, setLocalPbeContractStates] = useState<Record<string, PbeContractState>>({});
  const editStatesRef = useRef<Map<string, EditStateRow>>(new Map());
  const editCtxRef = useRef<{ enabled: boolean; programId: string | null }>({ enabled: false, programId: null });
  const refreshLedgerEdlRef = useRef<(() => Promise<void>) | null>(null);
  const [storyLedgerRefreshNonce, setStoryLedgerRefreshNonce] = useState(0);
  const [modeStoryTextItems, setModeStoryTextItems] = useState<Array<{
    fragmentId?: string | null;
    label?: string;
    dialogue?: string;
    stageDirection?: string;
    timelineItemId?: string;
    sourceId?: string;
    revision?: number | null;
    anchorStartMs?: number;
    anchorEndMs?: number;
    trimStartMs?: number;
    trimEndMs?: number;
    words?: Array<{ w: string; s_ms: number; e_ms: number; p?: number | null; excluded?: boolean }>;
    excludedRanges?: number[][];
  }>>([]);
  useEffect(() => {
    if (!modeGateOn || !activeNavItem || !activeNavItem.startsWith("proj_")) {
      setModeStoryTextItems([]);
      return;
    }
    let dead = false;
    fetch(`/api/ledger/${encodeURIComponent(activeNavItem)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (dead || !d?.ok) return;
        const sourceOrder = new Map((sourceEntries ?? []).map((s, i) => [s.source_id, i]));
        const perSource = new Map<string, number>();
        const rows = ((d.items ?? []) as any[])
          .filter((it) => !it.missing)
          .sort((a, b) => {
            const sourceCmp = (sourceOrder.get(a.source_id) ?? Number.MAX_SAFE_INTEGER) - (sourceOrder.get(b.source_id) ?? Number.MAX_SAFE_INTEGER);
            if (sourceCmp !== 0) return sourceCmp;
            return Number(a.anchor_start_ms ?? a.start_ms ?? 0) - Number(b.anchor_start_ms ?? b.start_ms ?? 0);
          })
          .map((it) => {
            const source = sourceEntries.find((s) => s.source_id === it.source_id);
            const sourceLabel = source?.label || "";
            const n = (perSource.get(sourceLabel) ?? 0) + 1;
            if (sourceLabel) perSource.set(sourceLabel, n);
            return {
              fragmentId: it.fragment_id ?? null,
              label: sourceLabel ? `${sourceLabel}${n}` : "",
              dialogue: fragmentTranscriptText(it),
              stageDirection: String(it.stage_direction ?? "").trim(),
              timelineItemId: it.timeline_item_id,
              sourceId: it.source_id,
              revision: it.revision ?? null,
              anchorStartMs: it.anchor_start_ms,
              anchorEndMs: it.anchor_end_ms,
              trimStartMs: it.trim_start_ms,
              trimEndMs: it.trim_end_ms,
              words: it.words ?? [],
              excludedRanges: it.excluded_ranges ?? [],
            };
          });
        setModeStoryTextItems(rows);
      })
      .catch(() => { if (!dead) setModeStoryTextItems([]); });
    return () => { dead = true; };
  }, [modeGateOn, activeNavItem, sourceEntries, storyLedgerRefreshNonce]);
  useEffect(() => { fetchGateEnabled().then(setEditContractV2); }, []);
  useEffect(() => { editCtxRef.current = { enabled: editContractV2, programId: activeNavItem }; }, [editContractV2, activeNavItem]);
  const refreshEditStates = useCallback(async (): Promise<EditStateRow[]> => {
    const ctx = editCtxRef.current;
    if (!ctx.enabled || !ctx.programId || !ctx.programId.startsWith("proj_")) return [];
    const states = await fetchEditStates(ctx.programId);
    editStatesRef.current = new Map(states.map((s) => [s.timeline_item_id, s]));
    setEditStatesList(states);
    return states;
  }, []);
  const refreshEditStatesRef = useRef(refreshEditStates);
  refreshEditStatesRef.current = refreshEditStates;
  // [R2 · STORY-LAYER-01 A-1] 표시 파생이 고를 상태 행 = 서버·클라 공통 발급식 그대로.
  // 제안키가 사라져 program+fid로 유일하므로, 구판의 'NA/B 분열'(같은 parent에 여러 행)이
  // 구조적으로 생기지 않는다. committedProposalId 의존이 없어져 effect 없이 상수 함수다.
  const preferredPbeItemIdFor = useCallback(
    (fid: string) => timelineItemIdFor(editCtxRef.current.programId ?? "", fid, 0),
    [],
  );
  const editStateForFragment = useCallback((fragment: Fragment): EditStateRow | null => {
    const fid = String((fragment as any).root_fragment_uid ?? (fragment as any).fragment_id ?? getUid(fragment));
    const candidates = Array.from(editStatesRef.current.values()).filter((state) => state.parent_fragment_id === fid);
    if (candidates.length === 0) return null;
    const preferred = preferredPbeItemIdFor(fid);
    return candidates.find((state) => state.timeline_item_id === preferred) ?? candidates[0];
  }, [preferredPbeItemIdFor]);
  const playImageFragmentInMini = useCallback(async (f: Fragment) => {
    const af = f as any;
    const sid = af.source_id ?? f.source_video;
    const url = af.video_url
      ?? (sourceEntries ?? []).find((e) => e.source_id === sid || e.label === sid)?.video_url;
    if (!url) return;
    const startSec = Number(af.start_sec ?? af.start_time ?? af.start ?? ((f.start_frame ?? 0) / 30));
    const endRaw = Number(af.end_sec ?? af.end_time ?? af.end ?? ((f.end_frame ?? 0) / 30));
    const endSec = endRaw > startSec ? endRaw : startSec + 1;
    const state = editStateForFragment(f);
    const spansMs = state?.spans ?? (Array.isArray(af.spans_ms) ? af.spans_ms : []);
    const editedSpans = spansMs
      .map(([s, e]: [number, number]) => [Number(s) / 1000, Number(e) / 1000] as [number, number])
      .filter(([s, e]: [number, number]) => Number.isFinite(s) && Number.isFinite(e) && e > s);
    const fallbackTarget = {
      videoUrl: url,
      spans: editedSpans.length > 0 ? editedSpans : [[startSec, endSec]] as [number, number][],
      fragmentId: f.fragment_id,
      label: af.display_id || undefined,
    };
    if (state && editedSpans.length > 1 && af.source_id) {
      try {
        const response = await fetch("/api/precision-preview", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            source_id: af.source_id,
            spans: spansMs,
          }),
        });
        const result = await response.json().catch(() => null);
        if (response.ok && result?.ok && result?.url && Number(result.duration_ms) > 0) {
          setMiniTarget({
            videoUrl: result.url,
            spans: [[0, Number(result.duration_ms) / 1000]],
            fragmentId: f.fragment_id,
            label: af.display_id || undefined,
          });
          return;
        }
      } catch {
        // Fail silent: the existing source seek preview remains available.
      }
    }
    setMiniTarget(fallbackTarget);
  }, [editStateForFragment, sourceEntries]);
  // [EDIT-CONTRACT-B0] PBE 재진입용 — DB state 우선, cutover 전에는 적용 세션 state로 복원.
  const sfeContractState = useMemo(() => {
    if (!singleEditTarget) return null;
    const persisted = editContractV2 ? editStateForFragment(singleEditTarget) : null;
    const fid = String((singleEditTarget as any).root_fragment_uid ?? (singleEditTarget as any).fragment_id ?? "");
    return persisted ?? localPbeContractStates[pbeContractKey(activeNavItem, fid)] ?? null;
  }, [activeNavItem, editContractV2, editStateForFragment, singleEditTarget, editStatesList, localPbeContractStates]);

  const sfePrecisionContext = useMemo(() => {
    if (!modeGateOn || !singleEditTarget || !activeNavItem) return null;
    const fid = String(
      (singleEditTarget as any).root_fragment_uid
      ?? (singleEditTarget as any).fragment_id
      ?? getUid(singleEditTarget),
    );
    const row = modeStoryTextItems.find((item) => item.fragmentId === fid);
    if (!row?.sourceId || !row.words?.length || !row.dialogue) return null;
    return {
      programId: activeNavItem,
      fragmentId: fid,
      sourceId: row.sourceId,
      text: row.dialogue,
      words: row.words,
    };
  }, [activeNavItem, modeGateOn, modeStoryTextItems, singleEditTarget]);
  const sfeSoundRole = useMemo(() => {
    if (!singleEditTarget) return null;
    const fid = String(
      (singleEditTarget as any).root_fragment_uid
      ?? (singleEditTarget as any).fragment_id
      ?? getUid(singleEditTarget),
    );
    return soundRoleItems.find((item) => item.fragment_id === fid) ?? null;
  }, [singleEditTarget, soundRoleItems]);

  const handleSingleFragmentApply = useCallback(
    (payload: {
      fragmentUid: string;
      newStartSec: number;
      newEndSec: number;
      origStart: number;
      origEnd: number;
      segments?: Array<{ startSec: number; endSec: number }>;
    }) => {
      const { fragmentUid, newStartSec, newEndSec, origStart, origEnd, segments } = payload;
      // [PBE-⑦] 중간 프레임 삭제 → 살아남는 구간이 2개 이상이면 조각을 분할한다.
      const isSplit = Array.isArray(segments) && segments.length > 1;

      const orig: any = editFragments.find((fr) => getUid(fr) === fragmentUid);
      const programId = editCtxRef.current.programId ?? activeNavItem;
      const rootFid = String(orig?.root_fragment_uid ?? orig?.fragment_id ?? fragmentUid);
      const segs = isSplit ? segments! : [{ startSec: newStartSec, endSec: newEndSec }];
      const { trim, excluded } = segmentsToExcludedMs(segs);
      const contractSnapshot: PbeContractState = {
        anchor_start_ms: toMs(Number(orig?.orig_start_sec ?? origStart)),
        anchor_end_ms: toMs(Number(orig?.orig_end_sec ?? origEnd)),
        trim_start_ms: trim[0],
        trim_end_ms: trim[1],
        excluded_ranges: excluded,
        removed: false,
      };
      setLocalPbeContractStates((prev) => ({
        ...prev,
        [pbeContractKey(programId, rootFid)]: contractSnapshot,
      }));

      if (editCtxRef.current.enabled) {
        // [R2] 배열 조작 금지 — 표시는 이벤트 누적이 아니라 상태의 순수 파생.
        // 저장 성공 → edit_state 최신값 확보 → 뿌리의 타일 전체를 파생 함수로 교체 (멱등).
        if (!orig?.source_id || !programId) {
          console.error("[EC-V2] edit-state 저장 불가: source_id/program 결손", { fragmentUid, programId });
          return;
        }
        // [STORY-LAYER-01 A-1] 사용본 ID는 제안과 무관 — 어느 안을 보고 있어도 같은 스토리에 쌓인다.
        const itemId = timelineItemIdFor(programId, rootFid, 0);
        const known = editStatesRef.current.get(itemId);
        postEditState({
          program_id: programId,
          timeline_item_id: itemId,
          source_id: orig.source_id,
          anchor_start_ms: contractSnapshot.anchor_start_ms,
          anchor_end_ms: contractSnapshot.anchor_end_ms,
          trim_start_ms: contractSnapshot.trim_start_ms,
          trim_end_ms: contractSnapshot.trim_end_ms,
          excluded_ranges: contractSnapshot.excluded_ranges,
          revision: known?.revision,
          parent_fragment_id: rootFid,
          command_type: isSplit ? "EXCLUDE_RANGE" : "TRIM",
          origin: "PBE",
        }).then(async (r: any) => {
          if (!r?.ok) {
            console.error("[EC-V2] edit-state 거부:", r);
            return;
          }
          const states = await refreshEditStatesRef.current();
          const prefer = (fid: string) => timelineItemIdFor(programId, fid, 0);
          const rebuilt = rebuildFragmentTiles(editFragments as any[], states, prefer) as typeof editFragments;
          setEditFragments(rebuilt);
          // 경계 편집은 '구성본'만 갱신한다 — 선택·순서(fids)는 사용자 결정이라 건드리지 않는다 (INV-0).
          applyStoryComposition(rebuilt);
          refreshLedgerEdlRef.current?.();
          setStoryLedgerRefreshNonce((n) => n + 1);
        }).catch((err) => console.error("[EC-V2] edit-state save error:", err));
        return;
      }

      // ── 레거시 (게이트 OFF) — 기존 flatMap + edit_overlay 경로 그대로 ──
      const next = editFragments.flatMap((fr) => {
        if (getUid(fr) !== fragmentUid) return [fr];
        if (!isSplit) {
          return [{
            ...fr,
            start_sec: newStartSec,
            end_sec: newEndSec,
            start_time: newStartSec,
            end_time: newEndSec,
            orig_start_sec: (fr as any).orig_start_sec ?? origStart,
            orig_end_sec:   (fr as any).orig_end_sec   ?? origEnd,
            trim_applied: true,
          }];
        }
        const rootId = (fr as any).root_fragment_uid ?? (fr as any).fragment_id ?? fragmentUid;
        return segments!.map((seg, k) => ({
          ...fr,
          fragment_id: `${(fr as any).fragment_id}_c${k + 1}`,
          fragment_uid: `${getUid(fr)}_c${k + 1}`,
          display_id: `${(fr as any).display_id ?? ""}${(fr as any).display_id ? `-${k + 1}` : ""}` || (fr as any).display_id,
          // [DISPLAY-NAME] 분할 파생 — 제목부 승계 + 시간부 새 구간으로 (낡은 구간 이름 승계 금지)
          display_name: rangeDisplayName((fr as any).display_name, seg.startSec, seg.endSec),
          start_sec: seg.startSec,
          end_sec: seg.endSec,
          start_time: seg.startSec,
          end_time: seg.endSec,
          start_frame: Math.round(seg.startSec * 30),
          end_frame: Math.round(seg.endSec * 30),
          orig_start_sec: (fr as any).orig_start_sec ?? origStart,
          orig_end_sec:   (fr as any).orig_end_sec   ?? origEnd,
          root_fragment_uid: rootId,
          trim_applied: true,
        }));
      });
      setEditFragments(next);

      // [F-2a-FIX] 편집 영속: edit_overlay 저장 — 레거시 경로 (게이트 OFF, 바이트 동일 행동)
      try {
        const editedList = next.filter((fr: any) =>
          getUid(fr) === fragmentUid || (isSplit && String(getUid(fr)).startsWith(`${fragmentUid}_c`))
        ) as any[];
        for (const edited of editedList) {
          if (!edited?.source_id) continue;
          videoService.upsertEditOverlay({
            source_id: edited.source_id,
            fragment_id: edited.fragment_id ?? fragmentUid,
            effective_start_sec: edited.start_sec ?? newStartSec,
            effective_end_sec: edited.end_sec ?? newEndSec,
            excluded: edited.excluded === true || edited.status === "removed",
            edit_type: isSplit ? "SPLIT" : "TRIM",
            root_fragment_id: edited.root_fragment_uid ?? edited.fragment_id ?? fragmentUid,
          }).catch((err) => console.error("edit-overlay save error:", err));
        }
      } catch (err) {
        console.error("edit-overlay save error:", err);
      }

      // 경계 편집(레거시 경로)도 구성본만 갱신 — 선택·순서는 사용자 결정 (INV-0).
      applyStoryComposition(next);
    },
    [editFragments]
  );

  const handleEditFragmentDoubleClick = useCallback((f: Fragment) => {
    setSelectedFragment(f);
    setActiveSource(f.source_video);
    setHighlightedPanoramaFrag(f.fragment_id);
    setExpandedFragment((prev) => (prev === f.fragment_id ? null : f.fragment_id));
  }, []);

  const handlePanoramaFragmentClick = useCallback(
    (f: Fragment) => {
      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
        setHighlightedPanoramaFrag(null);
        setMiniTarget(null);
      } else {
        setSelectedFragment(f);
        const label = (sourceEntries ?? []).find((e) => e.source_id === (f as any).source_id)?.label || f.source_video;
        if (label) setActiveSource(label);
        const highlightId = String((f as any).fragment_id ?? getUid(f));
        setHighlightedPanoramaFrag(highlightId);
        window.setTimeout(() => setHighlightedPanoramaFrag(highlightId), 0);
      }
    },
    [selectedFragment, sourceEntries]
  );

  // [STORY-TRACK-A A-4] 텍스트조각(우측 스토리 에디터) 클릭 → 원본맵 "나 여기있어".
  // source_id로 원본맵 소스를 맞추고(라벨 변환), fragment_id로 그 조각 강조.
  const handleTextFragmentFocus = useCallback(
    (fragmentId: string, sourceId: string) => {
      const label = (sourceEntries ?? []).find((e) => e.source_id === sourceId)?.label;
      if (label) setActiveSource(label);
      setHighlightedPanoramaFrag(fragmentId);
    },
    [sourceEntries, setActiveSource]
  );

  // [PLAYSTABILITY-FIX-01 1번] 조각 포커스의 출처. 시퀀스 진행이면 조각맵이 스크롤로 따라가지 않는다.
  //   재생 진행과 사용자 클릭이 둘 다 setSelectedFragment로 흐르므로 props만으로는 가를 수 없다.
  const [fragmentFocusOrigin, setFragmentFocusOrigin] = useState<"sequence" | "user">("user");

  const handleCenterStoryFragmentFocus = useCallback((fragmentId: string | null, origin: "sequence" | "user" = "user") => {
    if (!fragmentId) {
      // [SEQFRAGS-INV-01 4-4] 정지·종료 보고(id=null)는 사용자 선택이 아니다 — 출처를 바꾸지 않는다.
      //   구판은 여기서도 origin을 "user"로 올렸다. selectedFragment는 그대로 남아 있으므로
      //   시퀀스가 끝나는 순간 focusOrigin만 user로 뒤집혀 조각맵이 마지막 조각으로 1회 따라갔다
      //   — 실측: BOUNDARY_HIT(seqIdx=10) t=58553 직후 FragmentMap:122 2건(t=58570·58573).
      setHighlightedPanoramaFrag(null);
      return;
    }
    setFragmentFocusOrigin(origin);
    const all = [
      ...(editFragments ?? []),
      ...(sourceEntries ?? []).flatMap((e) => e.fragments ?? []),
    ];
    const frag = all.find((f: any) => getUid(f) === fragmentId || f.fragment_id === fragmentId);
    if (frag) {
      setSelectedFragment(frag);
      const label = (sourceEntries ?? []).find((e) => e.source_id === (frag as any).source_id)?.label || (frag as any).source_video;
      if (label) setActiveSource(label);
      const highlightId = String((frag as any).fragment_id ?? getUid(frag));
      setHighlightedPanoramaFrag(highlightId);
      window.setTimeout(() => setHighlightedPanoramaFrag(highlightId), 0);
      return;
    }
    setHighlightedPanoramaFrag(fragmentId);
  }, [editFragments, sourceEntries, setSelectedFragment, setActiveSource, setHighlightedPanoramaFrag, setFragmentFocusOrigin]);

  const roughCutFragmentPool = useMemo(() => {
    const byId = new Map<string, Fragment>();
    for (const fragment of [
      ...(editFragments ?? []),
      ...(sourceEntries ?? []).flatMap((entry) => entry.fragments ?? []),
    ]) {
      const uid = getUid(fragment);
      if (!byId.has(uid)) byId.set(uid, fragment);
    }
    return Array.from(byId.values());
  }, [editFragments, sourceEntries]);

  // [STORY-ANCHOR] 위쪽 fidAnchorsOf 가 읽는 ref — 풀이 바뀔 때마다 채운다.
  useEffect(() => { roughCutFragmentPoolRef.current = roughCutFragmentPool; }, [roughCutFragmentPool]);

  const roughCutFragmentForSpan = useCallback((span: RoughCutSpan): Fragment | null => {
    const spanStart = span.start_ms / 1000;
    const spanEnd = span.end_ms / 1000;
    let best: { fragment: Fragment; overlap: number; distance: number } | null = null;

    for (const fragment of roughCutFragmentPool) {
      const raw = fragment as any;
      if (String(raw.source_id ?? "") !== span.source_id) continue;
      const start = Number(raw.start_time ?? raw.start ?? ((fragment.start_frame ?? 0) / 30));
      const end = Number(raw.end_time ?? raw.end ?? ((fragment.end_frame ?? 0) / 30));
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
      const overlap = Math.max(0, Math.min(end, spanEnd) - Math.max(start, spanStart));
      const distance = Math.abs(((start + end) / 2) - ((spanStart + spanEnd) / 2));
      if (
        !best
        || overlap > best.overlap
        || (overlap === best.overlap && distance < best.distance)
      ) {
        best = { fragment, overlap, distance };
      }
    }
    return best && best.overlap > 0 ? best.fragment : null;
  }, [roughCutFragmentPool]);

  // [STORY-ANCHOR 2026-08-01] 원고 fid → 조각. fid 로 못 찾으면 **좌표로 다시 잇는다.**
  //   순서: ① fid 직접 매칭(기존 동작 그대로) ② 실패 시 좌표 재매칭 ③ 둘 다 실패면 버린다.
  //   ③이 중요하다 — 가까운 걸 아무거나 붙이지 않는다. 못 찾은 것은 못 찾은 것이다.
  //   재매칭은 새로 만들지 않고 계약의 rematchAnchor 를 부른다(editContract.ts:175,
  //   백엔드 edit_contract/edit_state.py:128 의 TS 미러 — 편집 상태가 쓰는 바로 그 함수).
  //   허용오차 STORY_REMATCH_TOL_MS 는 실측으로 정했다(감이 아니다):
  //     끊긴 원고 507건 중 vault 에 좌표가 남은 300건의 드리프트
  //       최소 0 · 중앙값 840ms · 90% 1840ms · 최대 2980ms
  //     tol 별 재연결/다중후보  500ms 28.3%/0 · 1000ms 62.0%/0 · 2000ms 97.7%/0 · 3000ms 100%/0
  //     ★ 모든 오차에서 **다중 후보 0건** — 양끝을 다 요구하므로 오매칭 위험이 관측되지 않았다.
  //     3000ms 로 잡으면 실측 전량이 복구되고, 그보다 크게 벌릴 이유는 없다.
  const STORY_REMATCH_TOL_MS = 3000;
  const roughCutFragmentsForFids = useCallback((fids: string[], anchors?: Record<string, any>) => {
    const byId = new Map(roughCutFragmentPool.map((fragment) => [getUid(fragment), fragment]));
    // 좌표 재매칭용 후보: 소스별로 시간순 정렬 (rematchAnchor 계약이 정렬을 요구한다)
    const bySource = new Map<string, Array<{ fragment: Fragment; range: [number, number] }>>();
    const coordsOf = (f: any): [number, number] | null => {
      const s = Number(f.start_time ?? f.start ?? (f.start_frame ?? 0) / 30);
      const e = Number(f.end_time ?? f.end ?? (f.end_frame ?? 0) / 30);
      if (!Number.isFinite(s) || !Number.isFinite(e) || e <= s) return null;
      return [toMs(s), toMs(e)];
    };
    if (anchors) {
      for (const fragment of roughCutFragmentPool) {
        const raw: any = fragment;
        const sid = String(raw.source_id ?? "");
        const range = coordsOf(raw);
        if (!sid || !range) continue;
        if (!bySource.has(sid)) bySource.set(sid, []);
        bySource.get(sid)!.push({ fragment, range });
      }
      for (const list of bySource.values()) list.sort((a, b) => a.range[0] - b.range[0]);
    }
    const out: Fragment[] = [];
    let rematched = 0;
    let lost = 0;
    for (const fid of fids) {
      const direct = byId.get(fid);
      if (direct) { out.push(direct); continue; }
      const anchor = anchors?.[fid];
      const list = anchor ? bySource.get(String(anchor.source_id)) : undefined;
      if (anchor && list?.length) {
        const idx = rematchAnchor(
          [Number(anchor.anchor_start_ms), Number(anchor.anchor_end_ms)],
          list.map((x) => x.range),
          STORY_REMATCH_TOL_MS,
        );
        if (idx !== null && idx >= 0) { out.push(list[idx].fragment); rematched++; continue; }
      }
      lost++;   // UNKNOWN — 억지로 붙이지 않는다
    }
    if (rematched || lost) {
      console.info(`[STORY-ANCHOR] 원고 ${fids.length}개 — fid 직행 ${fids.length - rematched - lost} `
        + `· 좌표 재연결 ${rematched} · 못 찾음 ${lost}(UNKNOWN, 억지 매핑 없음)`);
    }
    return out;
  }, [roughCutFragmentPool]);

  // [STORY-ANCHOR 2026-08-01] 치유: 복원된 원고에 현행 조각에 없는 fid 가 있으면
  //   저장해 둔 좌표로 **현 세대 fid 로 갈아 끼운다.** 프로젝트당 한 번만.
  //   여기서 고치는 이유: storyFids 를 읽는 곳이 조각맵·전사·가드·저장까지 여러 곳인데,
  //   각자 재연결하면 같은 일을 하는 자리가 여럿이 된다. 진실원 하나를 고친다.
  //   좌표가 없거나(옛 저장분) 좌표로도 못 찾으면 **그대로 둔다** — 억지로 붙이지 않는다.
  //   화면에서 사라지는 것은 예전과 같고, 다만 왜 사라졌는지 로그로 말한다.
  const storyHealedForRef = useRef<string | null>(null);
  useEffect(() => {
    const anchors = storyFidAnchorsRef.current;
    if (!activeNavItem?.startsWith("proj_")) return;
    if (storyHealedForRef.current === activeNavItem) return;
    if (!anchors || storyFids.length === 0 || roughCutFragmentPool.length === 0) return;
    const live = new Set(roughCutFragmentPool.map((f) => getUid(f)));
    const missing = storyFids.filter((f) => !live.has(f));
    if (missing.length === 0) { storyHealedForRef.current = activeNavItem; return; }
    const healed = roughCutFragmentsForFids(storyFids, anchors);
    const nextFids = healed.map((f) => getUid(f));
    storyHealedForRef.current = activeNavItem;
    if (nextFids.length === 0) {
      console.warn(`[STORY-ANCHOR] ${activeNavItem}: 끊긴 원고 ${missing.length}개를 좌표로도 잇지 못했다 — 원고를 비우지 않는다`);
      return;
    }
    if (JSON.stringify(nextFids) === JSON.stringify(storyFids)) return;
    console.info(`[STORY-ANCHOR] ${activeNavItem}: 원고 치유 ${storyFids.length} -> ${nextFids.length} `
      + `(끊겼던 ${missing.length}개 중 ${nextFids.length - (storyFids.length - missing.length)}개 좌표로 복구)`);
    setStoryFids(nextFids);
    storyFidsRef.current = nextFids;
  }, [activeNavItem, storyFids, roughCutFragmentPool, roughCutFragmentsForFids]);

  const roughCutSelectedSpanIds = useMemo(
    () => roughCutPlacement?.selectedSpanIds ?? roughCutData?.ordered_span_ids ?? [],
    [roughCutData?.ordered_span_ids, roughCutPlacement?.selectedSpanIds],
  );

  const persistRoughCutDecision = useCallback((fids: string[], selectedSpanIds: string[]) => {
    const programId = activeNavItem;
    const sourceIds = roughCutData?.owner?.source_ids;
    const inputHash = roughCutPlacement?.inputHash ?? roughCutData?.input_hash;
    if (!programId?.startsWith("proj_") || !sourceIds || !inputHash) {
      toast.error("가편집 변경을 저장하지 못했습니다.", {
        description: "프로젝트 소유권 정보를 확인할 수 없습니다.",
      });
      return Promise.resolve();
    }

    roughCutExplicitSaveSigRef.current = JSON.stringify([fids, selectedSpanIds]);
    const save = roughCutSaveQueueRef.current
      .catch(() => undefined)
      .then(async () => {
        try {
          const response = await fetch(
            `/api/rough-cut/project/${encodeURIComponent(programId)}/promote`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                source_ids: sourceIds,
                input_hash: inputHash,
                fids,
                selected_span_ids: selectedSpanIds,
              }),
            },
          );
          const body = await response.json().catch(() => null);
          if (!response.ok) {
            const detail = body?.detail;
            const reason = typeof detail === "string"
              ? detail
              : detail?.error || `HTTP ${response.status}`;
            throw new Error(String(reason));
          }
          toast.success("가편집 변경을 저장했습니다.");
        } catch (reason) {
          const message = reason instanceof Error ? reason.message : "unknown_error";
          console.error("[ROUGH-CUT-PROMOTE][FAIL]", message);
          toast.error("가편집 변경을 저장하지 못했습니다.", {
            description: message,
          });
        }
      });
    roughCutSaveQueueRef.current = save;
    return save;
  }, [
    activeNavItem,
    roughCutData?.input_hash,
    roughCutData?.owner?.source_ids,
    roughCutPlacement?.inputHash,
  ]);

  // 가편집은 기존 원고를 자동 확정하지 않는다. 배치 표식이 없는 프로젝트에서만
  // 화면용 씨앗으로 올리고, 첫 사용자 조작 뒤 기존 story.fids 저장 경로로 승격한다.
  useEffect(() => {
    if (!activeNavItem?.startsWith("proj_")) return;
    if (uiRestoredFor !== activeNavItem || !roughCutData || roughCutPlacement) return;
    if (roughCutData.project_id !== activeNavItem || roughCutFragmentPool.length === 0) return;

    const spansById = new Map(roughCutData.transcript.map((span) => [span.span_id, span]));
    const fragments: Fragment[] = [];
    const fids: string[] = [];
    for (const spanId of roughCutData.ordered_span_ids) {
      const span = spansById.get(spanId);
      const fragment = span ? roughCutFragmentForSpan(span) : null;
      if (!fragment) continue;
      const uid = getUid(fragment);
      if (fids.includes(uid)) continue;
      fids.push(uid);
      fragments.push(fragment);
    }
    if (fids.length === 0) return;

    setRoughCutPlacement({
      inputHash: roughCutData.input_hash ?? null,
      selectedSpanIds: roughCutData.ordered_span_ids,
    });
    setStoryFragments(fragments);
    setStoryFids(fids);
    storyFidsRef.current = fids;
    storyOriginRef.current = "server";
    console.info(`[ROUGH-CUT-PLACEMENT] ${activeNavItem}: 전사 ${roughCutData.eligible_count}개 중 ${fids.length}조각을 화면 씨앗으로 배치 (저장 안 함)`);
  }, [
    activeNavItem,
    roughCutData,
    roughCutFragmentForSpan,
    roughCutFragmentPool.length,
    roughCutPlacement,
    uiRestoredFor,
  ]);

  const handleRoughCutSpanAdd = useCallback((span: RoughCutSpan) => {
    const fragment = roughCutFragmentForSpan(span);
    if (!fragment) return;
    const fid = getUid(fragment);

    // [LAYER-FIX3 2026-08-04 국장 지시] 전사에서 고른 조각도 "나 여기 있어요" 하고 일어난다.
    //   ★어제 배선은 setHighlightedPanoramaFrag(fid) 하나만 세워서 아무 일도 안 났다.
    //     작동하던 길(텍스트조각 클릭)과 비교해 보니 네 가지가 빠져 있었다:
    //       (1) setSelectedFragment — 조각맵이 무엇을 가리킬지는 이 값이 정한다
    //       (2) setActiveSource     — 원본맵이 그 소스로 갈아타야 조각이 화면에 있다
    //       (3) fragment_id         — 원본맵 data-fid 는 getUid 가 아니라 이 값이다 (★진짜 원인)
    //       (4) setTimeout(...,0)   — 같은 id 를 다시 눌러도 effect 가 돌게 하는 재발화
    //   그래서 값을 직접 세우지 않고 ★이미 검증된 그 길을 그대로 부른다. 길이 하나여야
    //   전사·텍스트조각·이미지조각·원본맵이 같은 규칙으로 움직인다(국장 지시: 모두 연동).
    handleCenterStoryFragmentFocus(String((fragment as any).fragment_id ?? fid), "user");

    // [TOGGLE-RESTORE-2 2026-08-01] 전사도 재클릭으로 해제된다.
    //   조각맵(handleEditFragmentClick)에는 토글이 있었는데(07-25 게이트에 막혔다가
    //   18af4fb2 에서 복원) 전사에는 **애초에 없었다** — 도입 커밋 503e5d48
    //   "중앙 전사를 스토리 선택면으로 전환"부터 add-only 설계였다(git log -S 확인).
    //   그래서 배지가 붙으면 전사에서는 뺄 방법이 없었다. 조각맵과 같은 방식으로 맞춘다.
    //   판정 기준은 화면과 같은 것을 쓴다: 그 조각이 story 에 들어가 있는가(fid).
    //   RoughCutOutline 의 배지도 fid 기준(selectedOrderByFragment)이므로 눈과 코드가 일치한다.
    if (storyFidsRef.current.includes(fid)) {
      const nextFids = storyFidsWithout(fid);
      // 그 조각에 딸린 span 들만 선택에서 뺀다 — 다른 조각의 선택은 건드리지 않는다.
      const spanById = new Map((roughCutData?.transcript ?? []).map((s) => [s.span_id, s]));
      const selectedSpanIds = roughCutSelectedSpanIds.filter((spanId) => {
        const s = spanById.get(spanId);
        if (!s) return true;                       // 모르는 span 은 남긴다(임의 삭제 금지)
        const f = roughCutFragmentForSpan(s);
        return !f || getUid(f) !== fid;
      });
      setRoughCutPlacement({
        inputHash: roughCutPlacement?.inputHash ?? roughCutData?.input_hash ?? null,
        selectedSpanIds,
      });
      applyStory(roughCutFragmentsForFids(nextFids), nextFids);
      void persistRoughCutDecision(nextFids, selectedSpanIds);
      return;
    }

    const selectedSpanIds = roughCutSelectedSpanIds.includes(span.span_id)
      ? roughCutSelectedSpanIds
      : [...roughCutSelectedSpanIds, span.span_id];
    const nextFids = storyFidsWith(fid);
    setRoughCutPlacement({
      inputHash: roughCutPlacement?.inputHash ?? roughCutData?.input_hash ?? null,
      selectedSpanIds,
    });
    applyStory(roughCutFragmentsForFids(nextFids), nextFids);
    void persistRoughCutDecision(nextFids, selectedSpanIds);
  }, [
    applyStory,
    persistRoughCutDecision,
    roughCutData?.input_hash,
    roughCutFragmentForSpan,
    roughCutFragmentsForFids,
    roughCutPlacement?.inputHash,
    roughCutSelectedSpanIds,
    storyFidsWith,
    storyFidsWithout,
    roughCutData?.transcript,
    handleCenterStoryFragmentFocus,
  ]);

  const orderRoughCutSpanIds = useCallback((fids: string[], spanIds: string[]) => {
    if (!roughCutData) return spanIds;
    const spanById = new Map(roughCutData.transcript.map((span) => [span.span_id, span]));
    const rank = new Map(fids.map((fid, index) => [fid, index]));
    return spanIds
      .map((spanId, originalIndex) => {
        const span = spanById.get(spanId);
        const fragment = span ? roughCutFragmentForSpan(span) : null;
        return {
          spanId,
          originalIndex,
          rank: fragment ? (rank.get(getUid(fragment)) ?? Number.MAX_SAFE_INTEGER) : Number.MAX_SAFE_INTEGER,
        };
      })
      .sort((a, b) => a.rank - b.rank || a.originalIndex - b.originalIndex)
      .map((item) => item.spanId);
  }, [roughCutData, roughCutFragmentForSpan]);

  const handleRoughCutStoryReorder = useCallback((reorderedFragments: Fragment[]) => {
    const nextFids = reorderedFragments.map((fragment) => getUid(fragment));
    const nextSpanIds = orderRoughCutSpanIds(nextFids, roughCutSelectedSpanIds);
    setRoughCutPlacement({
      inputHash: roughCutPlacement?.inputHash ?? roughCutData?.input_hash ?? null,
      selectedSpanIds: nextSpanIds,
    });
    applyStory(reorderedFragments, nextFids);
    void persistRoughCutDecision(nextFids, nextSpanIds);
  }, [
    applyStory,
    orderRoughCutSpanIds,
    persistRoughCutDecision,
    roughCutData?.input_hash,
    roughCutPlacement?.inputHash,
    roughCutSelectedSpanIds,
  ]);

  const handleRoughCutStoryRemove = useCallback((fragment: Fragment) => {
    const uid = getUid(fragment);
    const nextFids = storyFidsWithout(uid);
    const spanById = new Map((roughCutData?.transcript ?? []).map((span) => [span.span_id, span]));
    const nextSpanIds = roughCutSelectedSpanIds.filter((spanId) => {
      const span = spanById.get(spanId);
      const mapped = span ? roughCutFragmentForSpan(span) : null;
      return !mapped || getUid(mapped) !== uid;
    });
    setRoughCutPlacement({
      inputHash: roughCutPlacement?.inputHash ?? roughCutData?.input_hash ?? null,
      selectedSpanIds: nextSpanIds,
    });
    applyStory(roughCutFragmentsForFids(nextFids), nextFids);
    void persistRoughCutDecision(nextFids, nextSpanIds);
  }, [
    applyStory,
    persistRoughCutDecision,
    roughCutData,
    roughCutFragmentForSpan,
    roughCutFragmentsForFids,
    roughCutPlacement?.inputHash,
    roughCutSelectedSpanIds,
    storyFidsWithout,
  ]);

  const handleRoughCutStoryInsert = useCallback((fragment: Fragment, insertAt?: number) => {
    const uid = getUid(fragment);
    const nextFids = storyFidsWith(uid, insertAt);
    let nextSpanIds = roughCutSelectedSpanIds;
    if (roughCutData) {
      const representative = roughCutData.transcript.find((span) => {
        const mapped = roughCutFragmentForSpan(span);
        return mapped && getUid(mapped) === uid;
      });
      if (representative && !nextSpanIds.includes(representative.span_id)) {
        nextSpanIds = [...nextSpanIds, representative.span_id];
      }
    }
    nextSpanIds = orderRoughCutSpanIds(nextFids, nextSpanIds);
    setReservedFragments((prev) => removeByUid(prev, fragment));
    setDeletedFragments((prev) => removeByUid(prev, fragment));
    setRoughCutPlacement({
      inputHash: roughCutPlacement?.inputHash ?? roughCutData?.input_hash ?? null,
      selectedSpanIds: nextSpanIds,
    });
    applyStory(roughCutFragmentsForFids(nextFids), nextFids);
    void persistRoughCutDecision(nextFids, nextSpanIds);
  }, [
    applyStory,
    orderRoughCutSpanIds,
    persistRoughCutDecision,
    removeByUid,
    roughCutData,
    roughCutFragmentForSpan,
    roughCutFragmentsForFids,
    roughCutPlacement?.inputHash,
    roughCutSelectedSpanIds,
    setDeletedFragments,
    setReservedFragments,
    storyFidsWith,
  ]);

  // [STORY-TRACK-B] 조각 단위 공용 미니 플레이창 — 텍스트·이미지 어디서 클릭해도 이 창 하나.
  const handleReservedClick = useCallback(
    (f: Fragment) => {
      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
        setHighlightedPanoramaFrag(null);
      } else {
        setSelectedFragment(f);
        setActiveSource(f.source_video);
        const highlightId = String((f as any).fragment_id ?? getUid(f));
        setHighlightedPanoramaFrag(highlightId);
        window.setTimeout(() => setHighlightedPanoramaFrag(highlightId), 0);
      }
    },
    [selectedFragment]
  );

  // ── [STORY-LAYER-01 A-1] 스토리 구성 핸들러 — 전부 applyStory 하나로 쓴다 ──
  // 구판은 각자 `committedProposalId`가 있을 때만 `proposals[target].key_fragments`에 썼다.
  // 그래서 (a) 제안을 확정하기 전 편집은 어디에도 남지 않고, (b) A와 B가 다른 이야기를 가졌다.
  const handleExcludeFromEdit = useCallback((f: Fragment) => {
    const next = editFragments.map((fr) => (getUid(fr) === getUid(f) ? { ...fr, excluded: true } : fr));
    setEditFragments(next);
    applyStory(next, storyFidsWithout(getUid(f)));
  }, [editFragments, applyStory, storyFidsWithout]);

  const handleRestoreFragment = useCallback((f: Fragment) => {
    const next = editFragments.map((fr) => (getUid(fr) === getUid(f) ? { ...fr, excluded: false } : fr));
    setEditFragments(next);
    applyStory(next, storyFidsWith(getUid(f)));
  }, [editFragments, applyStory, storyFidsWith]);

  const handleMoveToHold = useCallback(
    (f: Fragment) => {
      setReservedFragments((prev) => appendUniqueByUid(prev, { ...f, excluded: false }));
      const next = removeByUid(editFragments, f);
      setEditFragments(next);
      applyStory(next, storyFidsWithout(getUid(f)));

      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
      }
    },
    [appendUniqueByUid, removeByUid, selectedFragment, editFragments, applyStory, storyFidsWithout, setReservedFragments, setSelectedFragment]
  );

  const handleDropToHold = useCallback(
    (fragId: string, position?: { x: number; y: number }, frag?: Fragment) => {
      // [DROPPOS-FIX B] 조각맵 조각은 editFragments에서 찾고, 원본맵 소스조각은 넘겨받은 frag로 폴백.
      const target = editFragments.find((f) => getUid(f) === fragId) ?? frag;
      if (!target) return;
      if (position) {
        setHoldPositions((prev) => ({ ...prev, [fragId]: position }));
      }
      handleMoveToHold(target);
    },
    [editFragments, handleMoveToHold]
  );

  const handleRoughCutDropToHold = useCallback(
    (fragId: string, position?: { x: number; y: number }, frag?: Fragment) => {
      const target = roughCutFragmentPool.find((fragment) => getUid(fragment) === fragId) ?? frag;
      if (!target) return;
      if (position) {
        setHoldPositions((prev) => ({ ...prev, [fragId]: position }));
      }
      setReservedFragments((prev) => appendUniqueByUid(prev, { ...target, excluded: false }));
      handleRoughCutStoryRemove(target);
    },
    [
      appendUniqueByUid,
      handleRoughCutStoryRemove,
      roughCutFragmentPool,
      setHoldPositions,
      setReservedFragments,
    ],
  );

  const handleDeleteById = useCallback(
    (fid: string) => {
      const fromReserved = reservedFragments.find((f) => getUid(f) === fid);
      if (fromReserved) {
        setReservedFragments((prev) => prev.filter((f) => getUid(f) !== fid));
        setDeletedFragments((prev) => appendUniqueByUid(prev, fromReserved));
        return;
      }

      const fromEdit = editFragments.find((f) => getUid(f) === fid);
      if (fromEdit) {
        const next = editFragments.filter((f) => getUid(f) !== fid);
        setEditFragments(next);
        applyStory(next, storyFidsWithout(fid));
        setDeletedFragments((prev) => appendUniqueByUid(prev, fromEdit));
      }
    },
    [appendUniqueByUid, editFragments, reservedFragments, applyStory, storyFidsWithout, setDeletedFragments, setReservedFragments]
  );

  const handleFragmentsReorder = useCallback(
    (reorderedFrags: Fragment[]) => {
      setEditFragments(reorderedFrags);
      // 순서는 사용자 결정 그 자체 — 제안 확정 여부와 무관하게 스토리에 남는다.
      applyStory(reorderedFrags, reorderedFrags.map((f) => f.fragment_id));
    },
    [applyStory]
  );

  const handleRestoreFromHold = useCallback(
    (f: Fragment, insertAt?: number) => {
      setReservedFragments((prev) => removeByUid(prev, f));

      const already = editFragments.some((x) => getUid(x) === getUid(f));
      if (already) return;
      
      const newFrag = { ...f, excluded: false };
      let next: Fragment[] = [];
      if (insertAt === undefined) {
        next = [...editFragments, newFrag];
      } else {
        const arr = [...editFragments];
        arr.splice(insertAt, 0, newFrag);
        next = arr;
      }
      setEditFragments(next);
      applyStory(next, storyFidsWith(getUid(f), insertAt));
    },
    [removeByUid, editFragments, applyStory, storyFidsWith, setReservedFragments]
  );

  const handleAddFromSource = useCallback(
    (f: Fragment, insertAt?: number) => {
      if (editFragments.some((x) => getUid(x) === getUid(f))) return;

      const newFrag: Fragment = {
        ...f,
        excluded: false,
      };

      let next: Fragment[];
      if (insertAt === undefined) {
        next = [...editFragments, newFrag];
      } else {
        const arr = [...editFragments];
        arr.splice(insertAt, 0, newFrag);
        next = arr;
      }
      setEditFragments(next);
      setReservedFragments((prev) => removeByUid(prev, f));
      applyStory(next, storyFidsWith(getUid(f), insertAt));
    },
    [editFragments, removeByUid, applyStory, storyFidsWith, setReservedFragments]
  );

  const handleDeleteFromHold = useCallback(
    (f: Fragment) => {
      setReservedFragments((prev) => removeByUid(prev, f));
      setDeletedFragments((prev) => appendUniqueByUid(prev, f));

      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
      }
    },
    [appendUniqueByUid, removeByUid, selectedFragment]
  );

  const handleRestoreToHold = useCallback(
    (f: Fragment) => {
      setDeletedFragments((prev) => removeByUid(prev, f));
      setReservedFragments((prev) => appendUniqueByUid(prev, { ...f, excluded: false }));
    },
    [appendUniqueByUid, removeByUid]
  );

  const handleRestoreToEdit = useCallback(
    (f: Fragment, insertAt?: number) => {
      setDeletedFragments((prev) => removeByUid(prev, f));

      const already = editFragments.some((x) => getUid(x) === getUid(f));
      if (already) return;
      
      const newFrag = { ...f, excluded: false };
      let next: Fragment[] = [];
      if (insertAt === undefined) {
        next = [...editFragments, newFrag];
      } else {
        const arr = [...editFragments];
        arr.splice(insertAt, 0, newFrag);
        next = arr;
      }
      setEditFragments(next);
      applyStory(next, storyFidsWith(getUid(f), insertAt));
    },
    [removeByUid, editFragments, applyStory, storyFidsWith, setDeletedFragments]
  );

  // [#23 (가) 병합] mergeIntoPool 제거 — 유일 소비처가 'A/B 토글 시 각 안의 구성본을 웅덩이에
  // 재주입'하던 effect였고, 그 재주입이 A와 B가 다른 이야기를 갖게 만든 실행 경로였다.
  // 스토리가 program 단위 하나가 된 뒤로는 되돌릴 '각 안의 구성본'이 존재하지 않는다.

  // [STORY-WRITE-GUARD-01 2-2] 서버 원고를 화면용으로만 싣는다 (저장 자격 없음).
  //   ui_state에 스토리가 없는 프로젝트(신규·분석 직후)도 원고가 보여야 한다. 서버가
  //   resolve_sequence로 답한 목록을 읽어 화면에 세우고, 출처를 'server'로 찍는다.
  //   'server' 표식이면 저장 effect가 진입을 거부한다 — 폴백이 스토리로 굳는 경로 차단.
  useEffect(() => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return;
    if (uiRestoredFor !== activeNavItem) return;      // 재수화 끝난 뒤에만
    if (storyFidsRef.current.length > 0) return;      // 이미 스토리가 있으면 건드리지 않는다
    let dead = false;
    (async () => {
      const res = await fetch(`/api/ledger/${encodeURIComponent(activeNavItem)}`).then((r) => (r.ok ? r.json() : null)).catch(() => null);
      if (dead || !res?.ok) return;
      const fids = (res.items ?? [])
        .filter((it: any) => it.selected && !it.missing)
        .map((it: any) => String(it.fragment_id));
      if (fids.length === 0 || storyFidsRef.current.length > 0) return;
      setStoryFids(fids);
      storyOriginRef.current = "server";
      console.info(`[STORY-LOAD] ${activeNavItem}: 서버 원고 ${fids.length}조각 (출처=server · 저장 금지)`);
    })();
    return () => { dead = true; };
  }, [activeNavItem, uiRestoredFor]);

  // [STORY-WRITE-GUARD-01 2-1] 씨앗(seed) 폐기 — 금지 목록에 명시된 자동 쓰기다.
  //   구판 씨앗은 제안(A/B)에서 storyFids를 채웠다. 사용자가 고른 적 없는 목록이
  //   저장 경로로 흘러 '스토리'가 됐다. 이제 원고는 서버가 만든다:
  //   story_gate.resolve_sequence 가 ui_state → proposals → 조각(시간순) 순으로 답하므로
  //   씨앗 없이도 원고는 항상 뜬다. 화면은 그것을 '읽기'만 하고, 저장은 사용자 행위에서만.

  // [STORY-LAYER-01 A-1] 조각맵·전사의 재료는 **스토리**다 — 제안 선택과 무관하다.
  // 구판은 `if (!displayProposalId || !proposals) return []`로 제안이 없으면 조각을 0개로
  // 만들었다(=제안을 눌러야 조각이 보이던 원인). 스토리는 program 단위로 항상 존재한다.
  // 좌표·분할 복원용 alias는 A·B 양쪽을 합친 '프로그램 단위 풀'로 쓴다 — 어느 안을 골랐는지가
  // 스토리 해석을 바꾸면 안 되므로(INV-1/2), 선택이 아니라 합집합이다.
  const storyAliasPool = useMemo(() => [
    ...(((proposals as any)?.A?.resolved_aliases) ?? []),
    ...(((proposals as any)?.B?.resolved_aliases) ?? []),
  ], [proposals]);
  const storyForResolve = useMemo(
    () => ({ id: "STORY", key_fragments: storyFids, resolved_aliases: storyAliasPool }),
    [storyFids, storyAliasPool],
  );
  const resolverResult = useMemo(() => {
    if (storyFids.length === 0) {
      if (appState === "complete") {
        debugFragmentMap("[fragmentmap-debug] story empty — storyFids 0 (씨앗 대기)");
      }
      return { resolvedFragments: [], diagnostics: null };
    }
    const result = resolveProposalFragments(storyForResolve as any, editFragments, { expandAll: editContractV2 });

    // [STEP 10-I.5.12] Diagnostic Logging
    debugFragmentMap("[fragmentmap-debug] storyFids:", { count: storyFids.length, first10: storyFids.slice(0, 10) });
    debugFragmentMap("[fragmentmap-debug] displayProposalId (표시 방식):", displayProposalId);
    debugFragmentMap("[fragmentmap-debug] editFragments summary:", {
      count: editFragments.length,
      first10Ids: editFragments.slice(0, 10).map(f => f.fragment_id)
    });
    debugFragmentMap("[fragmentmap-debug] resolvedFragments summary:", {
      count: result.resolvedFragments.length,
      first10Ids: result.resolvedFragments.slice(0, 10).map(f => f.fragment_id)
    });

    return result;
  }, [storyForResolve, storyFids, editFragments, appState, debugFragmentMap, editContractV2, displayProposalId]);

  const isPreviewingSelectedProposal = !!displayProposalId && displayProposalId === selectedProposalId && !committedProposalId;
  const resolvedFragments = useMemo(() => {
    let nextFragments = resolverResult.resolvedFragments;
    if (storyFids.length > 0 && resolverResult.diagnostics?.missingIds?.length) {
      const proposalFragIds = storyFids;
      const aliases = storyAliasPool;
      const resolvedByAlias = new Map<string, typeof resolverResult.resolvedFragments[number]>();

      for (const fragment of resolverResult.resolvedFragments) {
        for (const alias of collectFragmentAliases(fragment)) {
          resolvedByAlias.set(alias, fragment);
        }
      }

      nextFragments = proposalFragIds
        .map((id: string, index: number) => {
          const resolved = resolvedByAlias.get(id);
          if (resolved) return resolved;

          const alias = aliases.find((item: any) =>
            item.proposal_fragment_id === id || item.source_fragment_id === id
          );
          if (!alias) return null;

          const startSec = Number(alias.start_sec ?? 0);
          const endSec = Number(alias.end_sec ?? (startSec + 5));
          const startFrame = Math.round(startSec * 30);
          const endFrame = Math.max(startFrame + 1, Math.round(endSec * 30));
          const sourceEntry = sourceEntries.find((entry) => entry.source_id === alias.source_id);
          const sourceFragment = sourceEntry?.fragments?.find((fragment: any) =>
            collectFragmentAliases(fragment).includes(id)
          );
          const sourceLabel = sourceEntry?.label;

          return {
            fragment_id: id,
            fragment_uid: id,
            root_fragment_uid: id,
            display_id: sourceFragment?.display_id || alias.display_id || id,
            // [DISPLAY-NAME] 제안 복원 경로에도 백엔드 권위 이름 통과 (조각맵→PBE 승계)
            display_name: sourceFragment?.display_name,
            selection_state: "S" as SelectionState,
            status: "committed" as FragmentStatus,
            // [STATE-DRIFT 수리 2026-07-22] source_id 폴백 제거 — source_video엔 문자 라벨만.
            source_video: sourceLabel || "",
            source_id: alias.source_id,
            start_time: startSec,
            end_time: endSec,
            start_frame: startFrame,
            end_frame: endFrame,
            duration: endFrame - startFrame,
            thumbnail_hue: index % 2 === 0 ? 211 : 30,
            thumbnail: {
              thumbnail_url: toFullUrl(sourceFragment?.thumbnail?.thumbnail_url || sourceFragment?.thumbnail_url || alias.thumbnail_url),
            },
            intelligence: {
              hook_score: 0.5,
              role: "Main",
              description: "",
            },
            preview_clip_url: null,
            stable_key: `STORY_${index}_${id}`,
          } as any;
        })
        .filter(Boolean);
    }

    const editAppliedFragments = editContractV2 && editStatesList.length
      ? (rebuildFragmentTiles(nextFragments as any[], editStatesList, preferredPbeItemIdFor) as typeof nextFragments)
      : nextFragments;

    if (!isPreviewingSelectedProposal) return editAppliedFragments;
    return editAppliedFragments.map((fragment) => ({
      ...fragment,
      excluded: false,
      selection_state: "S" as SelectionState,
      status: "committed" as FragmentStatus,
    }));
  }, [resolverResult, storyFids, storyAliasPool, sourceEntries, toFullUrl, isPreviewingSelectedProposal, editContractV2, editStatesList, preferredPbeItemIdFor]);

  // [STORY-LAYER-01 A-1] 구성본(storyFragments)이 아직 비어 있으면 현재 파생본을 구성본으로 승격.
  // 백엔드 좌표 폴백(ledger_r0 `snapshot_coords`)의 재료다 — 구판에서 A/B 토글 effect가
  // customEditFragments에 initialFrags를 처음 적재해 준 역할을 여기서 대신한다(D8 폴백 유지).
  // resolver는 storyFragments를 읽지 않으므로 순환하지 않는다.
  useEffect(() => {
    if (storyFragments.length > 0 || resolvedFragments.length === 0) return;
    applyStoryComposition(resolvedFragments as unknown as Fragment[]);
  }, [resolvedFragments, storyFragments.length, applyStoryComposition]);

  const [ledgerEdlClips, setLedgerEdlClips] = useState<PhysicalClip[]>([]);
  // [EDL-NO-RESURRECT] EDL 취득 결과를 '성공/실패/미조회'로 구분한다.
  //   구판은 실패도 빈 배열로 눕혀, 아래 폴백이 그것을 '조각 0개'로 읽고 원본을 되살렸다.
  const [ledgerEdlStatus, setLedgerEdlStatus] = useState<"idle" | "ok" | "error">("idle");
  const refreshLedgerEdl = useCallback(async () => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) {
      setLedgerEdlClips([]);
      setLedgerEdlStatus("idle");
      return;
    }
    try {
      const res = await fetch(`/api/ledger/${encodeURIComponent(activeNavItem)}/edl`);
      const edl = await res.json();
      const clips = Array.isArray(edl?.clips) ? edl.clips : [];
      setLedgerEdlClips(
        clips
          .map((clip: any, idx: number) => {
            const start = Number(clip.start_sec ?? 0);
            const end = Number(clip.end_sec ?? start);
            const duration = Number(clip.duration_sec ?? Math.max(0, end - start));
            return {
              order: Number(clip.order ?? idx),
              source_id: String(clip.source_id ?? ""),
              start_sec: Number(start.toFixed(3)),
              end_sec: Number(end.toFixed(3)),
              duration_sec: Number((Number.isFinite(duration) ? duration : Math.max(0, end - start)).toFixed(3)),
              fragment_id: String(clip.fragment_id ?? clip.clip_of ?? `clip_${idx}`),
              display_id: String(clip.clip_of ?? clip.fragment_id ?? `clip_${idx}`),
              video_url: clip.video_url,
              clip_of: clip.clip_of,
            } as PhysicalClip & { video_url?: string; clip_of?: string };
          })
          .filter((clip: PhysicalClip) => clip.source_id && clip.end_sec > clip.start_sec)
      );
      setLedgerEdlStatus("ok");
    } catch (e) {
      // [EDL-NO-RESURRECT] 취득 실패를 '조각 0개'와 같이 다루지 않는다 — 아래 폴백 차단의 근거.
      setLedgerEdlClips([]);
      setLedgerEdlStatus("error");
      console.error(`[EDL] 취득 실패 — 내보내기용 조각을 만들지 않는다(부활 금지). program=${activeNavItem}`, e);
    }
  }, [activeNavItem]);
  refreshLedgerEdlRef.current = refreshLedgerEdl;

  useEffect(() => { void refreshLedgerEdl(); }, [refreshLedgerEdl]);

  const physicalClips = useMemo(() => {
    if (ledgerEdlClips.length) return ledgerEdlClips;
    // [EDL-NO-RESURRECT] EDL 이 0건이거나 취득에 실패했을 때 resolvedFragments 로 되살리지 않는다.
    //   구판 폴백은 사용자가 전부 제거한 영상을 되살리고, 조각 내부 제외(EXCLUDE_RANGE)도
    //   단일 외피로 복원해 편집이 통째로 사라진 결과물을 내보냈다.
    //   폴백이 정당하게 필요한 소비처는 없다(확인):
    //     · 재생 — CenterPanel:1271 backendEdlApplies 가 이미 clips>0 을 요구하고,
    //       비면 제안 기반 경로로 내려간다(자체 폴백 보유).
    //     · 내보내기 — CenterPanel:1935 가 확정본을 요구하므로 EDL 이 있어야 정상이고,
    //       비면 "확정된 조각이 없습니다"로 멈춘다(침묵 아님).
    //   즉 이 폴백은 부활 외에 하는 일이 없었다.
    if (ledgerEdlStatus !== "idle") {
      console.warn(
        `[EDL] 내보낼 조각이 없습니다 — 원본으로 되살리지 않습니다 `
        + `(status=${ledgerEdlStatus}, edl=0, 조각맵=${resolvedFragments.length}).`
      );
    }
    return [] as PhysicalClip[];
  }, [ledgerEdlClips, ledgerEdlStatus, resolvedFragments.length]);

  // [LAYER-SPLIT 3-B 2026-08-04 국장 확정 ⑤] 편집미리보기 — 조각맵 전체의 편집 결과를 이어서 재생.
  //   ★새 플레이어를 만들지 않는다. 조각 플레이창(FragmentMiniPlayer)이 이미 다중 구간을 받는다.
  //   ★출처는 EDL(physicalClips)이다 — 조각 순서·trim·구간 제외가 이미 반영된 '계산 결과'.
  //     조각맵 배열에서 직접 만들면 편집이 빠진 것을 미리보기라고 보여주게 된다.
  //   ★미니창은 videoUrl 하나만 받는다. 여러 소스가 섞이면 첫 소스분만 재생하고
  //     빠진 수를 말한다 — 조용히 잘라내지 않는다.
  const handlePreviewEdit = useCallback(() => {
    if (!physicalClips.length) {
      toast.error("미리볼 편집 결과가 없습니다.", {
        description: "조각을 고르고 저장하면 만들어집니다.",
      });
      return;
    }
    const firstSource = physicalClips[0].source_id;
    const mine = physicalClips.filter((c) => c.source_id === firstSource);
    const skipped = physicalClips.length - mine.length;
    const urlMap = Object.fromEntries(
      (sourceEntries ?? []).flatMap((e) => [[e.source_id, e.video_url], [e.label, e.video_url]]).filter(([, v]) => v),
    ) as Record<string, string>;
    const rawUrl = urlMap[firstSource];
    if (!rawUrl) {
      toast.error("영상 주소를 찾지 못했습니다.", { description: firstSource });
      return;
    }
    if (skipped > 0) {
      console.warn(`[LAYER-SPLIT] 편집미리보기 — 다른 소스 ${skipped}개는 이번 재생에서 빠졌습니다.`);
      toast(`${mine.length}조각을 재생합니다.`, {
        description: `다른 영상의 ${skipped}조각은 이 창에서 함께 재생하지 못합니다.`,
      });
    }
    setMiniTarget({
      videoUrl: toFullUrl(rawUrl),
      spans: mine.map((c) => [c.start_sec, c.end_sec] as [number, number]),
      label: `편집 미리보기 · ${mine.length}조각`,
    });
  }, [physicalClips, sourceEntries, toFullUrl]);


  // [STEP 10-I.5.27-E7] Mark first preview ready
  useEffect(() => {
    if (physicalClips.length > 0) {
      markTiming("first_preview_ready");
    }
  }, [physicalClips.length, markTiming]);

  const handleEmptyTrash = useCallback(() => {
    // [HOLDMOVE-FIX B1] deps=[]는 첫 렌더(bucket A) setter를 고정 → 다른 버킷에선 비우기 무효.
    // 현재 버킷 setter를 참조하도록 deps에 포함.
    setDeletedFragments([]);
  }, [setDeletedFragments]);

  const handleBoundaryDragChange = useCallback(
    (leftFrag: Fragment | null, rightFrag: Fragment | null) => {
      if (!leftFrag || !rightFrag) {
        setBoundaryHighlightIds([]);
        setFragmentOverrides(new Map());
        return;
      }

      setActiveSource(leftFrag.source_video);
      setBoundaryHighlightIds([getUid(leftFrag), getUid(rightFrag)]);
    },
    []
  );

  useEffect(() => {
    if (boundaryHighlightIds.length === 0) return;

    const overrides = new Map<string, Fragment>();

    for (const fid of boundaryHighlightIds) {
      const frag = editFragments.find((f) => getUid(f) === fid);
      if (frag) overrides.set(fid, frag);
    }

    setFragmentOverrides(overrides);
  }, [boundaryHighlightIds, editFragments]);

  // [STORY-LAYER-01 A-1] 재료는 스토리(program 단위) — 제안 선택과 무관.
  const filteredFragments = useMemo(() => {
    const proposalFragIds = storyFids;
    if (proposalFragIds.length === 0) return [];

    // 보류탭에 있는 조각은 조각탭에서 제외 (중복 방지)
    const reservedIds = new Set(reservedFragments.map(f => getUid(f)));

    const matched = editFragments.filter((f) => {
      if (reservedIds.has(getUid(f))) return false;
      if (proposalFragIds.includes(f.fragment_id)) return true;
      if (f.root_fragment_uid && proposalFragIds.includes(f.root_fragment_uid)) return true;
      if (f.parent_fragment_uid && proposalFragIds.includes(f.parent_fragment_uid)) return true;
      if (f.derivedFrom && proposalFragIds.includes(f.derivedFrom)) return true;
      return false;
    });

    const result = proposalFragIds
      .filter(id => !reservedIds.has(id))
      .map((id) =>
        matched.find(
          (f) =>
            f.fragment_id === id ||
            f.root_fragment_uid === id ||
            f.parent_fragment_uid === id ||
            f.derivedFrom === id
        )
      )
      .filter(Boolean) as Fragment[];

    return result;
  }, [storyFids, editFragments, reservedFragments]);

  // [GHOST 소각 #4] 구 2조각 편집창 진입 핸들러 — 도달불가 본문(S|S·S|N|S seam 창 구성) 제거,
  // 차단 셸만 유지 (호출자 계약 보존 — 새 편집창 진입은 handleSingleFragmentEdit).
  const handleOpenBoundaryEditor = useCallback(
    async (_leftFragId: string | null, _rightFragId: string | null, _clickSide?: "left" | "right" | "center") => {
      console.log("[PBE_DISABLED] open blocked (rebuild in progress)");
      return;
    },
    []
  );

  // [F-2b] overlay 복원: currentSourceId 변경 시 DB trim값 merge
  useEffect(() => {
    if (!currentSourceId) return;
    (async () => {
      if (editCtxRef.current.enabled) {
        // [EDIT-CONTRACT-B0] 게이트 ON — edit-state 컴파일 재구성이 유일 권위 (fid 일치 병합 폐기)
        const states = await refreshEditStatesRef.current();
        if (states.length) setEditFragments((prev) => rebuildFragmentTiles(prev as any[], states, preferredPbeItemIdFor) as any);
        return;
      }
      try {
        const res = await videoService.getEditOverlay(currentSourceId);
        const overlays: any[] = Array.isArray(res) ? res : [];
        if (overlays.length === 0) return;
        setEditFragments(prev => {
          const map = new Map(overlays.map((o: any) => [o.fragment_id, o]));
          let changed = false;
          const next = prev.map(fr => {
            const o = map.get((fr as any).fragment_id ?? getUid(fr));
            if (!o) return fr;
            if ((fr as any).start_sec === o.effective_start_sec &&
                (fr as any).end_sec   === o.effective_end_sec) return fr;
            changed = true;
            return {
              ...fr,
              start_sec:    o.effective_start_sec,
              end_sec:      o.effective_end_sec,
              start_time:   o.effective_start_sec,
              end_time:     o.effective_end_sec,
              trim_applied: true,
            };
          });
          if (!changed) return prev;
          console.log("[F-2b] overlay merge applied:",
            next.filter(f => (f as any).trim_applied).length, "frags");
          return next;
        });
      } catch (err) {
        console.warn("[F-2b] overlay fetch failed:", err);
      }
    })();
  }, [currentSourceId]);

  // [GHOST 소각 #4] handleEditorApply(구 편집기 적용 — 무게이트 edit_overlay 쓰기 포함, GHOST #2의 쓰는 짝)와
  // SEAM 채팅 분기(/pbe/analyze — 백엔드 라우트도 소각됨) 제거. 채팅은 항상 협의 경로로 직행.
  const handleOnConsultation = useCallback(async (text: string) => {
    handleConsultation(text);
  }, [handleConsultation]);

  // [PLAYNOTICE-JUMP-01] 재생 불가 안내는 **채팅에 쌓지 않는다**.
  //
  //  구판은 이 안내를 storyPlan.messages 에 append 했다(F1 — toast 폐지, SEE FAIL 1 수리).
  //  그런데 messages.length 가 늘면 CenterPanel 의 성장 effect(:698)가 발동하고,
  //  그 조건이 `chatAtBottomRef.current || isChatNearBottom()` 이라 캐시가 낡은 true 면
  //  위에서 읽는 중에도 chatEnd 로 scrollIntoView 가 걸린다 → 화면이 위로 확 튄다.
  //  실측(조사): CenterPanel 전체에서 스크롤을 움직이는 코드는 그 scrollIntoView 2곳뿐이고,
  //  레이아웃 계열(무대 높이 변화·transform 변경·무대 리마운트)은 전부 브라우저 앵커링이
  //  흡수해 체감 이동 0px 이었다. 즉 "가끔 튀는" 유일한 방아쇠가 이 append 였다.
  //  "가끔"인 이유도 여기서 나온다 — 이 안내는 재생할 조각이 없을 때만 발화한다.
  //
  //  안내 자체는 없애지 않는다(침묵 화면 금지). 이미 있는 고지 표면(compositionNotice,
  //  FragmentMap.tsx:529)으로 흘린다 — 새 UI·새 상태를 만들지 않는다. 문구도 마침
  //  "보류맵에서 조각을 되돌리시면..."이라 그 패널이 가리키는 곳과 같다.
  const handlePlaybackNotice = useCallback((text: string) => {
    setCompositionNotice(text);
  }, []);

  const handleStartStoryEditing = useCallback(async (source?: unknown) => {
    const entrySource = source === "chat" ? "chat" : "button";
    console.info("[EDIT-FLOW][START-EDIT][ENTER]", {
      source: entrySource,
      program_id: activeNavItem,
      story_count: storyFidsRef.current.length,
      source_count: sourceEntries.length,
    });
    setPrecisionPaneMode("edit");
    appendStoryGateMessage("ai_edit_started", STORY_GATE_COPY.chat.editStarted);
    appendStoryGateMessage("ai_edit_preparing", STORY_GATE_COPY.chat.editPreparing);
    const roleCount = await refreshSoundRoles();
    const ok = await requestProposalsForApprovedStoryRef.current?.();
    console.info("[EDIT-FLOW][START-EDIT]", {
      program_id: activeNavItem,
      sound_roles: roleCount,
      proposals_ready: ok === true,
    });
  }, [activeNavItem, appendStoryGateMessage, refreshSoundRoles, sourceEntries.length]);
  startApprovedStoryEditingBridgeRef.current = async (source: "chat") => handleStartStoryEditing(source);

  const handleFlowProposalCommit = useCallback((key: string, pair?: any) => {
    const ok = handleProposalCommit(key, pair);
    if (!ok) return false;
    const picked = key === "A" ? "A" : "B";
    setPrecisionPaneMode("edit");
    appendStoryGateMessage(
      `ai_ab_picked_${picked}`,
      STORY_GATE_COPY.chat.proposalPicked(picked),
    );
    console.info("[EDIT-FLOW][AB-PICK]", {
      program_id: activeNavItem,
      picked,
      precision_pane: "edit",
    });
    return true;
  }, [activeNavItem, appendStoryGateMessage, handleProposalCommit]);

  const handleOpenProposalLarge = useCallback((key: "A" | "B", proposal: any, durationSec: number) => {
    const popupWidth = 720;
    const popupHeight = 520;
    const escapeHtml = (value: unknown) => String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
    const title = `${STORY_GATE_COPY.abCards.heading} ${key}`;
    const fragments = (proposal?.key_fragments ?? []) as string[];
    const summary = proposal?.desc || STORY_GATE_COPY.abCards.variants[key].desc;
    const reason = proposal?.proposal_story?.story_summary || proposal?.proposal_explanation?.project_summary || "";
    const html = `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    body { margin: 0; background: #101114; color: #f2f2f2; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    main { width: min(640px, calc(100vw - 48px)); margin: 0 auto; padding: 34px 0; }
    h1 { margin: 0 0 14px; font-size: 28px; font-weight: 760; letter-spacing: 0; }
    .meta { color: #b9bec8; font-size: 15px; margin-bottom: 24px; }
    .summary { font-size: 18px; line-height: 1.65; margin: 0 0 24px; }
    .reason { color: #c9ced8; font-size: 14px; line-height: 1.7; margin: 0 0 28px; }
    ol { margin: 0; padding-left: 24px; display: grid; gap: 8px; }
    li { color: #d9dde5; font-size: 14px; line-height: 1.4; }
  </style>
</head>
<body>
  <main data-ab-large-window="${escapeHtml(key)}" data-popup-width="${popupWidth}" data-popup-height="${popupHeight}">
    <h1>${escapeHtml(title)}</h1>
    <div class="meta">${Math.round(durationSec)}${escapeHtml(STORY_GATE_COPY.abCards.seconds)} · ${fragments.length}조각</div>
    <p class="summary">${escapeHtml(summary)}</p>
    ${reason ? `<p class="reason">${escapeHtml(reason)}</p>` : ""}
    <ol>${fragments.map((fid) => `<li>${escapeHtml(fid)}</li>`).join("")}</ol>
  </main>
</body>
</html>`;
    const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
    const win = window.open(url, `ccut_ab_${key}_${Date.now()}`, `popup=yes,width=${popupWidth},height=${popupHeight}`);
    if (!win) {
      URL.revokeObjectURL(url);
      toast.error(STORY_GATE_COPY.abCards.largeBlocked);
      return;
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    win.focus();
    console.info(`[EDIT-FLOW][AB-LARGE] key=${key} width=${popupWidth} height=${popupHeight} fragments=${fragments.length}`);
  }, []);

  const handleRestoreProposalEntry = useCallback((id: string) => {
    if (activeNavItem && activeNavItem.startsWith("proj_")) {
      reEditSessionStartRef.current = Date.now();
      setReEditProgramId(activeNavItem);
    }
    restoreProposalEntry(id);
  }, [activeNavItem, restoreProposalEntry]);

  const handleBackgroundClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest(".fragment-tile")) return;

    setSelectedFragment(null);
    setHighlightedPanoramaFrag(null);
    setExpandedFragment(null);
  }, []);
  const hasProjectMedia = sourceEntries.length > 0 || sourceFragments.length > 0 || resolvedFragments.length > 0;

  // [STAGE-VOICE] "지금 어느 단계인가"를 채팅이 말한다 — 철거한 오버레이 배지의 대체.
  //   원본맵 위에 얹지 않는다(국장 확정 원칙). 단계가 바뀔 때만 한 줄, 같은 단계 반복 금지.
  //   판정은 그대로 storyStageBadge(상태기계 파생) — 문구도 그 값을 그대로 읽는다.
  //   여기서 자기 상태를 만들지 않는다(분열 방지).
  const stageVoiceRef = useRef<string | null>(null);
  useEffect(() => {
    if (!storyGate.enabled) return;
    // [STAGE-LOADING 2026-08-02] 아직 모르는 것을 '분석 중'이라고 말하지 않는다.
    //   storyStageBadge 의 default 분기가 key="scanned"("분석 중")다(storyMode.ts:78).
    //   그 자리는 진짜 단계가 아니라 story_state 를 ★아직 못 받은 순간이 흘러든 곳이다.
    //   그래서 프로젝트를 열 때마다 scanned -> awaiting 두 줄이 원장에 쌓였다
    //   (실측 175 -> 177 -> 179, 열기 1회당 +2. Freesia 안내 121행 중 재출현 116).
    //   ★화면에서 숨기는 게 아니라 생성 자체를 막는다 — 이 effect 가 원장 유일 입구다
    //     (storyPlan.messages 로 들어가면 Index.tsx:1841 이 그대로 append 한다).
    //   ★로딩이 끝나면 이 effect 는 실제 확정 단계로 다시 돌아 한 번 말한다.
    //     stageVoiceRef 는 말을 실제로 냈을 때만 갱신하므로 건너뛴 것이 기록을 오염시키지 않는다.
    //   ★loading 하나로는 안 막힌다(1회차 실측: 189 -> 191, 여전히 +2).
    //     loading = active && (...) 인데 active = (appState === "complete") 라서,
    //     프로젝트를 막 열어 appState 가 아직 complete 가 아닌 창에서는
    //     loading 이 false 이면서 story 는 null 이다(useStoryGate.ts:106~110 이
    //     그 분기에서 story=null · storyReady=true 로 두고 나간다). 그 창이 '분석 중'의 문이었다.
    //   ★그래서 '조회 중'이 아니라 ★'아직 모른다'로 막는다.
    //     게이트가 켜져 있는데 원고를 못 받았으면 단계를 말할 자격이 없다.
    //     진짜 분석 중인 프로젝트는 서버가 story_state="scanned" 를 실어 주므로
    //     (실측: /story/{id} 는 늘 ok:true + story_state 를 준다) 그 경우는 그대로 말한다.
    if (storyGate.loading) return;
    if (storyGate.enabled && !storyGate.story) return;
    // [STAGE-LOADING 2차 2026-08-02] 열기만 해도 1행이 쌓이던 나머지 절반.
    //   1차(로딩 오독)로 +2 가 +1 이 됐지만 계약은 0이다. 남은 1행의 정체는
    //   "지난번에 이미 한 말을 다시 하는 것"이다 — stageVoiceRef 는 useRef 라
    //   새로고침마다 null 로 태어나고, 원장에는 같은 단계 안내가 이미 있다.
    //   실측: Freesia 안내 121행 = 서로 다른 key 5개 + 재출현 116.
    //   ★ref 를 원장에서 이어받는다. 마지막 안내가 지금과 같은 단계면 다시 말하지 않는다.
    //     단계가 진짜로 바뀌면 그때는 한 번 말한다(계약 D-1=0 · 실제 전환은 유지).
    //   ★복원 전에는 판단하지 않는다 — 원장을 못 본 채 '없다'고 읽으면 오늘 날짜로 덮인다.
    if (uiRestoredFor !== activeNavItem) return;
    if (!activeNavItem?.startsWith("proj_")) return;
    if (!hasProjectMedia) return;
    const sig = `${activeNavItem}:${storyStage.key}`;
    if (stageVoiceRef.current === sig) return;
    // [STAGE-ONE 보강 2026-08-02] 원장 승계를 ★방마다★ 한다.
    //   55b72c4d 는 `=== null` 일 때만 원장을 봤다. ref 는 페이지가 살아 있는 동안
    //   유지되므로, 새로고침 없이 방을 옮기면 ref 가 이미 non-null 이라 승계를 건너뛰고
    //   그 방에서 한 줄을 새로 썼다. 실측: Merope(새로고침 열기) 3회 DELTA 0 인데,
    //   같은 세션에서 Acrux -> Alcyone 로 옮기자 각 1행씩 생겼다
    //   (#5987 ai_stage_final · #5988 ai_stage_edit_consult — 둘 다 원장의 마지막 key 와
    //    같은 단계였다. 즉 "이미 한 말"을 방을 옮겼다는 이유로 다시 했다).
    //   판정을 "처음인가"가 아니라 ★"이 방에서 말한 적 있는가"로 바꾼다.
    const spokenHere = stageVoiceRef.current !== null
      && stageVoiceRef.current.startsWith(`${activeNavItem}:`);
    if (!spokenHere) {
      // 이 프로젝트에서 마지막으로 한 단계 안내를 원장(복원분)에서 읽는다.
      //   id 규약 `ai_stage_<key>_<ts>` — key 자체에 밑줄이 있다(edit_consult).
      const msgs = (storyPlan as any)?.messages ?? [];
      let lastKey: string | null = null;
      for (let i = msgs.length - 1; i >= 0; i--) {
        const m = /^ai_stage_(.+)_\d{10,}$/.exec(String(msgs[i]?.id ?? ""));
        if (m) { lastKey = m[1]; break; }
      }
      if (lastKey === storyStage.key) { stageVoiceRef.current = sig; return; }
    }
    stageVoiceRef.current = sig;
    const stageMsg = {
      id: `ai_stage_${storyStage.key}_${Date.now()}`,
      sender: "ai" as const,
      text: `지금은 ${storyStage.label}입니다. ${storyStage.hint}`,
      timestamp: Date.now(),
    };
    // 실패 경로(:1200)와 같은 null-안전 골격 — storyPlan이 아직 없어도 말이 삼켜지지 않는다.
    setStoryPlan((prev: any) => ({
      ...(prev ?? {
        story_plan_id: `STP_${Date.now()}`,
        source_count: sourceEntries.length,
        consultation_status: "draft_ready",
        confirmation_status: "pending",
        direction_options: [],
        detected_theme: "",
        selected_direction: undefined,
        messages: [],
      }),
      messages: [...((prev?.messages) ?? []), stageMsg],
    }));
  }, [storyGate.enabled, storyGate.loading, storyGate.story, activeNavItem, hasProjectMedia,
      uiRestoredFor, (storyPlan as any)?.messages?.length,
      storyStage.key, storyStage.label, storyStage.hint,
      sourceEntries.length, setStoryPlan]);

  return (
    <div
      ref={containerRef}
      className="flex h-screen w-full overflow-hidden bg-background"
      onClick={handleBackgroundClick}
    >
      <AppDialog
        open={!!appDialog}
        message={appDialog?.message ?? ""}
        confirmText="OK"
        cancelText={appDialog?.cancelText}
        onCancel={() => setAppDialog(null)}
        onConfirm={async () => {
          const next = appDialog;
          setAppDialog(null);
          await next?.onConfirm?.();
        }}
      />
      {/* [STAGE-VOICE] 단계 배지(GATE-LOOP-01 3번) 오버레이 철거 — 국장 확정 원칙:
          원본맵 위에는 어떤 오버레이도 얹지 않는다. 원본 영상 이름을 가렸다.
          배지가 담당하던 "지금 어느 단계인가"는 아래 effect가 채팅 문장으로 말한다.
          도입 취지(승인 화면을 임시 페이지로 오인한 사고 방지)는 문장으로 살아 있다. */}

      <div className="relative flex-shrink-0" style={{ width: navCollapsed ? 48 : navWidth }}>
        <LeftNav
          activeItem={activeNavItem}
          onItemClick={onNavItemClick}
          projects={projects}
          collapsed={navCollapsed}
          onHome={onHome}
          onToggleCollapse={onNavToggleCollapse}
          onRenameProject={onNavRenameProject}
          onDeleteProject={onNavDeleteProject}
          onNewProject={onNavNewProject}
        />
      </div>

      {/* [LAYOUT] 좌측 사이드바 리사이즈 핸들 — 모든 화면에서 폭 조절 가능 */}
      {!navCollapsed && (
        <ResizeHandle active={isNavDragging} onStart={() => setIsNavDragging(true)} />
      )}

      <div style={!(activeNavItem === "archive" || activeNavItem === "upload" || activeNavItem === "account" || activeNavItem === "settings" || activeNavItem === "trash") && hasProjectMedia ? { width: centerWidth, flexShrink: 0 } : { flex: 1, minWidth: 0 }} className="h-full">
        {activeNavItem === "settings" ? (
          <SettingsPanel />
        ) : activeNavItem === "archive" ? (
          <ArchivePanel
            onNavigateToProject={navigateToProject}
            onRenameProject={(id, newName) => {
              setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name: newName } : p)));
            }}
          />
        ) : activeNavItem === "upload" ? (
          <SnsUploadPanel
            onNavigateToProject={navigateToProject}
            onRenameProject={(id, newName) => {
              setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name: newName } : p)));
            }}
          />
        ) : activeNavItem === "trash" ? (
          <TrashPanel onChanged={reloadProjects} reloadDep={projects} />
        ) : activeNavItem === "account" ? (
          <AccountPanel />
        ) : isSwitchingProject ? (
          <div style={{display:"flex",alignItems:"center",justifyContent:"center",height:"100%",flexDirection:"column",gap:"16px"}}>
            <div style={{fontSize:"14px",color:"#888"}}>프로젝트를 불러오는 중입니다...</div>
          </div>
        ) : (
          <CenterPanel
            key={activeNavItem ?? "default"}
            selectedFragment={selectedFragment}
            selectedSource={activeSource}
            appState={appState}
            onAppStateChange={setAppState}
            analyzeProgress={analyzeProgress}
            analyzeMessage={analyzeMessage}
            analysisLogs={analysisLogs}
            proposals={proposals}
            reEditActive={activeReEdit}
            sourceFragments={sourceFragments}
            sourceId={currentSourceId}
            videoUrl={currentVideoUrl}
            onAnalyze={handleStartAnalysis}
            committedProposalId={committedProposalId}
            displayProposalId={displayProposalId}
            onPlaybackNotice={handlePlaybackNotice}
            onPreviewProposal={handleProposalPreview}
            onCommitProposal={handleFlowProposalCommit}
            onExport={handleExport}
            onConsultation={handleOnConsultation}
            onReproposal={(dir: any) => {
              handleReproposal(dir);
            }}
            fragments={resolvedFragments}
            storyFids={storyFids}
            exportClips={physicalClips}
            storyPlan={storyPlan}
            onStoryPlanConfirm={setStoryPlan}
            activeStoryFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : highlightedPanoramaFrag}
            modeGateEnabled={modeGateOn}
            activeFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : null}
            /* [LAYER-SPLIT 2026-08-04 국장 확정 ②] 저장된 버전 아이콘 줄.
               ★한 줄만 차지한다 — 가로로만 늘고 세로로는 자라지 않는다(flex-nowrap + overflow-x-auto,
                 원본맵과 같은 방식). 아이콘은 텍스트 한 줄 높이(h-6)에 맞춘다.
               ★저장한 적이 없으면 줄 자체를 그리지 않는다 — 빈 줄이 자리를 먹지 않게. */
            editVersionBar={editVersions.length > 0 ? (
              <div className="flex flex-row flex-nowrap items-center gap-2 overflow-x-auto no-scrollbar py-0.5">
                <span className="flex-shrink-0 text-micro text-muted-foreground/40 pr-0.5">{STORY_GATE_COPY.editVersionBar.label}</span>
                {editVersions.map((v) => (
                  <button
                    key={v.id}
                    type="button"
                    data-edit-version-chip={v.id}
                    className="group flex items-center gap-1.5 h-7 flex-shrink-0 rounded-full px-2.5 text-micro text-muted-foreground/60 hover:bg-foreground/5 hover:text-foreground transition-colors"
                  >
                    <span className="h-1 w-1 rounded-full bg-muted-foreground/30 group-hover:bg-muted-foreground/60 transition-colors" />
                    <span className="max-w-[130px] truncate">{v.name}</span>
                  </button>
                ))}
              </div>
            ) : undefined}
            versionBar={savedVersions.length > 0 ? (
              /* [LAYER-FIX3 2026-08-04 국장 지시] 심플하되 허허벌판이 아니게.
                 더한 것은 셋뿐이다 — 무엇을 보는 줄인지 알리는 라벨, 칩을 칩으로 읽히게 하는
                 아주 옅은 바탕, 지금 보고 있는 것만 켜지는 점. 테두리·그림자·색은 쓰지 않는다.
                 여전히 한 줄(h-7)이고 가로로만 늘어난다. */
              <div className="flex flex-row flex-nowrap items-center gap-2 overflow-x-auto no-scrollbar py-0.5">
                <span className="flex-shrink-0 text-micro text-muted-foreground/40 pr-0.5">{STORY_GATE_COPY.versionBar.label}</span>
                {savedVersions.map((v) => {
                  const active = v.version_id === activeVersionId;
                  return (
                    <button
                      key={v.version_id}
                      type="button"
                      data-version-chip={v.version_id}
                      onClick={() => handleVersionPick(v.version_id)}
                      title={`${v.name} · 조각 ${v.item_count}개`}
                      className={`group flex items-center gap-1.5 h-7 flex-shrink-0 rounded-full px-2.5 text-micro transition-colors ${
                        active
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground/60 hover:bg-foreground/5 hover:text-foreground"
                      }`}
                    >
                      <span
                        className={`h-1 w-1 rounded-full transition-colors ${
                          active ? "bg-primary" : "bg-muted-foreground/30 group-hover:bg-muted-foreground/60"
                        }`}
                      />
                      <span className="max-w-[130px] truncate">{v.name}</span>
                      <span className="tabular-nums opacity-50">{v.item_count}</span>
                    </button>
                  );
                })}
              </div>
            ) : undefined}
            roughCutStage={activeNavItem?.startsWith("proj_") ? (
              <RoughCutStage
                projectId={activeNavItem}
                sourceEntries={sourceEntries}
                selectedSpanIds={roughCutSelectedSpanIds}
                activeFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : highlightedPanoramaFrag}
                focusOrigin={fragmentFocusOrigin}
                fragmentForSpan={roughCutFragmentForSpan}
                onAddSpan={handleRoughCutSpanAdd}
                onData={setRoughCutData}
                onPlay={setMiniTarget}
                /* [FIRST-RUN 2026-08-04] 분석 완료 신호. 새 폴러를 만들지 않는다 —
                   이미 도는 분석 폴러(2초)가 끝에 찍는 setAppState("complete", :1408)와
                   기존 프로젝트 복원 경로(:1616)가 쓰는 바로 그 값이다.
                   false → true 로 바뀌는 순간 RoughCutStage 가 스스로 다시 묻는다.
                   ★item_count>0 을 쓰지 않는 이유: 그것은 semantic_fragments 개수라
                   (service.py:140) 무음 영상에서 영영 0이다. 그러면 '전사 부족'이라
                   말해야 할 영상이 '분석 중'에 갇힌다(F-5). appState 는 전사 유무와
                   무관하게 완료를 알린다. */
                analysisReady={appState === "complete"}
              />
            ) : undefined}
            storyReplacement={modeGateOn ? (
              precisionPaneMode === "edit" ? (
                <div data-precision-pane="edit" className="h-full min-h-[220px] text-left">
                  <FragmentMap
                    fragments={roughCutMapReady ? roughCutFragmentPool : []}
                    storyFragmentIds={roughCutMapReady ? storyFids : []}
                    storyOnly
                    onFragmentsChange={roughCutData ? handleRoughCutStoryReorder : handleFragmentsReorder}
                    selectedFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : null}
                    activeFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : highlightedPanoramaFrag}
                    focusOrigin={fragmentFocusOrigin}
                    expandedFragmentId={expandedFragment}
                    onFragmentClick={handleEditFragmentClick}
                    onFragmentPlay={playImageFragmentInMini}
                    onEditFragment={handleSingleFragmentEdit}
                    onFragmentDoubleClick={handleEditFragmentDoubleClick}
                    onExcludeFragment={roughCutData ? handleRoughCutStoryRemove : handleExcludeFromEdit}
                    onRestoreFragment={roughCutData ? handleRoughCutStoryInsert : handleRestoreFromHold}
                    onSourceRestore={roughCutData ? handleRoughCutStoryInsert : handleAddFromSource}
                    onMoveToHold={roughCutData ? handleRoughCutStoryRemove : handleMoveToHold}
                    onTrashRestore={roughCutData ? handleRoughCutStoryInsert : handleRestoreToEdit}
                    onBoundaryClick={handleOpenBoundaryEditor}
                    sourceVideoUrls={Object.fromEntries(
                      (sourceEntries ?? []).flatMap(e => [[e.source_id, e.video_url], [e.label, e.video_url]]).filter(([, v]) => v)
                    )}
                    modeGateEnabled={modeGateOn}
                    fragmentFace="image"
                    title={STORY_GATE_COPY.precisionPanel.editHeading}
                    textButtonLabel="텍스트"
                    textScope="selected"
                    showFaceControls
                    showCompositionActions={false}
                    compositionNotice={STORY_GATE_COPY.precisionPanel.editMapNote}
                    sourceFragments={(sourceEntries ?? []).flatMap((e) => e.fragments ?? [])}
                    storyTextItems={modeStoryTextItems}
                    programId={activeNavItem}
                    onTextEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); setStoryLedgerRefreshNonce((n) => n + 1); }}
                    soundViewEnabled
                    soundRoles={soundRoleItems}
                    soundRoleLoading={soundRoleLoading}
                    soundRoleError={soundRoleError}
                    soundRoleSavingIds={soundRoleSavingIds}
                    onSoundViewChange={handleSoundViewChange}
                    onSoundRoleChange={handleSoundRoleChange}
                  />
                </div>
              ) : (
                <FragmentMap
                  fragments={roughCutMapReady ? roughCutFragmentPool : []}
                  storyFragmentIds={roughCutMapReady ? storyFids : []}
                  storyOnly
                  onFragmentsChange={roughCutData ? handleRoughCutStoryReorder : handleFragmentsReorder}
                  selectedFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : null}
                  activeFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : highlightedPanoramaFrag}
                  focusOrigin={fragmentFocusOrigin}
                  expandedFragmentId={expandedFragment}
                  onFragmentClick={handleEditFragmentClick}
                  onFragmentPlay={playImageFragmentInMini}
                  onEditFragment={handleSingleFragmentEdit}
                  onFragmentDoubleClick={handleEditFragmentDoubleClick}
                  onExcludeFragment={roughCutData ? handleRoughCutStoryRemove : handleExcludeFromEdit}
                  onRestoreFragment={roughCutData ? handleRoughCutStoryInsert : handleRestoreFromHold}
                  onSourceRestore={roughCutData ? handleRoughCutStoryInsert : handleAddFromSource}
                  onMoveToHold={roughCutData ? handleRoughCutStoryRemove : handleMoveToHold}
                  onTrashRestore={roughCutData ? handleRoughCutStoryInsert : handleRestoreToEdit}
                  onBoundaryClick={handleOpenBoundaryEditor}
                  sourceVideoUrls={Object.fromEntries(
                    (sourceEntries ?? []).flatMap(e => [[e.source_id, e.video_url], [e.label, e.video_url]]).filter(([, v]) => v)
                  )}
                  modeGateEnabled={modeGateOn}
                  fragmentFace="text"
                  title=""
                  textScope="all"
                  showFaceControls={false}
                  showCompositionActions={false}
                  sourceFragments={(sourceEntries ?? []).flatMap((e) => e.fragments ?? [])}
                  storyTextItems={modeStoryTextItems}
                  programId={activeNavItem}
                  onTextEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); setStoryLedgerRefreshNonce((n) => n + 1); }}
                  soundViewEnabled={soundViewEnabled}
                  soundRoles={soundRoleItems}
                  soundRoleLoading={soundRoleLoading}
                  soundRoleError={soundRoleError}
                  soundRoleSavingIds={soundRoleSavingIds}
                  onSoundViewChange={handleSoundViewChange}
                  onSoundRoleChange={handleSoundRoleChange}
                />
              )
            ) : undefined}
            onActiveFragmentChange={handleCenterStoryFragmentFocus}
            onStoryEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); void storyGate.reload(); setStoryLedgerRefreshNonce((n) => n + 1); }}
            storyRefreshNonce={storyLedgerRefreshNonce}
            sourceEntries={sourceEntries}
            programId={activeNavItem}
            programTitle={projects.find(p => p.id === activeNavItem)?.name ?? undefined}
            onExportDone={() => {
              // [FIX-EXPORT-UISTATE] 내보내기 완료 시 ui_state 저장
              if (activeNavItem && activeNavItem.startsWith("proj_")) {
                // [#30] merge-저장 — 모르는 것을 지우지 않는다
                saveUiStateMergedTracked(activeNavItem, buildUiSnapshot()).catch(() => {});
              }
              setActiveNavItem("upload");
            }}
            proposalHistory={proposalHistory}
            activeProposalEntryId={activeProposalEntryId}
            onRestoreProposalEntry={handleRestoreProposalEntry}
            onStartStoryEditing={handleStartStoryEditing}
            onOpenProposalLarge={handleOpenProposalLarge}
            onIntake={(a) => { intakeRef.current = a; }}
            onRequestAddVideos={
              activeNavItem && activeNavItem.startsWith("proj_")
                ? () => appendInputRef.current?.click()
                : undefined /* 새 프로젝트 상태는 CenterPanel 스테이징 input 사용 */
            }
            onAddVideoFiles={(files) => {
              if (files.length === 0) return;
              handleAnalyzeRef.current?.(files[0], files.slice(1));
            }}
            timelineHasMore={timelineHasMore}
            timelineLoadingMore={timelineLoadingMore}
            onLoadOlderTimeline={loadOlderTimeline}
            transcriptRefTs={transcriptRefTs}
          />
        )}
      </div>

      {!(activeNavItem === "archive" || activeNavItem === "upload" || activeNavItem === "account" || activeNavItem === "trash") && hasProjectMedia && (
        <>
          <ResizeHandle active={isDragging} onStart={() => setIsDragging(true)} />

          {/* [#3+#13 재시공 2026-07-19] pb-0 — 이 컬럼의 p-2 바닥 패딩(8px)이 보류맵을
              viewport 하단에서 8px 띄우던 '공중부양'의 실제 원인(부모 높이 체인). 바닥만
              패딩 제거해 보류맵이 창 밑변에 dock되게 한다(상·좌·우 패딩은 유지). */}
          <div className="flex-1 flex flex-col gap-2 p-2 pb-0 overflow-hidden min-w-0">
            <input ref={appendInputRef} type="file" accept="video/*" multiple className="hidden" onChange={handleAppendFiles} />
            <OriginalPanorama
              activeSource={activeSource}
              onSourceChange={setActiveSource}
              highlightedFragmentId={highlightedPanoramaFrag}
              focusOrigin={fragmentFocusOrigin}
              selectedFragmentId={selectedFragment?.fragment_id || null}
              onFragmentClick={handlePanoramaFragmentClick}
              onFragmentPlay={playImageFragmentInMini}
              intelligenceOn={intelligenceOn}
              onToggleIntelligence={() => setIntelligenceOn((p) => !p)}

              fragmentOverrides={fragmentOverrides}

              boundaryHighlightIds={boundaryHighlightIds}
              onBoundaryClick={(leftFragId, rightFragId) => handleOpenBoundaryEditor(leftFragId, rightFragId, "center")}
              onAddSource={() => appendInputRef.current?.click()}
              onRemoveSource={handleRemoveSource}
              onRenameSource={handleRenameSource}
              compactLabels={modeGateOn}
              sourceFragments={
                sourceEntries.length > 0
                  ? sourceEntries.find((e) => e.label === activeSource)?.fragments ?? []
                  : sourceFragments
              }
              sources={
                sourceEntries.length > 0
                  ? sourceEntries.map((e) => ({
                    source_id: e.source_id,
                    label: e.label,
                    title: e.title,
                    display_name: e.display_name,
                    video_url: e.video_url,
                  }))
                  : currentSourceId
                    ? [{ source_id: currentSourceId, label: "A", video_url: currentVideoUrl || undefined }]
                    : []
              }
            />

            {/* [STORY-TRACK-C C-3][#3+#13 DOCK-CONTRACT 2026-07-19] 조각맵·보류맵 세로 분할
                영역 — 사이 리사이저로 비율 조절, localStorage 지속(ccut_map_hold_split).
                STORY·EDIT 양 단계 모두 보류맵·리사이저 상주(§계약: 하단 고정, 리사이저는
                top 경계만 이동, 패널 자체는 항상 컨테이너 하단에 붙는다 — flex-col 레이아웃이라
                마지막 자식의 bottom은 곧 컨테이너 bottom). 이전엔 편집 단계에서만 렌더돼
                스토리 단계에서 보류맵이 아예 사라지는 게 결함이었다. */}
            <div ref={mapHoldAreaRef} className="flex-1 flex flex-col gap-1.5 overflow-hidden min-h-0">
              <div className="overflow-y-auto min-h-0"
                   style={{ flexGrow: mapHoldSplit, flexBasis: 0 }}>
                {/* [STORY-TRACK-A A-1/A-2/A-3] 스토리 단계 = 조각맵 자리에 텍스트조각 에디터.
                    편집 단계 = 이미지 조각맵. 같은 아이 옷만 다름(뒤 식별자 동일). */}
                {modeGateOn && precisionPaneMode === "edit" ? (
                  <div data-precision-pane="edit" className="h-full min-h-[220px] text-left">
                    <FragmentMap
                      fragments={roughCutMapReady ? roughCutFragmentPool : []}
                      storyFragmentIds={roughCutMapReady ? storyFids : []}
                      storyOnly
                      onFragmentsChange={roughCutData ? handleRoughCutStoryReorder : handleFragmentsReorder}
                      selectedFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : null}
                      activeFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : highlightedPanoramaFrag}
                      focusOrigin={fragmentFocusOrigin}
                      expandedFragmentId={expandedFragment}
                      onFragmentClick={handleEditFragmentClick}
                      onFragmentPlay={playImageFragmentInMini}
                      onEditFragment={handleSingleFragmentEdit}
                      onFragmentDoubleClick={handleEditFragmentDoubleClick}
                      onExcludeFragment={roughCutData ? handleRoughCutStoryRemove : handleExcludeFromEdit}
                      onRestoreFragment={roughCutData ? handleRoughCutStoryInsert : handleRestoreFromHold}
                      onSourceRestore={roughCutData ? handleRoughCutStoryInsert : handleAddFromSource}
                      onMoveToHold={roughCutData ? handleRoughCutStoryRemove : handleMoveToHold}
                      onTrashRestore={roughCutData ? handleRoughCutStoryInsert : handleRestoreToEdit}
                      onBoundaryClick={handleOpenBoundaryEditor}
                      sourceVideoUrls={Object.fromEntries(
                        (sourceEntries ?? []).flatMap(e => [[e.source_id, e.video_url], [e.label, e.video_url]]).filter(([, v]) => v)
                      )}
                      modeGateEnabled={modeGateOn}
                      fragmentFace="image"
                      title={STORY_GATE_COPY.precisionPanel.editHeading}
                      textButtonLabel="텍스트"
                      textScope="selected"
                      showFaceControls
                      showCompositionActions={false}
                      compositionNotice={STORY_GATE_COPY.precisionPanel.editMapNote}
                      sourceFragments={(sourceEntries ?? []).flatMap((e) => e.fragments ?? [])}
                      storyTextItems={modeStoryTextItems}
                      programId={activeNavItem}
                      onTextEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); setStoryLedgerRefreshNonce((n) => n + 1); }}
                      soundViewEnabled
                      soundRoles={soundRoleItems}
                      soundRoleLoading={soundRoleLoading}
                      soundRoleError={soundRoleError}
                      soundRoleSavingIds={soundRoleSavingIds}
                      onSoundViewChange={handleSoundViewChange}
                      onSoundRoleChange={handleSoundRoleChange}
                    />
                  </div>
                ) : rightStoryMode && !modeGateOn ? (
                  <LedgerPage
                    key={`rightledger_${activeNavItem}_${storyLedgerRefreshNonce}`}
                    embedded
                    programId={activeNavItem ?? undefined}
                    onEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); void storyGate.reload(); setStoryLedgerRefreshNonce((n) => n + 1); }}
                    onItemFocus={handleTextFragmentFocus}
                    onPlayItem={setMiniTarget}
                    storyState={storyGate.story?.story_state}
                    onApproveStory={async () => {
                      setCompositionNotice(null);
                      const result = await storyGate.approve({
                        beforeFetch: async () => {
                          const pending = uiStateSaveRef.current;
                          if (pending) await pending.catch(() => {});
                        },
                      });
                      if (result.ok) {
                        recordMirrorEvent({
                          event_kind: "accept",
                          project_id: activeNavItem ?? undefined,
                          approval_id: result.body?.approval_id,
                          sequence_hash: result.body?.sequence_hash,
                          mode: result.body?.mode,
                          item_count: result.body?.item_count,
                        });
                      } else if (result.status === 409) {
                        setCompositionNotice(result.body?.user_message || result.body?.message || "구성이 방금 바뀌어 새로 확인했습니다. 다시 눌러 주세요.");
                      }
                      return result;
                    }}
                    sourceLabels={Object.fromEntries(
                      (sourceEntries ?? []).map((e) => [e.source_id, e.label]).filter(([, l]) => l)
                    )}
                  />
                ) : (
                  <FragmentMap
                    fragments={modeGateOn ? (roughCutMapReady ? roughCutFragmentPool : []) : resolvedFragments}
                    storyFragmentIds={modeGateOn ? (roughCutMapReady ? storyFids : []) : undefined}
                    storyOnly={modeGateOn}
                    onFragmentsChange={roughCutData ? handleRoughCutStoryReorder : handleFragmentsReorder}
                    selectedFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : null}
                    activeFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : highlightedPanoramaFrag}
                    focusOrigin={fragmentFocusOrigin}
                    expandedFragmentId={expandedFragment}
                    onFragmentClick={handleEditFragmentClick}
                    onFragmentPlay={playImageFragmentInMini}
                    onEditFragment={handleSingleFragmentEdit}
                    onFragmentDoubleClick={handleEditFragmentDoubleClick}
                    onExcludeFragment={roughCutData ? handleRoughCutStoryRemove : handleExcludeFromEdit}
                    onRestoreFragment={roughCutData ? handleRoughCutStoryInsert : handleRestoreFromHold}
                    onSourceRestore={roughCutData ? handleRoughCutStoryInsert : handleAddFromSource}
                    onMoveToHold={roughCutData ? handleRoughCutStoryRemove : handleMoveToHold}
                    onTrashRestore={roughCutData ? handleRoughCutStoryInsert : handleRestoreToEdit}
                    onBoundaryClick={handleOpenBoundaryEditor}
                    sourceVideoUrls={Object.fromEntries(
                      (sourceEntries ?? []).flatMap(e => [[e.source_id, e.video_url], [e.label, e.video_url]]).filter(([, v]) => v)
                    )}
                    modeGateEnabled={modeGateOn}
                        fragmentFace={fragmentFace}
                    onFragmentFaceChange={setFragmentFace}
                    title={undefined}
                    textButtonLabel="텍스트"
                    textScope="selected"
                    onSaveVersion={handleSaveVersion}
                    onPreviewEdit={handlePreviewEdit}
                    onReopenComposition={handleReopenComposition}
                    storyApproved={storyStage.key === "final" || storyStage.key === "edit_consult"}
                    // [APPROVAL-SYNC 2026-08-03] 승인 원고 vs 현재 원고 — 백엔드가 이미 준다.
                    //   storyGate.story.approved.stale / .item_count (story_gate/service.py:223~)
                    storyStale={!!storyGate.story?.approved?.stale}
                    approvedItemCount={storyGate.story?.approved?.item_count ?? null}
                    currentItemCount={storyGate.story?.item_count ?? null}
                    compositionNotice={compositionNotice}
                    modeRound={storyGate.story?.mode_round ?? 1}
                    sourceFragments={(sourceEntries ?? []).flatMap((e) => e.fragments ?? [])}
                    storyTextItems={modeStoryTextItems}
                    programId={activeNavItem}
                    onTextEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); setStoryLedgerRefreshNonce((n) => n + 1); }}
                    soundViewEnabled={soundViewEnabled}
                    soundRoles={soundRoleItems}
                    soundRoleLoading={soundRoleLoading}
                    soundRoleError={soundRoleError}
                    soundRoleSavingIds={soundRoleSavingIds}
                    onSoundViewChange={handleSoundViewChange}
                    onSoundRoleChange={handleSoundRoleChange}
                  />
                )}
              </div>

              {/* [#3+#13 DOCK-CONTRACT] 보류맵·리사이저 상주 — STORY·EDIT 양 단계 공통.
                  STORY 단계에선 reservedFragments가 비어 있을 수 있으나(그쪽 "빼기"는
                  LedgerPage 자체 excluded_items 별도 계약), 패널 자체는 접힌 채로도 항상 존재
                  해야 한다는 게 이번 계약. ReservedFragments는 빈 배열을 이미 안전하게 그린다. */}
              <div onMouseDown={startMapHoldDrag}
                   className="flex-shrink-0 h-2 cursor-row-resize group flex items-center justify-center rounded hover:bg-primary/10 transition-colors"
                   title="조각맵·보류맵 크기 조절">
                <div className="w-10 h-[3px] rounded-full bg-border/50 group-hover:bg-primary/50 transition-colors" />
              </div>
              <div className="overflow-y-auto min-h-0"
                   style={{ flexGrow: 1 - mapHoldSplit, flexBasis: 0 }}>
                <ReservedFragments
                  fragments={reservedFragments}
                  selectedFragmentId={selectedFragment ? getUid(selectedFragment) : null}
                  onFragmentClick={handleReservedClick}
                  onRestoreFragment={handleRestoreFromHold}
                  onDeleteFragment={handleDeleteFromHold}
                  deletedFragments={deletedFragments}
                  onRestoreToHold={handleRestoreToHold}
                  onRestoreToEdit={handleRestoreToEdit}
                  onEmptyTrash={handleEmptyTrash}
                  holdPositions={holdPositions}
                  onHoldPositionsChange={setHoldPositions}
                  onHoldPositionsCommit={handleHoldPositionsCommit}
                  onDropToHold={roughCutData ? handleRoughCutDropToHold : handleDropToHold}
                  compactLabels={modeGateOn}
                />
              </div>
            </div>
          </div>
        </>
      )}
      <SingleFragmentEditor
        open={singleEditOpen}
        onOpenChange={setSingleEditOpen}
        fragment={singleEditTarget}
        projectName={projects.find(p => p.id === activeNavItem)?.name}
        contractState={sfeContractState}
        precisionContext={sfePrecisionContext}
        soundRole={sfeSoundRole}
        soundRoleSaving={sfeSoundRole ? soundRoleSavingIds.has(sfeSoundRole.timeline_item_id) : false}
        onSoundRoleChange={handleSoundRoleChange}
        onApply={handleSingleFragmentApply}
      />
      {/* [STORY-TRACK-B] 조각 단위 공용 미니 플레이창 — 텍스트·이미지 클릭 공용. 창 1개. */}
      <FragmentMiniPlayer target={miniTarget} onClose={() => setMiniTarget(null)} />
    </div>
  );
};

export default Index;
