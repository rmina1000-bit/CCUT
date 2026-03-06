/**
 * fragment_interaction.js
 * ------------------------
 * Drag/resize/select/multi-select/move to board.
 * Thermal/CPU limits: max 60fps UI, 8 seeks/s hover, 30 updates/s drag.
 * Disable hover during drag/resize/preview.
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useVideo } from './context/VideoContext';

const CARD_W = 140;
const CARD_H = 70;
const CARD_GAP = 12;
const MIN_DUR = 0.5;
const DRAG_THROTTLE_MS = 1000 / 30; // 30 updates/s
const HOVER_THROTTLE_MS = 1000 / 8;  // 8 seeks/s

export default function FragmentInteraction({
  fragments,
  selectedIds = [],
  hoverId,
  disabled,
  onFragmentsChange,
  onSelect,
  onHover,
  onMoveToBoard,
  onInteraction,
}) {
  const containerRef = useRef(null);
  const [dragState, setDragState] = useState(null);
  const [resizeState, setResizeState] = useState(null);
  const [layout, setLayout] = useState([]);
  const dragThrottleRef = useRef(0);
  const hoverThrottleRef = useRef(0);

  // Layout: rows, left-to-right time flow; scale to video duration if available
  useEffect(() => {
    if (!containerRef.current) return;
    const width = containerRef.current.clientWidth;
    const cols = Math.max(1, Math.floor((width + CARD_GAP) / (CARD_W + CARD_GAP)));
    const rows = [];
    let row = [];
    fragments.forEach((frag) => {
      if (row.length >= cols) {
        rows.push(row);
        row = [];
      }
      row.push(frag);
    });
    if (row.length) rows.push(row);
    const { videoRef } = useVideo();
    const videoDuration = videoRef.current?.duration || 1;
    const totalFragDur = fragments.reduce((sum, f) => sum + (f.end - f.start), 0) || 1;
    const scale = videoDuration / totalFragDur;
    const scaledFrags = fragments.map(f => ({
      ...f,
      start: f.start * scale,
      end: f.end * scale,
    }));
    const newLayout = rows.map((rowArr, rIdx) =>
      rowArr.map((frag, cIdx) => ({
        x: cIdx * (CARD_W + CARD_GAP) + CARD_GAP,
        y: rIdx * (CARD_H + CARD_GAP) + CARD_GAP,
        w: CARD_W,
        h: CARD_H,
        fragment: scaledFrags.find(sf => sf.id === frag.id) || frag,
      }))
    ).flat();
    setLayout(newLayout);
  }, [fragments]);

  // Throttled drag update
  const updateDrag = useCallback((dx, dy) => {
    const now = performance.now();
    if (now - dragThrottleRef.current < DRAG_THROTTLE_MS) return;
    dragThrottleRef.current = now;
    setDragState(prev => prev ? { ...prev, offsetX: dx, offsetY: dy } : null);
  }, []);

  // Throttled hover seek
  const seekHover = useCallback((frag) => {
    const now = performance.now();
    if (now - hoverThrottleRef.current < HOVER_THROTTLE_MS) return;
    hoverThrottleRef.current = now;
    onHover?.(frag.id);
    const { videoRef } = useVideo();
    if (videoRef.current) {
      videoRef.current.currentTime = frag.start;
    }
  }, [onHover]);

  // Mouse move
  const handleMouseMove = useCallback((e) => {
    if (dragState) {
      const dx = e.clientX - dragState.startX;
      const dy = e.clientY - dragState.startY;
      updateDrag(dx, dy);
    } else if (resizeState) {
      const dx = e.clientX - resizeState.startX;
      const newEnd = Math.max(resizeState.start + MIN_DUR, resizeState.origEnd + dx / 40);
      onFragmentsChange(prev =>
        prev.map(f =>
          f.id === resizeState.id ? { ...f, end: newEnd } : f
        )
      );
    }
  }, [dragState, resizeState, updateDrag, onFragmentsChange]);

  // Mouse up
  const handleMouseUp = useCallback(() => {
    if (dragState) {
      // Apply drag reorder (simplified: swap positions)
      onInteraction?.(); // stop preview
    }
    setDragState(null);
    setResizeState(null);
  }, [dragState, onInteraction]);

  // Global mouse listeners
  useEffect(() => {
    if (dragState || resizeState) {
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
      return () => {
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };
    }
  }, [dragState, resizeState, handleMouseMove, handleMouseUp]);

  // Fragment click (select)
  const handleFragClick = useCallback((frag, e) => {
    e.stopPropagation();
    if (disabled) return;
    onInteraction?.(); // stop preview
    const isSelected = selectedIds.includes(frag.id);
    if (e.shiftKey && selectedIds.length) {
      // Multi-select (simplified: toggle)
      onSelect?.(
        isSelected
          ? selectedIds.filter(id => id !== frag.id)
          : [...selectedIds, frag.id]
      );
    } else {
      onSelect?.([frag.id]);
    }
  }, [disabled, selectedIds, onSelect, onInteraction]);

  // Drag start
  const handleDragStart = useCallback((frag, e) => {
    if (disabled) return;
    onInteraction?.(); // stop preview
    const { videoRef } = useVideo();
    if (videoRef.current) videoRef.current.pause();
    setDragState({
      id: frag.id,
      startX: e.clientX,
      startY: e.clientY,
      offsetX: 0,
      offsetY: 0,
    });
  }, [disabled, onInteraction]);

  // Resize start (right edge)
  const handleResizeStart = useCallback((frag, e) => {
    if (disabled) return;
    onInteraction?.(); // stop preview
    const { videoRef } = useVideo();
    if (videoRef.current) videoRef.current.pause();
    e.stopPropagation();
    setResizeState({
      id: frag.id,
      startX: e.clientX,
      start: frag.start,
      origEnd: frag.end,
    });
  }, [disabled, onInteraction]);

  // Move to board (right-click)
  const handleContextMenu = useCallback((frag, e) => {
    e.preventDefault();
    if (disabled) return;
    onMoveToBoard?.(frag.id);
  }, [disabled, onMoveToBoard]);

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        overflow: 'auto',
        background: '#0a1628',
        position: 'relative',
      }}
    >
      {layout.map((card) => {
        const isDragging = dragState?.id === card.fragment.id;
        const isHovered = hoverId === card.fragment.id;
        const isSelected = selectedIds.includes(card.fragment.id);
        return (
          <div
            key={card.fragment.id}
            style={{
              position: 'absolute',
              left: card.x + (isDragging ? dragState.offsetX : 0),
              top: card.y + (isDragging ? dragState.offsetY : 0),
              width: card.w,
              height: card.h,
              background: isSelected ? '#1e3a5a' : '#0d1117',
              border: isSelected ? '2px solid #38bdf8' : '1px solid #1e2a3a',
              borderRadius: 4,
              cursor: disabled ? 'not-allowed' : 'pointer',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
              alignItems: 'center',
              fontSize: 11,
              color: '#c8d0e0',
              opacity: disabled ? 0.4 : isHovered ? 0.85 : 1,
              transition: isDragging ? 'none' : 'all 0.15s',
              zIndex: isDragging ? 1000 : 1,
            }}
            onMouseDown={(e) => handleDragStart(card.fragment, e)}
            onClick={(e) => handleFragClick(card.fragment, e)}
            onMouseEnter={() => !disabled && seekHover(card.fragment)}
            onContextMenu={(e) => handleContextMenu(card.fragment, e)}
          >
            <div style={{ fontWeight: 'bold' }}>{card.fragment.id}</div>
            <div style={{ fontSize: 9, color: '#6b7280' }}>
              {card.fragment.start}s – {card.fragment.end}s
            </div>
            {/* Resize handle (right edge) */}
            {!disabled && (
              <div
                onMouseDown={(e) => handleResizeStart(card.fragment, e)}
                style={{
                  position: 'absolute',
                  right: 0,
                  top: 0,
                  bottom: 0,
                  width: 8,
                  cursor: 'ew-resize',
                  background: 'transparent',
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
