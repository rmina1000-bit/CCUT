import { Fragment } from "@/data/fragmentData";
import { DirectionSnapshot, Proposal } from "./proposalTypes";
import { buildProposalPair } from "./strategyEngine";

export function generateProposals(
    fragments: Fragment[],
    snapshot: DirectionSnapshot
): Record<"A" | "B", Proposal> {
    return buildProposalPair(fragments, snapshot);
}