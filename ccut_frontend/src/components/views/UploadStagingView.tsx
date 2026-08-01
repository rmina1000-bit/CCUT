import React, { useEffect, useRef, useState } from "react";
import { Upload, X, Plus, Clock, Play } from "lucide-react";

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

  // [UI-⑪ 국장지시] 여기서 바로 재생 — 별도 탐색기 없이 영상을 보고 한 줄을 단다.
  // 로컬 File 그대로 objectURL 재생(서버 왕복 없음). 한 번에 하나만, 닫으면 URL 해제.
  const [playingIdx, setPlayingIdx] = useState<number | null>(null);
  const playUrlRef = useRef<string | null>(null);
  const togglePlay = (i: number) => {
    if (playUrlRef.current) { URL.revokeObjectURL(playUrlRef.current); playUrlRef.current = null; }
    if (playingIdx === i) { setPlayingIdx(null); return; }
    playUrlRef.current = URL.createObjectURL(staged[i].file);
    setPlayingIdx(i);
  };
  useEffect(() => () => { if (playUrlRef.current) URL.revokeObjectURL(playUrlRef.current); }, []);
  useEffect(() => { if (playingIdx !== null && playingIdx >= staged.length) setPlayingIdx(null); }, [staged.length, playingIdx]);

  const { totalDur, analyzeSec, proposalSec } = estimateTimes(staged);
  const orientations = new Set(staged.map((s) => s.orientation).filter(Boolean));
  const mixedOrientation = orientations.size > 1;

  return (
    <div className="flex-1 w-full overflow-y-auto no-scrollbar px-4 py-6 flex flex-col items-center">
      <div className="w-full max-w-[760px] space-y-5">

        {/* [문진 도입부] — 의사 문진처럼, 대화 말투로 */}
        <div className="space-y-1">
          <h2 className="text-[14px] font-bold text-foreground">영상을 받았습니다. 편집 전에 몇 가지만 여쭤볼게요.</h2>
          <p className="text-[11px] text-muted-foreground/60 leading-relaxed">
            아래에서 영상을 더 넣거나 뺄 수 있고, 각 영상이 무엇인지 한 줄씩 알려주시면 편집 판단에 그대로 반영합니다.
          </p>
        </div>

        {/* 파일 목록 — 박스 없이 글자 행으로 */}
        <div className="divide-y divide-white/5">
          {staged.map((s, i) => (
            <div key={`${s.file.name}_${s.file.size}`} className="py-2.5 group/row">
              <div className="flex items-center gap-3">
                {/* [UI-⑪] 파일명 클릭 = 그 자리 재생/닫기 — 보고 나서 한 줄을 단다 */}
                <button
                  onClick={() => togglePlay(i)}
                  title={playingIdx === i ? "재생 닫기" : "여기서 바로 재생"}
                  className={`flex items-center gap-1.5 text-[12px] font-bold truncate max-w-[220px] transition-colors ${playingIdx === i ? "text-primary" : "text-foreground hover:text-primary"}`}
                >
                  <Play size={11} className={`flex-shrink-0 ${playingIdx === i ? "fill-primary" : "opacity-50"}`} />
                  <span className="truncate">{s.file.name}</span>
                </button>
                <span className="text-[10px] text-muted-foreground/76 font-mono flex-shrink-0">
                  {fmtDur(s.duration)}{s.orientation ? ` · ${s.orientation}` : ""}
                </span>
                <input
                  value={s.note}
                  onChange={(e) => onNoteChange(i, e.target.value)}
                  placeholder="무엇을 찍은 영상인가요? (예: 운동회 계주)"
                  className="flex-1 min-w-0 bg-transparent border-b border-white/10 focus:border-primary/50 px-1 py-1 text-[12px] text-foreground placeholder:text-muted-foreground/65 outline-none transition-colors"
                />
                <button
                  onClick={() => onRemove(i)}
                  title="이 영상 빼기"
                  className="p-1 text-muted-foreground/70 hover:text-red-400 transition-colors flex-shrink-0"
                >
                  <X size={13} />
                </button>
              </div>
              {playingIdx === i && playUrlRef.current && (
                <div className="mt-2 rounded-lg overflow-hidden border border-border/30 bg-black max-w-[420px]">
                  <video src={playUrlRef.current} controls autoPlay playsInline className="w-full max-h-[240px]" />
                </div>
              )}
            </div>
          ))}
          <div className="py-2.5">
            <button
              onClick={onAddFiles}
              className="flex items-center gap-1.5 text-[12px] text-muted-foreground/60 hover:text-primary transition-colors"
            >
              <Plus size={13} /> 영상 더 넣기
            </button>
          </div>
        </div>

        {/* [UI-⑫ 국장지시] 완성본 기준 질문은 '차이가 감지될 때만' —
            전부 같은 방향이면 방향을 묻지 않고, 영상이 1개면 볼륨을 묻지 않는다.
            (매번 같은 질문은 질문이 아니라 소음) */}
        {(mixedOrientation || staged.length > 1) && (
          <div className="space-y-3 pt-1">
            {mixedOrientation && (
            <div className="space-y-1.5">
              <p className="text-[12px] text-foreground">
                화면 방향이 섞여 있어요 — 완성본은 어느 방향으로 만들까요?
                <span className="text-[10px] text-muted-foreground/76 ml-2">
                  가로 {staged.filter((s) => s.orientation === "가로").length}개 · 세로 {staged.filter((s) => s.orientation === "세로").length}개
                </span>
              </p>
              <div className="flex gap-1.5">
                {([["auto", "자동 (다수를 따름)"], ["landscape", "가로로"], ["portrait", "세로로"]] as const).map(([v, l]) => (
                  <button key={v} onClick={() => setAspect(v)}
                    className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${aspect === v ? "bg-primary text-primary-foreground" : "bg-secondary/40 text-muted-foreground hover:text-foreground"}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>
            )}
            {staged.length > 1 && (
            <div className="space-y-1.5">
              <p className="text-[12px] text-foreground">
                영상이 여러 개예요 — 완성본 소리는 어떻게 할까요?
                <span className="text-[10px] text-muted-foreground/76 ml-2">녹음 크기가 서로 다르면 고르게 맞출 수 있어요</span>
              </p>
              <div className="flex gap-1.5">
                {([["original", "원본 소리 그대로"], ["normalize", "영상 간 볼륨 고르게"]] as const).map(([v, l]) => (
                  <button key={v} onClick={() => setSound(v)}
                    className={`px-2.5 py-1 rounded text-[11px] font-bold transition-all ${sound === v ? "bg-primary text-primary-foreground" : "bg-secondary/40 text-muted-foreground hover:text-foreground"}`}>
                    {l}
                  </button>
                ))}
              </div>
            </div>
            )}
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
