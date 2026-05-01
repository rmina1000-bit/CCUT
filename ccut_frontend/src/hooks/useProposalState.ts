import { useState, useCallback } from "react";
import { Proposal, Direction, DirectionSnapshot } from "@/proposal/proposalTypes";
import { createNextSnapshot } from "@/proposal/directionSnapshot";
import { generateProposals } from "@/proposal/proposalOrchestrator";
import { Fragment } from "@/data/fragmentData";

export const useProposalState = (sourceFragments: Fragment[]) => {
  const [selectedProposalId, setSelectedProposalId] = useState<string | null>(null);
  const [committedProposalId, setCommittedProposalId] = useState<string | null>(null);
  const [proposals, setProposals] = useState<Record<"A" | "B", Proposal> | null>(null);
  const [directionSnapshot, setDirectionSnapshot] = useState<DirectionSnapshot | null>(null);

  const logProposalPair = useCallback(
    (pair: Record<"A" | "B", Proposal>, label: string) => {
      const keyA = pair.A.key_fragments;
      const keyB = pair.B.key_fragments;
      const firstA = keyA[0] ?? "none";
      const firstB = keyB[0] ?? "none";
      const isFirstDiff = firstA !== firstB;

      console.log("[strategyEngine] A order:", keyA);
      console.log("[strategyEngine] B order:", keyB);
      console.log(`[strategyEngine] A/B first fragment differs: ${isFirstDiff}`);
      console.log(`[PROPOSAL][${label}] snapshot=${pair.A.snapshot_id} (A:${firstA}, B:${firstB})`);
    },
    []
  );

  const handleProposalPreview = useCallback((id: string) => {
    setSelectedProposalId(id);
  }, []);

  const handleProposalCommit = useCallback((id: string) => {
    if (!proposals || !proposals[id as "A" | "B"]) {
      console.warn("[proposalState] commit blocked: proposals not ready", id);
      return;
    }
    console.log("[proposalState] handleProposalCommit called with id:", id);
    setSelectedProposalId(id);
    setCommittedProposalId(id);
  }, [proposals]);

  const handleReproposal = useCallback(
    (nextDirection: Direction) => {
      if (!sourceFragments.length) {
        console.warn("[Reproposal] sourceFragments is empty. Skipping reproposal.");
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

  return {
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
  };
};
