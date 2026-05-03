import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import LeftNav from "@/components/LeftNav";
import CenterPanel from "@/components/CenterPanel";
import OriginalPanorama from "@/components/OriginalPanorama";
import FragmentMap from "@/components/FragmentMap";
import ReservedFragments from "@/components/ReservedFragments";
import { useWorkspaceLayout } from "@/hooks/useWorkspaceLayout";
import { useProposalState } from "@/hooks/useProposalState";


import {
  Fragment,
  SelectionState,
  FragmentStatus,
  initialEditFragments,
  initialReservedFragments,
} from "@/data/fragmentData";

import { assignShortDisplayIds, getUid, recalcDisplayIds } from "@/lib/fragmentIdentity";
import { videoService } from "@/services/videoService";

import { Direction, DirectionSnapshot, Proposal } from "@/proposal/proposalTypes";
import {
  createInitialSnapshot,
  createNextSnapshot,
} from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { resolveProposalFragments } from "@/utils/proposalFragmentResolver";
import { buildExportClipsFromResolvedFragments } from "@/utils/exportClipBuilder";

// Layout constants moved to useWorkspaceLayout.ts

type QuickScanData = {
  source_id?: string;
  status?: string;
  summary?: any;
  hypothesis?: any;
  questions?: any[];
  default_intent_seed?: any;
};

type SemanticFragmentData = {
  fragment_id: string;
  source_id?: string;
  start: number;
  end: number;
  semantic?: any;
  structural?: any;
  continuity?: any;
  confidence?: number;
  fallback_reason?: string | null;
};

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

  const [selectedFragment, setSelectedFragment] = useState<Fragment | null>(null);
  const [highlightedPanoramaFrag, setHighlightedPanoramaFrag] = useState<string | null>(null);
  const [expandedFragment, setExpandedFragment] = useState<string | null>(null);

  const [editFragments, setEditFragments] = useState<Fragment[]>(initialEditFragments);
  const [reservedFragments, setReservedFragments] = useState<Fragment[]>(initialReservedFragments);
  const [holdPositions, setHoldPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [deletedFragments, setDeletedFragments] = useState<Fragment[]>([]);

// selectedProposalId, committedProposalId moved to useProposalState

  const [appState, setAppState] = useState<"empty" | "analyzing" | "complete">("empty");
  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [analyzeMessage, setAnalyzeMessage] = useState("");
  const [intelligenceOn, setIntelligenceOn] = useState(false);

// proposals, directionSnapshot moved to useProposalState

  const [sourceFragments, setSourceFragments] = useState<Fragment[]>([]);
  const [currentSourceId, setCurrentSourceId] = useState<string | null>(null);
  const [currentVideoUrl, setCurrentVideoUrl] = useState<string | null>(null);
  const [quickScanData, setQuickScanData] = useState<QuickScanData | null>(null);
  const [semanticFragments, setSemanticFragments] = useState<SemanticFragmentData[]>([]);

  const {
    selectedProposalId,
    setSelectedProposalId,
    committedProposalId,
    setCommittedProposalId,
    proposals,
    setProposals,
    directionSnapshot,
    setDirectionSnapshot,
    handleProposalPreview,
    handleProposalCommit,
    handleReproposal,
    logProposalPair
  } = useProposalState(sourceFragments);


  type SourceEntry = {
    source_id: string;
    label: string;
    video_url: string;
    fragments: Fragment[];
    file_size_bytes?: number;
    duration_sec?: number;
  };
  const [sourceEntries, setSourceEntries] = useState<SourceEntry[]>([]);

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
    return `${videoService.API_BASE_URL}${path.startsWith("/") ? "" : "/"}${path}`;
  }, []);

  const appendUniqueByUid = useCallback((prev: Fragment[], nextFrag: Fragment) => {
    if (prev.some((f) => getUid(f) === getUid(nextFrag))) return prev;
    return [...prev, nextFrag];
  }, []);

  const removeByUid = useCallback((prev: Fragment[], target: Fragment) => {
    return prev.filter((f) => getUid(f) !== getUid(target));
  }, []);

// logProposalPair moved to useProposalState

  const resetAnalysisState = useCallback(() => {
    setSelectedProposalId(null);
    setCommittedProposalId(null);
    setProposals(null);
    setDirectionSnapshot(null);

    setSourceFragments([]);
    setEditFragments([]);
    setReservedFragments([]);
    setDeletedFragments([]);

    setSelectedFragment(null);
    setHighlightedPanoramaFrag(null);
    setExpandedFragment(null);

    setCurrentSourceId(null);
    setCurrentVideoUrl(null);
    setSourceEntries([]);
    setQuickScanData(null);
    setSemanticFragments([]);
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

        const mapFragments = (frags: any[], label: string) => {
          const mapped: Fragment[] = frags.map((f: any, idx: number) => {
            const fps = 30;
            // [STEP 10-I.5.5] Strict timing priority
            const startSec = f.start_sec ?? f.start ?? f.start_time ?? f.semantic?.start_sec ?? f.structural?.start_sec ?? 0;
            const endSec = f.end_sec ?? f.end ?? f.end_time ?? f.semantic?.end_sec ?? f.structural?.end_sec ?? 
                           (startSec + (f.duration_sec || f.structural?.duration || f.duration || 5));
            
            const startFrame = Math.round(f.start_frame ?? (startSec * fps));
            const endFrame = Math.round(f.end_frame ?? (endSec * fps));
            const durationFrames = Math.max(1, endFrame - startFrame);
            const rawThumb = f.intelligence?.thumb_url || f.thumb || f.thumbnail_url;

            return {
              fragment_id: f.fragment_id,
              fragment_uid: f.fragment_id,
              root_fragment_uid: f.root_fragment_uid || f.fragment_id,
              display_id: f.fragment_id,
              selection_state: "S" as SelectionState,
              status: "committed" as FragmentStatus,
              source_video: label,
              start_frame: startFrame,
              end_frame: endFrame,
              duration: durationFrames,
              thumbnail_hue: idx % 2 === 0 ? 211 : 30,
              thumbnail: {
                thumbnail_url: toFullUrl(rawThumb) ?? null,
              },
              intelligence: {
                hook_score: f.intelligence?.hook_score || f.structural?.market_value || 0.5,
                role: f.intelligence?.role || f.structural?.role || "Main",
                description: f.intelligence?.description || f.intelligence?.visual_description || f.semantic?.summary || "",
              },
            } as any;
          });

          if (mapped.length > 0) {
            console.log(`[mapFragments] ${label} (${mapped.length} frags) first thumb:`, mapped[0].thumbnail?.thumbnail_url);
          }
          return assignShortDisplayIds(recalcDisplayIds(mapped as any));
        };

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
        const projectId = `proj_${Date.now()}`;
        const fileCount = allFiles.length;

        setProjects((prev) => {
          const newProject = {
            id: projectId,
            name: dateStrYYMMDD + "-" + String(prev.length + 1).padStart(3, "0"),
            date: String(today.getMonth() + 1) + "/" + String(today.getDate()),
            count: fileCount,
          };
          return [newProject, ...prev];
        });


        setSourceEntries(collectedEntries);
        setActiveSource("A");

        const firstEntry = collectedEntries[0];
        if (!firstEntry) throw new Error("첫 번째 원본 처리 실패");

        setEditFragments(firstEntry.fragments);
        setSourceFragments(firstEntry.fragments);
        setAnalyzeProgress(80);
        setAnalyzeMessage("의미분석(Whisper) 진행 중입니다...");
        setAppState("analyzing");

        const uploadedSourceIds = collectedEntries.map(e => e.source_id).filter(Boolean);
        console.log("[N-01] 분석 대상 source_ids:", uploadedSourceIds);

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

              for (const sid of completedSourceIds) {
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
                  const mapped = mapFragments(rows, entry.label);
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
                if (completedSourceIds.length >= 2) {
                  // [STEP 10-I.5.27-E6] Source Identity Normalize: 업로드 순서(uploadedSourceIds) 유지
                  const orderedSourceIds = uploadedSourceIds.filter(id => completedSourceIds.includes(id));
                  
                  // 멀티 소스 프로젝트 제안
                  proposalData = await videoService.requestProjectProposals(projectId, orderedSourceIds, 60.0);
                  console.log("[proposal-project] Diagnostics:", {
                    project_id: proposalData.project_id,
                    source_ids: proposalData.source_ids,
                    source_usage: proposalData.source_usage,
                    warnings: proposalData.warnings,
                    completed: completedSourceIds,
                    failed: failedSourceIds
                  });
                } else {
                  // 단일 소스 제안
                  const sid = completedSourceIds[0];
                  const res = await fetch(`${videoService.API_BASE_URL}/proposals/${sid}`, { method: "POST" });
                  if (res.ok) proposalData = await res.json();
                }
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
                      proposal_story: p.proposal_story, // 스토리 보존
                      proposal_explanation: p.proposal_explanation, // [STEP 10-I.5.25-A] 설명 데이터 추가
                      direction: {},
                      snapshot_id: "R1",
                      template_id: p.mode,
                      slot_trace: []
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
    [logProposalPair, resetAnalysisState, toFullUrl]
  );

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
    setEditFragments((prev) =>
      prev.map((fr) => (getUid(fr) === getUid(f) ? { ...fr, excluded: true } : fr))
    );
  }, []);

  const handleRestoreFragment = useCallback((f: Fragment) => {
    setEditFragments((prev) =>
      prev.map((fr) => (getUid(fr) === getUid(f) ? { ...fr, excluded: false } : fr))
    );
  }, []);

  const handleMoveToHold = useCallback(
    (f: Fragment) => {
      setReservedFragments((prev) => appendUniqueByUid(prev, { ...f, excluded: false }));
      setEditFragments((prev) => removeByUid(prev, f));

      if (committedProposalId && proposals) {
        setProposals((prev) => {
          if (!prev) return prev;
          const proposal = prev[committedProposalId as "A" | "B"];
          if (!proposal) return prev;
          return {
            ...prev,
            [committedProposalId]: {
              ...proposal,
              key_fragments: proposal.key_fragments.filter((k) => k !== getUid(f)),
            },
          };
        });
      }

      if (selectedFragment && getUid(selectedFragment) === getUid(f)) {
        setSelectedFragment(null);
      }
    },
    [appendUniqueByUid, removeByUid, selectedFragment, committedProposalId, proposals]
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
        setEditFragments((prev) => prev.filter((f) => getUid(f) !== fid));
        setDeletedFragments((prev) => appendUniqueByUid(prev, fromEdit));
      }
    },
    [appendUniqueByUid, editFragments, reservedFragments]
  );

  const handleFragmentsReorder = useCallback(
    (reorderedFrags: Fragment[]) => {
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
          },
        };
      });
    },
    [committedProposalId, proposals]
  );

  const handleRestoreFromHold = useCallback(
    (f: Fragment, insertAt?: number) => {
      setReservedFragments((prev) => removeByUid(prev, f));

      setEditFragments((prev) => {
        const already = prev.some((x) => getUid(x) === getUid(f));
        if (already) return prev;
        const newFrag = { ...f, excluded: false };
        if (insertAt === undefined) return [...prev, newFrag];
        const arr = [...prev];
        arr.splice(insertAt, 0, newFrag);
        return arr;
      });

      if (committedProposalId && proposals) {
        setProposals((prev) => {
          if (!prev) return prev;
          const proposal = prev[committedProposalId as "A" | "B"];
          if (!proposal) return prev;
          const keys = proposal.key_fragments.filter((k) => k !== getUid(f));
          const idx = insertAt !== undefined ? Math.min(insertAt, keys.length) : keys.length;
          const newKeys = [...keys.slice(0, idx), getUid(f), ...keys.slice(idx)];
          return {
            ...prev,
            [committedProposalId]: { ...proposal, key_fragments: newKeys },
          };
        });
      }
    },
    [removeByUid, committedProposalId, proposals]
  );

  const handleAddFromSource = useCallback(
    (f: Fragment, insertAt?: number) => {
      if (!committedProposalId || !proposals) return;

      // 새 고유 ID 부여 — 원본과 구분되는 복사본
      const copyId = `${f.fragment_id}_copy_${Date.now()}`;
      const newFrag: Fragment = {
        ...f,
        fragment_id: copyId,
        fragment_uid: copyId,
        display_id: f.display_id ? `${f.display_id}+` : `${f.fragment_id}+`,
        excluded: false,
      };

      setEditFragments((prev) => [...prev, newFrag]);

      setProposals((prev) => {
        if (!prev) return prev;
        const proposal = prev[committedProposalId as "A" | "B"];
        if (!proposal) return prev;
        const keys = [...proposal.key_fragments];
        const idx = insertAt !== undefined ? Math.min(insertAt, keys.length) : keys.length;
        keys.splice(idx, 0, copyId);
        return {
          ...prev,
          [committedProposalId]: {
            ...proposal,
            key_fragments: keys,
          },
        };
      });
    },
    [committedProposalId, proposals]
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

      setEditFragments((prev) => {
        const already = prev.some((x) => getUid(x) === getUid(f));
        if (already) return prev;
        const newFrag = { ...f, excluded: false };
        if (insertAt === undefined) return [...prev, newFrag];
        const arr = [...prev];
        arr.splice(insertAt, 0, newFrag);
        return arr;
      });

      if (committedProposalId && proposals) {
        setProposals((prev) => {
          if (!prev) return prev;
          const proposal = prev[committedProposalId as "A" | "B"];
          if (!proposal) return prev;
          const keys = proposal.key_fragments.filter((k) => k !== getUid(f));
          const idx = insertAt !== undefined ? Math.min(insertAt, keys.length) : keys.length;
          const newKeys = [...keys.slice(0, idx), getUid(f), ...keys.slice(idx)];
          return {
            ...prev,
            [committedProposalId]: { ...proposal, key_fragments: newKeys },
          };
        });
      }
    },
    [removeByUid, committedProposalId, proposals]
  );

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
          onItemClick={setActiveNavItem}
          projects={projects}
          collapsed={navCollapsed}
          onToggleCollapse={() => setNavCollapsed((prev) => !prev)}
          onRenameProject={(id, newName) => {
            setProjects((prev) => prev.map((p) => (p.id === id ? { ...p, name: newName } : p)));
          }}
          onDeleteProject={(id) => {
            setProjects((prev) => prev.filter((p) => p.id !== id));
          }}
        />
      </div>

      <div style={{ width: centerWidth, flexShrink: 0 }}>
        <CenterPanel
          selectedFragment={selectedFragment}
          selectedSource={activeSource}
          appState={appState}
          onAppStateChange={setAppState}
          analyzeProgress={analyzeProgress}
          analyzeMessage={analyzeMessage}
          proposals={proposals}
          sourceFragments={sourceFragments}
          sourceId={currentSourceId}
          videoUrl={currentVideoUrl}
          onAnalyze={handleStartAnalysis}
          committedProposalId={committedProposalId}
          onPreviewProposal={handleProposalPreview}
          onCommitProposal={handleProposalCommit}
          onExport={handleExport}
          onReproposal={handleReproposal}
          fragments={resolvedFragments}
          exportClips={physicalClips}
          guidanceMessage={
            semanticFragments.length > 0
              ? "Semantic " + semanticFragments.length + " / Quick Scan " + (quickScanData?.status ?? "READY")
              : quickScanData?.status
                ? "Quick Scan " + quickScanData.status
                : undefined
          }
          sourceEntries={sourceEntries}
        />
      </div>

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

          fragmentOverrides={new Map()}

          boundaryHighlightIds={[]}
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
            onFragmentDoubleClick={handleEditFragmentDoubleClick}
            onExcludeFragment={handleExcludeFromEdit}
            onRestoreFragment={handleRestoreFromHold}
            onSourceRestore={handleAddFromSource}
            onMoveToHold={handleMoveToHold}
            onTrashRestore={handleRestoreToEdit}

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

    </div>
  );
};

export default Index;


