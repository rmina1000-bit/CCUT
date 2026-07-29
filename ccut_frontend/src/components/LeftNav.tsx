import React, { useState, useRef, useEffect } from "react";
import { Archive, Upload, Settings, User, Clapperboard, MoreVertical, PanelLeftClose, PanelLeftOpen, Plus, Trash2, CheckSquare, AlertTriangle } from "lucide-react";
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
  onNewProject?: () => void;
  onHome?: () => void;
}

const LeftNav: React.FC<LeftNavProps> = ({
  activeItem,
  onItemClick,
  projects = [],
  collapsed = false,
  onToggleCollapse,
  onRenameProject,
  onDeleteProject,
  onNewProject,
  onHome,
}) => {
  const [menuOpenId, setMenuOpenId] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  // [SOFT-DELETE] 강한 삭제 경고 모달 대상
  const [confirmDelete, setConfirmDelete] = useState<{ ids: string[]; names: string[] } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  // [NAV-SCROLL] 현재 열린(활성) 프로젝트 항목 — 목록 아래쪽에 있어도 보이도록 스크롤 대상
  const activeItemRef = useRef<HTMLDivElement>(null);

  // [NAV-SCROLL] 프로젝트가 열릴 때(특히 아카이브에서 이동) 활성 항목을 화면 안으로 끌어온다.
  // block:"nearest" → 아래에 가려져 있으면 최소한으로 스크롤해 하단 가장자리에 보이게 한다.
  useEffect(() => {
    if (!activeItem || !activeItem.startsWith("proj_")) return;
    const id = window.requestAnimationFrame(() => {
      activeItemRef.current?.scrollIntoView({ block: "nearest" });
    });
    return () => window.cancelAnimationFrame(id);
  }, [activeItem, projects]);

  const requestDelete = (ids: string[], names: string[]) => {
    setConfirmDelete({ ids, names });
    setMenuOpenId(null);
  };

  const confirmDeleteNow = () => {
    if (!confirmDelete) return;
    confirmDelete.ids.forEach((id) => onDeleteProject?.(id));
    setConfirmDelete(null);
    setSelectedIds(new Set());
    setIsSelecting(false);
  };

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpenId(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const allSelected = projects.length > 0 && projects.every((p) => selectedIds.has(p.id));
  const someSelected = selectedIds.size > 0;

  const toggleAll = () => {
    if (allSelected) setSelectedIds(new Set());
    else setSelectedIds(new Set(projects.map((p) => p.id)));
  };

  const toggleOne = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const deleteSelected = () => {
    const ids = Array.from(selectedIds);
    const names = ids.map((id) => projects.find((p) => p.id === id)?.name || id);
    if (ids.length) requestDelete(ids, names);
  };

  const exitSelecting = () => {
    setIsSelecting(false);
    setSelectedIds(new Set());
  };

  return (
    <div className="w-full flex flex-col bg-[hsl(228_14%_8%)] h-full border-r border-border/50 overflow-hidden">

      {/* 헤더 */}
      <div className="flex-shrink-0" style={{ height: 48, position: "relative" }}>
        <div
          className="absolute left-3 top-0 bottom-0 flex items-center"
          style={{ cursor: "pointer" }}
          onClick={onHome}
          title="첫 화면(홈)"
        >
          <span className="text-[15px] font-semibold whitespace-nowrap">
            <span className="bg-gradient-to-r from-blue-400 to-primary bg-clip-text text-transparent">CC</span>
            {!collapsed && <span className="text-[14.5px] font-semibold text-foreground/70 tracking-[0.04em]">UT</span>}
          </span>
        </div>
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

      {/* [C] 접힌 상태 전용 펼침 토글 아이콘 (#2 — 로고와 역할 분리, 독립 아이콘) */}
      {collapsed && (
        <div className="px-1 flex-shrink-0">
          <button
            onClick={onToggleCollapse}
            title="사이드바 열기"
            className="w-full flex items-center justify-center px-3 py-2 rounded-lg text-foreground/40 hover:text-foreground/70 hover:bg-secondary/40 transition-colors"
            style={{ minHeight: 36 }}
          >
            <PanelLeftOpen size={15} strokeWidth={1.5} />
          </button>
        </div>
      )}

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
            style={{ minHeight: 36 }}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
              ${activeItem === item.id
                ? "bg-secondary text-foreground"
                : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
              }`}
          >
            <div className="w-5 flex items-center justify-center flex-shrink-0">{item.icon}</div>
            {!collapsed && <span className="text-[12px] truncate">{item.label}</span>}
          </button>
        ))}
      </div>

      {/* [C] 접힌 상태 전용 새 프로젝트(+) 아이콘 (#5) */}
      {collapsed && (
        <div className="px-1 mt-0.5 flex-shrink-0">
          <button
            onClick={onNewProject}
            title="새 프로젝트"
            className="w-full flex items-center justify-center px-3 py-2 rounded-lg text-foreground/40 hover:text-foreground/70 hover:bg-secondary/40 transition-colors"
            style={{ minHeight: 36 }}
          >
            <Plus className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 프로젝트 섹션 헤더 */}
      <div className="px-3 mt-3 flex-shrink-0">
        {!collapsed && (
          <div className="flex items-center justify-between px-2">
            {isSelecting ? (
              /* 선택 모드 헤더 */
              <>
                {/* 전체선택 체크박스 */}
                <label className="flex items-center gap-1.5 cursor-pointer select-none" onClick={toggleAll}>
                  <span className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors
                    ${allSelected
                      ? "bg-primary border-primary"
                      : someSelected
                        ? "bg-primary/30 border-primary/60"
                        : "border-foreground/30 bg-transparent"
                    }`}
                  >
                    {allSelected && <span className="text-white text-[10px] leading-none">✓</span>}
                    {!allSelected && someSelected && <span className="text-white text-[10px] leading-none">−</span>}
                  </span>
                  <span className="text-[12px] text-foreground/50">
                    {someSelected ? `${selectedIds.size}개 선택` : "전체 선택"}
                  </span>
                </label>
                <div className="flex items-center gap-1">
                  {someSelected && (
                    <button
                      onClick={deleteSelected}
                      title="선택 삭제"
                      className="w-6 h-6 flex items-center justify-center rounded hover:bg-red-500/20 transition-colors text-red-400 hover:text-red-300"
                    >
                      <Trash2 size={13} strokeWidth={1.5} />
                    </button>
                  )}
                  <button
                    onClick={exitSelecting}
                    title="취소"
                    className="text-[12px] text-foreground/40 hover:text-foreground/70 px-1 transition-colors"
                  >
                    취소
                  </button>
                </div>
              </>
            ) : (
              /* 일반 헤더 */
              <>
                <span className="text-[12px] font-medium text-foreground/40 uppercase tracking-widest">
                  프로젝트
                </span>
                <div className="flex items-center gap-0.5">
                  {projects.length > 0 && (
                    <button
                      onClick={() => setIsSelecting(true)}
                      title="선택"
                      className="w-5 h-5 flex items-center justify-center rounded hover:bg-secondary/50 transition-colors text-foreground/30 hover:text-foreground/60"
                    >
                      <CheckSquare size={12} strokeWidth={1.5} />
                    </button>
                  )}
                  <button
                    onClick={onNewProject}
                    title="새 프로젝트"
                    className="w-5 h-5 flex items-center justify-center rounded hover:bg-secondary/50 transition-colors text-foreground/40 hover:text-foreground/70"
                  >
                    <Plus className="w-3.5 h-3.5" />
                  </button>
                </div>
              </>
            )}
          </div>
        )}
        {collapsed && <div className="w-4 h-px bg-border/30 mx-auto" />}
      </div>

      <ScrollArea className="flex-1 mt-1 px-1 min-h-0">
        <div className="flex flex-col gap-0.5" ref={menuRef}>
          {projects.map((proj) => {
            const isActive = activeItem === proj.id;
            const isChecked = selectedIds.has(proj.id);
            return (
              <div key={proj.id} className="relative group" ref={isActive ? activeItemRef : undefined}>
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
                      className="w-full bg-secondary/60 text-foreground text-[12px] px-2 py-1 rounded outline-none border border-primary/40"
                    />
                  </div>
                ) : (
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={(e) => {
                      if (isSelecting) {
                        toggleOne(proj.id, e);
                      } else {
                        onItemClick(proj.id);
                      }
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        if (isSelecting) toggleOne(proj.id, e as any);
                        else onItemClick(proj.id);
                      }
                    }}
                    title={proj.name}
                    className={`w-full text-left px-3 py-2.5 rounded-lg transition-colors duration-100 cursor-pointer outline-none focus-visible:ring-1 focus-visible:ring-primary/50
                      ${isSelecting
                        ? isChecked
                          ? "bg-primary/10 text-foreground"
                          : "text-foreground/70 hover:bg-secondary/50 hover:text-foreground/90"
                        : isActive
                          ? "bg-secondary text-foreground"
                          : "text-foreground/70 hover:bg-secondary/50 hover:text-foreground/90"
                      }`}
                  >
                    <div className="flex items-center gap-2.5">
                      {/* 아이콘 / 체크박스 */}
                      {isSelecting && !collapsed ? (
                        <span
                          className={`w-4 h-4 rounded border flex items-center justify-center flex-shrink-0 transition-colors
                            ${isChecked ? "bg-primary border-primary" : "border-foreground/30 bg-transparent"}`}
                          onClick={(e) => toggleOne(proj.id, e)}
                        >
                          {isChecked && <span className="text-white text-[10px] leading-none">✓</span>}
                        </span>
                      ) : (
                        <div className="w-5 flex items-center justify-center flex-shrink-0">
                          <Clapperboard size={14} className={isActive ? "text-primary" : "text-foreground/50"} strokeWidth={1.5} />
                        </div>
                      )}
                      {!collapsed && (
                        <>
                          <span className="text-[12px] font-normal truncate flex-1">{proj.name}</span>
                          {!isSelecting && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setMenuOpenId(menuOpenId === proj.id ? null : proj.id);
                              }}
                              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-white/10 transition-opacity flex-shrink-0"
                            >
                              <MoreVertical size={13} className="text-foreground/50" />
                            </button>
                          )}
                        </>
                      )}
                    </div>
                    {!collapsed && (
                      <span className="text-[12px] text-foreground/40 ml-[28px] block mt-0.5">
                        {proj.date} · {proj.count}개 영상
                      </span>
                    )}
                  </div>
                )}

                {menuOpenId === proj.id && !collapsed && !isSelecting && (
                  <div className="absolute right-0 top-8 z-[200] w-36 bg-[hsl(228,12%,12%)] border border-border/30 rounded-lg shadow-xl overflow-hidden">
                    <button
                      onClick={() => {
                        setRenameValue(proj.name);
                        setRenamingId(proj.id);
                        setMenuOpenId(null);
                      }}
                      className="w-full text-left px-3 py-2 text-[12px] text-foreground/70 hover:bg-secondary/50 hover:text-foreground transition-colors"
                    >
                      이름 변경
                    </button>
                    <button
                      onClick={() => requestDelete([proj.id], [proj.name])}
                      className="w-full text-left px-3 py-2 text-[12px] text-red-400 hover:bg-red-500/10 transition-colors"
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
          { id: "trash", icon: <Trash2 size={15} strokeWidth={1.5} />, label: "휴지통" },
        ].map((item) => (
          <button
            key={item.id}
            onClick={() => onItemClick(item.id)}
            title={item.label}
            style={{ minHeight: 36 }}
            className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg transition-colors duration-100
              ${activeItem === item.id
                ? "bg-secondary text-foreground"
                : "text-foreground/60 hover:text-foreground/80 hover:bg-secondary/40"
              }`}
          >
            <div className="w-5 flex items-center justify-center flex-shrink-0">{item.icon}</div>
            {!collapsed && <span className="text-[12px]">{item.label}</span>}
          </button>
        ))}
      </div>

      {/* [SOFT-DELETE] 강한 삭제 경고 모달 */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-[500] flex items-center justify-center bg-black/70 backdrop-blur-sm animate-in fade-in duration-200"
          onClick={() => setConfirmDelete(null)}
        >
          <div
            className="w-[420px] max-w-[90vw] bg-[hsl(228,12%,11%)] border border-red-500/30 rounded-2xl shadow-2xl overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 px-6 pt-6 pb-3">
              <div className="w-11 h-11 rounded-xl bg-red-500/15 flex items-center justify-center flex-shrink-0">
                <AlertTriangle size={22} className="text-red-400" />
              </div>
              <div>
                <h3 className="text-[15px] font-bold text-foreground">정말 삭제하시겠습니까?</h3>
                <p className="text-[12px] text-red-400/80">이 결정은 되돌리기 어렵습니다.</p>
              </div>
            </div>

            <div className="px-6 pb-2">
              <div className="rounded-xl bg-red-500/5 border border-red-500/15 px-4 py-3 mb-3">
                <p className="text-[13px] text-foreground/85 leading-relaxed">
                  {confirmDelete.names.length === 1 ? (
                    <>
                      <span className="font-semibold text-red-300">“{confirmDelete.names[0]}”</span>{" "}
                      프로젝트와 그 안의 <span className="font-semibold">모든 편집 이력</span>이 사라집니다.
                    </>
                  ) : (
                    <>
                      선택한 <span className="font-semibold text-red-300">{confirmDelete.names.length}개</span>{" "}
                      프로젝트와 그 안의 <span className="font-semibold">모든 편집 이력</span>이 사라집니다.
                    </>
                  )}
                </p>
              </div>
              <p className="text-[12px] text-muted-foreground/70 leading-relaxed px-1">
                삭제해도 <span className="text-emerald-400/90 font-medium">30일간 휴지통에 보관</span>되어 복원할 수 있습니다.
                <br />
                30일이 지나면 <span className="text-red-400/90 font-medium">영구적으로 완전히 삭제</span>되어 누구도 되살릴 수 없습니다.
              </p>
            </div>

            <div className="flex gap-2 px-6 py-5">
              <button
                onClick={() => setConfirmDelete(null)}
                className="flex-1 py-2.5 rounded-xl bg-secondary/60 text-foreground/90 text-[13px] font-medium hover:bg-secondary transition-colors"
              >
                취소 (안전)
              </button>
              <button
                onClick={confirmDeleteNow}
                className="flex-1 py-2.5 rounded-xl bg-red-500/90 text-white text-[13px] font-bold hover:bg-red-500 transition-colors flex items-center justify-center gap-1.5"
              >
                <Trash2 size={14} /> 삭제하겠습니다
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LeftNav;
