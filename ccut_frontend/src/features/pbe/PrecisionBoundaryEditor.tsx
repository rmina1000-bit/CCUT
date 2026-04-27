import React, { useState, useRef } from 'react';
import {
    applyBoundaryAdjustments,
    applySSBoundary,
    applySNSBoundary,
    applySingleTrim,
} from './pbeBoundaryOps';
import type { Fragment } from '@/data/fragmentData';
import { getUid } from '@/lib/pbeEngine';

export interface BoundaryEditorTarget {
    clickSide: 'left' | 'right' | 'center';
    leftRealIndex: number;
    rightRealIndex: number;
}

interface PBEFragment {
    fragment_id: string;
    selection_state: string;
    start_frame: number;
    end_frame: number;
    duration: number;
    source_video: string;
    thumbnail?: any;
    [key: string]: any;
}

interface PrecisionBoundaryEditorProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    target: BoundaryEditorTarget | null;
    fragments: PBEFragment[];
    editFragments: any[];
    onApply?: (result: any) => void;
}

interface FragmentGroup {
    fragment: PBEFragment;
    frames: Array<{ frameNumber: number; thumbnailBase: string }>;
}

interface BoundaryBar {
    position: number;
    leftFragId: string;
    rightFragId: string;
    type?: 'normal' | 'S_right' | 'S_left';
}

const PrecisionBoundaryEditor: React.FC<PrecisionBoundaryEditorProps> = ({
    open,
    onOpenChange,
    fragments,
    onApply,
}) => {
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [isDraggingModal, setIsDraggingModal] = useState(false);
    const [dragState, setDragState] = useState<{
        barIndex: number;
        initialX: number;
        currentOffset: number;
    } | null>(null);
    const [barAdjustments, setBarAdjustments] = useState<Map<number, number>>(new Map());

    const modalDragStart = useRef({ x: 0, y: 0 });

    // 조각 단위로 그룹핑
    const fragmentGroups: FragmentGroup[] = fragments.map((frag) => ({
        fragment: frag,
        frames: Array.from(
            { length: frag.end_frame - frag.start_frame },
            (_, i) => ({
                frameNumber: frag.start_frame + i,
                thumbnailBase: frag.thumbnail?.thumbnail_url || frag.thumbnail || '',
            })
        ).filter((f) => f.thumbnailBase),
    }));

    // 비례바 생성 - 모든 조각 경계에 생성
    const bars: BoundaryBar[] = [];
    for (let i = 0; i < fragments.length - 1; i++) {
        const left = fragments[i];
        const right = fragments[i + 1];

        if (left.selection_state === 'S' && right.selection_state === 'S') {
            // S|S double bar: 2개 생성
            bars.push({
                position: i,
                leftFragId: left.fragment_id,
                rightFragId: right.fragment_id,
                type: 'S_right',  // L의 우측 trim bar
            });
            bars.push({
                position: i,
                leftFragId: left.fragment_id,
                rightFragId: right.fragment_id,
                type: 'S_left',   // R의 좌측 trim bar
            });
        } else {
            // 일반 경계: 1개
            bars.push({
                position: i,
                leftFragId: left.fragment_id,
                rightFragId: right.fragment_id,
                type: 'normal',
            });
        }
    }

    // 상세 디버깅 로그 (Hooks must be at the top)
    React.useEffect(() => {
        if (open) {
            console.log('[PBE] === DEBUGGING START ===');

            console.log('[PBE] fragments:', fragments.map((f, idx) => ({
                index: idx,
                id: f.fragment_id,
                state: f.selection_state,
                start: f.start_frame,
                end: f.end_frame,
            })));

            const pattern = fragments.map(f => f.selection_state).join(',');
            console.log('[PBE] S/N Pattern:', pattern);

            // 경계 탐지
            for (let i = 0; i < fragments.length - 1; i++) {
                const left = fragments[i];
                const right = fragments[i + 1];
                console.log(`[PBE] Boundary check ${i}: ${left.fragment_id}(${left.selection_state}) | ${right.fragment_id}(${right.selection_state})`);

                if (
                    (left.selection_state === 'S' && right.selection_state === 'N') ||
                    (left.selection_state === 'N' && right.selection_state === 'S')
                ) {
                    console.log(`  → BOUNDARY FOUND at position ${i}`);
                } else {
                    console.log(`  → No boundary`);
                }
            }

            console.log('[PBE] bars count:', bars.length);
            console.log('[PBE] bars:', bars);
            console.log('[PBE] === DEBUGGING END ===');
        }
    }, [open, fragments, bars]);

    // 비례바 위치 계산
    const calculateBarPosition = (barPosition: number): string => {
        let accumulatedWidth = 0;

        for (let i = 0; i <= barPosition; i++) {
            const group = fragmentGroups[i];
            const frameCount = group.frames.length;
            const isSelected = group.fragment.selection_state === 'S';

            const singleFrameWidth = 80;
            const frameGap = 2;
            const frameWidth = (frameCount * singleFrameWidth) + ((frameCount - 1) * frameGap);

            const padding = isSelected ? 4 : 0;
            const border = isSelected ? 6 : 0;

            accumulatedWidth += frameWidth + padding + border;

            if (i < barPosition) {
                accumulatedWidth += 4;
            }
        }

        console.log(`[PBE] Calculated bar position ${barPosition}: ${accumulatedWidth}px`);

        return `${accumulatedWidth}px`;
    };

    // 비례바 드래그 핸들러
    const handleBarMouseDown = (barIdx: number, e: React.MouseEvent) => {
        e.stopPropagation();
        console.log('[PBE] Bar drag started:', barIdx);
        setDragState({
            barIndex: barIdx,
            initialX: e.clientX,
            currentOffset: 0,
        });
    };

    const handleBarMouseMove = (e: MouseEvent) => {
        if (!dragState) return;
        const offset = e.clientX - dragState.initialX;
        setDragState({
            ...dragState,
            currentOffset: offset,
        });
    };

    const handleBarMouseUp = () => {
        if (dragState && dragState.currentOffset !== 0) {
            const frameDelta = Math.round(dragState.currentOffset / 80);
            console.log('[PBE] Bar drag ended. frameDelta:', frameDelta);
            setBarAdjustments(prev => new Map(prev).set(dragState.barIndex, frameDelta));
        }
        setDragState(null);
    };

    // 모달 드래그 핸들러
    const handleModalMouseDown = (e: React.MouseEvent) => {
        const target = e.target as HTMLElement;
        if (
            target.tagName === 'IMG' ||
            target.tagName === 'BUTTON' ||
            target.dataset.barDrag === 'true' ||
            target.closest('button')
        ) {
            return;
        }

        setIsDraggingModal(true);
        modalDragStart.current = {
            x: e.clientX - position.x,
            y: e.clientY - position.y,
        };
    };

    const handleModalMouseMove = (e: MouseEvent) => {
        if (!isDraggingModal) return;
        setPosition({
            x: e.clientX - modalDragStart.current.x,
            y: e.clientY - modalDragStart.current.y,
        });
    };

    const handleModalMouseUp = () => {
        setIsDraggingModal(false);
    };

    // Apply 핸들러
    const handleApply = () => {
        if (barAdjustments.size === 0) return;

        console.log('[PBE] === APPLY START ===');
        console.log('[PBE] fragments:', fragments.map(f => ({ id: f.fragment_id, state: f.selection_state })));
        console.log('[PBE] barAdjustments:', Array.from(barAdjustments.entries()));

        // 패턴 판정
        const pattern = fragments.map(f => f.selection_state).join('|');
        const sFrags = fragments.filter(f => f.selection_state === 'S');
        const nFrags = fragments.filter(f => f.selection_state === 'N');

        console.log('[PBE] Pattern:', pattern);
        console.log('[PBE] S count:', sFrags.length, 'N count:', nFrags.length);

        let newFragments: Fragment[] = [];
        let removedIds: string[] = [];

        // Case 1/2: Single trim
        if (fragments.length === 1) {
            const frag = fragments[0];
            const delta = barAdjustments.get(0) || 0;

            console.log('[PBE] Case: Single trim, delta:', delta);

            if (delta !== 0) {
                const side = delta > 0 ? 'right' : 'left';
                const trimFrames = Math.abs(delta);
                const result = applySingleTrim(frag as any, trimFrames, side);

                newFragments = [result.kept as any];
                if (result.trimmed) newFragments.push(result.trimmed as any);
                removedIds = result.removed;
            }
        }
        // Case 3: S|S double bar
        else if (pattern === 'S|S' && sFrags.length === 2) {
            const L = sFrags[0];
            const R = sFrags[1];

            // barAdjustments에서 a, b 추출
            // index 0: L의 우측, index 1: R의 좌측
            const aBar = barAdjustments.get(0) || 0;
            const bBar = barAdjustments.get(1) || 0;

            const a = Math.abs(aBar);
            const b = Math.abs(bBar);

            console.log('[PBE] Case: S|S double bar, a:', a, 'b:', b);

            const result = applySSBoundary(L as any, R as any, a, b);

            newFragments = [result.left as any];
            if (result.newN) newFragments.push(result.newN as any);
            newFragments.push(result.right as any);
            removedIds = result.removed;
        }
        // Case 4/5: S|N|S or S|N|N|S
        else if (sFrags.length === 2 && nFrags.length >= 1) {
            const L = sFrags[0];
            const R = sFrags[1];
            const Ns = nFrags;

            // barAdjustments에서 a, b 추출
            const aBar = barAdjustments.get(0) || 0;  // 좌측 비례바
            const bBar = barAdjustments.get(bars.length - 1) || 0;  // 우측 비례바

            const a = Math.abs(aBar);
            const b = Math.abs(bBar);

            console.log('[PBE] Case: S|N|S, a:', a, 'b:', b);

            const result = applySNSBoundary(L as any, Ns as any, R as any, a, b);

            newFragments = [result.left as any];
            if (result.leftSub) newFragments.push(result.leftSub as any);
            if (result.midRem) newFragments.push(result.midRem as any);
            if (result.rightSub) newFragments.push(result.rightSub as any);
            newFragments.push(result.right as any);
            removedIds = result.removed;
        }
        // Fallback: 기존 단순 로직
        else {
            console.warn('[PBE] Unknown pattern, using fallback logic');

            const adjustments: any[] = [];
            barAdjustments.forEach((frameDelta, barIndex) => {
                const bar = bars[barIndex];
                adjustments.push({
                    barIndex,
                    leftFragId: bar.leftFragId,
                    rightFragId: bar.rightFragId,
                    frameDelta,
                });
            });

            const result = applyBoundaryAdjustments(fragments, adjustments);
            newFragments = result.updatedFragments;
            removedIds = result.removedFragmentIds;
        }

        console.log('[PBE] newFragments:', newFragments.map(f => ({ id: f.fragment_id, state: f.selection_state, start: f.start_frame, end: f.end_frame })));
        console.log('[PBE] removedIds:', removedIds);
        console.log('[PBE] === APPLY END ===');

        if (onApply) {
            onApply({
                updatedFragments: newFragments,
                removedFragmentIds: removedIds,
            });
        }

        onOpenChange(false);
    };

    React.useEffect(() => {
        if (dragState) {
            window.addEventListener('mousemove', handleBarMouseMove);
            window.addEventListener('mouseup', handleBarMouseUp);
            return () => {
                window.removeEventListener('mousemove', handleBarMouseMove);
                window.removeEventListener('mouseup', handleBarMouseUp);
            };
        }
    }, [dragState]);

    React.useEffect(() => {
        if (isDraggingModal) {
            window.addEventListener('mousemove', handleModalMouseMove);
            window.addEventListener('mouseup', handleModalMouseUp);
            return () => {
                window.removeEventListener('mousemove', handleModalMouseMove);
                window.removeEventListener('mouseup', handleModalMouseUp);
            };
        }
    }, [isDraggingModal]);

    // Hook Order Violation Fix: Conditional return must be AFTER all hooks
    if (!open) return null;

    const hasChanges = barAdjustments.size > 0;

    return (
        <>
            <style>{`
        .pbe-scroll::-webkit-scrollbar {
          height: 8px;
        }
        .pbe-scroll::-webkit-scrollbar-track {
          background: #1a1a2e;
        }
        .pbe-scroll::-webkit-scrollbar-thumb {
          background: #3a3a4a;
          border-radius: 4px;
        }
        .pbe-scroll::-webkit-scrollbar-thumb:hover {
          background: #4a4a5a;
        }
        .pbe-scroll::-webkit-scrollbar-button {
          display: none !important;
          width: 0 !important;
          height: 0 !important;
        }
      `}</style>

            <div
                style={{
                    position: 'fixed',
                    top: `calc(50vh + ${position.y}px)`,
                    left: `calc(50vw + ${position.x}px)`,
                    transform: 'translate(-50%, -50%)',
                    zIndex: 100,
                    cursor: isDraggingModal ? 'grabbing' : 'grab',
                }}
                onMouseDown={handleModalMouseDown}
            >
                <div
                    style={{
                        backgroundColor: '#2a2a40',
                        border: '1px solid #3a3a4a',
                        borderRadius: '8px',
                        maxWidth: '95vw',
                        width: '1400px',
                        maxHeight: '90vh',
                        overflow: 'hidden',
                        position: 'relative',
                        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
                        display: 'flex',
                        flexDirection: 'row',
                    }}
                >
                    {/* 중앙: 프레임 strip */}
                    <div
                        style={{
                            flex: 1,
                            position: 'relative',
                            overflow: 'hidden',
                        }}
                    >
                        <div
                            className="pbe-scroll"
                            style={{
                                display: 'flex',
                                flexDirection: 'row',
                                gap: '4px',
                                overflowX: 'auto',
                                padding: '12px',
                                paddingTop: '28px',
                                height: '100%',
                                position: 'relative', // Added to allow absolute bars to scroll with content
                            }}
                        >
                            {fragmentGroups.map((group) => {
                                const isSelected = group.fragment.selection_state === 'S';

                                return (
                                    <div
                                        key={group.fragment.fragment_id}
                                        style={{
                                            display: 'flex',
                                            flexDirection: 'row',
                                            gap: '2px',
                                            border: isSelected ? '3px solid rgba(255, 255, 255, 0.8)' : 'none',
                                            padding: isSelected ? '2px' : '0',
                                            opacity: isSelected ? 1 : 0.4,
                                            borderRadius: '4px',
                                            position: 'relative',
                                        }}
                                    >
                                        {/* 조각 명칭 */}
                                        <div
                                            style={{
                                                position: 'absolute',
                                                top: '-20px',
                                                left: '2px',
                                                fontSize: '11px',
                                                color: isSelected ? '#fff' : '#888',
                                                fontWeight: isSelected ? 'bold' : 'normal',
                                                whiteSpace: 'nowrap',
                                            }}
                                        >
                                            {group.fragment.display_id || group.fragment.fragment_id}
                                        </div>

                                        {/* 프레임들 */}
                                        {group.frames.map((frame, idx) => (
                                            <img
                                                key={`${group.fragment.fragment_id}-${frame.frameNumber}-${idx}`}
                                                src={`${frame.thumbnailBase}/frame_${frame.frameNumber}.jpg`}
                                                alt=""
                                                style={{
                                                    width: '80px',
                                                    height: '80px',
                                                    objectFit: 'cover',
                                                    flexShrink: 0,
                                                    border: '1px solid #333',
                                                    cursor: 'default',
                                                }}
                                                onError={(e) => {
                                                    (e.target as HTMLImageElement).style.backgroundColor = '#2a2a3e';
                                                    (e.target as HTMLImageElement).style.border = '1px solid #555';
                                                }}
                                            />
                                        ))}
                                    </div>
                                );
                            })}

                            {/* 비례바 오버레이 - Moved inside scrollable div */}
                            {bars.map((bar, barIdx) => {
                                const basePosition = calculateBarPosition(bar.position);
                                const isDraggingThisBar = dragState?.barIndex === barIdx;
                                const adjustment = barAdjustments.get(barIdx) || 0;
                                const totalOffset = isDraggingThisBar ? dragState.currentOffset : (adjustment * 80);

                                // S|S double bar offset logic
                                let typeOffset = 0;
                                if (bar.type === 'S_right') typeOffset = -10;
                                if (bar.type === 'S_left') typeOffset = 10;

                                const currentLeft = `calc(${basePosition} + ${totalOffset}px + 12px + ${typeOffset}px)`;

                                console.log(`[PBE] Rendering bar ${barIdx} at ${basePosition}, offset ${totalOffset}px, type: ${bar.type}`);

                                return (
                                    <div
                                        key={`bar-${bar.position}-${barIdx}`}
                                        data-bar-drag="true"
                                        onMouseDown={(e) => handleBarMouseDown(barIdx, e)}
                                        style={{
                                            position: 'absolute',
                                            left: currentLeft,
                                            top: '28px',
                                            width: isDraggingThisBar ? '10px' : '8px',
                                            height: 'calc(100% - 48px)',
                                            background: bar.type === 'normal' ? '#ff0000' : (bar.type === 'S_right' ? '#ff6b6b' : '#cc0000'),
                                            cursor: 'ew-resize',
                                            pointerEvents: 'auto',
                                            transition: isDraggingThisBar ? 'none' : 'all 0.1s',
                                            boxShadow: bar.type === 'normal'
                                                ? '0 0 8px rgba(255, 0, 0, 0.8)'
                                                : (bar.type === 'S_right' ? '0 0 8px rgba(255, 107, 107, 0.8)' : '0 0 8px rgba(204, 0, 0, 0.8)'),
                                            borderRadius: '2px',
                                            zIndex: 100,
                                        }}
                                    />
                                );
                            })}
                        </div>
                    </div>

                    {/* 우측 사이드바 */}
                    <div
                        style={{
                            width: '40px',
                            background: 'rgba(0, 0, 0, 0.3)',
                            position: 'relative',
                            flexShrink: 0,
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '16px',
                        }}
                    >
                        {/* X 버튼 */}
                        <button
                            onClick={() => onOpenChange(false)}
                            style={{
                                position: 'absolute',
                                top: '8px',
                                background: 'none',
                                border: 'none',
                                color: '#999',
                                fontSize: '14px',
                                cursor: 'pointer',
                                padding: '4px',
                                lineHeight: 1,
                            }}
                            onMouseEnter={(e) => {
                                e.currentTarget.style.color = '#fff';
                            }}
                            onMouseLeave={(e) => {
                                e.currentTarget.style.color = '#999';
                            }}
                        >
                            ✕
                        </button>

                        {/* OK 버튼 */}
                        <button
                            onClick={handleApply}
                            disabled={!hasChanges}
                            style={{
                                background: 'none',
                                border: 'none',
                                color: hasChanges ? '#9f9' : '#666',
                                fontSize: '14px',
                                cursor: hasChanges ? 'pointer' : 'not-allowed',
                                padding: '4px',
                                lineHeight: 1,
                                fontWeight: 'bold',
                            }}
                        >
                            OK
                        </button>
                    </div>
                </div>
            </div>
        </>
    );
};

export default PrecisionBoundaryEditor;
