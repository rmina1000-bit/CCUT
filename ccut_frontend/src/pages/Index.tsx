import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import LeftNav from "@/components/LeftNav";
import CenterPanel from "@/components/CenterPanel";
import OriginalPanorama from "@/components/OriginalPanorama";
import FragmentMap from "@/components/FragmentMap";
import ReservedFragments from "@/components/ReservedFragments";
import { useWorkspaceLayout } from "@/hooks/useWorkspaceLayout";
import { useProposalState } from "@/hooks/useProposalState";
import { ArchivePanel } from "@/components/ArchivePanel";
import { SnsUploadPanel } from "@/components/SnsUploadPanel";
import { AccountPanel } from "@/components/AccountPanel";
import { TrashPanel } from "@/components/TrashPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { SingleFragmentEditor } from "@/components/SingleFragmentEditor";
// [PBE REBUILD 2-1] 기존 PBE 컴포넌트 runtime import 제거. 타입만 임시 유지(새 편집창 신설 시 완전 제거).
// import PrecisionBoundaryEditor from "@/features/pbe/PrecisionBoundaryEditor";
import type { BoundaryEditorTarget } from "@/features/pbe/pbeTypes";


import {
  Fragment,
  SelectionState,
  FragmentStatus,
  initialEditFragments,
  initialReservedFragments,
} from "@/data/fragmentData";
import { useAnalysisFlow } from "@/hooks/useAnalysisFlow";
import type { SourceEntry } from "@/hooks/useAnalysisFlow";

import { assignShortDisplayIds, getUid, recalcDisplayIds } from "@/lib/fragmentIdentity";
import { videoService } from "@/services/videoService";

import { Direction, DirectionSnapshot, Proposal, StoryPlanPreview } from "@/proposal/proposalTypes";
import {
  createInitialSnapshot,
  createNextSnapshot,
} from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { resolveProposalFragments } from "@/utils/proposalFragmentResolver";
import { buildExportClipsFromResolvedFragments } from "@/utils/exportClipBuilder";

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

  const [holdPositions, setHoldPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [boundaryHighlightIds, setBoundaryHighlightIds] = useState<string[]>([]);
  const [editorTarget, setEditorTarget] = useState<BoundaryEditorTarget | null>(null);
  const [pbeWindow, setPbeWindow] = useState<Fragment[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
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
    logProposalPair
  } = useProposalState(
    sourceFragments,
    activeNavItem || "default_project",
    sourceEntries.length > 0
      ? sourceEntries.map(e => e.source_id)
      : currentSourceId ? [currentSourceId] : []
  );

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

        const labelFromIndex = (idx: number) => String.fromCharCode(65 + idx);

        const collectedEntries: SourceEntry[] = [];
        let firstSourceId: string | null = null;

        for (let i = 0; i < allFiles.length; i++) {
          const label = labelFromIndex(i);
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
            video_url: vurl,
            fragments: initialFrags,
            file_size_bytes: allFiles[i].size,
            duration_sec: initialFrags.length > 0 ? initialFrags[initialFrags.length - 1].end_frame / 30 : 0
          });

          console.log(`[N-01] ${label}: ${initialFrags.length}개 초벌 조각 완료`);
        }
        markTiming("upload_done");

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
          setProjects((prev) => prev.map((p) => (p.id === projectId ? { ...p, count: fileCount } : p)));
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


        setSourceEntries(collectedEntries);
        setActiveSource("A");

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

              setSourceEntries(updatedEntries);

              // 3. 제안 생성 요청
              let generatedProposals: Record<"A" | "B", any> = {} as any;
              let proposalData: any = null;
              markTiming("proposal_requested");

              try {
                // [B-5-FIX] 단일/멀티 모두 프로젝트(program_id) 경로로 일원화 — program_id 저장돼야 복원 가능
                const orderedSourceIds = uploadedSourceIds.filter(id => completedSourceIds.includes(id));
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
              }

              // 4. 최종 상태 적용
              if (Object.keys(generatedProposals).length === 0) {
                const initialSnapshot = createInitialSnapshot();
                generatedProposals = generateProposals(finalEditFragments, initialSnapshot);
                setDirectionSnapshot(initialSnapshot);
              }

              setEditFragments(finalEditFragments);
              setSourceFragments(updatedEntries[0]?.fragments || []);
              setProposals(generatedProposals);
              markTiming("proposal_mapped_to_ui");
              markTiming("story_visible"); // Set at same time as proposals are mapped
              setSemanticFragments(Object.values(semanticResults).flat());

              setAnalyzeProgress(100);
              setAnalyzeMessage(failedSourceIds.length > 0 ? `일부 분석 실패 (${failedSourceIds.length}개), 제안 생성 완료` : "모든 영상 분석 및 제안 완료");
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
    [logProposalPair, resetAnalysisState, toFullUrl, activeNavItem]
  );

  // Hash-based debug hydration for Playwright verification
  useEffect(() => {
    if (typeof window === "undefined") return;
    console.log("[Debug] hash hook checking hash:", window.location.hash);
    if (window.location.hash !== "#debug-hydrate") return;
    
    console.log("[Debug] Running Playwright mockup hydration adapter...");
    
    (window as any).triggerPBEMock = (caseTypeOrData?: any) => {
      if (typeof caseTypeOrData === "object" && caseTypeOrData !== null) {
        console.log("[Debug] Hydrating mock data from caller...");
        const { projects, sourceEntries, editFragments, proposals } = caseTypeOrData;
        if (projects) setProjects(projects);
        if (sourceEntries) setSourceEntries(sourceEntries);
        if (editFragments) {
          setEditFragments(editFragments);
          setSourceFragments(editFragments);
        }
        if (proposals) setProposals(proposals);
        setAppState("complete");
        return;
      }

      const caseType = typeof caseTypeOrData === "string" ? caseTypeOrData : "mid";
      console.log(`[Debug] triggerPBEMock called with caseType: ${caseType}`);

      const targetFps = 30.0;
      let targetFrags = [];
      const currentFrags = editFragments;

      if (caseType === "first") {
        targetFrags = [currentFrags[0]].filter(Boolean);
      } else if (caseType === "mid") {
        targetFrags = [currentFrags[0], currentFrags[1]].filter(Boolean);
      } else {
        targetFrags = [currentFrags[0], currentFrags[1], currentFrags[4] || currentFrags[2]].filter(Boolean);
      }

      setPbeWindow(targetFrags);
      setEditorTarget({
        leftRealIndex: 0,
        rightRealIndex: targetFrags.length - 1,
        clickSide: caseType === "first" ? "left" : caseType === "mid" ? "right" : "center",
      });
      setEditorOpen(true);

      const logDisplayIds = targetFrags.map(f => f.display_id || f.fragment_id);
      const logSelectionStates = targetFrags.map(f => f.selection_state || "S");
      console.log(`[PBE_OPEN_CONTEXT] leftFragId=${targetFrags[0]?.fragment_id || 'null'} rightFragId=${targetFrags[targetFrags.length - 1]?.fragment_id || 'null'} clickSide=${caseType === "first" ? "left" : caseType === "mid" ? "right" : "center"} targetFrags=[${logDisplayIds.join(', ')}] selection_states=[${logSelectionStates.join('/')}]`);
    };
  }, [editFragments]);

  // [B-5c] 마운트 시 백엔드 프로젝트 목록 로드 (재기동/새로고침 후에도 프로젝트 영속)
  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash === "#debug-hydrate") return;
    let alive = true;
    (async () => {
      try {
        const res = await videoService.listProjects();
        if (!alive || !res || !Array.isArray(res.projects)) return;
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
    })();
    return () => { alive = false; };
  }, []);

  // [FIX-HYD-A] 마지막으로 하이드레이션한 프로젝트 id. 진짜 '프로젝트 전환'과
  // '신규 업로드로 막 생성된 프로젝트(첫 하이드레이션)'를 구분하기 위한 기준점.
  const previousHydratedProjectRef = useRef<string | null>(null);
  // [FIX-HYD-EMPTY] 방금 업로드로 생성한 프로젝트 id. 분석 중 신규 프로젝트로 진입할 때
  // hydration의 fetch-전 클리어가 갓 만든 세션을 비우지 않도록 1회 표식(소비형).
  const justCreatedProjectRef = useRef<string | null>(null);

  // [CCUT1.0.4 PROPOSALS PROJECT SOURCES HYDRATION]
  useEffect(() => {
    if (typeof window !== "undefined" && window.location.hash === "#debug-hydrate") {
      console.log("[Hydration] Skipping backend hydration because #debug-hydrate is active");
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
        console.log(`[Hydration] Loading sources for project: ${activeNavItem}`);
        pushAnalysisLog(`[Hydration] Loading sources for project: ${activeNavItem}`.slice(0, 120));
        const data = await videoService.getProjectSources(activeNavItem);
        if (!isMounted) return;

        // 2. API 응답 project_id 가 요청 projectId와 다르면 hydration skip
        if (!data || data.project_id !== activeNavItem) {
          console.warn(`[Hydration] project_id mismatch. Request: ${activeNavItem}, Response: ${data?.project_id}`);
          return;
        }

        // 3. 응답 sources.length === 0
        //    NO_PROPOSALS_FOUND 는 "아직 제안 없음(분석 중)"일 수 있으므로,
        //    [FIX-HYD-A] 세션에 이미 소스가 있으면 업로드 화면으로 내리지 않고 그대로 유지한다.
        //    세션이 진짜 비어 있을 때만 empty 처리(빈 프로젝트 → 업로드 화면).
        if (!data.sources || data.sources.length === 0) {
          if (sourceEntries.length === 0) {
            console.log("[Hydration] Response sources length is 0 and session empty. Showing upload screen.");
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
            console.log("[Hydration] Response sources length is 0 but session has sources. Keeping current session (proposals likely not generated yet).");
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
              if (stateRes && stateRes.ui_state && isMounted) {
                const snap = JSON.parse(stateRes.ui_state);
                if (snap.reservedFragments?.length) setReservedFragments(snap.reservedFragments);
                if (snap.holdPositions) setHoldPositions(snap.holdPositions);
                if (snap.committedProposalId) setCommittedProposalId(snap.committedProposalId);
                if (snap.selectedProposalId) setSelectedProposalId(snap.selectedProposalId);
                if (snap.activeSource) setActiveSource(snap.activeSource);
                if (snap.deletedFragments?.length) setDeletedFragments(snap.deletedFragments);
                // [수정 6] proposals.key_fragments + customEditFragments 복원
                // DB proposals 원본 위에 저장된 현재 상태를 덮어씀
                if (snap.proposalsKeyFragments || snap.proposalsCustomFragments) {
                  setProposals((prev) => {
                    if (!prev) return prev;
                    const next: any = { ...prev };
                    for (const mode of ["A", "B"] as const) {
                      if (!next[mode]) continue;
                      if (snap.proposalsKeyFragments?.[mode] !== undefined) {
                        next[mode] = { ...next[mode], key_fragments: snap.proposalsKeyFragments[mode] };
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

            console.log(`[Hydration] Successfully hydrated ${restoredEntries.length} sources, ${(data.proposals || []).length} proposals for project: ${activeNavItem}`);
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
        messages: [
            { id: "ai_init", sender: "ai", text: draft, timestamp: Date.now() }
        ],
        story_intent: {}
    };

    setStoryPlan(newPlan);
  }, [appState, proposals, sourceEntries, storyPlan, setStoryPlan]);

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

  const handleSingleFragmentApply = useCallback(
    (payload: {
      fragmentUid: string;
      newStartSec: number;
      newEndSec: number;
      origStart: number;
      origEnd: number;
    }) => {
      const { fragmentUid, newStartSec, newEndSec, origStart, origEnd } = payload;
      const next = editFragments.map((fr) => {
        if (getUid(fr) !== fragmentUid) return fr;
        return {
          ...fr,
          start_sec: newStartSec,
          end_sec: newEndSec,
          start_time: newStartSec,
          end_time: newEndSec,
          orig_start_sec: (fr as any).orig_start_sec ?? origStart,
          orig_end_sec:   (fr as any).orig_end_sec   ?? origEnd,
          trim_applied: true,
        };
      });
      setEditFragments(next);

      // [F-2a-FIX] 편집 영속: 적용된 조각을 edit_overlay에 저장 (단건)
      try {
        const edited = next.find((fr) => getUid(fr) === fragmentUid) as any;
        if (edited?.source_id) {
          videoService.upsertEditOverlay({
            source_id: edited.source_id,
            fragment_id: edited.fragment_id ?? fragmentUid,
            effective_start_sec: newStartSec,
            effective_end_sec: newEndSec,
            excluded: edited.excluded === true || edited.status === "removed",
            edit_type: "TRIM",
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
      setEditFragments((proposal as any).customEditFragments);
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
    if (!committedProposalId || !proposals) {
      if (appState === "complete") {
        debugFragmentMap("[fragmentmap-debug] No committedProposalId or proposals. committedProposalId:", committedProposalId, "proposals:", !!proposals);
      }
      return { resolvedFragments: [], diagnostics: null };
    }
    const proposal = proposals[committedProposalId as "A" | "B"];
    const result = resolveProposalFragments(proposal, editFragments);
    
    // [STEP 10-I.5.12] Diagnostic Logging
    debugFragmentMap("[fragmentmap-debug] committedProposalId:", committedProposalId);
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
  }, [committedProposalId, editFragments, proposals, appState, debugFragmentMap]);

  const resolvedFragments = useMemo(() => resolverResult.resolvedFragments, [resolverResult]);

  const physicalClips = useMemo(() => {
    return buildExportClipsFromResolvedFragments(resolvedFragments);
  }, [resolvedFragments]);

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
    if (!committedProposalId || !proposals) return [];

    const proposal = proposals[committedProposalId as "A" | "B"];
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
  }, [committedProposalId, editFragments, proposals, reservedFragments]);

  const handleOpenBoundaryEditor = useCallback(
    async (leftFragId: string | null, rightFragId: string | null, clickSide?: "left" | "right" | "center") => {
      // [PBE REBUILD 2-1] 기존 편집창 진입 차단. 새 편집창 준비 중.
      console.log("[PBE_DISABLED] open blocked (rebuild in progress)");
      return;
      // ↓ 이하 기존 본문은 새 편집창 연결 시 정리 (지금은 도달 불가)
      // 1. Get left and right fragments based on the ID/UID strings in the timeline (filteredFragments)
      const leftFrag = leftFragId
        ? filteredFragments.find(f => f.fragment_id === leftFragId || getUid(f) === leftFragId)
        : null;
      const rightFrag = rightFragId
        ? filteredFragments.find(f => f.fragment_id === rightFragId || getUid(f) === rightFragId)
        : null;

      if (!leftFrag && !rightFrag) return;

      // 2. Build the exact PBE Window targeting the seam context (DoD §6 boundary context rules)
      // We want to load:
      // - If S|S: [leftFrag, rightFrag]
      // - If S|N|S: [leftFrag, ...middle_N_fragments, rightFrag]
      // - If Left single trim: [leftFrag]
      // - If Right single trim: [rightFrag]
      // [BETA1 PBE REDUCTION] PBE는 parent fragment 1개만 편집한다.
      // 두 조각 경계 / S|N|S / cross-source 편집은 1차 베타에서 제외.
      // 어떤 클릭이 들어와도 단일 조각으로 축소한다 (이음새/center = 좌측 조각).
      let targetFrags: Fragment[] = [];
      if (leftFrag) {
        targetFrags = [leftFrag];
      } else if (rightFrag) {
        targetFrags = [rightFrag];
      }

      // Format for PBE fragment specifications
      const pbeFragments = targetFrags.map(f => ({
        ...f,
        start_frame: f.start_frame ?? Math.round((f.start ?? f.start_time ?? 0) * 30),
        end_frame: f.end_frame ?? Math.round(((f.start ?? f.start_time ?? 0) + (f.duration ?? 0)) * 30),
        selection_state: f.selection_state || (reservedFragments.some(r => getUid(r) === getUid(f)) ? "N" : "S"),
      }));

      setPbeWindow(pbeFragments);
      setEditorTarget({
        leftRealIndex: 0,
        rightRealIndex: pbeFragments.length - 1,
        clickSide: clickSide || "center",
      });
      setEditorOpen(true);

      // 3. Proactively trigger backend panorama frame extraction to prevent broken frame thumbnails
      try {
        const payloadFrags = pbeFragments.map(f => ({
          fragment_id: f.fragment_id,
          source_id: f.source_id || currentSourceId,
          start_time: (f.start_frame ?? 0) / 30,
          end_time: (f.end_frame ?? 0) / 30
        }));

        fetch(`${videoService.API_BASE_URL}/pbe/extract-panoramas`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fragments: payloadFrags }),
        }).catch(err => console.error("Extract panorama request failed async:", err));
      } catch (e) {
        console.error("Failed to post extract panorama:", e);
      }
    },
    [filteredFragments, reservedFragments, currentSourceId]
  );

  // [F-2b] overlay 복원: currentSourceId 변경 시 DB trim값 merge
  useEffect(() => {
    if (!currentSourceId) return;
    (async () => {
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

  const handleEditorApply = useCallback(async (result: { updatedFragments: Fragment[]; removedFragmentIds: string[] }) => {
    const { updatedFragments } = result;
    setEditFragments(updatedFragments);
    setPbeWindow([]);
    setEditorOpen(false);

    if (committedProposalId && proposals) {
      setProposals((prev) => {
        if (!prev) return prev;
        const target = committedProposalId as "A" | "B";
        const newKeyOrder = updatedFragments
          .filter((f) => f.status !== "removed")
          .map((f) => getUid(f));
        return {
          ...prev,
          [target]: {
            ...prev[target],
            key_fragments: newKeyOrder,
            customEditFragments: updatedFragments
          },
        };
      });
    }

    setStoryPlan((prev: any) => {
      if (!prev) return prev;
      const systemMessage = {
        id: `pbe_apply_${Date.now()}`,
        sender: "ai" as const,
        text: `정밀 편집(PBE)을 통해 조각 경계가 수정되었습니다. 수정된 프레임 범위가 타임라인에 반영되었으며 새 편집안으로 저장되었습니다.`,
        timestamp: Date.now(),
      };
      return {
        ...prev,
        messages: [...(prev.messages ?? []), systemMessage],
      };
    });

    try {
      await fetch(`${videoService.API_BASE_URL}/save_edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fragments: updatedFragments,
          timestamp: Date.now(),
        }),
      });
    } catch (e) {
      console.error("Save edit error:", e);
    }

    // [F-2a] 편집 영속: 유효 조각을 edit_overlay에 저장 (기존 save_edit 유지, 별도)
    try {
      for (const f of updatedFragments) {
        const s = (f as any).start_time ?? (f as any).start_sec ?? (f as any).start;
        const e = (f as any).end_time ?? (f as any).end_sec ?? (f as any).end;
        if (typeof s !== "number" || typeof e !== "number") continue;
        await videoService.upsertEditOverlay({
          source_id: (f as any).source_id,
          fragment_id: f.fragment_id,
          effective_start_sec: s,
          effective_end_sec: e,
          excluded: (f as any).excluded === true || (f as any).status === "removed",
          edit_type: "TRIM",
          root_fragment_id: (f as any).root_fragment_uid ?? f.fragment_id,
        });
      }
    } catch (err) {
      console.error("edit-overlay save error:", err);
    }
  }, [setStoryPlan, committedProposalId, proposals, setProposals]);


  const handleOnConsultation = useCallback(async (text: string) => {
    if (editorOpen) {
      const userMsgId = `user_${Date.now()}`;
      const aiMsgId = `ai_${Date.now() + 1}`;

      const userMsg = {
        id: userMsgId,
        sender: "user" as const,
        text,
        timestamp: Date.now(),
      };

      const aiMsg = {
        id: aiMsgId,
        sender: "ai" as const,
        text: "비례바 명령을 처리 중입니다...",
        timestamp: Date.now() + 1,
        isInterpreting: true
      };

      setStoryPlan((prev: any) => {
        if (!prev) return prev;
        return {
          ...prev,
          messages: [...(prev.messages ?? []), userMsg, aiMsg],
        };
      });

      try {
        const seamId = pbeWindow.length > 0
          ? `SEAM_${pbeWindow[0]?.fragment_id}_${pbeWindow[pbeWindow.length - 1]?.fragment_id}`
          : "";
        const res = await fetch(`${videoService.API_BASE_URL}/pbe/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text, seam_id: seamId })
        });
        if (res.ok) {
          const data = await res.json();
          window.dispatchEvent(new CustomEvent("pbe-chat-command", { detail: data }));

          setStoryPlan((prev: any) => {
            if (!prev) return prev;
            return {
              ...prev,
              messages: (prev.messages ?? []).map((m: any) =>
                m.id === aiMsgId ? { ...m, text: data.ai_msg || "처리 완료.", isInterpreting: false } : m
              )
            };
          });
        }
      } catch (e) {
        console.error("PBE chat command failed:", e);
        setStoryPlan((prev: any) => {
          if (!prev) return prev;
          return {
            ...prev,
            messages: (prev.messages ?? []).map((m: any) =>
              m.id === aiMsgId ? { ...m, text: "오류가 발생했습니다.", isInterpreting: false } : m
            )
          };
        });
      }
      return;
    }

    handleConsultation(text);
  }, [editorOpen, handleConsultation, pbeWindow, setStoryPlan]);

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
      <div className="relative flex-shrink-0" style={{ width: navCollapsed ? 48 : 320 }}>
        <LeftNav
          activeItem={activeNavItem}
          onItemClick={(newId) => {
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
          }}
          projects={projects}
          collapsed={navCollapsed}
          onHome={onHome}
          onToggleCollapse={() => setNavCollapsed((prev) => !prev)}
          onRenameProject={(id, newName) => {
            setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name: newName } : p)));
            fetch(`${videoService.API_BASE_URL}/programs/${id}/name`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ name: newName }),
            }).catch((e) => console.error("[rename]", e));
          }}
          onDeleteProject={(id) => {
            videoService.deleteProject(id).catch(() => {});
            setProjects((prev) => prev.filter((p) => p.id !== id));
            if (activeNavItem === id) {
              setActiveNavItem("__new__");
            }
          }}
          onNewProject={() => {
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
          }}
        />
      </div>

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
          <TrashPanel />
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
            sourceEntries={sourceEntries}
            programId={activeNavItem}
            programTitle={projects.find(p => p.id === activeNavItem)?.name ?? undefined}
            onExportDone={() => {
              // [FIX-EXPORT-UISTATE] 내보내기 완료 시 ui_state 저장
              if (activeNavItem && activeNavItem.startsWith("proj_")) {
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
                videoService.saveProjectState(
                  activeNavItem,
                  { ui_state: JSON.stringify(uiSnap) }
                ).catch(() => {});
              }
              setActiveNavItem("upload");
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
      {/* [PBE REBUILD 2-1] 기존 편집창 진입 차단. 새 SingleFragmentEditor로 교체 예정.
      <PrecisionBoundaryEditor
        open={editorOpen}
        onOpenChange={setEditorOpen}
        fragments={pbeWindow}
        editFragments={editFragments}
        target={editorTarget}
        videoUrl={toFullUrl(currentVideoUrl)}
        sources={sourceEntries.map(s => ({ source_id: s.source_id, label: s.label, video_url: toFullUrl(s.video_url) || "" }))}
        onApply={handleEditorApply}
      />
      */}
      <SingleFragmentEditor
        open={singleEditOpen}
        onOpenChange={setSingleEditOpen}
        fragment={singleEditTarget}
        onApply={handleSingleFragmentApply}
      />
    </div>
  );
};

export default Index;


