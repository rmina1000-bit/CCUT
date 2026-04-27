import React, { useState, useCallback, useRef, useEffect } from "react";
import { Fragment } from "@/data/fragmentData";
import { Trash2, X, GripVertical, ExternalLink } from "lucide-react";

interface TrashBinProps {
  deletedFragments: Fragment[];
  onRestoreToHold: (f: Fragment) => void;
  onRestoreToEdit: (f: Fragment) => void;
  onEmptyTrash: () => void;
  onTrashDrop: (f: Fragment) => void;
  isMagnetic?: boolean;
}

const sourceColors: Record<string, string> = {
  A: "text-orange-400",
  B: "text-blue-400",
  C: "text-emerald-400",
  D: "text-purple-400",
  E: "text-pink-400",
  F: "text-yellow-400",
  G: "text-cyan-400",
};

const TrashBin: React.FC<TrashBinProps> = ({
  deletedFragments,
  onRestoreToHold,
  onRestoreToEdit,
  onEmptyTrash,
  onTrashDrop,
  isMagnetic = false,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isDraggingOut, setIsDraggingOut] = useState(false);
  const windowRef = useRef<HTMLDivElement>(null);

  const [windowPos, setWindowPos] = useState<{ x: number; y: number } | null>(null);
  const [isWindowDragging, setIsWindowDragging] = useState(false);
  const windowDragOffset = useRef({ x: 0, y: 0 });

  useEffect(() => {
    if (isOpen && !windowPos) {
      setWindowPos({
        x: window.innerWidth - 344,
        y: window.innerHeight - 400,
      });
    }
  }, [isOpen, windowPos]);

  const handleTitleBarMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!windowRef.current) return;
    const rect = windowRef.current.getBoundingClientRect();
    windowDragOffset.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setIsWindowDragging(true);
  }, []);

  useEffect(() => {
    if (!isWindowDragging) return;

    const handleMove = (e: MouseEvent) => {
      setWindowPos({
        x: Math.max(0, Math.min(window.innerWidth - 320, e.clientX - windowDragOffset.current.x)),
        y: Math.max(0, Math.min(window.innerHeight - 60, e.clientY - windowDragOffset.current.y)),
      });
    };

    const handleUp = () => setIsWindowDragging(false);

    document.addEventListener("mousemove", handleMove);
    document.addEventListener("mouseup", handleUp);

    return () => {
      document.removeEventListener("mousemove", handleMove);
      document.removeEventListener("mouseup", handleUp);
    };
  }, [isWindowDragging]);

  const handleDragStart = useCallback((e: React.DragEvent, frag: Fragment) => {
    e.dataTransfer.setData("text/plain", frag.fragment_id);
    e.dataTransfer.setData("application/ccut-trash-restore", JSON.stringify(frag));
    e.dataTransfer.effectAllowed = "move";
  }, []);

  return (
    <>
      <style
        dangerouslySetInnerHTML={{
          __html: `
        @keyframes trash-pulse {
          0% { transform: scale(1); filter: drop-shadow(0 0 0 rgba(220, 38, 38, 0)); }
          50% { transform: scale(1.1); filter: drop-shadow(0 0 16px rgba(220, 38, 38, 0.4)); }
          100% { transform: scale(1); filter: drop-shadow(0 0 0 rgba(220, 38, 38, 0)); }
        }
        .trash-magnetic {
          animation: trash-pulse 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite;
        }
      `,
        }}
      />

      <div
        className={`cursor-pointer relative group ${isMagnetic || isDragOver ? "trash-magnetic" : ""}`}
        onClick={() => setIsOpen((prev) => !prev)}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("application/ccut-reserve-restore")) {
            e.preventDefault();
            e.dataTransfer.dropEffect = "move";
            setIsDragOver(true);
          }
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          setIsDragOver(false);
          const data = e.dataTransfer.getData("application/ccut-reserve-restore");
          if (data) {
            e.preventDefault();
            try {
              const frag = JSON.parse(data) as Fragment;
              onTrashDrop(frag);
            } catch { }
          }
        }}
      >
        <Trash2
          size={32}
          className={`transition-all duration-150 ${deletedFragments.length > 0 ? "text-destructive/80" : "text-muted-foreground/30"
            }`}
          strokeWidth={1.2}
        />
        {deletedFragments.length > 0 && (
          <span className="absolute -top-3 -right-3 w-6 h-6 rounded-full bg-destructive text-[11px] text-foreground flex items-center justify-center font-bold shadow-lg">
            {deletedFragments.length}
          </span>
        )}
      </div>

      {isOpen && (
        <div
          className="fixed inset-0 z-[100]"
          onClick={() => {
            if (!isDraggingOut) setIsOpen(false);
          }}
          style={{ pointerEvents: isWindowDragging || isDraggingOut ? "none" : "auto" }}
        >
          <div
            ref={windowRef}
            className="absolute bg-[hsl(228,12%,10%)] border border-border/40 rounded-xl shadow-[0_32px_64px_-12px_rgba(0,0,0,0.8)] overflow-hidden"
            style={{
              width: 560,
              left: windowPos?.x ?? "auto",
              top: windowPos?.y ?? "auto",
              maxHeight: "70vh",
              pointerEvents: "auto",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div
              className="flex items-center justify-between px-3 py-1.5 border-b border-border/15 cursor-move select-none"
              onMouseDown={handleTitleBarMouseDown}
            >
              <div className="flex items-center gap-1.5">
                <Trash2 size={11} className="text-muted-foreground/40" strokeWidth={1.5} />
                <span className="text-[10px] font-medium text-foreground/60">휴지통</span>
                {deletedFragments.length > 0 && (
                  <span className="text-[9px] text-muted-foreground/35">{deletedFragments.length}</span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    window.open(
                      "/trash",
                      "_blank",
                      "width=1000,height=800,menubar=no,toolbar=no,location=no,status=no"
                    );
                    setIsOpen(false);
                  }}
                  className="text-muted-foreground/30 hover:text-blue-400 transition-colors p-0.5"
                  title="새창으로 열기"
                >
                  <ExternalLink size={11} />
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setIsOpen(false);
                  }}
                  onMouseDown={(e) => e.stopPropagation()}
                  className="text-muted-foreground/30 hover:text-foreground/60 transition-colors p-0.5"
                >
                  <X size={11} />
                </button>
              </div>
            </div>

            <div className="overflow-y-auto" style={{ maxHeight: "calc(50vh - 60px)" }}>
              {deletedFragments.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-6 gap-1">
                  <Trash2 size={16} className="text-muted-foreground/10" strokeWidth={1} />
                  <p className="text-[9px] text-muted-foreground/30">비어 있음</p>
                </div>
              ) : (
                deletedFragments.map((f) => (
                  <div
                    key={getRowKey(f)}
                    draggable
                    onDragStart={(e) => {
                      handleDragStart(e, f);
                      setIsDraggingOut(true);
                    }}
                    onDragEnd={() => setIsDraggingOut(false)}
                    className="flex items-center gap-2 px-2.5 py-1.5 hover:bg-secondary/20 transition-colors cursor-grab active:cursor-grabbing group"
                  >
                    <GripVertical
                      size={8}
                      className="text-muted-foreground/15 group-hover:text-muted-foreground/40 flex-shrink-0"
                    />
                    <div
                      className="flex-shrink-0 rounded-[2px] bg-secondary"
                      style={{
                        width: 32,
                        height: 20,
                        backgroundImage: f.thumbnail?.thumbnail_url
                          ? `url(${f.thumbnail.thumbnail_url})`
                          : "none",
                        backgroundSize: "cover",
                        backgroundPosition: "center",
                      }}
                    />
                    <div className="flex-1 min-w-0 flex items-center gap-1">
                      <span
                        className={`text-[9px] font-medium ${sourceColors[f.source_video] || "text-foreground"
                          }`}
                      >
                        {f.fragment_id}
                      </span>
                      <span className="text-[8px] text-muted-foreground/35">
                        {f.duration.toFixed(1)}s
                      </span>
                    </div>
                  </div>
                ))
              )}
            </div>

            {deletedFragments.length > 0 && (
              <div className="px-2.5 py-1.5 border-t border-border/10">
                <button
                  onClick={onEmptyTrash}
                  className="w-full flex items-center justify-center gap-1 text-[9px] text-muted-foreground/35 hover:text-muted-foreground/60 transition-colors py-1 rounded hover:bg-secondary/20"
                >
                  <Trash2 size={8} strokeWidth={1.5} />
                  비우기
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
};

function getRowKey(f: Fragment) {
  return `${f.fragment_id}-${f.start_frame ?? 0}-${f.end_frame ?? 0}`;
}

export default TrashBin;
