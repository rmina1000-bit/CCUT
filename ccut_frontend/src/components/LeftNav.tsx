import React, { useState, useRef, useEffect } from "react";
import { Archive, Upload, Settings, User, Clapperboard, MoreVertical, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Project {
  id: string;
  name: string;
  date: string;
  count: number;
}

interface LeftNavProps {
  activeItem: string;
  onItemClick: (item: string) => void;
  projects?: Project[];
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onRenameProject?: (id: string, newName: string) => void;
  onDeleteProject?: (id: string) => void;
}

const LeftNav: React.FC<LeftNavProps> = ({
  activeItem,
  onItemClick,
  projects = [],
  collapsed = false,
  onToggleCollapse,
  onRenameProject,
  onDeleteProject,
}) => {
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  return (
    <div className="w-full flex flex-col bg-[hsl(228_14%_8%)] h-full border-r border-border/50 overflow-hidden">

      {/* 헤더 */}
      <div className="flex-shrink-0" style={{ height: 48, position: "relative" }}>
        {/* 로고 — 항상 좌측 고정 (접혔을 때 클릭 시 펼침) */}
        <div
          className="absolute left-3 top-0 bottom-0 flex items-center"
          style={{ cursor: collapsed ? "pointer" : "default" }}
          onClick={collapsed ? onToggleCollapse : undefined}
          title={collapsed ? "사이드바 열기" : undefined}
        >
          <span className="text-[15px] font-semibold whitespace-nowrap">
            <span className="bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">CC</span>
            {!collapsed && <span className="text-[14.5px] font-semibold text-foreground/70 tracking-[0.04em]">UT</span>}
          </span>
        </div>
        {/* 토글 버튼 — 펼쳐졌을 때만 우측 고정 노출 */}
        <div className="absolute right-1 top-0 bottom-0 flex items-center" style={{ display: collapsed ? "none" : "flex" }}>
          <button
            onClick={onToggleCollapse}
            className="w-7 h-7 flex items-center justify-center rounded-lg hover:bg-secondary/50 transition-colors text-foreground/40 hover:text-foreground/70"
            title="사이드바 닫기"
          >
            <PanelLeftClose size={14} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* 상단 메뉴 */}
      <div className="px-1 mt-2 flex flex-col gap-0.5 flex-shrink-0">
        {[
          { id: "archive", icon: <Archive size={15} strokeWidth={1.5} />, label: "아카이브" },
          { id: "upload", icon: <Upload size={15} strokeWidth={1.5} />, label: "SNS 업로드" },
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => onItemClick(item.id)}
            title={item.label}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
              ${activeItem === item.id
                ? "bg-secondary text-foreground"
                : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
              }`}
          >
            <div className="w-5 flex items-center justify-center flex-shrink-0">{item.icon}</div>
            {!collapsed && <span className="text-[13px] truncate">{item.label}</span>}
          </button>
        ))}
      </div>

      {/* 프로젝트 섹션 */}
      <div className="px-3 mt-3 flex-shrink-0">
        {!collapsed && (
          <span className="text-[11px] font-medium text-foreground/40 uppercase tracking-widest px-2">
            프로젝트
          </span>
        )}
        {collapsed && <div className="w-4 h-px bg-border/30 mx-auto" />}
      </div>

      <ScrollArea className="flex-1 mt-1 px-1 min-h-0">
        <div className="flex flex-col gap-0.5" ref={menuRef}>
          {projects.map((proj) => {
            const isActive = activeItem === proj.id;
            return (
              <div key={proj.id} className="relative group">
                {renamingId === proj.id ? (
                  <div className="px-2 py-2">
                    <input
                      autoFocus
                      value={renameValue}
                      onChange={(e) => setRenameValue(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          onRenameProject?.(proj.id, renameValue);
                          setRenamingId(null);
                        }
                        if (e.key === "Escape") setRenamingId(null);
                      }}
                      onBlur={() => setRenamingId(null)}
                      className="w-full bg-secondary/60 text-foreground text-[13px] px-2 py-1 rounded outline-none border border-primary/40"
                    />
                  </div>
                ) : (
                  <button
                    onClick={() => onItemClick(proj.id)}
                    title={proj.name}
                    className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors duration-100
                      ${isActive
                        ? "bg-secondary text-foreground"
                        : "text-foreground/70 hover:bg-secondary/50 hover:text-foreground/90"
                      }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="w-5 flex items-center justify-center flex-shrink-0">
                        <Clapperboard size={14} className={isActive ? "text-primary" : "text-foreground/50"} strokeWidth={1.5} />
                      </div>
                      {!collapsed && (
                        <>
                          <span className="text-[13px] font-normal truncate flex-1">{proj.name}</span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setMenuOpenId(menuOpenId === proj.id ? null : proj.id);
                            }}
                            className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-white/10 transition-opacity flex-shrink-0"
                          >
                            <MoreVertical size={13} className="text-foreground/50" />
                          </button>
                        </>
                      )}
                    </div>
                    {!collapsed && (
                      <span className="text-[11px] text-foreground/40 ml-[28px] block mt-0.5">
                        {proj.date} · {proj.count}개 영상
                      </span>
                    )}
                  </button>
                )}

                {menuOpenId === proj.id && !collapsed && (
                  <div className="absolute right-0 top-8 z-[200] w-36 bg-[hsl(228,12%,12%)] border border-border/30 rounded-lg shadow-xl overflow-hidden">
                    <button
                      onClick={() => {
                        setRenameValue(proj.name);
                        setRenamingId(proj.id);
                        setMenuOpenId(null);
                      }}
                      className="w-full text-left px-3 py-2 text-[13px] text-foreground/70 hover:bg-secondary/50 hover:text-foreground transition-colors"
                    >
                      이름 변경
                    </button>
                    <button
                      onClick={() => {
                        onDeleteProject?.(proj.id);
                        setMenuOpenId(null);
                      }}
                      className="w-full text-left px-3 py-2 text-[13px] text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                      삭제
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </ScrollArea>

      {/* 하단 메뉴 */}
      <div className="px-1 pb-3 pt-1 flex flex-col gap-0.5 border-t border-border/20 flex-shrink-0">
        {[
          { id: "account", icon: <User size={15} strokeWidth={1.5} />, label: "내 계정" },
          { id: "settings", icon: <Settings size={15} strokeWidth={1.5} />, label: "설정" },
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => onItemClick(item.id)}
            title={item.label}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
              ${activeItem === item.id
                ? "bg-secondary text-foreground"
                : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
              }`}
          >
            <div className="w-5 flex items-center justify-center flex-shrink-0">{item.icon}</div>
            {!collapsed && <span className="text-[13px]">{item.label}</span>}
          </button>
        ))}
      </div>
    </div>
  );
};

export default LeftNav;