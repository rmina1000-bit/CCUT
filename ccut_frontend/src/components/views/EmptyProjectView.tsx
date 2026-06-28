import React from "react";
import { Upload } from "lucide-react";

interface EmptyProjectViewProps {
  handleUpload: () => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  handleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export function EmptyProjectView({ handleUpload, fileInputRef, handleFileChange }: EmptyProjectViewProps) {
  return (
    <div className="flex-1 flex items-center justify-center p-6 text-center">
      <div
        className="w-full max-w-[320px] border-2 border-dashed border-primary/20 rounded-3xl p-12 flex flex-col items-center gap-5 hover:border-primary/40 hover:bg-primary/5 transition-all cursor-pointer group shadow-2xl shadow-primary/5"
        onClick={handleUpload}
      >
        <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center group-hover:scale-110 group-hover:rotate-3 transition-all duration-300">
          <Upload size={24} className="text-primary" />
        </div>

        <div className="space-y-2">
          <h2 className="text-[15px] font-bold text-foreground">새 프로젝트 시작</h2>
          <p className="text-[12px] text-muted-foreground/60 leading-relaxed">
            원본 영상들을 이곳에 끌어다 놓으세요.
            <br />
            AI가 인지 분할하고 편집 제안을 생성합니다.
          </p>
        </div>

        <button
          className="mt-4 px-8 py-2.5 rounded-xl bg-primary text-primary-foreground text-[12px] font-bold hover:opacity-90 hover:translate-y-[-2px] transition-all shadow-xl shadow-primary/20"
          onClick={(e) => {
            e.stopPropagation();
            handleUpload();
          }}
        >
          파일 업로드
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          multiple
          className="hidden"
          onChange={handleFileChange}
        />
      </div>
    </div>
  );
}
