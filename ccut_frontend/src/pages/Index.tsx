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
import { toMs } from "@/utils/editContract";
import { buildExportClipsFromResolvedFragments, type PhysicalClip } from "@/utils/exportClipBuilder";
import { DEBUG_LOG } from "@/utils/debugFlags";
import { closeMirrorPendingForProject, recordMirrorEvent } from "@/utils/mirrorEventLog";

type PbeContractState = Pick<
  EditStateRow,
  "anchor_start_ms" | "anchor_end_ms" | "trim_start_ms" | "trim_end_ms" | "excluded_ranges" | "removed"
>;

type RoughCutPlacement = {
  inputHash: string | null;
  selectedSpanIds: string[];
};

const pbeContractKey = (programId: string | null | undefined, fid: string) => `${programId ?? "local"}:${fid}`;

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
  const requestProposalsForApprovedStoryRef = useRef<(() => void) | null>(null);

  const handleApproveComposition = useCallback(async () => {
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
      await storyGate.reload();
      // [GATE-LOOP-01 2-1] 승인이 A/B 생성의 방아쇠다. 생성 게이트가 승인 전 생성을
      // 거절하므로(backend STORY_NOT_APPROVED), 승인된 지금이 만들 시점이다.
      // 실패해도 승인은 유효 — 이유만 남기고 사용자는 계속 진행할 수 있다.
      requestProposalsForApprovedStoryRef.current?.();
    } else if (result.status === 409) {
      setCompositionNotice(result.body?.user_message || result.body?.message || "구성이 방금 바뀌어 새로 확인했습니다. 다시 눌러 주세요.");
    }
  }, [activeNavItem, storyGate]);

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
      : currentSourceId ? [currentSourceId] : []
  );
  // [FLOW] 확정/선택 전에도 조각맵이 비지 않게 — 무대에 선 제안(기본 A)을 따라간다.
  // [STORY-LAYER-01 A-1] 이 값은 '표시 방식'(어느 편집안을 무대에 세울지)일 뿐이며,
  // 스토리(조각·순서·대사)를 가르지 않는다. 조각맵·전사·보류맵은 이 값을 참조하지 않는다.
  const displayProposalId = committedProposalId ?? selectedProposalId ?? (proposals ? "A" : null);

  // [GATE-LOOP-01 3번] 단계 배지 — 상태기계에서 파생만 한다 (배지가 자기 상태를 갖지 않는다).
  const storyStage = storyStageBadge(storyGate.story?.story_state, committedProposalId, activeReEdit);


  // ── [STORY-LAYER-01 A-1] live story = program 단위 하나 ──
  // storyFids       : 선택된 조각 + 순서 (사용자 결정 — INV-0. AI가 바꾸지 않는다)
  // storyFragments  : 그 스토리의 구성본(좌표·분할 포함 표시용) — 구판 customEditFragments 대체
  // 제안(A/B)은 이 하나의 스토리를 '어떻게 편집할지'이므로, 스토리를 소유하지 않는다.
  const [storyFids, setStoryFids] = useState<string[]>([]);
  const [storyFragments, setStoryFragments] = useState<Fragment[]>([]);
  const [roughCutData, setRoughCutData] = useState<RoughCutData | null>(null);
  const [roughCutPlacement, setRoughCutPlacement] = useState<RoughCutPlacement | null>(null);
  const roughCutMapReady = storyStage.key !== "scanned" && roughCutData !== null;
  // 이 프로젝트의 ui_state 재수화가 끝났는가 (저장이 복원을 앞질러 덮는 것을 막는 문턱)
  const [uiRestoredFor, setUiRestoredFor] = useState<string | null>(null);

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
      console.log(`[mapFragments] ${label} (${mapped.length} frags) first thumb:`, mapped[0].thumbnail?.thumbnail_url);
      pushAnalysisLog(`[mapFragments] ${label} (${mapped.length} frags)`);
      console.log(
        `[THUMB_AUDIT_ALL_JSON] ${label}\n` +
        JSON.stringify(
          mapped.map((f: any) => ({
            fragment_id: f.fragment_id,
            display_id: f.display_id,
            source_video: f.source_video,
            start_frame: f.start_frame,
            end_frame: f.end_frame,
            duration: f.duration,
            thumb: f.thumbnail?.thumbnail_url,
            thumb_direct: f.thumbnail_url,
            intelligence_thumb: f.intelligence?.thumb_url,
          })),
          null,
          2
        )
      );
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
  const buildUiSnapshot = useCallback(() => ({
    story: { fids: storyFids },
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
    if (nextFids && serverFidCount !== null && serverFidCount > 0
        && nextFids.length > serverFidCount * 3) {
      console.error(
        `[STORY-WRITE-GUARD][REJECT] story.fids 급증 — 저장 거부. `
        + `program=${programId} before=${serverFidCount} after=${nextFids.length} `
        + `ratio=${(nextFids.length / serverFidCount).toFixed(1)}x origin=${storyOriginRef.current} `
        + `first3=[${nextFids.slice(0, 3).join(", ")}]`,
      );
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
        console.error(
          `[STORY-WRITE-GUARD][REJECT] 외래 원고 — 저장 거부. `
          + `program=${programId} fids=${nextFids.length} 이 프로젝트 조각=${editFragments.length} `
          + `교집합=0 origin=${storyOriginRef.current} first3=[${nextFids.slice(0, 3).join(", ")}]`,
        );
        return { status: "REJECTED_FOREIGN_STORY" } as any;
      }
    }
    return videoService.saveProjectState(programId, { ui_state: JSON.stringify({ ...unknown, ...snapshot }) });
  }, [OWNED_UI_FIELDS, setStoryPlan, editFragments]);

  const saveUiStateMergedTracked = useCallback((programId: string, snapshot: Record<string, any>) => {
    const p = saveUiStateMerged(programId, snapshot);
    uiStateSaveRef.current = p;
    p.finally(() => {
      if (uiStateSaveRef.current === p) uiStateSaveRef.current = null;
    });
    return p;
  }, [saveUiStateMerged]);


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
    resetAnalysisFlow, setActiveNavItem, setNavCollapsed, setProjects,
    activeNavItem, appState, buildUiSnapshot,
    saveUiState: saveUiStateMergedTracked, // [#30] merge-저장 주입
  });

  // [B-5-FIX] 저장된 백엔드 proposals → UI proposals 형태 매핑 (복원용, 업로드 매핑과 동일 형태)
  const mapBackendProposals = useCallback((proposals: any[]) => {
    const out: Record<"A" | "B", any> = {} as any;
    (proposals || []).forEach((p: any) => {
      const mode = p.mode === "A" ? "A" : "B";
      out[mode] = {
        id: mode,
        proposal_id: p.proposal_id,
        mode: p.mode === "A" ? "market" : "user",
        title: p.mode === "A" ? "시장형 편집 (A)" : "사용자친화형 편집 (B)",
        desc: p.proposal_reason?.mode_reason || "백엔드 분석 기반 추천 편집안입니다.",
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
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) return;
    const sourceIds = (sourceEntries ?? []).map((e) => e.source_id).filter(Boolean);
    if (sourceIds.length === 0) return;
    try {
      const res: any = await videoService.requestProjectProposals(activeNavItem, sourceIds, 60.0);
      if (res?.status === "STORY_NOT_APPROVED") {
        console.warn("[PROPOSAL] 승인 직후인데 게이트가 아직 승인 전으로 봄 — 다음 승인에서 재시도", res);
        return;
      }
      if (Array.isArray(res?.proposals) && res.proposals.length > 0) {
        setProposals(mapBackendProposals(res.proposals));
        console.info(`[PROPOSAL] 승인 후 A/B 생성 완료 — ${res.proposals.length}건`);
      } else {
        console.warn("[PROPOSAL] 승인 후 생성이 제안을 반환하지 않음", res?.status);
      }
    } catch (e) {
      console.error("[PROPOSAL] 승인 후 A/B 생성 실패 — 승인은 유효합니다", e);
    }
  }, [activeNavItem, sourceEntries, mapBackendProposals, setProposals]);
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
                    generatedProposals[mode] = {
                      id: mode,
                      proposal_id: p.proposal_id,
                      mode: p.mode === "A" ? "market" : "user",
                      title: p.mode === "A" ? "시장형 편집 (A)" : "사용자친화형 편집 (B)",
                      desc: p.proposal_reason?.mode_reason || "백엔드 분석 기반 추천 편집안입니다.",
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
                ? (proposalData?.message || "원고를 먼저 승인해 주세요. 승인하면 편집안(A·B)을 만듭니다.")
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
                // 승인 전이면 A·B가 없는 게 정상이다 — 그 사실을 그대로 말한다.
                const _tail = proposalNotice ?? "편집안(A·B)도 준비됐습니다.";
                const _doneMsg = {
                  id: `ai_analysis_done_${Date.now()}`,
                  sender: "ai" as const,
                  text: `분석을 마쳤습니다 — 조각 ${_fragCount}개를 만들었습니다${_failNote}. ${_tail}`,
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
              restoredTimelineRef.current = null;
              try {
                const tl = await videoService.getTimeline(activeNavItem, 300);
                if (tl?.entries?.length && isMounted) {
                  const msgs: any[] = [];
                  const gens: any[] = [];
                  for (const en of tl.entries) {
                    syncedTimelineIdsRef.current.add(en.client_id);
                    // [C 증발 방어] 재수화 메시지는 항상 확정 상태 — 혹 isInterpreting=true가
                    // 실린 payload가 있어도(중단 세션 잔재) 스피너로 숨지 않게 강제 해제.
                    if (en.kind === "message" && en.payload) msgs.push({ ...en.payload, isInterpreting: false });
                    else if (en.kind === "generation" && en.payload) gens.push(en.payload);
                  }
                  if (msgs.length) {
                    restoredTimelineRef.current = msgs; // 스켈레톤이 승계
                    // [TIMELINE-RACE] 스켈레톤이 이미 지나간 뒤 복원이 도착하면(HTTP가
                    // setProposals보다 느린 보통의 경우) ref는 영영 소비되지 않는다 —
                    // storyPlan이 있으면 직접 병합(id 중복 제외, 과거이므로 앞에).
                    setStoryPlan((prev: any) => {
                      if (!prev) return prev;
                      restoredTimelineRef.current = null;
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
  const restoredTimelineRef = useRef<any[] | null>(null);
  const syncedTimelineIdsRef = useRef<Set<string>>(new Set());
  const genSaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
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
      if (!modeGateOn && selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
        setHighlightedPanoramaFrag(null);
        setExpandedFragment(null);
        setMiniTarget(null);  // [B-2] 재클릭 해제 시 미니 창도 닫는다
      } else {
        setSelectedFragment(f);
        setActiveSource(f.source_video);
        const highlightId = String((f as any).fragment_id ?? getUid(f));
        setHighlightedPanoramaFrag(highlightId);
        window.setTimeout(() => setHighlightedPanoramaFrag(highlightId), 0);
        setExpandedFragment(null);
      }
    },
    [modeGateOn, selectedFragment]
  );

  // [2-2b] 조각편집 진입 (단일 조각 1개).
  const handleSingleFragmentEdit = useCallback(
    (f: Fragment) => {
      setSingleEditTarget(f);
      setSingleEditOpen(true);
    },
    []
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

  const roughCutFragmentsForFids = useCallback((fids: string[]) => {
    const byId = new Map(roughCutFragmentPool.map((fragment) => [getUid(fragment), fragment]));
    return fids
      .map((fid) => byId.get(fid))
      .filter((fragment): fragment is Fragment => !!fragment);
  }, [roughCutFragmentPool]);

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
    const selectedSpanIds = roughCutSelectedSpanIds.includes(span.span_id)
      ? roughCutSelectedSpanIds
      : [...roughCutSelectedSpanIds, span.span_id];
    const nextFids = storyFidsWith(getUid(fragment));
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
  const refreshLedgerEdl = useCallback(async () => {
    if (!activeNavItem || !activeNavItem.startsWith("proj_")) {
      setLedgerEdlClips([]);
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
    } catch (_) {
      setLedgerEdlClips([]);
    }
  }, [activeNavItem]);
  refreshLedgerEdlRef.current = refreshLedgerEdl;

  useEffect(() => { void refreshLedgerEdl(); }, [refreshLedgerEdl]);

  const physicalClips = useMemo(() => {
    return ledgerEdlClips.length ? ledgerEdlClips : buildExportClipsFromResolvedFragments(resolvedFragments);
  }, [ledgerEdlClips, resolvedFragments]);

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
    if (!activeNavItem?.startsWith("proj_")) return;
    if (!hasProjectMedia) return;
    const sig = `${activeNavItem}:${storyStage.key}`;
    if (stageVoiceRef.current === sig) return;
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
  }, [storyGate.enabled, activeNavItem, hasProjectMedia,
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
        <div
          className={`flex-shrink-0 flex items-center justify-center cursor-col-resize group transition-colors ${isNavDragging ? "bg-primary/15" : "hover:bg-primary/8"}`}
          style={{ width: 6 }}
          onMouseDown={(e) => {
            e.preventDefault();
            setIsNavDragging(true);
          }}
        >
          <div
            className={`w-[2px] h-10 rounded-full transition-all duration-150 ${isNavDragging
              ? "bg-primary/60 h-16"
              : "bg-border/40 group-hover:bg-primary/40 group-hover:h-14"
              }`}
          />
        </div>
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
            onCommitProposal={handleProposalCommit}
            onExport={handleExport}
            onConsultation={handleOnConsultation}
            onReproposal={(dir: any) => {
              handleReproposal(dir);
            }}
            fragments={resolvedFragments}
            exportClips={physicalClips}
            storyPlan={storyPlan}
            onStoryPlanConfirm={setStoryPlan}
            activeStoryFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : highlightedPanoramaFrag}
            modeGateEnabled={modeGateOn}
            activeFragmentId={selectedFragment ? String((selectedFragment as any).fragment_id ?? getUid(selectedFragment)) : null}
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
              />
            ) : undefined}
            storyReplacement={modeGateOn ? (
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
              />
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
          />
        )}
      </div>

      {!(activeNavItem === "archive" || activeNavItem === "upload" || activeNavItem === "account" || activeNavItem === "trash") && hasProjectMedia && (
        <>
          <div
            className={`flex-shrink-0 flex items-center justify-center cursor-col-resize group transition-colors ${isDragging ? "bg-primary/15" : "hover:bg-primary/8"
              }`}
            style={{ width: 6 }}
            onMouseDown={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
          >
            <div
              className={`w-[2px] h-10 rounded-full transition-all duration-150 ${isDragging
                ? "bg-primary/60 h-16"
                : "bg-border/40 group-hover:bg-primary/40 group-hover:h-14"
                }`}
            />
          </div>

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
                {rightStoryMode && !modeGateOn ? (
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
                    textButtonLabel="텍스트 조각"
                    textScope="selected"
                    onApproveComposition={handleApproveComposition}
                    onReopenComposition={handleReopenComposition}
                    storyApproved={storyStage.key === "final" || storyStage.key === "edit_consult"}
                    compositionNotice={compositionNotice}
                    modeRound={storyGate.story?.mode_round ?? 1}
                    sourceFragments={(sourceEntries ?? []).flatMap((e) => e.fragments ?? [])}
                    storyTextItems={modeStoryTextItems}
                    programId={activeNavItem}
                    onTextEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); setStoryLedgerRefreshNonce((n) => n + 1); }}
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
        onApply={handleSingleFragmentApply}
      />
      {/* [STORY-TRACK-B] 조각 단위 공용 미니 플레이창 — 텍스트·이미지 클릭 공용. 창 1개. */}
      <FragmentMiniPlayer target={miniTarget} onClose={() => setMiniTarget(null)} />
    </div>
  );
};

export default Index;
