import { Direction, DirectionSnapshot } from "./proposalTypes";

export function createInitialSnapshot(): DirectionSnapshot {
    return {
        snapshot_id: "R1",
        active_direction: {},
        change_log: ["R1: initial proposal"],
    };
}

export function createNextSnapshot(
    prev: DirectionSnapshot | null,
    nextDirection: Direction
): DirectionSnapshot {
    const nextRound =
        prev?.snapshot_id && /^R\d+$/.test(prev.snapshot_id)
            ? Number(prev.snapshot_id.slice(1)) + 1
            : 1;

    const snapshotId = `R${nextRound}`;

    return {
        snapshot_id: snapshotId,
        active_direction: { ...nextDirection },
        change_log: [
            ...(prev?.change_log ?? []),
            `${snapshotId}: ${JSON.stringify(nextDirection)}`,
        ],
    };
}