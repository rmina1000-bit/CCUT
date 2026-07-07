import React from "react";
import { Plus, ArrowUp } from "lucide-react";
import type { AppState } from "@/types";
import { StoryPlanPreview } from "@/proposal/proposalTypes";

interface ComposerSectionProps {
  storyPlan?: StoryPlanPreview | null;
  appState: AppState;
  onAddVideoFiles?: (files: File[]) => void;
  onRequestAddVideos?: () => void;
  handleUpload: () => void;
  consultationTextareaRef: React.RefObject<HTMLTextAreaElement>;
  consultationInput: string;
  setConsultationInput: (value: string) => void;
  resizeConsultationTextarea: (textarea?: HTMLTextAreaElement | null) => void;
  handleSubmitConsultation: () => void;
  chatValue: string;
  setChatValue: (value: string) => void;
  handleSendFull: () => void;
}

export function ComposerSection({
  storyPlan,
  appState,
  onAddVideoFiles,
  onRequestAddVideos,
  handleUpload,
  consultationTextareaRef,
  consultationInput,
  setConsultationInput,
  resizeConsultationTextarea,
  handleSubmitConsultation,
  chatValue,
  setChatValue,
  handleSendFull,
}: ComposerSectionProps) {
  return (
    <>
      {/* [STEP 10-I.5.28-E9-R2-R3-R2] ChatGPT-style auto-grow Composer */}
      {/* [UI-⑩⑪] 중앙창과 같은 배경색으로 통일, 과한 라운드 축소 */}
      {storyPlan && (
        <div
          className="sticky bottom-0 z-20 w-full bg-[#0a0a0b] px-5 py-4"
          onDragOver={(e) => { e.preventDefault(); }}
          onDrop={(e) => {
            // [UI-⑧] 채팅창에 영상 드래그 → 프로젝트에 추가
            e.preventDefault();
            const files = Array.from(e.dataTransfer?.files ?? []).filter((f) => f.type.startsWith("video/"));
            if (files.length > 0) onAddVideoFiles?.(files);
          }}
        >
          <div className="mx-auto flex w-full max-w-3xl items-end gap-3 rounded-lg border border-white/10 bg-[#161618] px-4 py-3 shadow-sm">
            {/* [UI-⑧] 영상 추가 — 컴포저 맨 앞 + */}
            <button
              type="button"
              title="영상 추가"
              onClick={() => (onRequestAddVideos ? onRequestAddVideos() : handleUpload())}
              className="flex h-9 w-9 shrink-0 items-center justify-center text-zinc-400 hover:text-white transition-colors"
            >
              <Plus size={18} />
            </button>
            <textarea
              ref={consultationTextareaRef}
              value={consultationInput}
              rows={1}
              placeholder="편하게 말씀해 주세요. 예: 사람 중심으로 / 더 빠르게 / 풍경 줄여"
              disabled={appState === "analyzing"}
              onChange={(e) => {
                setConsultationInput(e.target.value);
                resizeConsultationTextarea(e.currentTarget);
              }}
              onKeyDown={(e) => {
                if (e.nativeEvent.isComposing) return;
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmitConsultation();
                }
              }}
              className="min-h-[44px] max-h-[160px] flex-1 resize-none overflow-y-auto bg-transparent py-2 text-sm leading-relaxed text-zinc-100 outline-none placeholder:text-zinc-500 whitespace-pre-wrap break-words disabled:opacity-40"
            />
            {/* [UI-⑫] 원형 배경 제거, 위로 향한 화살표만 글자색으로 */}
            <button
              type="button"
              onClick={handleSubmitConsultation}
              disabled={!consultationInput.trim() || appState === "analyzing"}
              className="flex h-9 w-9 shrink-0 items-center justify-center text-zinc-100 hover:text-white disabled:opacity-30 transition-opacity"
              aria-label="의견 보내기"
            >
              <ArrowUp size={18} />
            </button>
          </div>
        </div>
      )}

      {/* [UI-이전디자인 삭제] 비컨설팅 상태 채팅바 — 새 컴포저와 동일 디자인으로 통일 */}
      {!storyPlan && (
        <div className="sticky bottom-0 z-20 w-full bg-[#0a0a0b] px-5 py-4">
          <div className="mx-auto flex w-full max-w-3xl items-center gap-3 rounded-lg border border-white/10 bg-[#161618] px-4 py-3 shadow-sm">
            {/* [UI-⑧] 영상 추가 — 컴포저 맨 앞 + */}
            <button
              type="button"
              title="영상 추가"
              onClick={() => (onRequestAddVideos ? onRequestAddVideos() : handleUpload())}
              className="flex h-9 w-9 shrink-0 items-center justify-center text-zinc-400 hover:text-white transition-colors"
            >
              <Plus size={18} />
            </button>
            <input
              type="text"
              value={chatValue}
              onChange={(e) => setChatValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSendFull();
              }}
              disabled={appState === "analyzing"}
              placeholder={
                appState === "analyzing"
                  ? "분석 중에는 잠시만 기다려 주세요..."
                  : "편하게 말씀해 주세요. 예: 사람 중심으로 / 더 빠르게 / 풍경 줄여"
              }
              className={`flex-1 bg-transparent py-2 text-sm leading-relaxed text-zinc-100 outline-none placeholder:text-zinc-500 ${appState === "analyzing" ? "opacity-40" : ""}`}
            />
            <button
              onClick={handleSendFull}
              disabled={!chatValue.trim() || appState === "analyzing"}
              className="flex h-9 w-9 shrink-0 items-center justify-center text-zinc-100 hover:text-white disabled:opacity-30 transition-opacity"
              aria-label="보내기"
            >
              <ArrowUp size={18} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
