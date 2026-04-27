import React, { useState, useEffect } from "react";
import { Fragment } from "@/data/fragmentData";
import { Trash2, X, RotateCcw } from "lucide-react";
import { getFragmentThumbnail } from "@/data/thumbnailMap";

/**
 * TrashPortal - Separate window for Trash Bin
 * This syncs with Main window via BroadcastChannel.
 */
const TrashPortal: React.FC = () => {
    const [deletedFragments, setDeletedFragments] = useState<Fragment[]>([]);
    const bc = new BroadcastChannel("ccut_trash_sync");

    useEffect(() => {
        bc.onmessage = (event) => {
            if (event.data.type === "UPDATE_TRASH") {
                setDeletedFragments(event.data.fragments);
            }
        };
        // Initial request for state
        bc.postMessage({ type: "REQUEST_TRASH" });
        return () => bc.close();
    }, []);

    const handleRestore = (f: Fragment, to: "edit" | "hold") => {
        bc.postMessage({ type: "RESTORE_REQUEST", fragmentId: f.fragment_id, target: to });
    };

    const handleEmpty = () => {
        bc.postMessage({ type: "EMPTY_REQUEST" });
    };

    return (
        <div className="min-h-screen bg-[hsl(228,12%,8%)] text-foreground flex flex-col font-sans select-none">
            <div className="flex items-center justify-between px-6 py-4 border-b border-border/15 bg-card/10">
                <div className="flex items-center gap-3">
                    <Trash2 size={24} className="text-destructive/60" />
                    <h1 className="text-xl font-bold tracking-tight">휴지통 전용창</h1>
                    <span className="text-sm bg-destructive/10 text-destructive/80 px-2 py-0.5 rounded-full">
                        {deletedFragments.length} 조각
                    </span>
                </div>
                <button onClick={handleEmpty} className="text-xs text-muted-foreground/40 hover:text-destructive flex items-center gap-1 transition-colors">
                    <Trash2 size={12} /> 전체 비우기
                </button>
            </div>

            <div className="flex-1 p-6 overflow-y-auto">
                {deletedFragments.length === 0 ? (
                    <div className="h-full flex flex-col items-center justify-center opacity-20">
                        <Trash2 size={80} strokeWidth={1} />
                        <p className="mt-4">비어 있음</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
                        {deletedFragments.map((f) => (
                            <div key={f.fragment_id} className="bg-card/50 border border-border/20 rounded-xl p-3 flex flex-col gap-3 group">
                                <div
                                    className="aspect-video bg-secondary rounded-lg overflow-hidden"
                                    style={{ backgroundImage: `url(${getFragmentThumbnail(f.fragment_id, f.source_video)})`, backgroundSize: "cover", backgroundPosition: "center" }}
                                />
                                <div className="flex items-center justify-between">
                                    <span className="text-sm font-semibold">{f.fragment_id}</span>
                                    <span className="text-xs text-muted-foreground">{f.duration.toFixed(1)}s</span>
                                </div>
                                <div className="flex gap-2">
                                    <button
                                        onClick={() => handleRestore(f, "edit")}
                                        className="flex-1 bg-primary/10 text-primary text-[11px] py-1.5 rounded-lg hover:bg-primary/20 transition-all font-medium flex items-center justify-center gap-1"
                                    >
                                        <RotateCcw size={11} /> 편집 복원
                                    </button>
                                    <button
                                        onClick={() => handleRestore(f, "hold")}
                                        className="flex-1 bg-secondary/30 text-foreground/70 text-[11px] py-1.5 rounded-lg hover:bg-secondary/50 transition-all"
                                    >
                                        보류 복원
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
};

export default TrashPortal;
