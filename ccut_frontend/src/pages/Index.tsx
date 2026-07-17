import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import LeftNav from "@/components/LeftNav";
import CenterPanel from "@/components/CenterPanel";
import OriginalPanorama from "@/components/OriginalPanorama";
import FragmentMap from "@/components/FragmentMap";
import ReservedFragments from "@/components/ReservedFragments";
import { useWorkspaceLayout } from "@/hooks/useWorkspaceLayout";
import { useProposalState } from "@/hooks/useProposalState";
import { useStoryGate } from "@/hooks/useStoryGate";
import { ArchivePanel } from "@/components/ArchivePanel";
import { SnsUploadPanel } from "@/components/SnsUploadPanel";
import { AccountPanel } from "@/components/AccountPanel";
import { TrashPanel } from "@/components/TrashPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { SingleFragmentEditor } from "@/components/SingleFragmentEditor";
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

type PbeContractState = Pick<
  EditStateRow,
  "anchor_start_ms" | "anchor_end_ms" | "trim_start_ms" | "trim_end_ms" | "excluded_ranges" | "removed"
>;

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
    reservedByProposal, setReservedByProposal,
    deletedByProposal, setDeletedByProposal,
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
  const storyGate = useStoryGate(activeNavItem, appState === "complete");

  // [#38] 보류맵 좌표도 제안별 구성 정보 (버킷 별칭은 displayProposalId 정의 뒤에)
  const [holdPositionsByProposal, setHoldPositionsByProposal] = useState<Record<"A" | "B", Record<string, { x: number; y: number }>>>({ A: {}, B: {} });
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
  const displayProposalId = committedProposalId ?? selectedProposalId ?? (proposals ? "A" : null);

  // [#38 — "조각의 속성은 공유, 제안의 구성은 분리"] 표시 제안의 버킷으로 보류·좌표·휴지통을 선택.
  // 기존 소비처(~20곳)의 호출 계약을 보존하기 위해 옛 이름의 파생 별칭 + 버킷 지향 setter를 제공한다.
  const proposalBucket: "A" | "B" = displayProposalId === "B" ? "B" : "A";
  const reservedFragments = reservedByProposal[proposalBucket];
  const deletedFragments = deletedByProposal[proposalBucket];
  const holdPositions = holdPositionsByProposal[proposalBucket];
  const setReservedFragments = useCallback((updater: Fragment[] | ((prev: Fragment[]) => Fragment[])) => {
    setReservedByProposal((prev) => ({
      ...prev,
      [proposalBucket]: typeof updater === "function" ? (updater as any)(prev[proposalBucket]) : updater,
    }));
  }, [proposalBucket, setReservedByProposal]);
  const setDeletedFragments = useCallback((updater: Fragment[] | ((prev: Fragment[]) => Fragment[])) => {
    setDeletedByProposal((prev) => ({
      ...prev,
      [proposalBucket]: typeof updater === "function" ? (updater as any)(prev[proposalBucket]) : updater,
    }));
  }, [proposalBucket, setDeletedByProposal]);
  const setHoldPositions = useCallback((updater: Record<string, { x: number; y: number }> | ((prev: Record<string, { x: number; y: number }>) => Record<string, { x: number; y: number }>)) => {
    setHoldPositionsByProposal((prev) => ({
      ...prev,
      [proposalBucket]: typeof updater === "function" ? (updater as any)(prev[proposalBucket]) : updater,
    }));
  }, [proposalBucket]);

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
          hook_score: f.intelligence?.hook_score || f.structural?.market_value || 0.5,
          role: f.intelligence?.role || f.structural?.role || "Main",
          description: f.intelligence?.description || f.intelligence?.visual_description || f.semantic?.summary || "",
        },
        preview_clip_url: f.preview_clip_url ?? null,
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

  // [#38] 스냅샷은 제안별 전체(byProposal)를 저장 — 같은 필드명, 값 형태만 승격 (하위호환 읽기는 재수화에서)
  const buildUiSnapshot = useCallback(() => ({
    reservedFragments: reservedByProposal,
    holdPositions: holdPositionsByProposal,
    committedProposalId,
    selectedProposalId,
    activeSource,
    deletedFragments: deletedByProposal,
    proposalsKeyFragments: proposals ? {
      A: (proposals as any).A?.key_fragments,
      B: (proposals as any).B?.key_fragments,
    } : undefined,
    proposalsCustomFragments: proposals ? {
      A: (proposals as any).A?.customEditFragments,
      B: (proposals as any).B?.customEditFragments,
    } : undefined,
  }), [reservedByProposal, holdPositionsByProposal, committedProposalId, selectedProposalId, activeSource, deletedByProposal, proposals]);

  // [#30 merge-저장 — 원칙 "모르는 것을 지우지 않는다" (국장 승인 2026-07-17)]
  // 클라 소유 필드(아래 목록)는 스냅샷이 덮어쓰고, 그 외(서버 소유·미지 — 예: paperCutOrder)는
  // 저장 직전 서버 원본을 읽어 보존 병합한다. 경계: 클라가 의도적으로 비운 소유 필드를
  // merge가 되살리면 #1(스냅샷 부활)의 재림 — 소유 필드는 절대 병합하지 않는다.
  const OWNED_UI_FIELDS = useMemo(() => new Set([
    "reservedFragments", "holdPositions", "committedProposalId", "selectedProposalId",
    "activeSource", "deletedFragments", "proposalsKeyFragments", "proposalsCustomFragments",
  ]), []);
  const saveUiStateMerged = useCallback(async (programId: string, snapshot: Record<string, any>) => {
    let unknown: Record<string, any> = {};
    try {
      const cur = await videoService.getProjectState(programId);
      if (cur?.ui_state) {
        const parsed = JSON.parse(cur.ui_state);
        for (const [k, v] of Object.entries(parsed)) {
          if (!OWNED_UI_FIELDS.has(k)) unknown[k] = v;
        }
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
    return videoService.saveProjectState(programId, { ui_state: JSON.stringify({ ...unknown, ...snapshot }) });
  }, [OWNED_UI_FIELDS, setStoryPlan]);

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
    saveUiState: saveUiStateMerged, // [#30] merge-저장 주입
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
              sourceStatusMap[sid] = statusData.status;

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

              setEditFragments(finalEditFragments);
              setSourceFragments(updatedEntries[0]?.fragments || []);
              if (!proposalsEmpty) setProposals(generatedProposals);
              markTiming("proposal_mapped_to_ui");
              markTiming("story_visible"); // Set at same time as proposals are mapped
              setSemanticFragments(Object.values(semanticResults).flat());

              setAnalyzeProgress(100);
              setAnalyzeMessage(
                proposalsEmpty
                  ? `분석은 끝났지만 편집 제안 생성에 실패했습니다 — ${proposalError ?? "백엔드가 제안을 반환하지 않았습니다"}. 조각은 보존되어 있으니 다시 시도해 주세요.`
                  : (failedSourceIds.length > 0 ? `일부 분석 실패 (${failedSourceIds.length}개), 제안 생성 완료` : "모든 영상 분석 및 제안 완료")
              );
              if (proposalsEmpty) {
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
        alert(`[분석 실패] ${errorMsg}`);
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
      return;
    }

    // [FIX-HYD-A] '진짜 프로젝트 전환'만 클리어 대상. 첫 하이드레이션(마운트/업로드 직후
    // 신규 프로젝트로 activeNavItem 최초 진입)은 전환이 아니므로 방금 분석한 세션을 보존한다.
    const isRealProjectSwitch =
      previousHydratedProjectRef.current !== null &&
      previousHydratedProjectRef.current !== activeNavItem;
    // [FIX-HYD-EMPTY] 방금 업로드로 생성한 프로젝트면 fetch-전 클리어 스킵(분석 세션 보존). 표식은 1회 소비.
    const isJustCreated = justCreatedProjectRef.current === activeNavItem;
    if (isJustCreated) justCreatedProjectRef.current = null;
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
        // [#38] 프로젝트 전환 클리어는 양 버킷 전체
        setReservedByProposal({ A: [], B: [] });
        setHoldPositionsByProposal({ A: {}, B: {} });
        setDeletedByProposal({ A: [], B: [] });
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
          DEBUG_LOG && console.warn(`[Hydration] project_id mismatch. Request: ${activeNavItem}, Response: ${data?.project_id}`);
          return;
        }

        // 3. 응답 sources.length === 0
        //    NO_PROPOSALS_FOUND 는 "아직 제안 없음(분석 중)"일 수 있으므로,
        //    [FIX-HYD-A] 세션에 이미 소스가 있으면 업로드 화면으로 내리지 않고 그대로 유지한다.
        //    세션이 진짜 비어 있을 때만 empty 처리(빈 프로젝트 → 업로드 화면).
        if (!data.sources || data.sources.length === 0) {
          if (sourceEntries.length === 0) {
            DEBUG_LOG && console.log("[Hydration] Response sources length is 0 and session empty. Showing upload screen.");
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
            DEBUG_LOG && console.log("[Hydration] Response sources length is 0 but session has sources. Keeping current session (proposals likely not generated yet).");
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
            setEditFragments(firstEntry.fragments);
            setSourceFragments(firstEntry.fragments);
            
            setCurrentSourceId(firstEntry.source_id);
            setCurrentVideoUrl(firstEntry.video_url);

            // [B-5-FIX] 저장된 A/B 제안 복원 → 돌아오면 하던 그대로
            if (data.proposals && data.proposals.length > 0) {
              setProposals(mapBackendProposals(data.proposals));
              setAppState("complete");
            } else {
              setAppState("empty");
            }

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
                    if (en.kind === "message" && en.payload) msgs.push(en.payload);
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
                DEBUG_LOG && console.warn("[TIMELINE] 복원 실패 — 새 흐름으로 시작", e);
              }
              if (stateRes && stateRes.ui_state && isMounted) {
                const snap = JSON.parse(stateRes.ui_state);
                // [#38 하위호환 읽기 — 유일 지점] 구형(공용 1벌)은 A·B 양쪽 복제로 승격,
                // 신형({A,B})은 그대로. 마이그레이션 스크립트 불요 — 열 때 자가 승격.
                const upFrags = (v: any): Record<"A" | "B", Fragment[]> | null => {
                  if (!v) return null;
                  if (Array.isArray(v)) return v.length ? { A: v, B: v } : null;
                  if (Array.isArray(v.A) || Array.isArray(v.B)) return { A: v.A ?? [], B: v.B ?? [] };
                  return null;
                };
                const upPos = (v: any): Record<"A" | "B", Record<string, { x: number; y: number }>> | null => {
                  if (!v || typeof v !== "object") return null;
                  // 신형 판별: A/B 키 보유 (조각 uid는 SF_/frag_ 계열이라 충돌 없음)
                  if (v.A !== undefined || v.B !== undefined) return { A: v.A ?? {}, B: v.B ?? {} };
                  return { A: v, B: v }; // 구형 평면 Record → 복제 승격
                };
                const rf = upFrags(snap.reservedFragments);
                if (rf) setReservedByProposal(rf);
                const hp = upPos(snap.holdPositions);
                if (hp) setHoldPositionsByProposal(hp);
                if (snap.committedProposalId) setCommittedProposalId(snap.committedProposalId);
                if (snap.selectedProposalId) setSelectedProposalId(snap.selectedProposalId);
                if (snap.activeSource) setActiveSource(snap.activeSource);
                const df = upFrags(snap.deletedFragments);
                if (df) setDeletedByProposal(df);
                // [수정 6] proposals.key_fragments + customEditFragments 복원
                // DB proposals 원본 위에 저장된 현재 상태를 덮어씀
                if (snap.proposalsKeyFragments || snap.proposalsCustomFragments) {
                  setProposals((prev) => {
                    if (!prev) return prev;
                    const next: any = { ...prev };
                    for (const mode of ["A", "B"] as const) {
                      if (!next[mode]) continue;
                      if (snap.proposalsKeyFragments?.[mode] !== undefined) {
                        const snapKF = snap.proposalsKeyFragments[mode];
                        // [HONEST-EMPTY GUARD] 빈 스냅샷은 사용자 편집이 아니라 빈 제안의 잔상.
                        // DB에 실제 조각이 있는 제안을 빈 배열로 덮지 않는다 (Hollyhock 사례).
                        if (Array.isArray(snapKF) && snapKF.length === 0 && (next[mode].key_fragments?.length ?? 0) > 0) {
                          DEBUG_LOG && console.warn("[Hydration] skip empty key_fragments snapshot for", mode);
                        } else {
                          next[mode] = { ...next[mode], key_fragments: snapKF };
                        }
                      }
                      if (snap.proposalsCustomFragments?.[mode] !== undefined) {
                        next[mode] = { ...next[mode], customEditFragments: snap.proposalsCustomFragments[mode] };
                      }
                    }
                    return next;
                  });
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
        if (isMounted) setIsSwitchingProject(false);
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


  // [STEP 10-I.5.28-E9-R1] StoryPlanPreview 자동 생성 (Skeleton)
  useEffect(() => {
    if (appState !== "complete" || !proposals) return;
    // [FIX-STORYPLAN-STALE] 소스 수 변경 시 storyPlan 재생성
    if (storyPlan && (storyPlan as any).source_count === (sourceEntries ?? []).length) return;

    const sourceCount = (sourceEntries ?? []).length;
    const isMulti = sourceCount >= 3;
    
    // 1. Project Type & Theme
    const projectType = isMulti ? "multi_source_memory" : "highlight_collection";
    const detectedTheme = isMulti ? "여러 영상 기반 기록형 프로젝트" : "짧은 하이라이트형 프로젝트";
    
    // 2. Risk Sources (analyzed_fragment_count 기반)
    const riskSources: any[] = [];
    (sourceEntries ?? []).forEach(entry => {
        if (entry.fragments.length <= 1) {
            riskSources.push({
                source_id: entry.source_id,
                label: entry.label,
                reason: "분석된 의미 조각이 매우 적음",
                status: "JUNK_SUSPECT"
            });
        }
    });

    // 3. Narrative Draft 생성 (A/B 구분 없이)
    const sourceNames = (sourceEntries ?? []).map(e => e.label).join(", ");
    const totalDuration = (sourceEntries ?? []).reduce((acc, e) => acc + (e.duration_sec ?? 0), 0);
    const draft = `이 프로젝트는 ${sourceCount}개의 영상(${sourceNames})을 기반으로 하며, 총 길이는 약 ${Math.floor(totalDuration)}초입니다. 
분석 결과, ${isMulti ? "여러 장소와 상황이 교차되는 복합적인 기록" : "특정 상황에 집중된 하이라이트"} 형태의 편집이 적합해 보입니다.

초반에는 영상의 분위기를 환기시키는 장면으로 시작하여, 중반에는 주요 인물이나 동작이 명확한 조각들을 중심으로 리듬감 있게 배치하고, 마지막은 여운이 남는 장면으로 마무리하는 흐름을 추천합니다.
특히 ${sourceNames} 영상들 사이의 자연스러운 연결을 위해 맥락이 닿는 조각들을 우선적으로 고려할 예정입니다.

이 방향이 맞을까요? 원하시면 '더 빠르게', '사람 중심으로', '감성적으로', '여러 영상 골고루'와 같이 말씀해 주세요.`;

    const newPlan: StoryPlanPreview = {
        story_plan_id: `STP_${Date.now()}`,
        source_count: sourceCount,
        project_type: projectType,
        detected_theme: detectedTheme,
        default_direction: isMulti ? "user_memory" : "market_highlight",
        direction_options: [
            { id: "market_highlight", label: "하이라이트", description: "강한 장면 위주의 빠른 전개" },
            { id: "user_memory", label: "자연스러운 기록", description: "현장감을 살린 자연스러운 구성" },
            { id: "fast", label: "더 빠르게", description: "핵심만 골라 템포 조절" },
            { id: "emotional", label: "더 감성적으로", description: "분위기 있는 장면 위주" }
        ],
        source_roles: {}, 
        risk_sources: riskSources,
        confirmation_status: "pending",
        consultation_status: "draft_ready",
        narrative_draft: draft,
        // [FLOW] 재생성 시 기존 대화를 지우지 않는다 — 개략은 새 메시지로 흐름에 추가.
        // (프로젝트 전환은 setStoryPlan(null)로 이미 초기화되므로 여기 병합은 같은 프로젝트 한정)
        // [TIMELINE] 저장된 과거 흐름(복원분)을 맨 앞에 승계 — 삭제 전까지 쌓이는 역사
        messages: [
            // 같은 텍스트의 개략(ai_init) 레거시 중복은 화면에서 1개로 접는다 —
            // 아래 fresh 개략(draft)과 겹치는 복원분 제외 (복원분끼리 포함)
            ...(() => { const seen = new Set([draft]); return (restoredTimelineRef.current ?? []).filter((m: any) => {
                if (!String(m.id).startsWith("ai_init_")) return true;
                if (seen.has(m.text)) return false;
                seen.add(m.text); return true;
            }); })(),
            ...(((storyPlan as any)?.messages) ?? []),
            // 결정론 id — 열 때마다 새 개략이 역사에 중복 누적되지 않게 (프로젝트×소스수당 1개;
            // 서버 client_id 멱등 + 복원 병합의 id 중복 제외가 같은 id로 물린다)
            { id: `ai_init_${activeNavItem}_${sourceCount}`, sender: "ai", text: draft, timestamp: Date.now() },
            // [UI-③⑤ 국장지시 v2] 영상 소개 기록 — 프로젝트의 시작이자 가장 중요한 내용.
            // 전 영상을 라벨(A,B..)·원본 제목과 함께 남겨 "어느 영상이 어느 영상인지"
            // 재생 없이도 알 수 있게 한다 (라벨 = 업로드 순서 = 원본맵 탭 순서)
            ...(intakeRef.current ? [{
                id: `ai_intake_${Date.now()}`,
                sender: "ai" as const,
                text: "영상 소개 — 말씀해주신 내용을 편집 판단에 그대로 반영합니다.\n" + [
                    ...intakeRef.current.videoNotes.map((v, i) =>
                        `${String.fromCharCode(65 + i)} · ${v.name.replace(/\.[A-Za-z0-9]{2,4}$/, "")}: ${v.note || "(설명 없음)"}`),
                    `화면 기준: ${intakeRef.current.aspectPreference === "portrait" ? "세로" : intakeRef.current.aspectPreference === "landscape" ? "가로" : "자동"} · 사운드: ${intakeRef.current.soundPreference === "normalize" ? "볼륨 고르게" : "원본 그대로"}`,
                ].join("\n"),
                timestamp: Date.now() + 1,
            }] : []),
        ],
        story_intent: {
            ...((storyPlan as any)?.story_intent ?? {}),
            ...(intakeRef.current ? {
                aspect_preference: intakeRef.current.aspectPreference,
                sound_preference: intakeRef.current.soundPreference,
                video_notes: intakeRef.current.videoNotes.filter((v) => v.note),
            } : {}),
        }
    };
    intakeRef.current = null; // 1회 주입 후 소진
    restoredTimelineRef.current = null; // [TIMELINE] 복원분 1회 승계 후 소진

    setStoryPlan(newPlan);
  }, [appState, proposals, sourceEntries, storyPlan, setStoryPlan]);

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

  const handleEditFragmentClick = useCallback(
    (f: Fragment) => {
      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
        setHighlightedPanoramaFrag(null);
        setExpandedFragment(null);
      } else {
        setSelectedFragment(f);
        setActiveSource(f.source_video);
        setHighlightedPanoramaFrag(getUid(f));
        setExpandedFragment(null);
      }
    },
    [selectedFragment]
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
    if (!window.confirm(`영상 ${label}을(를) 이 프로젝트에서 빼시겠어요?\n(원본 파일과 조각은 보존됩니다)`)) return;
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
      console.log(`[UI-②] source removed from project: ${source.source_id}`);
    } catch (err) {
      console.error("[UI-②] remove source failed:", err);
    }
  }, [activeNavItem, activeSource]);

  // [EDIT-CONTRACT-B0 IMPL-2b] EDIT_CONTRACT_V2 게이트 — OFF면 아래 전 분기 기존 경로 그대로 (쓰기 0)
  const [editContractV2, setEditContractV2] = useState(false);
  const [editStatesList, setEditStatesList] = useState<EditStateRow[]>([]);
  const [localPbeContractStates, setLocalPbeContractStates] = useState<Record<string, PbeContractState>>({});
  const editStatesRef = useRef<Map<string, EditStateRow>>(new Map());
  const editCtxRef = useRef<{ enabled: boolean; programId: string | null }>({ enabled: false, programId: null });
  const refreshLedgerEdlRef = useRef<(() => Promise<void>) | null>(null);
  const [storyLedgerRefreshNonce, setStoryLedgerRefreshNonce] = useState(0);
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
  // [EDIT-CONTRACT-B0] PBE 재진입용 — DB state 우선, cutover 전에는 적용 세션 state로 복원.
  const sfeContractState = useMemo(() => {
    if (!singleEditTarget) return null;
    const fid = String((singleEditTarget as any).root_fragment_uid ?? (singleEditTarget as any).fragment_id ?? "");
    const persisted = editContractV2 ? editStatesList.find((s) => s.parent_fragment_id === fid) : null;
    return persisted ?? localPbeContractStates[pbeContractKey(activeNavItem, fid)] ?? null;
  }, [activeNavItem, editContractV2, singleEditTarget, editStatesList, localPbeContractStates]);

  // [R2] 같은 parent에 상태 행이 여럿(NA/B 분열)일 때 표시 파생이 고를 행 = PBE 발급식 그대로.
  // ref 경유로 identity를 고정해 재수화 effect/memo의 deps를 흔들지 않는다.
  const preferredPbeItemIdRef = useRef<(fid: string) => string>(() => "");
  useEffect(() => {
    preferredPbeItemIdRef.current = (fid: string) =>
      timelineItemIdFor(editCtxRef.current.programId ?? "", String(committedProposalId ?? "NA"), fid, 0);
  }, [committedProposalId]);
  const preferredPbeItemIdFor = useCallback((fid: string) => preferredPbeItemIdRef.current(fid), []);

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
        const proposalKey = String(committedProposalId ?? "NA");
        const itemId = timelineItemIdFor(programId, proposalKey, rootFid, 0);
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
          const prefer = (fid: string) => timelineItemIdFor(programId, proposalKey, fid, 0);
          const rebuilt = rebuildFragmentTiles(editFragments as any[], states, prefer) as typeof editFragments;
          setEditFragments(rebuilt);
          if (committedProposalId && proposals) {
            setProposals((pPrev) => {
              if (!pPrev) return pPrev;
              const target = committedProposalId as "A" | "B";
              return { ...pPrev, [target]: { ...pPrev[target], customEditFragments: rebuilt } };
            });
          }
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

      if (committedProposalId && proposals) {
        setProposals((pPrev) => {
          if (!pPrev) return pPrev;
          const target = committedProposalId as "A" | "B";
          return {
            ...pPrev,
            [target]: {
              ...pPrev[target],
              customEditFragments: next,
            },
          };
        });
      }
    },
    [editFragments, committedProposalId, proposals, setProposals]
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
      } else {
        setSelectedFragment(f);
      }
    },
    [selectedFragment]
  );

  const handleReservedClick = useCallback(
    (f: Fragment) => {
      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
        setHighlightedPanoramaFrag(null);
      } else {
        setSelectedFragment(f);
        setActiveSource(f.source_video);
        setHighlightedPanoramaFrag(getUid(f));
      }
    },
    [selectedFragment]
  );

  const handleExcludeFromEdit = useCallback((f: Fragment) => {
    const next = editFragments.map((fr) => (getUid(fr) === getUid(f) ? { ...fr, excluded: true } : fr));
    setEditFragments(next);
    if (committedProposalId && proposals) {
      setProposals((pPrev) => {
        if (!pPrev) return pPrev;
        const target = committedProposalId as "A" | "B";
        return {
          ...pPrev,
          [target]: {
            ...pPrev[target],
            customEditFragments: next,
            key_fragments: next.filter((x) => !x.excluded && x.status !== "removed").map((x) => getUid(x))
          }
        };
      });
    }
  }, [editFragments, committedProposalId, proposals, setProposals]);

  const handleRestoreFragment = useCallback((f: Fragment) => {
    const next = editFragments.map((fr) => (getUid(fr) === getUid(f) ? { ...fr, excluded: false } : fr));
    setEditFragments(next);
    if (committedProposalId && proposals) {
      setProposals((pPrev) => {
        if (!pPrev) return pPrev;
        const target = committedProposalId as "A" | "B";
        return {
          ...pPrev,
          [target]: {
            ...pPrev[target],
            customEditFragments: next,
            key_fragments: next.filter((x) => !x.excluded && x.status !== "removed").map((x) => getUid(x))
          }
        };
      });
    }
  }, [editFragments, committedProposalId, proposals, setProposals]);

  const handleMoveToHold = useCallback(
    (f: Fragment) => {
      setReservedFragments((prev) => appendUniqueByUid(prev, { ...f, excluded: false }));
      const next = removeByUid(editFragments, f);
      setEditFragments(next);
      if (committedProposalId && proposals) {
        setProposals((pPrev) => {
          if (!pPrev) return pPrev;
          const target = committedProposalId as "A" | "B";
          const proposal = pPrev[target];
          if (!proposal) return pPrev;
          const keys = proposal.key_fragments.filter((k) => k !== getUid(f));
          return {
            ...pPrev,
            [target]: {
              ...proposal,
              key_fragments: keys,
              customEditFragments: next
            }
          };
        });
      }

      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
      }
    },
    [appendUniqueByUid, removeByUid, selectedFragment, editFragments, committedProposalId, proposals, setProposals]
  );

  const handleDropToHold = useCallback(
    (fragId: string, position?: { x: number; y: number }) => {
      const frag = editFragments.find((f) => getUid(f) === fragId);
      if (!frag) return;
      if (position) {
        setHoldPositions((prev) => ({ ...prev, [fragId]: position }));
      }
      handleMoveToHold(frag);
    },
    [editFragments, handleMoveToHold]
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
        if (committedProposalId && proposals) {
          setProposals((pPrev) => {
            if (!pPrev) return pPrev;
            const target = committedProposalId as "A" | "B";
            const proposal = pPrev[target];
            if (!proposal) return pPrev;
            return {
              ...pPrev,
              [target]: {
                ...proposal,
                key_fragments: proposal.key_fragments.filter((k) => k !== fid),
                customEditFragments: next
              }
            };
          });
        }
        setDeletedFragments((prev) => appendUniqueByUid(prev, fromEdit));
      }
    },
    [appendUniqueByUid, editFragments, reservedFragments, committedProposalId, proposals, setProposals]
  );

  const handleFragmentsReorder = useCallback(
    (reorderedFrags: Fragment[]) => {
      setEditFragments(reorderedFrags);
      const newKeyOrder = reorderedFrags.map((f) => f.fragment_id);

      if (!committedProposalId || !proposals) return;

      setProposals((prev) => {
        if (!prev) return prev;
        const target = committedProposalId as "A" | "B";
        return {
          ...prev,
          [target]: {
            ...prev[target],
            key_fragments: newKeyOrder,
            customEditFragments: reorderedFrags
          },
        };
      });
    },
    [committedProposalId, proposals, setProposals]
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

      if (committedProposalId && proposals) {
        setProposals((pPrev) => {
          if (!pPrev) return pPrev;
          const target = committedProposalId as "A" | "B";
          const proposal = pPrev[target];
          if (!proposal) return pPrev;
          const keys = proposal.key_fragments.filter((k) => k !== getUid(f));
          const idx = insertAt !== undefined ? Math.min(insertAt, keys.length) : keys.length;
          const newKeys = [...keys.slice(0, idx), getUid(f), ...keys.slice(idx)];
          return {
            ...pPrev,
            [target]: {
              ...proposal,
              key_fragments: newKeys,
              customEditFragments: next
            }
          };
        });
      }
    },
    [removeByUid, editFragments, committedProposalId, proposals, setProposals]
  );

  const handleAddFromSource = useCallback(
    (f: Fragment, insertAt?: number) => {
      if (!committedProposalId || !proposals) return;

      const copyId = `${f.fragment_id}_copy_${Date.now()}`;
      const newFrag: Fragment = {
        ...f,
        fragment_id: copyId,
        fragment_uid: copyId,
        display_id: f.display_id ? `${f.display_id}+` : `${f.fragment_id}+`,
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

      setProposals((pPrev) => {
        if (!pPrev) return pPrev;
        const target = committedProposalId as "A" | "B";
        const proposal = pPrev[target];
        if (!proposal) return pPrev;
        const keys = [...proposal.key_fragments];
        const idx = insertAt !== undefined ? Math.min(insertAt, keys.length) : keys.length;
        keys.splice(idx, 0, copyId);
        return {
          ...pPrev,
          [target]: {
            ...proposal,
            key_fragments: keys,
            customEditFragments: next
          }
        };
      });
    },
    [editFragments, committedProposalId, proposals, setProposals]
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

      if (committedProposalId && proposals) {
        setProposals((pPrev) => {
          if (!pPrev) return pPrev;
          const target = committedProposalId as "A" | "B";
          const proposal = pPrev[target];
          if (!proposal) return pPrev;
          const keys = proposal.key_fragments.filter((k) => k !== getUid(f));
          const idx = insertAt !== undefined ? Math.min(insertAt, keys.length) : keys.length;
          const newKeys = [...keys.slice(0, idx), getUid(f), ...keys.slice(idx)];
          return {
            ...pPrev,
            [target]: {
              ...proposal,
              key_fragments: newKeys,
              customEditFragments: next
            }
          };
        });
      }
    },
    [removeByUid, editFragments, committedProposalId, proposals, setProposals]
  );

  // A/B안 토글 시 각 안의 편집 상태(editFragments) 복원
  useEffect(() => {
    if (!committedProposalId || !proposals) return;

    const target = committedProposalId as "A" | "B";
    const proposal = proposals[target];
    if (!proposal) return;

    if ((proposal as any).customEditFragments) {
      // [GHOST#1 2a] 스냅샷 직주입 금지 — 순서·구성은 스냅샷을 따르되, 좌표·분할은
      // edit-state 재파생이 항상 이긴다 (edit-state 무근거 편집 잔상은 표시하지 않는다).
      // 게이트 OFF·상태 미로드 시엔 종전 그대로 (ref 경유라 effect deps 무변).
      const snap = (proposal as any).customEditFragments as any[];
      const states = Array.from(editStatesRef.current.values());
      setEditFragments(
        editCtxRef.current.enabled && states.length
          ? (rebuildFragmentTiles(snap, states, preferredPbeItemIdFor) as any)
          : (snap as any)
      );
    } else {
      const rawSeq = (proposal as any).resolved_aliases || (proposal as any).sequence || [];
      if (rawSeq.length > 0) {
        const initialFrags = rawSeq.map((s: any) => {
          const fragId = s.proposal_fragment_id || s.fragment_id || s.id;
          const baseFragId = fragId.replace(/_P\d{3}.*$/, "");
          const allSourceFrags: Fragment[] = sourceEntries.length > 0
            ? (sourceEntries as any[]).flatMap((e) => e.fragments ?? [])
            : sourceFragments;
          const matchSource = allSourceFrags.find(
            (sf) =>
              sf.fragment_id === (s.source_fragment_id || s.fragment_id || fragId) ||
              sf.fragment_id === baseFragId
          );

          const startF = s.start_sec !== undefined
            ? Math.round(s.start_sec * 30)
            : (s.start !== undefined ? Math.round(s.start * 30) : (matchSource?.start_frame ?? 0));
          const endF = s.end_sec !== undefined
            ? Math.round(s.end_sec * 30)
            : (s.end !== undefined ? Math.round(s.end * 30) : (matchSource?.end_frame ?? 150));

          // [2-2c-Fix2] 초 원본 보존 — 이미 존재하는 초 키에서만. 없으면 undefined. /30 역산 금지.
          const startSecVal = s.start_sec ?? s.start ?? s.start_time ?? matchSource?.start_time ?? matchSource?.start;
          const endSecVal   = s.end_sec   ?? s.end   ?? s.end_time   ?? matchSource?.end_time   ?? matchSource?.end;

          return {
            fragment_id: fragId,
            fragment_uid: fragId,
            source_video: s.source_video || matchSource?.source_video || activeSource,
            source_id: s.source_id || matchSource?.source_id || currentSourceId,
            display_id: matchSource?.display_id || (s.display_id && !/^\d+$/.test(s.display_id) && !s.display_id.startsWith("?") ? s.display_id : undefined),
            // [DISPLAY-NAME] 시퀀스 즉시표시 경로에도 권위 이름 통과
            display_name: (s as any).display_name || matchSource?.display_name,
            start_frame: startF,
            end_frame: endF,
            duration: endF - startF,
            start_time: startSecVal,
            end_time: endSecVal,
            selection_state: "S",
            excluded: false,
            thumbnail: s.thumbnail_url || matchSource?.thumbnail,
            intelligence: matchSource?.intelligence
          };
        });

        // 즉시 rawSeq 버전으로 표시
        setEditFragments(initialFrags);

        // [F-2b-MERGE] overlay 비동기 조회 → mergedFrags를 customEditFragments에 저장
        // 이렇게 해야 다음 L1395 재실행(A→B→A 전환) 시 overlay가 보존됨
        const snapSourceId = currentSourceId;
        if (snapSourceId) {
          (async () => {
            if (editCtxRef.current.enabled) {
              // [EDIT-CONTRACT-B0] ui_state로 복원된 customEditFragments를 덮어쓰지 않는다 — edit-state 권위
              const states = await refreshEditStatesRef.current();
              const rebuilt = states.length ? (rebuildFragmentTiles(initialFrags as any[], states, preferredPbeItemIdFor) as any[]) : initialFrags;
              setEditFragments(rebuilt as any);
              setProposals((prev) => {
                if (!prev || !prev[target]) return prev;
                const existing = (prev[target] as any).customEditFragments;
                // [GHOST#1 2a] 스냅샷이 신선한 rebuild를 이기지 않는다 —
                // 순서는 existing 유지, 좌표·분할은 edit-state로 재파생. 상태 미로드 시엔 종전 그대로.
                const refreshed = states.length
                  ? (existing?.length ? (rebuildFragmentTiles(existing as any[], states, preferredPbeItemIdFor) as any[]) : rebuilt)
                  : (existing?.length ? existing : rebuilt);
                return { ...prev, [target]: { ...prev[target], customEditFragments: refreshed } };
              });
              return;
            }
            try {
              const res = await videoService.getEditOverlay(snapSourceId);
              const overlays: any[] = Array.isArray(res) ? res : [];
              let mergedFrags: any[] = initialFrags;
              if (overlays.length > 0) {
                const overlayMap = new Map(overlays.map((o: any) => [o.fragment_id, o]));
                let changed = false;
                const merged = initialFrags.map((fr: any) => {
                  const o = overlayMap.get(fr.fragment_id ?? getUid(fr));
                  if (!o) return fr;
                  if (fr.start_sec === o.effective_start_sec && fr.end_sec === o.effective_end_sec) return fr;
                  changed = true;
                  return {
                    ...fr,
                    start_sec: o.effective_start_sec,
                    end_sec: o.effective_end_sec,
                    start_time: o.effective_start_sec,
                    end_time: o.effective_end_sec,
                    trim_applied: true,
                  };
                });
                if (changed) mergedFrags = merged;
              }
              setEditFragments(mergedFrags as any);
              setProposals((prev) => {
                if (!prev || !prev[target]) return prev;
                return {
                  ...prev,
                  [target]: {
                    ...prev[target],
                    customEditFragments: mergedFrags,
                  },
                };
              });
            } catch (_) {
              setProposals((prev) => {
                if (!prev || !prev[target]) return prev;
                return {
                  ...prev,
                  [target]: { ...prev[target], customEditFragments: initialFrags },
                };
              });
            }
          })();
        } else {
          setProposals((prev) => {
            if (!prev || !prev[target]) return prev;
            return {
              ...prev,
              [target]: { ...prev[target], customEditFragments: initialFrags },
            };
          });
        }
      }
    }
  }, [committedProposalId]);

  const resolverResult = useMemo(() => {
    if (!displayProposalId || !proposals) {
      if (appState === "complete") {
        debugFragmentMap("[fragmentmap-debug] No displayProposalId or proposals. displayProposalId:", displayProposalId, "proposals:", !!proposals);
      }
      return { resolvedFragments: [], diagnostics: null };
    }
    const proposal = proposals[displayProposalId as "A" | "B"];
    const result = resolveProposalFragments(proposal, editFragments, { expandAll: editContractV2 });
    
    // [STEP 10-I.5.12] Diagnostic Logging
    debugFragmentMap("[fragmentmap-debug] committedProposalId:", committedProposalId);
    debugFragmentMap("[fragmentmap-debug] selectedProposalId:", selectedProposalId);
    debugFragmentMap("[fragmentmap-debug] displayProposalId:", displayProposalId);
    debugFragmentMap("[fragmentmap-debug] proposals keys:", proposals ? Object.keys(proposals) : null);
    debugFragmentMap("[fragmentmap-debug] active proposal keys sample:", {
      count: proposal?.key_fragments?.length || 0,
      first10: proposal?.key_fragments?.slice(0, 10)
    });
    debugFragmentMap("[fragmentmap-debug] editFragments summary:", {
      count: editFragments.length,
      first10Ids: editFragments.slice(0, 10).map(f => f.fragment_id)
    });
    debugFragmentMap("[fragmentmap-debug] resolvedFragments summary:", {
      count: result.resolvedFragments.length,
      first10Ids: result.resolvedFragments.slice(0, 10).map(f => f.fragment_id)
    });

    return result;
  }, [displayProposalId, committedProposalId, selectedProposalId, editFragments, proposals, appState, debugFragmentMap, editContractV2]);

  const isPreviewingSelectedProposal = !!displayProposalId && displayProposalId === selectedProposalId && !committedProposalId;
  const resolvedFragments = useMemo(() => {
    let nextFragments = resolverResult.resolvedFragments;
    if (displayProposalId && proposals && resolverResult.diagnostics?.missingIds?.length) {
      const proposal = proposals[displayProposalId as "A" | "B"] as any;
      const proposalFragIds = proposal?.key_fragments || proposal?.sequence || [];
      const aliases = proposal?.resolved_aliases || [];
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
            source_video: sourceLabel || alias.source_id || "",
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
            stable_key: `${proposal?.proposal_id || displayProposalId}_${index}_${id}`,
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
  }, [resolverResult, displayProposalId, proposals, sourceEntries, toFullUrl, isPreviewingSelectedProposal, editContractV2, editStatesList]);

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
    setDeletedFragments([]);
  }, []);

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

  const filteredFragments = useMemo(() => {
    if (!displayProposalId || !proposals) return [];

    const proposal = proposals[displayProposalId as "A" | "B"];
    const proposalFragIds = proposal?.key_fragments || [];
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
  }, [displayProposalId, editFragments, proposals, reservedFragments]);

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

  // [F1 하나의 강물 — SEE FAIL 1 수리] 재생 불가 안내를 지휘부 채팅에 흘린다 (toast 폐지).
  // 연타 도배 금지: 직전 메시지가 동일 문구면 재전송하지 않는다. storyPlan 부재 시
  // 최소 골격 생성 (#3 절개분과 동일 규약 — 침묵 화면 금지).
  const handlePlaybackNotice = useCallback((text: string) => {
    setStoryPlan((prev: any) => {
      const msgs = prev?.messages ?? [];
      const last = msgs[msgs.length - 1];
      if (last?.sender === "ai" && last?.text === text) return prev;
      const notice = {
        id: `ai_playback_notice_${Date.now()}`,
        sender: "ai" as const,
        text,
        timestamp: Date.now(),
      };
      return { ...(prev ?? { story_plan_id: `STP_${Date.now()}` }), messages: [...msgs, notice] };
    });
  }, []);

  const handleBackgroundClick = useCallback((e: React.MouseEvent) => {
    const target = e.target as HTMLElement;
    if (target.closest(".fragment-tile")) return;

    setSelectedFragment(null);
    setHighlightedPanoramaFrag(null);
    setExpandedFragment(null);
  }, []);

  return (
    <div
      ref={containerRef}
      className="flex h-screen w-full overflow-hidden bg-background"
      onClick={handleBackgroundClick}
    >
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

      <div style={!(activeNavItem === "archive" || activeNavItem === "upload" || activeNavItem === "account" || activeNavItem === "settings" || activeNavItem === "trash") ? { width: centerWidth, flexShrink: 0 } : { flex: 1, minWidth: 0 }} className="h-full">
        {activeNavItem === "settings" ? (
          <SettingsPanel />
        ) : activeNavItem === "archive" ? (
          <ArchivePanel
            onNavigateToProject={(id) => setActiveNavItem(id)}
            onRenameProject={(id, newName) => {
              setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name: newName } : p)));
            }}
          />
        ) : activeNavItem === "upload" ? (
          <SnsUploadPanel
            onNavigateToProject={(id) => setActiveNavItem(id)}
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
            onStoryEditStateChanged={() => { refreshEditStatesRef.current(); void refreshLedgerEdl(); }}
            storyRefreshNonce={storyLedgerRefreshNonce}
            sourceEntries={sourceEntries}
            programId={activeNavItem}
            programTitle={projects.find(p => p.id === activeNavItem)?.name ?? undefined}
            onExportDone={() => {
              // [FIX-EXPORT-UISTATE] 내보내기 완료 시 ui_state 저장
              if (activeNavItem && activeNavItem.startsWith("proj_")) {
                // [#30] merge-저장 — 모르는 것을 지우지 않는다
                saveUiStateMerged(activeNavItem, buildUiSnapshot()).catch(() => {});
              }
              setActiveNavItem("upload");
            }}
            proposalHistory={proposalHistory}
            activeProposalEntryId={activeProposalEntryId}
            onRestoreProposalEntry={restoreProposalEntry}
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

      {!(activeNavItem === "archive" || activeNavItem === "upload" || activeNavItem === "account" || activeNavItem === "trash") && (
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

          <div className="flex-1 flex flex-col gap-2 p-2 overflow-hidden min-w-0">
            <input ref={appendInputRef} type="file" accept="video/*" multiple className="hidden" onChange={handleAppendFiles} />
            <OriginalPanorama
              activeSource={activeSource}
              onSourceChange={setActiveSource}
              highlightedFragmentId={highlightedPanoramaFrag}
              selectedFragmentId={selectedFragment?.fragment_id || null}
              onFragmentClick={handlePanoramaFragmentClick}
              intelligenceOn={intelligenceOn}
              onToggleIntelligence={() => setIntelligenceOn((p) => !p)}

              fragmentOverrides={fragmentOverrides}

              boundaryHighlightIds={boundaryHighlightIds}
              onBoundaryClick={(leftFragId, rightFragId) => handleOpenBoundaryEditor(leftFragId, rightFragId, "center")}
              onAddSource={() => appendInputRef.current?.click()}
              onRemoveSource={handleRemoveSource}
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
                    video_url: e.video_url,
                  }))
                  : currentSourceId
                    ? [{ source_id: currentSourceId, label: "A", video_url: currentVideoUrl || undefined }]
                    : []
              }
            />

            <div className="flex-1 overflow-y-auto">
              <FragmentMap
                fragments={resolvedFragments}
                onFragmentsChange={handleFragmentsReorder}
                selectedFragmentId={selectedFragment ? getUid(selectedFragment) : null}
                expandedFragmentId={expandedFragment}
                onFragmentClick={handleEditFragmentClick}
                onEditFragment={handleSingleFragmentEdit}
                onFragmentDoubleClick={handleEditFragmentDoubleClick}
                onExcludeFragment={handleExcludeFromEdit}
                onRestoreFragment={handleRestoreFromHold}
                onSourceRestore={handleAddFromSource}
                onMoveToHold={handleMoveToHold}
                onTrashRestore={handleRestoreToEdit}
                onBoundaryClick={handleOpenBoundaryEditor}
                sourceVideoUrls={Object.fromEntries(
                  (sourceEntries ?? []).map(e => [e.source_id, e.video_url]).filter(([, v]) => v)
                )}
              />
            </div>

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
              onDropToHold={handleDropToHold}
            />
          </div>
        </>
      )}
      <SingleFragmentEditor
        open={singleEditOpen}
        onOpenChange={setSingleEditOpen}
        fragment={singleEditTarget}
        projectName={projects.find(p => p.id === activeNavItem)?.name}
        contractState={sfeContractState}
        onApply={handleSingleFragmentApply}
      />
    </div>
  );
};

export default Index;
