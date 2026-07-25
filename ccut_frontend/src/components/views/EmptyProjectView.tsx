import React from "react";

interface EmptyProjectViewProps {
  handleUpload: () => void;
  fileInputRef: React.RefObject<HTMLInputElement>;
  handleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}

export function EmptyProjectView({ handleUpload, fileInputRef, handleFileChange }: EmptyProjectViewProps) {
  return (
    <div className="flex-1 flex items-center justify-center p-6 text-center">
      <div
        className="w-full max-w-[360px] p-12 flex flex-col items-center gap-5 transition-all cursor-pointer group"
        onClick={handleUpload}
      >
        <div className="w-40 h-40 flex items-center justify-center text-primary/85">
          <img
            src="/ccut-empty-slate-white.svg"
            alt=""
            aria-hidden="true"
            className="h-40 w-40 opacity-85"
            draggable={false}
          />
        </div>

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
