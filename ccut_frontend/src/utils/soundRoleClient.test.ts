import { afterEach, describe, expect, it, vi } from "vitest";

import {
  fetchSoundRoles,
  saveSoundRole,
  type SoundRoleItem,
} from "./soundRoleClient";

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

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("soundRoleClient", () => {
  it("saves a correction and restores it on the next read", async () => {
    const corrected = {
      ...ITEM,
      effective_role: "background" as const,
      overridden: true,
      revision: 1,
    };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        timeline_item_id: ITEM.timeline_item_id,
        fragment_id: ITEM.fragment_id,
        detected_role: ITEM.detected_role,
        effective_role: corrected.effective_role,
        overridden: true,
        revision: 1,
      }), { status: 200, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        ok: true,
        program_id: "proj_test",
        sequence_source: "ui_state",
        item_count: 1,
        storage_ready: true,
        material_missing_count: 0,
        items: [corrected],
      }), { status: 200, headers: { "Content-Type": "application/json" } }));
    vi.stubGlobal("fetch", fetchMock);

    const saved = await saveSoundRole("proj_test", ITEM, "background");
    const restored = await fetchSoundRoles("proj_test");

    expect(saved.effective_role).toBe("background");
    expect(restored.items[0]).toMatchObject({
      effective_role: "background",
      overridden: true,
      revision: 1,
    });
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/sound-role/proj_test", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        timeline_item_id: ITEM.timeline_item_id,
        fragment_id: ITEM.fragment_id,
        role: "background",
        expected_revision: null,
      }),
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/sound-role/proj_test");
  });
});
