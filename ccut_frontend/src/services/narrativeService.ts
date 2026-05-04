import { fetcher } from "./api";

export interface StoryIntentPatch {
  patch_type: string;
  tone: string;
  target_length: string;
  must_keep: string[];
  avoid: string[];
  reason: string;
}

export interface ConversationIntent {
  input_type: string;
  confidence: number;
  needs_story_patch: boolean;
  reply_type: string;
  short_reply: string;
  reason: string;
}

export interface NarrativeIntentResponse {
  status: string;
  patch?: StoryIntentPatch;
  classification?: ConversationIntent;
  latency_ms?: number;
  response_json_ok?: boolean;
  contract_valid?: boolean;
  error?: string;
}

export const narrativeService = {
  interpretIntent: async (message: string): Promise<NarrativeIntentResponse> => {
    return await fetcher("/narrative/intent", {
      method: "POST",
      body: JSON.stringify({ message }),
    });
  },
};
