export function getFragmentThumbnail(fragmentId: string): string | null {
  return null;
}

export function buildInitialBoardState(fragments: any[]): Record<string, {x: number, y: number}> {
  const positions: Record<string, {x: number, y: number}> = {};
  fragments.forEach((f, i) => {
    positions[f.fragment_id] = {
      x: (i % 4) * 120,
      y: Math.floor(i / 4) * 100
    };
  });
  return positions;
}
