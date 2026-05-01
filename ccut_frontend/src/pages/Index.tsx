import React, { useState, useCallback, useRef, useEffect, useMemo } from "react";
import LeftNav from "@/components/LeftNav";
import CenterPanel from "@/components/CenterPanel";
import OriginalPanorama from "@/components/OriginalPanorama";
import FragmentMap from "@/components/FragmentMap";
import ReservedFragments from "@/components/ReservedFragments";

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

const MIN_CENTER = 420;
const MIN_RIGHT = 400;
const LEFT_NAV_WIDTH = 220;

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
  const [activeNavItem, setActiveNavItem] = useState("projects");
  const [navCollapsed, setNavCollapsed] = useState(false);
  const [projects, setProjects] = useState<{ id: string; name: string; date: string; count: number }[]>([]);

  const [activeSource, setActiveSource] = useState("A");

  const [selectedFragment, setSelectedFragment] = useState<Fragment | null>(null);
  const [highlightedPanoramaFrag, setHighlightedPanoramaFrag] = useState<string | null>(null);
  const [expandedFragment, setExpandedFragment] = useState<string | null>(null);

  const [editFragments, setEditFragments] = useState<Fragment[]>(initialEditFragments);
  const [reservedFragments, setReservedFragments] = useState<Fragment[]>(initialReservedFragments);
  const [holdPositions, setHoldPositions] = useState<Record<string, { x: number; y: number }>>({});
  const [deletedFragments, setDeletedFragments] = useState<Fragment[]>([]);

  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [committedProposalId, setCommittedProposalId] = useState<string | null>(null);

  const [appState, setAppState] = useState<"empty" | "analyzing" | "complete">("empty");
  const [analyzeProgress, setAnalyzeProgress] = useState(0);
  const [analyzeMessage, setAnalyzeMessage] = useState("");
  const [intelligenceOn, setIntelligenceOn] = useState(false);

  const [proposals, setProposals] = useState<Record<"A" | "B", Proposal> | null>(null);
  const [directionSnapshot, setDirectionSnapshot] = useState<DirectionSnapshot | null>(null);

  const [sourceFragments, setSourceFragments] = useState<Fragment[]>([]);
  const [currentSourceId, setCurrentSourceId] = useState<string | null>(null);
  const [currentVideoUrl, setCurrentVideoUrl] = useState<string | null>(null);
  const [quickScanData, setQuickScanData] = useState<QuickScanData | null>(null);
  const [semanticFragments, setSemanticFragments] = useState<SemanticFragmentData[]>([]);

  type SourceEntry = {
    source_id: string;
    label: string;
    video_url: string;
    fragments: Fragment[];
  };
  const [sourceEntries, setSourceEntries] = useState<SourceEntry[]>([]);

  const [centerWidth, setCenterWidth] = useState<number>(() => {
    const vw = typeof window !== "undefined" ? window.innerWidth : 1200;
    return Math.max(MIN_CENTER, Math.floor(vw * 0.55));
  });

  const [isDragging, setIsDragging] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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

  const logProposalPair = useCallback(
    (pair: Record<"A" | "B", Proposal>, label: string) => {
      const keyA = pair.A.key_fragments;
      const keyB = pair.B.key_fragments;
      const firstA = keyA[0] ?? "없음";
      const firstB = keyB[0] ?? "없음";
      const isFirstDiff = firstA !== firstB;

      console.log(`[strategyEngine] A안 순서:`, keyA);
      console.log(`[strategyEngine] B안 순서:`, keyB);
      console.log(`[strategyEngine] A/B 첫 조각 다름: ${isFirstDiff}`);
      console.log(`[PROPOSAL][${label}] snapshot=${pair.A.snapshot_id} (A:${firstA}, B:${firstB})`);
    },
    []
  );

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

  const handleStartAnalysis = useCallback(
    async (file?: File, extraFiles?: File[]) => {
      resetAnalysisState();

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
            // SF vs VF structure support
            const durationSec = f.duration || f.structural?.duration || (f.end_time - f.start_time) || (f.end - f.start) || 5;
            const startTime = f.start_time ?? f.start ?? 0;
            const startFrame = Math.round(f.start_frame ?? (startTime * fps));
            const endFrame = Math.round(
              f.end_frame ?? ((f.end_time ?? f.end ?? (startTime + durationSec)) * fps)
            );
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
                thumbnail_url:
                  toFullUrl(rawThumb) ??
                  `http://127.0.0.1:8000/static/thumbnails/${f.fragment_id}.jpg`,
              },
              intelligence: {
                hook_score: f.intelligence?.hook_score || f.structural?.market_value || 0.5,
                role: f.intelligence?.role || f.structural?.role || "Main",
                description: f.intelligence?.description || f.intelligence?.visual_description || f.semantic?.summary || "",
              },
            } as any;
          });

          if (mapped.length > 0) {
            console.log(`[mapFragments] ${label} 첫 조각 thumb:`, mapped[0].thumbnail?.thumbnail_url);
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

          const data = await videoService.generateFragments(sid);
          const initialFrags = mapFragments(data.fragments || [], label);

          collectedEntries.push({
            source_id: sid,
            label,
            video_url: vurl,
            fragments: initialFrags,
          });

          console.log(`[N-01] ${label}: ${initialFrags.length}개 초벌 조각 완료`);
        }

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

        if (!firstSourceId) throw new Error("source_id 확인 실패");

        let pollCount = 0;
        const MAX_POLLS = 100;

        const pollInterval = setInterval(async () => {
          try {
            pollCount++;
            const statusData = await videoService.getFragmentStatus(firstSourceId!);
            console.log(`[analysis-status] (${pollCount})`, statusData.status);

            if (statusData.status === "ANALYSIS_COMPLETE") {
              clearInterval(pollInterval);

              const freshData = await videoService.getFragmentsBySource(firstSourceId!);
              const finalMappedA = mapFragments(freshData.fragments || [], "A");

              setSourceEntries((prev) =>
                prev.map((e) => (e.label === "A" ? { ...e, fragments: finalMappedA } : e))
              );

              const combinedForEditing: Fragment[] = [
                ...finalMappedA,
                ...collectedEntries
                  .filter((e) => e.label !== "A")
                  .flatMap((e) => e.fragments),
              ];

              console.log(
                "[multi-source] merged fragments: " + combinedForEditing.length,
                "(A: " + finalMappedA.length + ", others: " + (combinedForEditing.length - finalMappedA.length) + ")"
              );

              const hooks = combinedForEditing.map(
                (f) => (f.intelligence as any)?.hook_score ?? 0.5
              );
              const uniqueHooks = new Set(hooks).size;
              const roles = combinedForEditing.map((f) => (f.intelligence as any)?.role);
              const uniqueRoles = new Set(roles.filter(Boolean)).size;
              const canProceed = uniqueHooks > 1 && uniqueRoles > 1;

              console.log(
                "[proposal-gate] canProceed:",
                canProceed,
                "| uniqueHooks:",
                uniqueHooks,
                "| uniqueRoles:",
                uniqueRoles
              );

              let generatedProposals: Record<"A" | "B", any> = {} as any;
              let semanticReady = false;

              try {
                setAnalyzeMessage("편집 제안 생성 중...");
                // [STEP 9] 2. Backend Proposal 생성 (POST /proposals/{source_id})
                try {
                  const quickScanRes = await fetch(
                    `${videoService.API_BASE_URL}/quick-scan/${firstSourceId}`
                  );
                  if (!quickScanRes.ok) {
                    throw new Error(`Quick Scan 조회 실패 (${quickScanRes.status})`);
                  }
                  const quickScan = await quickScanRes.json();
                  setQuickScanData(quickScan);
                  setAnalyzeMessage("Quick Scan 완료");
                } catch (quickScanErr) {
                  console.warn("[Index] Quick Scan Error:", quickScanErr);
                  setAnalyzeMessage("Quick Scan 조회 실패 - 계속 진행");
                }

                setAnalyzeMessage("Semantic Fragment 생성 중...");
                const semanticRes = await fetch(
                  `${videoService.API_BASE_URL}/semantic-fragments/${firstSourceId}`,
                  { method: "POST" }
                );
                if (!semanticRes.ok) {
                  throw new Error(`Semantic Fragment 생성 실패 (${semanticRes.status})`);
                }
                const semanticData = await semanticRes.json();
                const semanticRows = semanticData.fragments || [];
                if (semanticRows.length === 0) {
                  throw new Error("Semantic Fragment 결과가 비어 있습니다.");
                }
                semanticReady = true;
                setSemanticFragments(semanticRows);
                setAnalyzeMessage("Semantic Fragment 생성 완료");

                setAnalyzeMessage("편집 제안 생성 중...");
                const proposalRes = await fetch(`${videoService.API_BASE_URL}/proposals/${firstSourceId}`, {
                  method: "POST"
                });
                if (!proposalRes.ok) throw new Error("백엔드 제안 생성 실패");
                const proposalData = await proposalRes.json();

                const backendProposals = proposalData.proposals || [];
                if (backendProposals.length > 0) {
                  backendProposals.forEach((p: any) => {
                    const mode = p.mode === "A" ? "A" : "B";
                    generatedProposals[mode] = {
                      id: mode,
                      proposal_id: p.proposal_id,
                      mode: p.mode === "A" ? "market" : "user",
                      title: p.mode === "A" ? "시장형 편집 (A)" : "사용자친화형 편집 (B)",
                      desc: p.proposal_reason?.mode_reason || "백엔드 분석 기반 추천 편집안입니다.",
                      score: String(Math.round(p.confidence * 100)) + "%",
                      key_fragments: p.sequence.map((s: any) => s.fragment_id),
                      direction: {},
                      snapshot_id: "R1",
                      template_id: p.mode,
                      slot_trace: []
                    };
                    
                    // Enrich sequence with aliases for resolver
                    if (generatedProposals[mode].key_fragments.length > 0) {
                      (generatedProposals[mode] as any).resolved_aliases = p.sequence.map((s: any) => ({
                        proposal_fragment_id: s.fragment_id,
                        source_fragment_id: s.source_id,
                        display_id: s.display_id,
                        start_sec: s.start,
                        end_sec: s.end
                      }));
                    }
                  });
                }

                if (generatedProposals.A && !generatedProposals.B) {
                  generatedProposals.B = { ...generatedProposals.A, id: "B", title: "사용자친화형 편집 (B)" };
                } else if (!generatedProposals.A && generatedProposals.B) {
                  generatedProposals.A = { ...generatedProposals.B, id: "A", title: "시장형 편집 (A)" };
                }
              } catch (err) {
                if (!semanticReady) {
                  console.error("[Index] Semantic pipeline error:", err);
                  setAnalyzeMessage("Semantic Fragment 조회 실패");
                  setAnalyzeProgress(100);
                  setAppState("complete");
                  return;
                }
                console.error("[Index] Backend Proposal Error, fallback to client-side:", err);
              }

              // Fallback if backend failed or returned nothing
              if (Object.keys(generatedProposals).length === 0) {
                if (canProceed) {
                  const initialSnapshot = createInitialSnapshot();
                  generatedProposals = generateProposals(combinedForEditing, initialSnapshot);
                  setDirectionSnapshot(initialSnapshot);
                } else {
                  console.warn("[proposal-gate] 의미 데이터 분산 부족 - fallback 사용");
                  const allFragIds = combinedForEditing.map((f) => f.fragment_id);
                  const timeOrdered = [...combinedForEditing]
                    .sort((a, b) => (a.start_frame ?? 0) - (b.start_frame ?? 0))
                    .map((f) => f.fragment_id);

                  generatedProposals = {
                    A: {
                      id: "A",
                      mode: "market",
                      title: "시장형 편집",
                      desc: "분석 완료 후 더 정교한 제안이 생성됩니다.",
                      score: "50%",
                      key_fragments: allFragIds,
                      direction: {},
                      snapshot_id: "R0",
                      template_id: "fallback",
                      slot_trace: [],
                    },
                    B: {
                      id: "B",
                      mode: "user",
                      title: "사용자친화형 편집",
                      desc: "원본 시간 순서를 유지한 편집안입니다.",
                      score: "50%",
                      key_fragments: timeOrdered,
                      direction: {},
                      snapshot_id: "R0",
                      template_id: "fallback_time",
                      slot_trace: [],
                    },
                  };
                }
              }

              logProposalPair(generatedProposals, "INITIAL");

              setEditFragments(combinedForEditing);
              setSourceFragments(finalMappedA);

              setProposals(generatedProposals);
              setAnalyzeProgress(100);
              setAnalyzeMessage("분석 완료!");
              setAppState("complete");

              console.log("[N-01] analysis complete, proposal count fragments:", combinedForEditing.length);
            } else if (statusData.status === "FAILED") {
              clearInterval(pollInterval);
              setAnalyzeMessage("분석 실패: " + statusData.error);
              setAppState("complete");
            } else if (pollCount >= MAX_POLLS) {
              clearInterval(pollInterval);
              setAnalyzeMessage("분석 시간 초과 (백엔드에서 계속 진행될 수 있습니다)");
              setAppState("complete");
            }
          } catch (err) {
            console.error("[Index] Polling error:", err);
            if (pollCount >= MAX_POLLS) clearInterval(pollInterval);
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

  const handleProposalPreview = useCallback((id: string) => {
    console.log(`[STEP5] Proposal previewed: ${id}`);
    setSelectedProposalId(id);
  }, []);

  const handleProposalCommit = useCallback((id: string) => {
    console.log(`[STEP5] Proposal committed: ${id}`);
    setSelectedProposalId(id);
    setCommittedProposalId(id);
  }, []);

  const handleReproposal = useCallback(
    (nextDirection: Direction) => {
      if (!sourceFragments.length) {
        console.warn("[Reproposal] sourceFragments가 없어 재제안을 건너뜁니다.");
        return;
      }

      const nextSnapshot = createNextSnapshot(directionSnapshot, nextDirection);
      const nextProposals = generateProposals(sourceFragments, nextSnapshot);

      logProposalPair(nextProposals, "REPROPOSAL");

      setSelectedProposalId(null);
      setCommittedProposalId(null);
      setProposals(nextProposals);
      setDirectionSnapshot(nextSnapshot);

      console.log("[Reproposal] active_direction:", nextSnapshot.active_direction);
      console.log("[Reproposal] snapshot_id:", nextSnapshot.snapshot_id);
    },
    [directionSnapshot, logProposalPair, sourceFragments]
  );

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

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;

      const containerRect = containerRef.current.getBoundingClientRect();
      const totalWidth = containerRect.width;
      const relativeX = e.clientX - containerRect.left - LEFT_NAV_WIDTH;
      const maxCenter = totalWidth - LEFT_NAV_WIDTH - MIN_RIGHT;
      const clamped = Math.max(MIN_CENTER, Math.min(maxCenter, relativeX));

      setCenterWidth(clamped);
    };

    const handleMouseUp = () => setIsDragging(false);

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isDragging]);

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

  const filteredFragments = useMemo(() => {
    if (!committedProposalId || !proposals) return [];

    const proposal = proposals[committedProposalId as "A" | "B"];
    const proposalFragIds = proposal?.key_fragments || [];
    const aliases = (proposal as any)?.resolved_aliases || [];
    
    if (proposalFragIds.length === 0) {
      console.warn("[proposalResolver] proposalFragIds is empty for:", committedProposalId);
      return [];
    }

    console.log("[proposalResolver] proposal ids:", proposalFragIds);
    console.log("[proposalResolver] fragment aliases:", aliases.length);

    const result: Fragment[] = [];
    let exactCount = 0;
    let timeFallbackCount = 0;
    let singleFallbackCount = 0;

    proposalFragIds.forEach((id, idx) => {
      const alias = aliases[idx];
      
      // 1. Exact ID match (Exhaustive search)
      let found = editFragments.find((f: any) => {
        return (
          f.fragment_id === id ||
          f.fragment_uid === id ||
          f.id === id ||
          f.uid === id ||
          f.display_id === id ||
          f.original_id === id ||
          f.source_fragment_id === id ||
          f.root_fragment_uid === id ||
          f.parent_fragment_uid === id ||
          f.derivedFrom === id ||
          f.semantic?.id === id ||
          f.semantic?.fragment_id === id ||
          f.structural?.source_fragment_id === id ||
          f.intelligence?.semantic_fragment_id === id ||
          f.intelligence?.source_fragment_id === id
        );
      });

      if (found) {
        exactCount++;
      } else if (alias) {
        // 2. Time range fallback
        const pStart = alias.start_sec;
        const pEnd = alias.end_sec;
        
        found = editFragments.find((f: any) => {
          const fps = 30;
          const fStart = f.start_time ?? f.start ?? f.semantic?.start_sec ?? f.structural?.start_sec ?? (f.start_frame / fps);
          const fEnd = f.end_time ?? f.end ?? f.semantic?.end_sec ?? f.structural?.end_sec ?? (f.end_frame / fps);
          
          // Overlap check (within 0.5s tolerance)
          return Math.abs(fStart - pStart) < 0.5 && Math.abs(fEnd - pEnd) < 0.5;
        });
        
        if (found) timeFallbackCount++;
      }

      // 3. Single-fragment fallback
      if (!found && editFragments.length === 1 && proposalFragIds.length === 1) {
        found = editFragments[0];
        if (found) {
          singleFallbackCount++;
          console.warn("[proposalResolver] single fallback matched for ID:", id);
        }
      }

      if (found) {
        result.push(found);
      }
    });

    console.log(`[proposalResolver] exact matched: ${exactCount}`);
    console.log(`[proposalResolver] time fallback matched: ${timeFallbackCount}`);
    console.log(`[proposalResolver] single fallback matched: ${singleFallbackCount}`);
    console.log(`[filteredFragments] mode: ${committedProposalId}, proposalFragIds: ${proposalFragIds.length}, matched: ${result.length}`);

    if (result.length < proposalFragIds.length) {
      console.warn(
        `[proposalResolver] mismatch! result count: ${result.length}, expected: ${proposalFragIds.length}`
      );
    }

    return result;
  }, [committedProposalId, editFragments, proposals]);

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
          fragments={filteredFragments}
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
                source_id: e.label,
                video_url: e.video_url,
              }))
              : currentSourceId
                ? [{ source_id: "A", video_url: currentVideoUrl || undefined }]
                : []
          }
        />

        <div className="flex-1 overflow-y-auto">
          <FragmentMap
            fragments={filteredFragments}
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


