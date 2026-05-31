export const MOCK_PROJECTS = [
  { id: "proj_1779800484308", name: "Active Verification Project", date: "5/26", count: 3 }
];

export const VERIFICATION_MOCK_FRAGMENTS = [
  {
    fragment_id: "SF_A_1",
    fragment_uid: "SF_A_1",
    root_fragment_uid: "SF_A_1",
    display_id: "A1",
    selection_state: "S",
    status: "committed",
    source_video: "A",
    start_frame: 0,
    end_frame: 150,
    duration: 150,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P001.jpg" },
    intelligence: { hook_score: 0.8, role: "Main", description: "Source A Clip 1" },
  },
  {
    fragment_id: "SF_A_2",
    fragment_uid: "SF_A_2",
    root_fragment_uid: "SF_A_2",
    display_id: "A2",
    selection_state: "S",
    status: "committed",
    source_video: "A",
    start_frame: 150,
    end_frame: 300,
    duration: 150,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P002.jpg" },
    intelligence: { hook_score: 0.5, role: "Sub", description: "Source A Clip 2" },
  },
  {
    fragment_id: "SF_B_1",
    fragment_uid: "SF_B_1",
    root_fragment_uid: "SF_B_1",
    display_id: "B1",
    selection_state: "S",
    status: "committed",
    source_video: "B",
    start_frame: 0,
    end_frame: 150,
    duration: 150,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P001.jpg" },
    intelligence: { hook_score: 0.9, role: "Main", description: "Source B Clip 1 (Untouched)" },
  },
  {
    fragment_id: "SF_B_2",
    fragment_uid: "SF_B_2",
    root_fragment_uid: "SF_B_2",
    display_id: "B2",
    selection_state: "S",
    status: "committed",
    source_video: "B",
    start_frame: 150,
    end_frame: 300,
    duration: 150,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P002.jpg" },
    intelligence: { hook_score: 0.7, role: "Sub", description: "Source B Clip 2 (Base)" },
  },
  {
    fragment_id: "SF_G_1",
    fragment_uid: "SF_G_1",
    root_fragment_uid: "SF_G_1",
    display_id: "G1",
    selection_state: "S",
    status: "committed",
    source_video: "G",
    start_frame: 0,
    end_frame: 150,
    duration: 150,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P001.jpg" },
    intelligence: { hook_score: 0.6, role: "Main", description: "Imported Clip G1" },
  },
  {
    fragment_id: "SF_A_1_M",
    fragment_uid: "SF_A_1_M",
    root_fragment_uid: "SF_A_1",
    parent_fragment_uid: "SF_A_1",
    display_id: "A1_M",
    selection_state: "S",
    status: "committed",
    source_video: "A",
    start_frame: 0,
    end_frame: 120,
    duration: 120,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P001.jpg" },
    intelligence: { hook_score: 0.8, role: "Main", description: "Source A Clip 1 (Modified)" },
  },
  {
    fragment_id: "SF_A_2_M",
    fragment_uid: "SF_A_2_M",
    root_fragment_uid: "SF_A_2",
    parent_fragment_uid: "SF_A_2",
    display_id: "A2_M",
    selection_state: "S",
    status: "committed",
    source_video: "A",
    start_frame: 150,
    end_frame: 270,
    duration: 120,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P002.jpg" },
    intelligence: { hook_score: 0.5, role: "Sub", description: "Source A Clip 2 (Modified)" },
  },
  {
    fragment_id: "SF_A_3_R",
    fragment_uid: "SF_A_3_R",
    root_fragment_uid: "SF_A_2",
    parent_fragment_uid: "SF_A_2",
    display_id: "A3_R",
    selection_state: "S",
    status: "committed",
    source_video: "A",
    start_frame: 200,
    end_frame: 300,
    duration: 100,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P002.jpg" },
    intelligence: { hook_score: 0.5, role: "Sub", description: "Source A Clip 2 (Reversed)" },
  },
  {
    fragment_id: "SF_B_2_M",
    fragment_uid: "SF_B_2_M",
    root_fragment_uid: "SF_B_2",
    parent_fragment_uid: "SF_B_2",
    display_id: "B2_M",
    selection_state: "S",
    status: "committed",
    source_video: "B",
    start_frame: 150,
    end_frame: 270,
    duration: 120,
    thumbnail: { thumbnail_url: "/static/thumbnails/SF_7F0980_SRC_CB9107CA_P002.jpg" },
    intelligence: { hook_score: 0.7, role: "Sub", description: "Source B Clip 2 (Modified)" },
  }
];

export const MOCK_SOURCE_ENTRIES = [
  {
    source_id: "SRC_A",
    label: "A",
    video_url: "/static/uploads/103434-662525884_medium.mp4",
    fragments: [VERIFICATION_MOCK_FRAGMENTS[0], VERIFICATION_MOCK_FRAGMENTS[1]],
    file_size_bytes: 1000000,
    duration_sec: 30
  },
  {
    source_id: "SRC_B",
    label: "B",
    video_url: "/static/uploads/148597-794221559_medium.mp4",
    fragments: [VERIFICATION_MOCK_FRAGMENTS[2], VERIFICATION_MOCK_FRAGMENTS[3]],
    file_size_bytes: 2000000,
    duration_sec: 30
  },
  {
    source_id: "SRC_G",
    label: "G",
    video_url: "/static/uploads/240659_medium.mp4",
    fragments: [VERIFICATION_MOCK_FRAGMENTS[4]],
    file_size_bytes: 3000000,
    duration_sec: 30
  }
];

export const MOCK_PROPOSALS_IDENTITY_EVIDENCE = {
  A: {
    proposal_id: "PROP_A",
    mode: "market",
    title: "시장형 편집 (A)",
    desc: "Mock Proposal A",
    score: "95%",
    key_fragments: ["SF_A_1", "SF_A_2"],
    resolved_aliases: [
      {
        proposal_fragment_id: "SF_A_1",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_1",
        display_id: "A1",
        start_sec: 0,
        end_sec: 5
      },
      {
        proposal_fragment_id: "SF_A_2",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_2",
        display_id: "A2",
        start_sec: 5,
        end_sec: 10
      }
    ]
  },
  B: {
    proposal_id: "PROP_B",
    mode: "user",
    title: "사용자형 편집 (B)",
    desc: "Mock Proposal B",
    score: "85%",
    key_fragments: ["SF_B_1", "SF_B_2_M", "SF_G_1"],
    resolved_aliases: [
      {
        proposal_fragment_id: "SF_B_1",
        source_id: "SRC_B",
        source_fragment_id: "SF_B_1",
        display_id: "B1",
        start_sec: 0,
        end_sec: 5
      },
      {
        proposal_fragment_id: "SF_B_2_M",
        source_id: "SRC_B",
        source_fragment_id: "SF_B_2_M",
        display_id: "B2_M",
        start_sec: 5,
        end_sec: 9
      },
      {
        proposal_fragment_id: "SF_G_1",
        source_id: "SRC_G",
        source_fragment_id: "SF_G_1",
        display_id: "G1",
        start_sec: 0,
        end_sec: 5
      }
    ]
  }
};

export const MOCK_PROPOSALS_THUMBNAIL_FIX = {
  A: {
    proposal_id: "PROP_A",
    mode: "market",
    title: "시장형 편집 (A)",
    desc: "Mock Proposal A",
    score: "95%",
    key_fragments: ["SF_A_1", "SF_A_2"],
    resolved_aliases: [
      {
        proposal_fragment_id: "SF_A_1",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_1",
        display_id: "A1",
        start_sec: 0,
        end_sec: 5
      },
      {
        proposal_fragment_id: "SF_A_2",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_2",
        display_id: "A2",
        start_sec: 5,
        end_sec: 10
      }
    ]
  },
  B: {
    proposal_id: "PROP_B",
    mode: "user",
    title: "사용자형 편집 (B)",
    desc: "Mock Proposal B",
    score: "85%",
    key_fragments: ["SF_A_1", "SF_A_2", "SF_A_1_M", "SF_A_2_M", "SF_A_3_R", "SF_G_1"],
    resolved_aliases: [
      {
        proposal_fragment_id: "SF_A_1",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_1",
        display_id: "A1",
        start_sec: 0,
        end_sec: 5
      },
      {
        proposal_fragment_id: "SF_A_2",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_2",
        display_id: "A2",
        start_sec: 5,
        end_sec: 10
      },
      {
        proposal_fragment_id: "SF_A_1_M",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_1_M",
        display_id: "A1_M",
        start_sec: 0,
        end_sec: 4
      },
      {
        proposal_fragment_id: "SF_A_2_M",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_2_M",
        display_id: "A2_M",
        start_sec: 5,
        end_sec: 9
      },
      {
        proposal_fragment_id: "SF_A_3_R",
        source_id: "SRC_A",
        source_fragment_id: "SF_A_3_R",
        display_id: "A3_R",
        start_sec: 6,
        end_sec: 9
      },
      {
        proposal_fragment_id: "SF_G_1",
        source_id: "SRC_G",
        source_fragment_id: "SF_G_1",
        display_id: "G1",
        start_sec: 0,
        end_sec: 5
      }
    ]
  }
};
