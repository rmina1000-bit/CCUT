import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SoundRoleControl } from "./SoundRoleControl";
import type { SoundRoleItem } from "@/utils/soundRoleClient";

const ITEM: SoundRoleItem = {
  ordinal: 0,
  timeline_item_id: "timeline-1",
  fragment_id: "fragment-1",
  source_id: "source-1",
  anchor_start_ms: 1000,
  anchor_end_ms: 5000,
  coord_source: "proposal_sequence",
  detected_role: "dialogue",
  effective_role: "dialogue",
  reason: "transcript",
  evidence: {
    transcript: { available: true, word_count: 38, segment_count: 2 },
    silero: { available: false, speech_ratio: null },
    audio_energy: { available: false, value: null },
    silence: { available: false, detected: false },
  },
  overridden: false,
  revision: null,
  editable: true,
};

describe("SoundRoleControl", () => {
  it("shows the sensor reason and sends an explicit user correction", () => {
    const onChange = vi.fn();
    const onPlay = vi.fn();
    render(<SoundRoleControl item={ITEM} compact onChange={onChange} onPlay={onPlay} />);

    expect(screen.getByText("38단어")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "편집에서 다룰 방식" }), {
      target: { value: "background" },
    });
    fireEvent.click(screen.getByRole("button", { name: "조각 재생" }));

    expect(onChange).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenCalledWith(ITEM, "background");
    expect(onPlay).toHaveBeenCalledOnce();
  });
});
