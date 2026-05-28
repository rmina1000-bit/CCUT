import React, { useState, useRef, useEffect, useMemo } from 'react';
import {
    applySSBoundary,
    applySNSBoundary,
    applySingleTrim,
    applyPBEResultToFragments,
} from './pbeBoundaryOps';
import {
    getUid,
    recalcDisplayIds,
    assignShortDisplayIds,
} from '@/lib/fragmentIdentity';

export interface BoundaryEditorTarget {
    clickSide: 'left' | 'right' | 'center';
    leftRealIndex: number;
    rightRealIndex: number;
}

interface PBEFragment {
    fragment_uid?: string;
    fragment_id: string;
    selection_state: string;
    start_frame: number;
    end_frame: number;
    duration: number;
    source_video: string;
    thumbnail?: any;
    [key: string]: any;
}

interface SourceInfo {
    source_id?: string;
    label: string;
    video_url: string;
}

interface PrecisionBoundaryEditorProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    target: BoundaryEditorTarget | null;
    fragments: PBEFragment[];
    editFragments: any[];
    videoUrl?: string | null;
    sources?: SourceInfo[];
    onApply?: (result: any) => void;
}

interface FragmentGroup {
    fragment: PBEFragment;
    frames: Array<{ frameNumber: number; thumbnailBase: string }>;
    waveform: {
        points: number[];
    };
}

// Ultra-premium image placeholder component to prevent broken state and handle load delays smoothly
const CapCutFrameImage: React.FC<{
    src: string;
    alt: string;
    style?: React.CSSProperties;
}> = ({ src, alt, style }) => {
    const [imgSrc, setImgSrc] = useState(src);
    const [retryCount, setRetryCount] = useState(0);
    const [status, setStatus] = useState<'loading' | 'loaded' | 'fallback'>('loading');

    useEffect(() => {
        setImgSrc(src);
        setRetryCount(0);
        setStatus('loading');
    }, [src]);

    const handleError = () => {
        if (retryCount < 8) {
            setTimeout(() => {
                setImgSrc(`${src}?retry=${retryCount}&t=${Date.now()}`);
                setRetryCount(prev => prev + 1);
            }, 300 + retryCount * 150); // Fast backoff retry
        } else {
            setStatus('fallback');
        }
    };

    return (
        <div style={{
            position: 'relative',
            width: style?.width || '100%',
            height: style?.height || '100%',
            backgroundColor: '#18181b',
            overflow: 'hidden',
            flexShrink: 0
        }}>
            {status !== 'fallback' ? (
                <img
                    src={imgSrc}
                    alt={alt}
                    style={{
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover', // Fill the container height beautifully
                        opacity: status === 'loaded' ? 1 : 0,
                        transition: 'opacity 0.15s ease-out',
                    }}
                    onLoad={() => setStatus('loaded')}
                    onError={handleError}
                    draggable={false}
                />
            ) : (
                <div style={{
                    width: '100%',
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: '#1f1f24',
                    border: '1px solid rgba(255,255,255,0.03)',
                    color: '#4e4e56',
                    fontSize: '10px',
                }}>
                    <span>프레임</span>
                </div>
            )}
        </div>
    );
};

function getDeterministicAudioData(fragmentId: string) {
    let hash = 0;
    for (let i = 0; i < fragmentId.length; i++) {
        hash = fragmentId.charCodeAt(i) + ((hash << 5) - hash);
    }
    const seed = Math.abs(hash);
    let randomCount = 0;
    const random = () => {
        const x = Math.sin(seed + randomCount++) * 10000;
        return x - Math.floor(x);
    };

    const points: number[] = [];
    let current = 0.4;
    for (let i = 0; i < 40; i++) {
        const change = random() * 0.3 - 0.15;
        current = Math.max(0.05, Math.min(0.95, current + change));
        points.push(current);
    }
    return { points };
}

const getBarVisuals = (type: string) => {
    switch (type) {
        case 'trim-left':
        case 'boundary-left':
            return {
                color: '#f59e0b',
                textColor: '#fff',
                label: '◀',
                offset: -12,
                borderRadius: '6px 0 0 6px',
            };
        case 'trim-right':
        case 'boundary-right':
            return {
                color: '#3b82f6',
                textColor: '#fff',
                label: '▶',
                offset: 12,
                borderRadius: '0 6px 6px 0',
            };
        case 'boundary-seam':
        default:
            return {
                color: '#a855f7',
                textColor: '#fff',
                label: '◀▶',
                offset: 0,
                borderRadius: '6px',
            };
    }
};

const PrecisionBoundaryEditor: React.FC<PrecisionBoundaryEditorProps> = ({
    open,
    onOpenChange,
    fragments,
    editFragments,
    target,
    videoUrl,
    sources,
    onApply,
}) => {
    const [selectedClipIdx, setSelectedClipIdx] = useState<number>(0);
    const [isPlaying, setIsPlaying] = useState<boolean>(false);
    const [currentPlayTime, setCurrentPlayTime] = useState<number>(0);
    const [leftAdjs, setLeftAdjs] = useState<Map<number, number>>(new Map());
    const [rightAdjs, setRightAdjs] = useState<Map<number, number>>(new Map());

    // Calculate pattern (Hoisted to prevent TDZ ReferenceError in applyChatAdjustment and useEffect)
    const pattern = useMemo(() => {
        return fragments.map(f => f.selection_state).join('|');
    }, [fragments]);

    const [dragState, setDragState] = useState<{
        type: 'trim-left' | 'trim-right' | 'boundary-left' | 'boundary-right' | 'boundary-seam';
        clipIdx?: number;
        leftIdx?: number;
        rightIdx?: number;
        initialX: number;
        initialAdj: number;
    } | null>(null);

    const timelineRef = useRef<HTMLDivElement>(null);
    const timelineContainerRef = useRef<HTMLDivElement>(null);
    const videoRef = useRef<HTMLVideoElement>(null);

    // Resizing state variables
    const [dimensions, setDimensions] = useState({ width: 920, height: 640 });
    const [isResizing, setIsResizing] = useState(false);
    const resizeStartRef = useRef({ x: 0, y: 0, w: 0, h: 0 });
    const isDraggingRef = useRef<boolean>(false);

    const handleResizeMouseDown = (e: React.MouseEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setIsResizing(true);
        resizeStartRef.current = {
            x: e.clientX,
            y: e.clientY,
            w: dimensions.width,
            h: dimensions.height
        };
    };

    const handleGlobalResizeMouseMove = (e: MouseEvent) => {
        if (!isResizing) return;
        const deltaX = e.clientX - resizeStartRef.current.x;
        const deltaY = e.clientY - resizeStartRef.current.y;
        setDimensions({
            width: Math.max(700, resizeStartRef.current.w + deltaX),
            height: Math.max(500, resizeStartRef.current.h + deltaY)
        });
    };

    const handleGlobalResizeMouseUp = () => {
        setIsResizing(false);
    };

    useEffect(() => {
        if (isResizing) {
            window.addEventListener('mousemove', handleGlobalResizeMouseMove);
            window.addEventListener('mouseup', handleGlobalResizeMouseUp);
            return () => {
                window.removeEventListener('mousemove', handleGlobalResizeMouseMove);
                window.removeEventListener('mouseup', handleGlobalResizeMouseUp);
            };
        }
    }, [isResizing]);

    // Setup groups
    const fragmentGroups = useMemo<FragmentGroup[]>(() => {
        return fragments.map((frag) => ({
            fragment: frag,
            frames: Array.from(
                { length: 12 },
                (_, i) => ({
                    frameNumber: i,
                    thumbnailBase: `/static/thumbnails/P_${frag.fragment_id}_${i}.jpg`,
                })
            ),
            waveform: getDeterministicAudioData(frag.fragment_id),
        }));
    }, [fragments]);

    const activeGroup = fragmentGroups[selectedClipIdx] || fragmentGroups[0];

    // Find the correct video URL
    const activeVideoUrl = useMemo(() => {
        if (!activeGroup) return videoUrl;
        const srcLabel = activeGroup.fragment.source_video;
        const srcId = activeGroup.fragment.source_id;
        
        // Find matching source using both source_id and label to handle various data aliases
        const matchedSource = sources?.find(s => 
            (s.source_id && (s.source_id === srcId || s.source_id === srcLabel)) || 
            s.label === srcLabel
        );
        return matchedSource ? matchedSource.video_url : videoUrl;
    }, [activeGroup, sources, videoUrl]);

    // Bounds calculations (using untrimmed fragment bounds to enable scrubbing in N regions)
    const clipStartSec = useMemo(() => {
        if (!activeGroup) return 0;
        return activeGroup.fragment.start_frame / 30;
    }, [activeGroup]);

    const clipEndSec = useMemo(() => {
        if (!activeGroup) return 0;
        return activeGroup.fragment.end_frame / 30;
    }, [activeGroup]);

    const lastClipIdxRef = useRef<number>(-1);
    const lastVideoUrlRef = useRef<string>("");
    const hasInitializedSeekRef = useRef<boolean>(false);
    const targetPlayTimeRef = useRef<number>(0);
    const isSeekingRef = useRef<boolean>(false);
    const seekTimerRef = useRef<any>(null);
    const playRequestedRef = useRef<boolean>(false);
    
    // Throttling for smooth, lightweight 60fps drag interaction
    const lastSeekTimeRef = useRef<number>(0);
    const pendingSeekTimeRef = useRef<number | null>(null);

    const startSeekTimer = () => {
        isSeekingRef.current = true;
        if (seekTimerRef.current) {
            clearTimeout(seekTimerRef.current);
        }
        seekTimerRef.current = setTimeout(() => {
            isSeekingRef.current = false;
        }, 300);
    };

    // Clean up timer on unmount
    useEffect(() => {
        return () => {
            if (seekTimerRef.current) {
                clearTimeout(seekTimerRef.current);
            }
        };
    }, []);

    // Reset PBE adjustments and selections when target or open changes to prevent bleeding
    useEffect(() => {
        if (open) {
            setLeftAdjs(new Map());
            setRightAdjs(new Map());
            setSelectedClipIdx(0);
            setIsPlaying(false);
            if (videoRef.current) {
                videoRef.current.pause();
            }
        }
    }, [open, target?.leftRealIndex, target?.rightRealIndex]);

    const applyChatAdjustment = (frameDelta: number) => {
        if (fragments.length === 0) return;
        
        if (fragments.length === 1) {
            const clickSide = target?.clickSide || 'left';
            if (clickSide === 'left') {
                const initialAdj = leftAdjs.get(0) || 0;
                const clip = fragments[0];
                const origDur = clip.end_frame - clip.start_frame;
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                if (newAdj < 0) newAdj = 0;
                if (origDur - newAdj < minDur) newAdj = origDur - minDur;
                setLeftAdjs(prev => new Map(prev).set(0, newAdj));
                seekVideo((clip.start_frame + newAdj) / 30);
            } else {
                const initialAdj = rightAdjs.get(0) || 0;
                const clip = fragments[0];
                const origDur = clip.end_frame - clip.start_frame;
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                if (newAdj > 0) newAdj = 0;
                if (origDur + newAdj < minDur) newAdj = minDur - origDur;
                setRightAdjs(prev => new Map(prev).set(0, newAdj));
                seekVideo((clip.end_frame + newAdj) / 30);
            }
        }
        else if (pattern === 'S|S' && fragments.length === 2) {
            const L = fragments[0];
            const R = fragments[1];
            const initLeftAdj = leftAdjs.get(1) || 0;
            let newLeftAdj = initLeftAdj + frameDelta;
            if (newLeftAdj < 0) newLeftAdj = 0;
            const origDurR = R.end_frame - R.start_frame;
            if (origDurR - newLeftAdj < 15) newLeftAdj = origDurR - 15;
            setLeftAdjs(prev => new Map(prev).set(1, newLeftAdj));
            
            const initRightAdj = rightAdjs.get(0) || 0;
            let newRightAdj = initRightAdj - frameDelta;
            if (newRightAdj > 0) newRightAdj = 0;
            const origDurL = L.end_frame - L.start_frame;
            if (origDurL + newRightAdj < 15) newRightAdj = 15 - origDurL;
            setRightAdjs(prev => new Map(prev).set(0, newRightAdj));
            
            seekVideo((R.start_frame + newLeftAdj) / 30);
        }
        else if (fragments.length === 2 && fragments[0].selection_state === 'N' && fragments[1].selection_state === 'S') {
            const N = fragments[0];
            const S = fragments[1];
            const initialAdj = rightAdjs.get(0) || 0;
            let newAdj = initialAdj + frameDelta;
            const minDur = 15;
            const origDurN = N.end_frame - N.start_frame;
            const origDurS = S.end_frame - S.start_frame;
            if (newAdj < -origDurN) newAdj = -origDurN;
            if (newAdj > origDurS - minDur) newAdj = origDurS - minDur;
            
            setRightAdjs(prev => new Map(prev).set(0, newAdj));
            setLeftAdjs(prev => new Map(prev).set(1, newAdj));
            seekVideo((S.start_frame + newAdj) / 30);
        }
        else if (fragments.length === 2 && fragments[0].selection_state === 'S' && fragments[1].selection_state === 'N') {
            const S = fragments[0];
            const N = fragments[1];
            const initialAdj = rightAdjs.get(0) || 0;
            let newAdj = initialAdj + frameDelta;
            const minDur = 15;
            const origDurS = S.end_frame - S.start_frame;
            const origDurN = N.end_frame - N.start_frame;
            if (newAdj < -(origDurS - minDur)) newAdj = -(origDurS - minDur);
            if (newAdj > origDurN) newAdj = origDurN;
            
            setRightAdjs(prev => new Map(prev).set(0, newAdj));
            setLeftAdjs(prev => new Map(prev).set(1, newAdj));
            seekVideo((S.end_frame + newAdj) / 30);
        }
        else if (fragments.length >= 3 && fragments[0].selection_state === 'S' && fragments[fragments.length - 1].selection_state === 'S') {
            const lastIdx = fragments.length - 1;
            if (selectedClipIdx === 0) {
                const L = fragments[0];
                const initialAdj = rightAdjs.get(0) || 0;
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                const origDurL = L.end_frame - L.start_frame;
                if (origDurL + newAdj < minDur) newAdj = minDur - origDurL;
                
                const m = fragments.slice(1, lastIdx).reduce((sum, f) => sum + (f.end_frame - f.start_frame), 0);
                const b = Math.max(0, -(leftAdjs.get(lastIdx) || 0));
                if (newAdj > m - b) newAdj = m - b;
                
                setRightAdjs(prev => new Map(prev).set(0, newAdj));
                seekVideo((L.end_frame + newAdj) / 30);
            } else {
                const R = fragments[lastIdx];
                const initialAdj = leftAdjs.get(lastIdx) || 0;
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                const origDurR = R.end_frame - R.start_frame;
                if (origDurR - newAdj < minDur) newAdj = origDurR - minDur;
                
                const m = fragments.slice(1, lastIdx).reduce((sum, f) => sum + (f.end_frame - f.start_frame), 0);
                const a = Math.max(0, rightAdjs.get(0) || 0);
                const b = -newAdj;
                if (b > m - a) newAdj = -(m - a);
                
                setLeftAdjs(prev => new Map(prev).set(lastIdx, newAdj));
                seekVideo((R.start_frame + newAdj) / 30);
            }
        }
    };

    // Listen to custom window commands for PBE natural language chat integration
    useEffect(() => {
        const handleChatCommand = (e: Event) => {
            const detail = (e as CustomEvent).detail;
            if (!detail) return;
            
            const { action, adjustment } = detail;
            console.log("[PBE] Chat command received in editor:", detail);
            
            if (action === "apply") {
                handleApply();
            } else if (action === "cancel") {
                onOpenChange(false);
            } else if (action === "play") {
                if (videoRef.current && !isPlaying) {
                    videoRef.current.play().catch(err => console.error(err));
                    setIsPlaying(true);
                }
            } else if (action === "pause") {
                if (videoRef.current && isPlaying) {
                    videoRef.current.pause();
                    setIsPlaying(false);
                }
            } else if (action === "move" && typeof adjustment === "number") {
                applyChatAdjustment(adjustment);
            }
        };
        
        window.addEventListener("pbe-chat-command", handleChatCommand);
        return () => window.removeEventListener("pbe-chat-command", handleChatCommand);
    }, [open, fragments, leftAdjs, rightAdjs, selectedClipIdx, target]);

    // Initialize position when modal opens, video URL changes, or selected clip index changes
    useEffect(() => {
        if (open) {
            const urlChanged = lastVideoUrlRef.current !== activeVideoUrl;
            const clipChanged = lastClipIdxRef.current !== selectedClipIdx;

            if (urlChanged || clipChanged || !hasInitializedSeekRef.current) {
                lastVideoUrlRef.current = activeVideoUrl;
                lastClipIdxRef.current = selectedClipIdx;
                hasInitializedSeekRef.current = true;
                
                // Do not reset the playhead position to midpoint if we are actively dragging a bar or scrubbing the timeline
                if (!isDraggingRef.current && !isScrubbingRef.current) {
                    const initialTime = (clipStartSec + clipEndSec) / 2;
                    targetPlayTimeRef.current = initialTime;
                    setCurrentPlayTime(initialTime);
                    console.log("[PBE_DEBUG] Initialized play time state:", initialTime);
                    
                    if (videoRef.current) {
                        startSeekTimer();
                        try {
                            videoRef.current.currentTime = initialTime;
                        } catch (err) {
                            console.warn("Initial seek failed:", err);
                            isSeekingRef.current = false;
                        }
                    }
                }
            }
        } else {
            hasInitializedSeekRef.current = false;
            lastClipIdxRef.current = -1;
            lastVideoUrlRef.current = "";
        }
    }, [open, activeVideoUrl, selectedClipIdx, clipStartSec, clipEndSec]);

    const isScrubbingRef = useRef<boolean>(false);

    // Guard against slow-loading video source metadata resetting currentTime to 0
    const handleLoadedMetadata = () => {
        if (videoRef.current) {
            console.log("[PBE_DEBUG] onLoadedMetadata. currentTime =", videoRef.current.currentTime, "targetPlayTime =", targetPlayTimeRef.current);
            try {
                videoRef.current.currentTime = targetPlayTimeRef.current;
            } catch (err) {
                console.warn("Restore currentTime on metadata load failed:", err);
            }
        }
    };

    // Synchronize playhead time
    const handleTimeUpdate = () => {
        if (videoRef.current) {
            try {
                const current = videoRef.current.currentTime;
                if (isSeekingRef.current || videoRef.current.seeking) {
                    return;
                }
                
                // If native video player fires 0 during metadata loading state transitions, ignore it to prevent jumpback
                if (current === 0 && targetPlayTimeRef.current > 0.1 && videoRef.current.readyState < 2) {
                    return;
                }

                if (isScrubbingRef.current) {
                    return;
                }

                if (!isPlaying) {
                    return;
                }

                // Skip inactive (N) regions during active playback
                const F = Math.round(current * 30);
                const activeSourceVideo = activeGroup?.fragment.source_video;
                const sourceClips = visualClips.filter(c => c.source_video === activeSourceVideo);
                
                // Find which clip the current playhead is in
                const currentClip = sourceClips.find(c => F >= c.start_frame && F < c.end_frame);
                
                if (currentClip && currentClip.selection_state === 'N') {
                    // Find the next active clip
                    const nextActive = sourceClips.find(c => c.selection_state === 'S' && c.start_frame >= currentClip.end_frame);
                    if (nextActive) {
                        const nextTime = nextActive.start_frame / 30;
                        startSeekTimer();
                        videoRef.current.currentTime = nextTime;
                        targetPlayTimeRef.current = nextTime;
                        setCurrentPlayTime(nextTime);
                        return;
                    } else {
                        // Loop to the first active clip of this source
                        const firstActive = sourceClips.find(c => c.selection_state === 'S');
                        if (firstActive) {
                            const nextTime = firstActive.start_frame / 30;
                            startSeekTimer();
                            videoRef.current.currentTime = nextTime;
                            targetPlayTimeRef.current = nextTime;
                            setCurrentPlayTime(nextTime);
                            return;
                        }
                    }
                }

                // If F exceeds the end of the last active frame, loop back
                const maxFrame = sourceClips.reduce((max, c) => Math.max(max, c.end_frame), 0);
                if (F >= maxFrame) {
                    const firstActive = sourceClips.find(c => c.selection_state === 'S');
                    if (firstActive) {
                        const nextTime = firstActive.start_frame / 30;
                        startSeekTimer();
                        videoRef.current.currentTime = nextTime;
                        targetPlayTimeRef.current = nextTime;
                        setCurrentPlayTime(nextTime);
                        return;
                    }
                }

                if (isPlaying && current < targetPlayTimeRef.current - 0.15) {
                    return;
                }

                setCurrentPlayTime(current);
                targetPlayTimeRef.current = current;

                if (current > clipEndSec + 0.05) {
                    startSeekTimer();
                    videoRef.current.currentTime = clipStartSec;
                    targetPlayTimeRef.current = clipStartSec;
                    setCurrentPlayTime(clipStartSec);
                }
            } catch (err) {
                console.warn("Time update processing failed:", err);
            }
        }
    };

    const handlePlayPause = () => {
        if (videoRef.current) {
            if (isPlaying) {
                videoRef.current.pause();
                setIsPlaying(false);
            } else {
                if (isSeekingRef.current || videoRef.current.seeking) {
                    playRequestedRef.current = true;
                    setIsPlaying(true);
                } else {
                    try {
                        const timeDiff = Math.abs(videoRef.current.currentTime - targetPlayTimeRef.current);
                        if (timeDiff > 0.15) {
                            startSeekTimer();
                            videoRef.current.currentTime = targetPlayTimeRef.current;
                        }
                    } catch (err) {
                        console.warn("Setting currentTime before play failed:", err);
                        isSeekingRef.current = false;
                    }
                    videoRef.current.play().catch(e => console.error("Play failed:", e));
                    setIsPlaying(true);
                }
            }
        }
    };

    const seekVideo = (timeSec: number) => {
        targetPlayTimeRef.current = timeSec;
        if (videoRef.current) {
            try {
                startSeekTimer();
                videoRef.current.currentTime = timeSec;
            } catch (err) {
                isSeekingRef.current = false;
            }
        }
        setCurrentPlayTime(timeSec);
    };

    const seekVideoThrottled = (timeSec: number) => {
        const now = Date.now();
        // Limit seeks to once every 75ms during drag to avoid blocking the UI thread,
        // while updating the timeline itself at full 60fps.
        if (now - lastSeekTimeRef.current > 75) {
            seekVideo(timeSec);
            lastSeekTimeRef.current = now;
            pendingSeekTimeRef.current = null;
        } else {
            pendingSeekTimeRef.current = timeSec;
        }
    };



    // Constant scaling factor: 6px per frame
    const scale = 6;

    // Construct the visual clips that will be rendered proportionally
    const visualClips = useMemo(() => {
        const list: Array<{
            id: string;
            selection_state: 'S' | 'N';
            duration: number;
            start_frame: number;
            end_frame: number;
            source_video: string;
            originalIdx: number;
        }> = [];

        if (fragments.length === 0) return list;

        // Case 1/2: Single Trim
        if (fragments.length === 1) {
            const frag = fragments[0];
            const clickSide = target?.clickSide || 'left';
            const origDur = frag.end_frame - frag.start_frame;

            if (clickSide === 'left') {
                const a = leftAdjs.get(0) || 0;
                if (a > 0) {
                    list.push({
                        id: `${frag.fragment_id}_trimmed_N`,
                        selection_state: 'N',
                        duration: a,
                        start_frame: frag.start_frame,
                        end_frame: frag.start_frame + a,
                        source_video: frag.source_video,
                        originalIdx: 0,
                    });
                }
                list.push({
                    id: frag.fragment_id,
                    selection_state: 'S',
                    duration: origDur - a,
                    start_frame: frag.start_frame + a,
                    end_frame: frag.end_frame,
                    source_video: frag.source_video,
                    originalIdx: 0,
                });
            } else {
                const b = rightAdjs.get(0) || 0;
                const trim = -b;
                list.push({
                    id: frag.fragment_id,
                    selection_state: 'S',
                    duration: origDur - trim,
                    start_frame: frag.start_frame,
                    end_frame: frag.end_frame - trim,
                    source_video: frag.source_video,
                    originalIdx: 0,
                });
                if (trim > 0) {
                    list.push({
                        id: `${frag.fragment_id}_trimmed_N`,
                        selection_state: 'N',
                        duration: trim,
                        start_frame: frag.end_frame - trim,
                        end_frame: frag.end_frame,
                        source_video: frag.source_video,
                        originalIdx: 0,
                    });
                }
            }
        }
        // Case 3: S|S (Double Bar)
        else if (pattern === 'S|S' && fragments.length === 2) {
            const L = fragments[0];
            const R = fragments[1];
            const rightAdj = rightAdjs.get(0) || 0;
            const leftAdj = leftAdjs.get(1) || 0;
            const a = -rightAdj;
            const b = leftAdj;

            list.push({
                id: L.fragment_id,
                selection_state: 'S',
                duration: (L.end_frame - L.start_frame) - a,
                start_frame: L.start_frame,
                end_frame: L.end_frame - a,
                source_video: L.source_video,
                originalIdx: 0,
            });
            if (a > 0) {
                list.push({
                    id: `${L.fragment_id}_trimmed_N`,
                    selection_state: 'N',
                    duration: a,
                    start_frame: L.end_frame - a,
                    end_frame: L.end_frame,
                    source_video: L.source_video,
                    originalIdx: 0,
                });
            }
            if (b > 0) {
                list.push({
                    id: `${R.fragment_id}_trimmed_N`,
                    selection_state: 'N',
                    duration: b,
                    start_frame: R.start_frame,
                    end_frame: R.start_frame + b,
                    source_video: R.source_video,
                    originalIdx: 1,
                });
            }
            list.push({
                id: R.fragment_id,
                selection_state: 'S',
                duration: (R.end_frame - R.start_frame) - b,
                start_frame: R.start_frame + b,
                end_frame: R.end_frame,
                source_video: R.source_video,
                originalIdx: 1,
            });
        }
        // Case 4/5: S|N|S or S|N|N|S
        else if (fragments.length >= 3 && fragments[0].selection_state === 'S' && fragments[fragments.length - 1].selection_state === 'S') {
            const lastIdx = fragments.length - 1;
            const L = fragments[0];
            const R = fragments[lastIdx];
            const Ns = fragments.slice(1, lastIdx);
            const isRightSameSource = Ns[Ns.length - 1].source_video === R.source_video;

            const encroachL = rightAdjs.get(0) || 0;

            list.push({
                id: L.fragment_id,
                selection_state: 'S',
                duration: (L.end_frame - L.start_frame) + encroachL,
                start_frame: L.start_frame,
                end_frame: L.end_frame + encroachL,
                source_video: L.source_video,
                originalIdx: 0,
            });

            if (isRightSameSource) {
                const encroachR = -(leftAdjs.get(lastIdx) || 0);
                let currentOffsetL = encroachL;
                let currentOffsetR = encroachR;

                Ns.forEach((n, idx) => {
                    const actualIdx = idx + 1;
                    const origDur = n.end_frame - n.start_frame;

                    const safeL = Math.min(origDur, currentOffsetL);
                    currentOffsetL -= safeL;

                    const remainingAfterL = origDur - safeL;
                    const safeR = Math.min(remainingAfterL, currentOffsetR);
                    currentOffsetR -= safeR;

                    const start = n.start_frame + safeL;
                    const end = n.end_frame - safeR;
                    const dur = end - start;

                    if (dur > 0) {
                        list.push({
                            id: n.fragment_id,
                            selection_state: 'N',
                            duration: dur,
                            start_frame: start,
                            end_frame: end,
                            source_video: n.source_video,
                            originalIdx: actualIdx,
                        });
                    }
                });

                list.push({
                    id: R.fragment_id,
                    selection_state: 'S',
                    duration: (R.end_frame - R.start_frame) + encroachR,
                    start_frame: R.start_frame - encroachR,
                    end_frame: R.end_frame,
                    source_video: R.source_video,
                    originalIdx: lastIdx,
                });
            } else {
                const b = leftAdjs.get(lastIdx) || 0;
                let currentOffsetL = encroachL;

                Ns.forEach((n, idx) => {
                    const actualIdx = idx + 1;
                    const origDur = n.end_frame - n.start_frame;

                    const safeL = Math.min(origDur, currentOffsetL);
                    currentOffsetL -= safeL;

                    const start = n.start_frame + safeL;
                    const end = n.end_frame;
                    const dur = end - start;

                    if (dur > 0) {
                        list.push({
                            id: n.fragment_id,
                            selection_state: 'N',
                            duration: dur,
                            start_frame: start,
                            end_frame: end,
                            source_video: n.source_video,
                            originalIdx: actualIdx,
                        });
                    }
                });

                if (b > 0) {
                    list.push({
                        id: `${R.fragment_id}_trimmed_N`,
                        selection_state: 'N',
                        duration: b,
                        start_frame: R.start_frame,
                        end_frame: R.start_frame + b,
                        source_video: R.source_video,
                        originalIdx: lastIdx,
                    });
                }

                list.push({
                    id: R.fragment_id,
                    selection_state: 'S',
                    duration: (R.end_frame - R.start_frame) - b,
                    start_frame: R.start_frame + b,
                    end_frame: R.end_frame,
                    source_video: R.source_video,
                    originalIdx: lastIdx,
                });
            }
        }
        // Case: N|S
        else if (fragments.length === 2 && fragments[0].selection_state === 'N' && fragments[1].selection_state === 'S') {
            const N = fragments[0];
            const S = fragments[1];
            const delta = leftAdjs.get(1) || 0;

            list.push({
                id: N.fragment_id,
                selection_state: 'N',
                duration: (N.end_frame - N.start_frame) + delta,
                start_frame: N.start_frame,
                end_frame: N.end_frame + delta,
                source_video: N.source_video,
                originalIdx: 0,
            });
            list.push({
                id: S.fragment_id,
                selection_state: 'S',
                duration: (S.end_frame - S.start_frame) - delta,
                start_frame: S.start_frame + delta,
                end_frame: S.end_frame,
                source_video: S.source_video,
                originalIdx: 1,
            });
        }
        // Case: S|N
        else if (fragments.length === 2 && fragments[0].selection_state === 'S' && fragments[1].selection_state === 'N') {
            const S = fragments[0];
            const N = fragments[1];
            const delta = rightAdjs.get(0) || 0;

            list.push({
                id: S.fragment_id,
                selection_state: 'S',
                duration: (S.end_frame - S.start_frame) + delta,
                start_frame: S.start_frame,
                end_frame: S.end_frame + delta,
                source_video: S.source_video,
                originalIdx: 0,
            });
            list.push({
                id: N.fragment_id,
                selection_state: 'N',
                duration: (N.end_frame - N.start_frame) - delta,
                start_frame: N.start_frame + delta,
                end_frame: N.end_frame,
                source_video: N.source_video,
                originalIdx: 1,
            });
        }
        else {
            fragments.forEach((f, idx) => {
                const lAdj = leftAdjs.get(idx) || 0;
                const rAdj = rightAdjs.get(idx) || 0;
                list.push({
                    id: f.fragment_id,
                    selection_state: f.selection_state as 'S' | 'N',
                    duration: (f.end_frame - f.start_frame) + rAdj - lAdj,
                    start_frame: f.start_frame + lAdj,
                    end_frame: f.end_frame + rAdj,
                    source_video: f.source_video,
                    originalIdx: idx,
                });
            });
        }

        return list;
    }, [fragments, leftAdjs, rightAdjs, target, pattern]);

    const totalFrames = useMemo(() => {
        return visualClips.reduce((sum, c) => sum + c.duration, 0);
    }, [visualClips]);

    const totalWidth = useMemo(() => {
        return totalFrames * scale;
    }, [totalFrames]);

    // Position of proportional bars in frames from start of timeline
    const barsConfig = useMemo(() => {
        const list: Array<{
            id: string;
            type: 'trim-left' | 'trim-right' | 'boundary-left' | 'boundary-right' | 'boundary-seam';
            clipIdx?: number;
            leftIdx?: number;
            rightIdx?: number;
            positionFrame: number;
        }> = [];

        if (fragments.length === 0) return list;

        // Case 1/2: Single Trim
        if (fragments.length === 1) {
            const frag = fragments[0];
            const clickSide = target?.clickSide || 'left';
            if (clickSide === 'left') {
                const a = leftAdjs.get(0) || 0;
                list.push({
                    id: 'bar-trim-left',
                    type: 'trim-left',
                    clipIdx: 0,
                    positionFrame: a,
                });
            } else {
                const b = rightAdjs.get(0) || 0;
                const origDur = frag.end_frame - frag.start_frame;
                list.push({
                    id: 'bar-trim-right',
                    type: 'trim-right',
                    clipIdx: 0,
                    positionFrame: origDur + b,
                });
            }
        }
        // Case 3: S|S
        else if (pattern === 'S|S' && fragments.length === 2) {
            const L = fragments[0];
            const rightAdj = rightAdjs.get(0) || 0;
            const leftAdj = leftAdjs.get(1) || 0;
            const a = -rightAdj;

            list.push({
                id: 'bar-trim-right',
                type: 'trim-right',
                clipIdx: 0,
                positionFrame: (L.end_frame - L.start_frame) - a,
            });
            list.push({
                id: 'bar-trim-left',
                type: 'trim-left',
                clipIdx: 1,
                positionFrame: (L.end_frame - L.start_frame) + leftAdj,
            });
        }
        // Case 4/5: S|N|S or S|N|N|S
        else if (fragments.length >= 3 && fragments[0].selection_state === 'S' && fragments[fragments.length - 1].selection_state === 'S') {
            const lastIdx = fragments.length - 1;
            const L = fragments[0];
            const encroachL = rightAdjs.get(0) || 0;

            list.push({
                id: 'bar-boundary-left',
                type: 'boundary-left',
                leftIdx: 0,
                rightIdx: 1,
                positionFrame: (L.end_frame - L.start_frame) + encroachL,
            });

            const totalDurExcludingLast = visualClips
                .slice(0, visualClips.length - 1)
                .reduce((sum, c) => sum + c.duration, 0);

            list.push({
                id: 'bar-boundary-right',
                type: 'boundary-right',
                leftIdx: lastIdx - 1,
                rightIdx: lastIdx,
                positionFrame: totalDurExcludingLast,
            });
        }
        // Case: N|S
        else if (fragments.length === 2 && fragments[0].selection_state === 'N' && fragments[1].selection_state === 'S') {
            const N = fragments[0];
            const delta = leftAdjs.get(1) || 0;
            list.push({
                id: 'bar-boundary-seam',
                type: 'boundary-seam',
                leftIdx: 0,
                rightIdx: 1,
                positionFrame: (N.end_frame - N.start_frame) + delta,
            });
        }
        // Case: S|N
        else if (fragments.length === 2 && fragments[0].selection_state === 'S' && fragments[1].selection_state === 'N') {
            const S = fragments[0];
            const delta = rightAdjs.get(0) || 0;
            list.push({
                id: 'bar-boundary-seam',
                type: 'boundary-seam',
                leftIdx: 0,
                rightIdx: 1,
                positionFrame: (S.end_frame - S.start_frame) + delta,
            });
        }

        return list;
    }, [fragments, pattern, leftAdjs, rightAdjs, visualClips, target]);

    const hasCenteredRef = useRef<boolean>(false);

    useEffect(() => {
        if (open) {
            if (!hasCenteredRef.current && barsConfig.length > 0) {
                const timer = setTimeout(() => {
                    if (timelineContainerRef.current) {
                        const avgFrame = barsConfig.reduce((sum, bar) => sum + bar.positionFrame, 0) / barsConfig.length;
                        const seamPx = avgFrame * scale;
                        const containerWidth = timelineContainerRef.current.clientWidth;
                        timelineContainerRef.current.scrollLeft = seamPx - containerWidth / 2;
                        hasCenteredRef.current = true;
                        console.log("[PBE_DEBUG] Centered seam at px:", seamPx, "scrollLeft:", timelineContainerRef.current.scrollLeft);
                    }
                }, 100);
                return () => clearTimeout(timer);
            }
        } else {
            hasCenteredRef.current = false;
        }
    }, [open, barsConfig]);

    // Position of playhead in pixels from start of timeline
    const playheadPx = useMemo(() => {
        if (fragments.length === 0 || visualClips.length === 0) return 0;
        
        const currentFrame = Math.round(currentPlayTime * 30);
        const activeSourceVideo = activeGroup?.fragment.source_video;
        
        let accumulatedFrame = 0;
        for (const c of visualClips) {
            if (c.source_video === activeSourceVideo && currentFrame >= c.start_frame && currentFrame <= c.end_frame) {
                const offset = currentFrame - c.start_frame;
                return (accumulatedFrame + offset) * scale;
            }
            accumulatedFrame += c.duration;
        }
        
        // Fallback: if not found, just use the beginning of the activeGroup
        let fallbackAccumulated = 0;
        for (const c of visualClips) {
            if (c.originalIdx === selectedClipIdx) {
                return fallbackAccumulated * scale;
            }
            fallbackAccumulated += c.duration;
        }
        return 0;
    }, [visualClips, selectedClipIdx, currentPlayTime, activeGroup]);

    const handleBarMouseDown = (bar: typeof barsConfig[0], e: React.MouseEvent) => {
        e.stopPropagation();
        e.preventDefault();
        
        isDraggingRef.current = true;
        
        let initialAdj = 0;
        let activeIdx = selectedClipIdx;
        let initialTimeSec = currentPlayTime;

        if (bar.type === 'trim-left') {
            initialAdj = leftAdjs.get(bar.clipIdx!) || 0;
            activeIdx = bar.clipIdx!;
            const clip = fragments[activeIdx];
            initialTimeSec = (clip.start_frame + initialAdj) / 30;
        } else if (bar.type === 'trim-right') {
            initialAdj = rightAdjs.get(bar.clipIdx!) || 0;
            activeIdx = bar.clipIdx!;
            const clip = fragments[activeIdx];
            initialTimeSec = (clip.end_frame + initialAdj) / 30;
        } else if (bar.type === 'boundary-left') {
            initialAdj = rightAdjs.get(0) || 0;
            activeIdx = 0;
            const L = fragments[activeIdx];
            initialTimeSec = (L.end_frame + initialAdj) / 30;
        } else if (bar.type === 'boundary-right') {
            initialAdj = leftAdjs.get(fragments.length - 1) || 0;
            activeIdx = fragments.length - 1;
            const R = fragments[activeIdx];
            initialTimeSec = (R.start_frame + initialAdj) / 30;
        } else if (bar.type === 'boundary-seam') {
            initialAdj = bar.leftIdx === 0 ? (rightAdjs.get(0) || 0) : (leftAdjs.get(1) || 0);
            activeIdx = bar.leftIdx === 0 ? 0 : 1;
            const S = fragments[activeIdx];
            initialTimeSec = (bar.leftIdx === 0 ? (S.end_frame + initialAdj) : (S.start_frame + initialAdj)) / 30;
        }

        setSelectedClipIdx(activeIdx);
        
        // Immediately seek the playhead to the boundary position on mouse down so it does not jump randomly when active video switches
        targetPlayTimeRef.current = initialTimeSec;
        setCurrentPlayTime(initialTimeSec);
        if (videoRef.current) {
            startSeekTimer();
            try {
                videoRef.current.currentTime = initialTimeSec;
            } catch (err) {
                console.warn("Initial bar seek failed:", err);
                isSeekingRef.current = false;
            }
        }
        
        setDragState({
            type: bar.type,
            clipIdx: bar.clipIdx,
            leftIdx: bar.leftIdx,
            rightIdx: bar.rightIdx,
            initialX: e.clientX,
            initialAdj,
        });
    };

    const handleGlobalMouseMove = (e: MouseEvent) => {
        if (!dragState) return;
        const deltaX = e.clientX - dragState.initialX;
        const frameDelta = Math.round(deltaX / scale);
        const initialAdj = dragState.initialAdj;
        
        if (dragState.type === 'trim-left') {
            const clipIdx = dragState.clipIdx!;
            const clip = fragments[clipIdx];
            const origDur = clip.end_frame - clip.start_frame;
            let newAdj = initialAdj + frameDelta;
            
            const minDur = 15;
            if (newAdj < 0) newAdj = 0;
            if (origDur - newAdj < minDur) newAdj = origDur - minDur;
            
            setLeftAdjs(prev => new Map(prev).set(clipIdx, newAdj));
            
            const startSec = (clip.start_frame + newAdj) / 30;
            seekVideoThrottled(startSec);
        }
        else if (dragState.type === 'trim-right') {
            const clipIdx = dragState.clipIdx!;
            const clip = fragments[clipIdx];
            const origDur = clip.end_frame - clip.start_frame;
            let newAdj = initialAdj + frameDelta;
            
            const minDur = 15;
            if (newAdj > 0) newAdj = 0;
            if (origDur + newAdj < minDur) newAdj = minDur - origDur;
            
            setRightAdjs(prev => new Map(prev).set(clipIdx, newAdj));
            
            const endSec = (clip.end_frame + newAdj) / 30;
            seekVideoThrottled(endSec);
        }
        else if (dragState.type === 'boundary-left') {
            const L = fragments[0];
            const lastIdx = fragments.length - 1;
            const m = fragments.slice(1, lastIdx).reduce((sum, f) => sum + (f.end_frame - f.start_frame), 0);
            
            let newAdj = initialAdj + frameDelta;
            const minDur = 15;
            
            const origDurL = L.end_frame - L.start_frame;
            if (origDurL + newAdj < minDur) newAdj = minDur - origDurL;
            
            const b = Math.max(0, -(leftAdjs.get(lastIdx) || 0));
            if (newAdj > m - b) newAdj = m - b;
            
            setRightAdjs(prev => new Map(prev).set(0, newAdj));
            
            const boundarySec = (L.end_frame + newAdj) / 30;
            seekVideoThrottled(boundarySec);
        }
        else if (dragState.type === 'boundary-right') {
            const lastIdx = fragments.length - 1;
            const R = fragments[lastIdx];
            const isRightSameSource = fragments[lastIdx - 1].source_video === R.source_video;
            
            if (isRightSameSource) {
                const m = fragments.slice(1, lastIdx).reduce((sum, f) => sum + (f.end_frame - f.start_frame), 0);
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                const origDurR = R.end_frame - R.start_frame;
                if (origDurR - newAdj < minDur) newAdj = origDurR - minDur;
                
                const a = Math.max(0, rightAdjs.get(0) || 0);
                const b = -newAdj;
                if (b > m - a) newAdj = -(m - a);
                
                setLeftAdjs(prev => new Map(prev).set(lastIdx, newAdj));
                const boundarySec = (R.start_frame + newAdj) / 30;
                seekVideoThrottled(boundarySec);
            } else {
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                const origDurR = R.end_frame - R.start_frame;
                
                if (newAdj < 0) newAdj = 0;
                if (origDurR - newAdj < minDur) newAdj = origDurR - minDur;
                
                setLeftAdjs(prev => new Map(prev).set(lastIdx, newAdj));
                const boundarySec = (R.start_frame + newAdj) / 30;
                seekVideoThrottled(boundarySec);
            }
        }
        else if (dragState.type === 'boundary-seam') {
            const isLeftS = fragments[0].selection_state === 'S';
            if (isLeftS) {
                // S|N
                const S = fragments[0];
                const N = fragments[1];
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                const origDurS = S.end_frame - S.start_frame;
                const origDurN = N.end_frame - N.start_frame;
                
                if (newAdj < -(origDurS - minDur)) newAdj = -(origDurS - minDur);
                if (newAdj > origDurN) newAdj = origDurN;
                
                setRightAdjs(prev => new Map(prev).set(0, newAdj));
                setLeftAdjs(prev => new Map(prev).set(1, newAdj));
                
                seekVideoThrottled((S.end_frame + newAdj) / 30);
            } else {
                // N|S
                const N = fragments[0];
                const S = fragments[1];
                let newAdj = initialAdj + frameDelta;
                const minDur = 15;
                const origDurN = N.end_frame - N.start_frame;
                const origDurS = S.end_frame - S.start_frame;
                
                if (newAdj < -origDurN) newAdj = -origDurN;
                if (newAdj > origDurS - minDur) newAdj = origDurS - minDur;
                
                setRightAdjs(prev => new Map(prev).set(0, newAdj));
                setLeftAdjs(prev => new Map(prev).set(1, newAdj));
                
                seekVideoThrottled((S.start_frame + newAdj) / 30);
            }
        }
    };

    const handleGlobalMouseUp = () => {
        isDraggingRef.current = false;
        setDragState(null);
        if (pendingSeekTimeRef.current !== null) {
            seekVideo(pendingSeekTimeRef.current);
            pendingSeekTimeRef.current = null;
        }
    };

    const handleTimelineMouseDown = (e: React.MouseEvent<HTMLDivElement>) => {
        if ((e.target as HTMLElement).closest('.pbe-bar')) return;
        
        isScrubbingRef.current = true;
        
        const timelineElem = e.currentTarget;
        const doScrub = (clientX: number) => {
            const rect = timelineElem.getBoundingClientRect();
            const clickX = clientX - rect.left;
            const clickFrame = Math.max(0, Math.min(totalFrames, Math.round(clickX / scale)));
            
            let currentSum = 0;
            let foundClipIdx = 0;
            let frameOffsetInClip = 0;
            let targetClip = null;
            
            for (let i = 0; i < visualClips.length; i++) {
                const clip = visualClips[i];
                if (clickFrame >= currentSum && clickFrame <= currentSum + clip.duration) {
                    foundClipIdx = clip.originalIdx;
                    frameOffsetInClip = clickFrame - currentSum;
                    targetClip = clip;
                    break;
                }
                currentSum += clip.duration;
            }
            
            setSelectedClipIdx(foundClipIdx);
            
            if (targetClip) {
                const targetFrame = targetClip.start_frame + frameOffsetInClip;
                seekVideo(targetFrame / 30);
            }
        };
        
        doScrub(e.clientX);
        
        const handleMouseMove = (moveEvent: MouseEvent) => {
            doScrub(moveEvent.clientX);
        };
        
        const handleMouseUp = () => {
            setTimeout(() => {
                isScrubbingRef.current = false;
            }, 150);
            window.removeEventListener('mousemove', handleMouseMove);
            window.removeEventListener('mouseup', handleMouseUp);
        };
        
        window.addEventListener('mousemove', handleMouseMove);
        window.addEventListener('mouseup', handleMouseUp);
    };

    const handleApply = () => {
        console.log('[PBE] === APPLY START ===');
        const sFrags = fragments.filter(f => f.selection_state === 'S');
        const nFrags = fragments.filter(f => f.selection_state === 'N');

        let newFragments: any[] = [];
        let removedIds: string[] = [];

        // Case 1/2: Single trim (length 1)
        if (fragments.length === 1) {
            const frag = fragments[0];
            const lAdj = leftAdjs.get(0) || 0;
            const rAdj = rightAdjs.get(0) || 0;

            if (lAdj !== 0) {
                const result = applySingleTrim(frag as any, Math.abs(lAdj), 'left');
                newFragments = [result.kept];
                if (result.trimmed) newFragments.push(result.trimmed);
                removedIds = result.removed;
            } else if (rAdj !== 0) {
                const result = applySingleTrim(frag as any, Math.abs(rAdj), 'right');
                newFragments = [result.kept];
                if (result.trimmed) newFragments.push(result.trimmed);
                removedIds = result.removed;
            } else {
                newFragments = [frag];
            }
        }
        // Case 3: S|S double bar
        else if (pattern === 'S|S' && sFrags.length === 2) {
            const L = sFrags[0];
            const R = sFrags[1];
            const rightAdj = rightAdjs.get(0) || 0;
            const a = rightAdj < 0 ? -rightAdj : 0;
            const leftAdj = leftAdjs.get(1) || 0;
            const b = leftAdj > 0 ? leftAdj : 0;

            const result = applySSBoundary(L as any, R as any, a, b);
            newFragments = [result.left];
            if (result.leftTrimmed) newFragments.push(result.leftTrimmed);
            if (result.rightTrimmed) newFragments.push(result.rightTrimmed);
            newFragments.push(result.right);
            removedIds = result.removed;
        }
        // Case 4/5: S|N|S or S|N|N|S
        else if (sFrags.length === 2 && nFrags.length >= 1) {
            const L = sFrags[0];
            const R = sFrags[sFrags.length - 1];
            const Ns = nFrags;
            
            const isRightSameSource = Ns[Ns.length - 1].source_video === R.source_video;
            
            if (isRightSameSource) {
                const a = Math.max(0, rightAdjs.get(0) || 0);
                const b = Math.max(0, -(leftAdjs.get(fragments.length - 1) || 0));

                const result = applySNSBoundary(L as any, Ns as any, R as any, a, b);
                newFragments = [result.left];
                if (result.leftSub) newFragments.push(result.leftSub);
                if (result.midRem) newFragments.push(result.midRem);
                if (result.rightSub) newFragments.push(result.rightSub);
                newFragments.push(result.right);
                removedIds = result.removed;
            } else {
                const a = Math.max(0, rightAdjs.get(0) || 0);
                const trimB = Math.max(0, leftAdjs.get(fragments.length - 1) || 0);

                // 1. Process L and Ns (same-source)
                const result = applySNSBoundary(L as any, Ns as any, R as any, a, 0);
                newFragments = [result.left];
                if (result.leftSub) newFragments.push(result.leftSub);
                if (result.midRem) newFragments.push(result.midRem);
                removedIds = [...result.removed];

                // 2. Process R (cross-source)
                if (trimB > 0) {
                    const trimResult = applySingleTrim(R as any, trimB, 'left');
                    if (trimResult.trimmed) newFragments.push(trimResult.trimmed);
                    newFragments.push(trimResult.kept);
                    removedIds.push(...trimResult.removed);
                } else {
                    newFragments.push(R);
                }
            }
        }
        else {
            // Fallback: simple boundary adjustments
            const updated = fragments.map((f, idx) => {
                const lAdj = leftAdjs.get(idx) || 0;
                const rAdj = rightAdjs.get(idx) || 0;
                const start = f.start_frame + lAdj;
                const end = f.end_frame + rAdj;
                return {
                    ...f,
                    start_frame: start,
                    end_frame: end,
                    duration: Math.max(0, end - start),
                };
            });
            newFragments = updated;
        }

        // Merge back into full edit timeline to avoid truncating editFragments
        const originalIds = fragments.map(f => getUid(f));
        const mergedTimeline = applyPBEResultToFragments(
            editFragments,
            originalIds,
            newFragments,
            removedIds
        );

        // Recalculate display IDs and short display IDs to match 비례바편집창_번호부여.md rules
        const finalTimeline = assignShortDisplayIds(recalcDisplayIds(mergedTimeline));

        if (onApply) {
            onApply({
                updatedFragments: finalTimeline,
                removedFragmentIds: removedIds,
            });
        }
        onOpenChange(false);
    };

    useEffect(() => {
        if (dragState) {
            window.addEventListener('mousemove', handleGlobalMouseMove);
            window.addEventListener('mouseup', handleGlobalMouseUp);
            return () => {
                window.removeEventListener('mousemove', handleGlobalMouseMove);
                window.removeEventListener('mouseup', handleGlobalMouseUp);
            };
        }
    }, [dragState]);

    const currentTimecode = useMemo(() => {
        const sec = typeof currentPlayTime === 'number' ? currentPlayTime : clipStartSec;
        const h = Math.floor(sec / 3600);
        const m = Math.floor((sec % 3600) / 60);
        const s = Math.floor(sec % 60);
        const f = Math.floor((sec % 1) * 30);
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}:${f.toString().padStart(2, '0')}`;
    }, [currentPlayTime, clipStartSec]);

    const renderStaticClipThumbnails = (frag: PBEFragment) => {
        const origDur = frag.end_frame - frag.start_frame;
        const cardWidth = origDur * scale;
        const numThumbs = Math.max(1, Math.round(cardWidth / 36));

        const thumbs: React.ReactNode[] = [];
        for (let i = 0; i < numThumbs; i++) {
            const p = numThumbs > 1 ? i / (numThumbs - 1) : 0;
            const thumbIdx = Math.max(0, Math.min(11, Math.round(p * 11)));
            const src = `/static/thumbnails/P_${frag.fragment_id}_${thumbIdx}.jpg`;
            
            thumbs.push(
                <CapCutFrameImage
                    key={i}
                    src={src}
                    alt=""
                    style={{
                        width: `${cardWidth / numThumbs}px`,
                        height: '100%',
                    }}
                />
            );
        }
        return thumbs;
    };

    const renderStaticClipWaveform = (frag: PBEFragment) => {
        const waveformData = getDeterministicAudioData(frag.fragment_id);
        const origDur = frag.end_frame - frag.start_frame;
        const cardWidth = origDur * scale;
        const numBars = Math.max(5, Math.round(cardWidth / 12));

        const bars: React.ReactNode[] = [];
        for (let i = 0; i < numBars; i++) {
            const p = numBars > 1 ? i / (numBars - 1) : 0;
            const ptIdx = Math.max(0, Math.min(waveformData.points.length - 1, Math.round(p * (waveformData.points.length - 1))));
            const pt = waveformData.points[ptIdx];

            bars.push(
                <div
                    key={i}
                    style={{
                        width: '2px',
                        height: `${pt * 100}%`,
                        backgroundColor: '#22c55e',
                        borderRadius: '1px',
                    }}
                />
            );
        }
        return bars;
    };

    const renderClipThumbnails = (clip: typeof visualClips[0]) => {
        const origFrag = fragments[clip.originalIdx];
        if (!origFrag) return null;
        const origStart = origFrag.start_frame;
        const origEnd = origFrag.end_frame;
        const origDur = origEnd - origStart;

        const cardWidth = clip.duration * scale;
        const numThumbs = Math.max(1, Math.round(cardWidth / 36));

        const thumbs: React.ReactNode[] = [];
        for (let i = 0; i < numThumbs; i++) {
            const t = numThumbs > 1 ? i / (numThumbs - 1) : 0;
            const mappedFrame = clip.start_frame + t * (clip.end_frame - clip.start_frame);
            const p = origDur > 0 ? (mappedFrame - origStart) / origDur : 0;
            const thumbIdx = Math.max(0, Math.min(11, Math.round(p * 11)));
            const src = `/static/thumbnails/P_${origFrag.fragment_id}_${thumbIdx}.jpg`;
            
            thumbs.push(
                <CapCutFrameImage
                    key={i}
                    src={src}
                    alt=""
                    style={{
                        width: `${cardWidth / numThumbs}px`,
                        height: '100%',
                    }}
                />
            );
        }
        return thumbs;
    };

    const renderClipWaveform = (clip: typeof visualClips[0]) => {
        const origFrag = fragments[clip.originalIdx];
        if (!origFrag) return null;
        const origStart = origFrag.start_frame;
        const origEnd = origFrag.end_frame;
        const origDur = origEnd - origStart;

        const waveformData = getDeterministicAudioData(origFrag.fragment_id);
        const cardWidth = clip.duration * scale;
        const numBars = Math.max(5, Math.round(cardWidth / 12));

        const bars: React.ReactNode[] = [];
        for (let i = 0; i < numBars; i++) {
            const t = numBars > 1 ? i / (numBars - 1) : 0;
            const mappedFrame = clip.start_frame + t * (clip.end_frame - clip.start_frame);
            const p = origDur > 0 ? (mappedFrame - origStart) / origDur : 0;
            const ptIdx = Math.max(0, Math.min(waveformData.points.length - 1, Math.round(p * (waveformData.points.length - 1))));
            const pt = waveformData.points[ptIdx];

            bars.push(
                <div
                    key={i}
                    style={{
                        width: '2px',
                        height: `${pt * 100}%`,
                        backgroundColor: clip.selection_state === 'S' ? '#22c55e' : '#4e5e54',
                        borderRadius: '1px',
                    }}
                />
            );
        }
        return bars;
    };

    if (!open) return null;

    // Premium dynamic scaling fitting both max width and max height
    const maxPlayerW = dimensions.width - 80;
    const maxPlayerH = dimensions.height - 320;
    
    let playerWidth = maxPlayerW;
    let playerHeight = maxPlayerW * (9 / 16);
    
    if (playerHeight > maxPlayerH) {
        playerHeight = maxPlayerH;
        playerWidth = maxPlayerH * (16 / 9);
    }
    
    playerWidth = Math.max(320, playerWidth);
    playerHeight = Math.max(180, playerHeight);

    return (
        <div
            style={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: 'rgba(6, 6, 8, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 1000,
                pointerEvents: 'none',
            }}
        >
            {/* Main Window */}
            <div
                style={{
                    backgroundColor: '#121214',
                    border: '1px solid #222226',
                    borderRadius: '16px',
                    width: `${dimensions.width}px`,
                    height: `${dimensions.height}px`,
                    boxShadow: '0 25px 60px -15px rgba(0,0,0,0.9), 0 0 1px 1px rgba(255,255,255,0.05) inset',
                    display: 'flex',
                    flexDirection: 'column',
                    userSelect: 'none',
                    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
                    overflow: 'hidden',
                    position: 'relative',
                    pointerEvents: 'auto',
                }}
            >
                {/* Header Section */}
                <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '14px 20px',
                    backgroundColor: '#16161a',
                    borderBottom: '1px solid #222226',
                    flexShrink: 0,
                }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: '#f1f5f9', letterSpacing: '0.01em' }}>정밀 편집 (PBE)</span>
                    <button
                        onClick={() => onOpenChange(false)}
                        style={{
                            background: 'transparent',
                            border: 'none',
                            color: '#94a3b8',
                            cursor: 'pointer',
                            fontSize: '18px',
                            transition: 'color 0.2s',
                        }}
                    >
                        ✕
                    </button>
                </div>

                {/* Player Section */}
                <div style={{
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    padding: '10px 0',
                    backgroundColor: '#0a0a0c',
                    position: 'relative',
                    flex: 1,
                    minHeight: 0,
                }}>
                    <div style={{
                        width: `${playerWidth}px`,
                        height: `${playerHeight}px`,
                        backgroundColor: '#000',
                        borderRadius: '8px',
                        border: '1px solid #222226',
                        overflow: 'hidden',
                        position: 'relative',
                        boxShadow: '0 12px 30px rgba(0,0,0,0.8)',
                    }}>
                        {activeVideoUrl && (
                            <video
                                ref={videoRef}
                                src={activeVideoUrl}
                                onTimeUpdate={handleTimeUpdate}
                                onLoadedMetadata={handleLoadedMetadata}
                                onLoadedData={handleLoadedMetadata}
                                onPause={() => setIsPlaying(false)}
                                onPlay={() => setIsPlaying(true)}
                                onSeeked={() => {
                                    isSeekingRef.current = false;
                                    if (playRequestedRef.current && videoRef.current) {
                                        playRequestedRef.current = false;
                                        videoRef.current.play().catch(e => console.error("Deferred play failed:", e));
                                    }
                                }}
                                style={{ 
                                    width: '100%', 
                                    height: '100%', 
                                    objectFit: 'contain',
                                    display: 'block'
                                }}
                                preload="auto"
                                playsInline
                                muted
                                crossOrigin="anonymous"
                            />
                        )}

                        <div 
                            id="pbe-absolute-timecode"
                            style={{
                                position: 'absolute',
                                bottom: '10px',
                                right: '10px',
                                backgroundColor: 'rgba(15, 15, 20, 0.75)',
                                backdropFilter: 'blur(4px)',
                                border: '1px solid rgba(255,255,255,0.06)',
                                color: '#f8fafc',
                                padding: '3px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontFamily: 'monospace',
                                zIndex: 40,
                            }}
                        >
                            {currentTimecode}
                        </div>
                    </div>

                    {/* Compact Control Button Group */}
                    <div style={{ display: 'flex', gap: '8px', marginTop: '20px' }}>
                        <button
                            onClick={handlePlayPause}
                            style={{
                                backgroundColor: isPlaying ? '#ef4444' : '#22c55e',
                                border: 'none',
                                borderRadius: '6px',
                                color: '#fff',
                                fontSize: '12px',
                                fontWeight: 600,
                                padding: '8px 20px',
                                cursor: 'pointer',
                                transition: 'all 0.2s',
                                minWidth: '80px',
                            }}
                        >
                            {isPlaying ? '일시정지' : '재생'}
                        </button>
                    </div>
                </div>

                {/* Timeline Panel */}
                <div style={{
                    padding: '20px 24px 28px 24px',
                    backgroundColor: '#121214',
                    borderTop: '1px solid #222226',
                }}>
                    {/* Time Ruler */}
                    <div style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        fontSize: '10px',
                        color: '#64748b',
                        fontFamily: 'monospace',
                        paddingBottom: '8px',
                        borderBottom: '1px solid #1e1e22',
                    }}>
                        <span>00:00:00:00</span>
                        <span>00:00:02:00</span>
                        <span>00:00:04:00</span>
                        <span>00:00:06:00</span>
                    </div>

                    {/* Proportional Continuous Filmstrip Timeline */}
                    <div 
                        ref={timelineContainerRef}
                        style={{
                            overflowX: 'auto',
                            padding: '16px 0 8px 0',
                        }}
                    >
                        <div 
                            onMouseDown={handleTimelineMouseDown}
                            style={{
                                position: 'relative',
                                width: `${totalWidth}px`,
                                height: '110px',
                                backgroundColor: '#09090b',
                                borderRadius: '8px',
                                cursor: 'ew-resize',
                                overflow: 'visible',
                            }}
                        >
                            {/* Static filmstrip background cards packed side-by-side */}
                            <div style={{
                                display: 'flex',
                                width: '100%',
                                height: '100%',
                                borderRadius: '8px',
                                overflow: 'hidden',
                            }}>
                                {fragments.map((frag, idx) => {
                                    const cardW = (frag.end_frame - frag.start_frame) * scale;
                                    
                                    return (
                                        <div
                                            key={frag.fragment_id}
                                            style={{
                                                width: `${cardW}px`,
                                                height: '100%',
                                                flexShrink: 0,
                                                position: 'relative',
                                                borderRight: '1px dashed rgba(255,255,255,0.08)',
                                                boxSizing: 'border-box',
                                            }}
                                        >
                                            {/* Filmstrip frame images (Static) */}
                                            <div style={{
                                                height: '80px',
                                                width: '100%',
                                                display: 'flex',
                                                overflow: 'hidden',
                                            }}>
                                                {renderStaticClipThumbnails(frag)}
                                            </div>

                                            {/* Waveform track (Static) */}
                                            <div style={{
                                                height: '30px',
                                                backgroundColor: '#1b2c21',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'space-around',
                                                padding: '0 6px',
                                            }}>
                                                {renderStaticClipWaveform(frag)}
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>

                            {/* Absolute overlays of selected/unselected intervals */}
                            {(() => {
                                let accumulatedFrame = 0;
                                return visualClips.map((clip) => {
                                    const startFrame = accumulatedFrame;
                                    const duration = clip.duration;
                                    accumulatedFrame += duration;

                                    const isSelected = selectedClipIdx === clip.originalIdx;
                                    const isS = clip.selection_state === 'S';
                                    const cardW = duration * scale;
                                    const leftPx = startFrame * scale;

                                    return (
                                        <React.Fragment key={clip.id}>
                                            {/* Dark overlay for unselected (N) filmstrip */}
                                            {!isS && (
                                                <div style={{
                                                    position: 'absolute',
                                                    left: `${leftPx}px`,
                                                    width: `${cardW}px`,
                                                    top: 0,
                                                    height: '80px',
                                                    backgroundColor: 'rgba(9, 9, 11, 0.75)',
                                                    pointerEvents: 'none',
                                                    zIndex: 10,
                                                }} />
                                            )}

                                            {/* Dark overlay for unselected (N) waveform */}
                                            {!isS && (
                                                <div style={{
                                                    position: 'absolute',
                                                    left: `${leftPx}px`,
                                                    width: `${cardW}px`,
                                                    top: '80px',
                                                    height: '30px',
                                                    backgroundColor: 'rgba(20, 20, 22, 0.75)',
                                                    pointerEvents: 'none',
                                                    zIndex: 10,
                                                }} />
                                            )}

                                            {/* Selection borders */}
                                            {isS && (
                                                <div style={{
                                                    position: 'absolute',
                                                    left: `${leftPx}px`,
                                                    width: `${cardW}px`,
                                                    top: 0,
                                                    height: '110px',
                                                    border: isSelected ? '2px solid #3b82f6' : '1px solid rgba(255,255,255,0.25)',
                                                    pointerEvents: 'none',
                                                    boxSizing: 'border-box',
                                                    borderRadius: '4px',
                                                    zIndex: 20,
                                                }} />
                                            )}

                                            {/* Clip Label */}
                                            <div style={{
                                                position: 'absolute',
                                                top: '6px',
                                                left: `${leftPx + 8}px`,
                                                backgroundColor: 'rgba(15,15,20,0.7)',
                                                padding: '2px 6px',
                                                borderRadius: '4px',
                                                fontSize: '10px',
                                                color: isS ? '#f8fafc' : '#94a3b8',
                                                fontFamily: 'sans-serif',
                                                pointerEvents: 'none',
                                                border: '1px solid rgba(255,255,255,0.08)',
                                                zIndex: 30,
                                                display: 'flex',
                                                gap: '4px',
                                                alignItems: 'center',
                                            }}>
                                                <span style={{ fontWeight: 600 }}>{clip.id}</span>
                                                <span style={{ opacity: 0.6, fontSize: '9px' }}>({clip.source_video})</span>
                                            </div>
                                        </React.Fragment>
                                    );
                                });
                            })()}

                            {/* Absolute overlay of proportional boundary bars */}
                            {barsConfig.map((bar) => {
                                const barPx = bar.positionFrame * scale;
                                const visuals = getBarVisuals(bar.type);
                                
                                let containerLeft = barPx - 15;
                                let containerWidth = 30;
                                let lineStyle: React.CSSProperties = {
                                    width: '2px',
                                    height: '100%',
                                    backgroundColor: visuals.color,
                                    borderRadius: '1px',
                                    boxShadow: `0 0 8px ${visuals.color}`,
                                    position: 'absolute',
                                    left: '14px'
                                };
                                let pillLeft = '50%';
                                
                                if (bar.type === 'trim-left' || bar.type === 'boundary-left') {
                                    containerLeft = barPx - 21;
                                    containerWidth = 23;
                                    lineStyle = {
                                        width: '2px',
                                        height: '100%',
                                        backgroundColor: visuals.color,
                                        borderRadius: '1px',
                                        boxShadow: `0 0 8px ${visuals.color}`,
                                        position: 'absolute',
                                        right: '1px',
                                    };
                                    pillLeft = '10px';
                                } else if (bar.type === 'trim-right' || bar.type === 'boundary-right') {
                                    containerLeft = barPx - 2;
                                    containerWidth = 23;
                                    lineStyle = {
                                        width: '2px',
                                        height: '100%',
                                        backgroundColor: visuals.color,
                                        borderRadius: '1px',
                                        boxShadow: `0 0 8px ${visuals.color}`,
                                        position: 'absolute',
                                        left: '1px',
                                    };
                                    pillLeft = '13px';
                                }
                                
                                return (
                                    <div
                                        key={bar.id}
                                        className="pbe-bar"
                                        onMouseDown={(e) => handleBarMouseDown(bar, e)}
                                        style={{
                                            position: 'absolute',
                                            left: `${containerLeft}px`,
                                            width: `${containerWidth}px`,
                                            top: 0,
                                            height: '110px',
                                            cursor: 'ew-resize',
                                            zIndex: 50,
                                            display: 'flex',
                                            justifyContent: 'center',
                                            alignItems: 'center',
                                        }}
                                    >
                                        {/* Bar line */}
                                        <div style={lineStyle} />
                                        
                                        {/* Premium Pill drag handle */}
                                        <div style={{
                                            position: 'absolute',
                                            left: pillLeft,
                                            transform: 'translateX(-50%)',
                                            width: '18px',
                                            height: '24px',
                                            backgroundColor: '#18181b',
                                            border: `2px solid ${visuals.color}`,
                                            borderRadius: visuals.borderRadius,
                                            boxShadow: '0 4px 10px rgba(0,0,0,0.6)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            fontSize: '8px',
                                            fontWeight: 'bold',
                                            color: visuals.textColor,
                                            userSelect: 'none',
                                        }}>
                                            {visuals.label}
                                        </div>
                                    </div>
                                );
                            })}

                            {/* Playhead absolute overlay line */}
                            <div 
                                id="pbe-playhead-line"
                                style={{
                                    position: 'absolute',
                                    left: `${playheadPx}px`,
                                    top: '-4px',
                                    bottom: '-4px',
                                    width: '2px',
                                    backgroundColor: '#ef4444',
                                    zIndex: 60,
                                    pointerEvents: 'none',
                                    transition: isPlaying ? 'none' : 'left 0.1s ease-out',
                                }}
                            >
                                <div style={{
                                    width: '8px',
                                    height: '8px',
                                    backgroundColor: '#ef4444',
                                    borderRadius: '50%',
                                    position: 'absolute',
                                    top: '-4px',
                                    left: '-3px',
                                    boxShadow: '0 0 6px rgba(239,68,68,0.8)',
                                }} />
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer Section */}
                <div style={{
                    padding: '16px 20px',
                    borderTop: '1px solid #222226',
                    backgroundColor: '#16161a',
                    display: 'flex',
                    justifyContent: 'flex-end',
                    gap: '12px',
                    flexShrink: 0,
                }}>
                    <button
                        onClick={() => onOpenChange(false)}
                        style={{
                            backgroundColor: 'transparent',
                            border: '1px solid #2e2e34',
                            color: '#94a3b8',
                            fontSize: '12px',
                            fontWeight: 600,
                            padding: '8px 20px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                        }}
                    >
                        취소
                    </button>
                    <button
                        onClick={handleApply}
                        style={{
                            backgroundColor: '#22c55e',
                            border: 'none',
                            color: '#fff',
                            fontSize: '12px',
                            fontWeight: 600,
                            padding: '8px 24px',
                            borderRadius: '6px',
                            cursor: 'pointer',
                            transition: 'all 0.2s',
                            boxShadow: '0 4px 12px rgba(34,197,94,0.2)',
                        }}
                    >
                        적용하기
                    </button>
                </div>

                {/* Resize Handle */}
                <div
                    onMouseDown={handleResizeMouseDown}
                    style={{
                        position: 'absolute',
                        right: 0,
                        bottom: 0,
                        width: '20px',
                        height: '20px',
                        cursor: 'se-resize',
                        zIndex: 100,
                        display: 'flex',
                        alignItems: 'flex-end',
                        justifyContent: 'flex-end',
                        padding: '4px',
                    }}
                >
                    <svg width="10" height="10" viewBox="0 0 10 10" style={{ pointerEvents: 'none' }}>
                        <line x1="10" y1="0" x2="0" y2="10" stroke="#64748b" strokeWidth="1.5" />
                        <line x1="10" y1="4" x2="4" y2="10" stroke="#64748b" strokeWidth="1.5" />
                    </svg>
                </div>
            </div>
        </div>
    );
};

export default PrecisionBoundaryEditor;
