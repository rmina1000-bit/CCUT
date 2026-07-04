import React, { useEffect, useState } from "react";
import { Upload, X, Plus, Clock, Film } from "lucide-react";

/* [UI-①③④⑤] 업로드 스테이징 + 문진(問診)
   - 파일을 넣고/빼고/더 넣고 자유롭게 정리 (분석은 사용자가 시작 버튼을 눌러야)
   - 각 영상의 개략(길이/해상도/방향)을 브라우저에서 즉시 훑고,
     의사의 문진처럼 사용자에게 내용을 묻는다 (영상별 한 줄 + 화면/사운드 기준)
   - 분석·편집 예상 시간을 항상 먼저 말한다 (시간 개념의 CCUT) */

export interface StagedMeta {
  file: File;
  duration?: number;      // sec
  width?: number;
  height?: number;
  orientation?: "가로" | "세로" | "정방";
  note: string;           // 문진: 이 영상은 무엇인가
}

export interface IntakeAnswers {
  videoNotes: Array<{ name: string; note: string; duration?: number; orientation?: string }>;
  aspectPreference: "auto" | "landscape" | "portrait";
  soundPreference: "original" | "normalize";
}

interface Props {
  staged: StagedMeta[];
  onAddFiles: () => void;               // 파일 선택창 다시 열기
  onRemove: (index: number) => void;
  onNoteChange: (index: number, note: string) => void;
  onStart: (answers: IntakeAnswers) => void;
  onCancel: () => void;
}

const fmtDur = (s?: number) => {
  if (!s || !Number.isFinite(s)) return "—";
  const m = Math.floor(s / 60);
  return m > 0 ? `${m}분 ${Math.round(s % 60)}초` : `${Math.round(s)}초`;
};

export function estimateTimes(staged: StagedMeta[]) {
  const totalDur = staged.reduce((a, s) => a + (s.duration || 60), 0);
  // 실측 근거: 분석 병목은 ASR(whisper-vulkan ≈ x1.5 실시간) + 조각화/색인 오버헤드
  const analyzeSec = Math.ceil(totalDur / 1.5 + staged.length * 12);
  // 제안(A/B) 생성: 초회 판단+프리뷰 렌더 실측 1~2분대
  const proposalSec = Math.ceil(45 + staged.length * 8);
  return { totalDur, analyzeSec, proposalSec };
}

export function UploadStagingView({ staged, onAddFiles, onRemove, onNoteChange, onStart, onCancel }: Props) {
  const [aspect, setAspect] = useState<IntakeAnswers["aspectPreference"]>("auto");
  const [sound, setSound] = useState<IntakeAnswers["soundPreference"]>("original");

  const { totalDur, analyzeSec, proposalSec } = estimateTimes(staged);
  const orientations = new Set(staged.map((s) => s.orientation).filter(Boolean));
  const mixedOrientation = orientations.size > 1;

  return (
    <div className="flex-1 w-full overflow-y-auto no-scrollbar px-4 py-6 flex flex-col items-center">
      <div className="w-full max-w-[760px] space-y-5">

        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-[15px] font-bold text-foreground">영상 정리 & 문진</h2>
            <p className="text-[11px] text-muted-foreground/60 mt-0.5">
              넣고, 빼고, 더 넣으세요. 준비되면 아래에서 분석을 시작합니다.
            </p>
          </div>
          <button
            onClick={onAddFiles}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary/15 text-primary text-[12px] font-bold hover:bg-primary hover:text-primary-foreground transition-all"
          >
            <Plus size={14} /> 영상 추가
          </button>
        </div>

        {/* 파일 목록 + 영상별 문진 */}
        <div className="space-y-2">
          {staged.map((s, i) => (
            <div key={`${s.file.name}_${s.file.size}`} className="flex items-start gap-3 bg-[#161618] border border-white/8 rounded-lg px-4 py-3">
              <div className="w-8 h-8 rounded-md bg-primary/10 flex items-center justify-center flex-shrink-0 mt-0.5">
                <Film size={14} className="text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-[12px] font-bold text-foreground truncate">{s.file.name}</span>
                  <span className="text-[10px] text-muted-foreground/60 font-mono flex-shrink-0">
                    {fmtDur(s.duration)} · {s.width && s.height ? `${s.width}×${s.height}` : "훑는 중..."} · {s.orientation ?? ""}
                  </span>
                </div>
                <input
                  value={s.note}
                  onChange={(e) => onNoteChange(i, e.target.value)}
                  placeholder="이 영상은 무엇을 찍은 건가요? (예: 아이들 갯벌 체험, 운동회 계주)"
                  className="mt-1.5 w-full bg-black/30 border border-white/5 rounded-md px-2.5 py-1.5 text-[12px] text-foreground placeholder:text-muted-foreground/30 outline-none focus:border-white/15"
                />
              </div>
              <button
                onClick={() => onRemove(i)}
                title="이 영상 빼기"
                className="p-1.5 rounded-md text-muted-foreground/50 hover:text-red-400 hover:bg-red-500/10 transition-all flex-shrink-0"
              >
                <X size={14} />
              </button>
            </div>
          ))}
          {staged.length === 0 && (
            <div className="text-center py-10 text-[12px] text-muted-foreground/50 border border-dashed border-white/10 rounded-lg">
              영상이 없습니다. [영상 추가]로 넣어주세요.
            </div>
          )}
        </div>

        {/* 전역 문진: 화면/사운드 기준 (⑤) */}
        {staged.length > 0 && (
          <div className="grid grid-cols-2 gap-3">
            <div className="bg-[#161618] border border-white/8 rounded-lg px-4 py-3 space-y-2">
              <p className="text-[11px] font-bold text-foreground">
                화면 기준 {mixedOrientation && <span className="text-amber-400 font-medium">— 가로/세로가 섞여 있어요</span>}
              </p>
              <div className="flex gap-1.5">
                {([["auto", "자동(다수 기준)"], ["landscape", "가로"], ["portrait", "세로"]] as const).map(([v, l]) => (
                  <button key={v} onClick={() => setAspect(v)}
                    className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${aspect === v ? "bg-primary text-primary-foreground" : "bg-secondary/40 text-muted-foreground hover:text-foreground"}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>
            <div className="bg-[#161618] border border-white/8 rounded-lg px-4 py-3 space-y-2">
              <p className="text-[11px] font-bold text-foreground">사운드 기준</p>
              <div className="flex gap-1.5">
                {([["original", "원본 그대로"], ["normalize", "볼륨 고르게"]] as const).map(([v, l]) => (
                  <button key={v} onClick={() => setSound(v)}
                    className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${sound === v ? "bg-primary text-primary-foreground" : "bg-secondary/40 text-muted-foreground hover:text-foreground"}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 예상 시간 (④) + 시작 */}
        {staged.length > 0 && (
          <div className="bg-[#161618] border border-white/8 rounded-lg px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground/80">
              <Clock size={13} className="text-primary" />
              <span>
                영상 {staged.length}개 · 총 {fmtDur(totalDur)} — 분석 약 <b className="text-foreground">{fmtDur(analyzeSec)}</b>,
                이후 A/B 제안 약 <b className="text-foreground">{fmtDur(proposalSec)}</b> 예상
              </span>
            </div>
            <div className="flex gap-2">
              <button onClick={onCancel}
                className="px-3 py-1.5 rounded-lg text-[12px] text-muted-foreground hover:text-foreground transition-all">
                취소
              </button>
              <button
                onClick={() => onStart({
                  videoNotes: staged.map((s) => ({ name: s.file.name, note: s.note.trim(), duration: s.duration, orientation: s.orientation })),
                  aspectPreference: aspect,
                  soundPreference: sound,
                })}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-primary text-primary-foreground text-[12px] font-bold hover:opacity-90 transition-all"
              >
                <Upload size={13} /> 분석 시작
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* 브라우저에서 영상 개략 훑기(메타데이터만 — 파일 전송 없음) */
export function probeFileMeta(file: File): Promise<Partial<StagedMeta>> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "metadata";
    const done = (meta: Partial<StagedMeta>) => { URL.revokeObjectURL(url); resolve(meta); };
    v.onloadedmetadata = () => {
      const w = v.videoWidth, h = v.videoHeight;
      done({
        duration: Number.isFinite(v.duration) ? v.duration : undefined,
        width: w, height: h,
        orientation: w && h ? (w > h ? "가로" : w < h ? "세로" : "정방") : undefined,
      });
    };
    v.onerror = () => done({});
    v.src = url;
  });
}
