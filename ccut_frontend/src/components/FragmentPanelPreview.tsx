import React, { useMemo, useState } from "react";
import FragmentPanel, {
  type EditStatePayload,
  type FragmentPanelContractState,
  type SoundMix,
} from "@/components/FragmentPanel";
import type { SoundRole, SoundRoleItem } from "@/utils/soundRoleClient";

function mockFrame(color: string, number: number): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="84" height="64" viewBox="0 0 84 64"><rect width="84" height="64" fill="${color}"/><circle cx="${18 + (number % 5) * 12}" cy="25" r="12" fill="#dbe7f0" opacity=".4"/><path d="M0 52L24 33l14 11 13-17 33 25v12H0z" fill="#18212a" opacity=".72"/><text x="6" y="14" fill="#fff" opacity=".8" font-size="9">${number}</text></svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

const INITIAL_STATE: FragmentPanelContractState = {
  anchor_start_ms: 203000,
  anchor_end_ms: 220700,
  trim_start_ms: 203900,
  trim_end_ms: 219100,
  excluded_ranges: [[207400, 209100], [214600, 215800]],
  removed: false,
  revision: 5,
};

const INITIAL_MIX: SoundMix[] = [
  { key: "voice", on: true, volume: 0.86 },
  { key: "ambience", on: true, volume: 0.64 },
  { key: "noise", on: false, volume: 0.24 },
];

const INITIAL_ROLE: SoundRoleItem = {
  ordinal: 3,
  timeline_item_id: "TI-0082",
  fragment_id: "FV-146",
  source_id: "SRC-20250730",
  anchor_start_ms: INITIAL_STATE.anchor_start_ms,
  anchor_end_ms: INITIAL_STATE.anchor_end_ms,
  coord_source: "transcript",
  detected_role: "dialogue",
  effective_role: "dialogue",
  reason: "transcript_overlap",
  evidence: {
    transcript: { available: true, word_count: 31, segment_count: 1 },
    silero: { available: false, speech_ratio: null },
    audio_energy: { available: true, value: 0.72 },
    silence: { available: false, detected: false },
  },
  overridden: false,
  revision: 5,
  editable: true,
};

const WORDS = Array.from({ length: 22 }, (_, index) => ({
  w: ["오늘", "여기", "정말", "바람이", "좋네요", "조금", "천천히", "가면", "더", "잘", "보여요"][index % 11],
  s_ms: 203400 + index * 690,
  e_ms: 203920 + index * 690 + (index % 4 === 0 ? 240 : 0),
}));

const FragmentPanelPreview: React.FC = () => {
  const [state, setState] = useState(INITIAL_STATE);
  const [pos, setPos] = useState(INITIAL_STATE.trim_start_ms);
  const [mix, setMix] = useState(INITIAL_MIX);
  const [role, setRole] = useState<SoundRoleItem>(INITIAL_ROLE);
  const [lastPayload, setLastPayload] = useState<EditStatePayload | null>(null);

  const frameUrls = useMemo(
    () => Array.from({ length: 12 }, (_, index) => mockFrame(["#415b72", "#695d54", "#486b62", "#6b5264"][index % 4], index + 1)),
    [],
  );

  const handleApply = (payload: EditStatePayload) => {
    setLastPayload(payload);
    const segments = payload.segments.map(({ startSec, endSec }) => [Math.round(startSec * 1000), Math.round(endSec * 1000)] as [number, number]);
    setState((current) => ({
      ...current,
      trim_start_ms: Math.round(payload.newStartSec * 1000),
      trim_end_ms: Math.round(payload.newEndSec * 1000),
      excluded_ranges: segments.length > 1 ? segments.slice(0, -1).map((segment, index) => [segment[1], segments[index + 1][0]]) : [],
    }));
  };

  const handleRoleChange = (_item: SoundRoleItem, nextRole: SoundRole) => {
    setRole((current) => ({ ...current, effective_role: nextRole, overridden: nextRole !== current.detected_role }));
  };

  return (
    <main className="min-h-screen bg-[var(--ccut-bg-0)] p-6 text-[var(--ccut-text-1)]">
      <div className="mx-auto max-w-[1120px]">
        <p className="mb-3 text-[11px] text-[var(--ccut-text-3)]">PBE 판 목업 · 외부 저장·재생 연결 없음</p>
        <FragmentPanel
          index={2}
          total={8}
          pos={pos}
          contractState={state}
          ids={{ fragmentId: "FV-146", timelineItemId: "TI-0082", sourceId: "SRC-20250730" }}
          sourceLabel="20250730_133445"
          sourceStartMs={203000}
          sourceEndMs={220700}
          text="바람이 좋아서 조금 천천히 가면 더 잘 보여요"
          words={WORDS}
          frameUrls={frameUrls}
          soundMix={mix}
          soundRole={role}
          onSoundRoleChange={handleRoleChange}
          onSoundMix={setMix}
          onApply={handleApply}
          onSeek={setPos}
          onPrev={() => setPos(INITIAL_STATE.trim_start_ms)}
          onNext={() => setPos(INITIAL_STATE.trim_end_ms)}
          onClose={() => undefined}
          onOpenBig={() => undefined}
          onRemoveFragment={() => setState((current) => ({ ...current, removed: true }))}
        />
        <pre className="mt-3 max-h-44 overflow-auto border border-[var(--ccut-line-soft)] p-3 text-[10px] text-[var(--ccut-text-3)]" data-pbe-preview-payload="true">
          {JSON.stringify(lastPayload, null, 2)}
        </pre>
      </div>
    </main>
  );
};

export default FragmentPanelPreview;
