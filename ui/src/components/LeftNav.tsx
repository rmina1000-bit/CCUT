import React from "react";
import { Archive, Upload, Settings, User, Clapperboard } from "lucide-react";
import { ScrollArea } from "./ui/scroll-area";

interface LeftNavProps {
  activeItem: string;
  onItemClick: (item: string) => void;
}

const projects = [
  { id: "p1", name: "제주 여행 3월", date: "3월 18일", count: 4 },
  { id: "p2", name: "먹방 시리즈 EP3", date: "3월 15일", count: 7 },
  { id: "p3", name: "일상 브이로그", date: "3월 12일", count: 3 },
  { id: "p4", name: "제품 리뷰", date: "3월 10일", count: 5 },
  { id: "p5", name: "여행 하이라이트", date: "3월 8일", count: 2 },
];

const LeftNav: React.FC<LeftNavProps> = ({ activeItem, onItemClick }) => {
  return (
    <div className="w-[220px] flex flex-col bg-[hsl(228_14%_8%)] h-full flex-shrink-0 border-r border-border/50">
      {/* Logo — flush */}
      <div className="px-5 pt-4 pb-0">
        <span className="text-[16px] font-semibold tracking-[0.06em]">
          <span className="bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">CC</span>
          <span className="text-[14.5px] font-semibold text-foreground/70 tracking-[0.04em]">UT</span>
        </span>
      </div>

      {/* Archive + SNS Upload */}
      <div className="px-2 mt-1 flex flex-col gap-0.5">
        <button
          onClick={() => onItemClick("archive")}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
            ${activeItem === "archive"
              ? "bg-secondary text-foreground"
              : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
            }`}
        >
          <Archive size={15} strokeWidth={1.5} />
          <span className="text-[13px]">아카이브</span>
        </button>
        <button
          onClick={() => onItemClick("upload")}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
            ${activeItem === "upload"
              ? "bg-secondary text-foreground"
              : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
            }`}
        >
          <Upload size={15} strokeWidth={1.5} />
          <span className="text-[13px]">SNS 업로드</span>
        </button>
      </div>

      {/* Projects section */}
      <div className="px-3 mt-3">
        <span className="text-[11px] font-medium text-foreground/40 uppercase tracking-widest px-2">
          프로젝트
        </span>
      </div>

      <ScrollArea className="flex-1 mt-1 px-2 min-h-0">
        <div className="flex flex-col gap-0.5">
          {projects.map((proj) => {
            const isActive = activeItem === proj.id;
            return (
              <button
                key={proj.id}
                onClick={() => onItemClick(proj.id)}
                className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors duration-100 group
                  ${isActive
                    ? "bg-secondary text-foreground"
                    : "text-foreground/70 hover:bg-secondary/50 hover:text-foreground/90"
                  }`}
              >
                <div className="flex items-center gap-2.5">
                  <Clapperboard size={14} className={isActive ? "text-primary" : "text-foreground/50"} strokeWidth={1.5} />
                  <span className="text-[13px] font-normal truncate flex-1">{proj.name}</span>
                </div>
                <span className="text-[11px] text-foreground/40 ml-[26px] block mt-0.5">
                  {proj.date} · {proj.count}개 영상
                </span>
              </button>
            );
          })}
        </div>
      </ScrollArea>

      {/* Bottom: Account + Settings */}
      <div className="px-2 pb-3 pt-1 flex flex-col gap-0.5 border-t border-border/20">
        <button
          onClick={() => onItemClick("account")}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
            ${activeItem === "account"
              ? "bg-secondary text-foreground"
              : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
            }`}
        >
          <User size={15} strokeWidth={1.5} />
          <span className="text-[13px]">내 계정</span>
        </button>
        <button
          onClick={() => onItemClick("settings")}
          className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
            ${activeItem === "settings"
              ? "bg-secondary text-foreground"
              : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
            }`}
        >
          <Settings size={15} strokeWidth={1.5} />
          <span className="text-[13px]">설정</span>
        </button>
      </div>
    </div>
  );
};

export default LeftNav;
export { LeftNav };
