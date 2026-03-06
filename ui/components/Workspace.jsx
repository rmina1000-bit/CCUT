/**
 * Workspace.jsx
 * ------------
 * CCUT Decision Workspace: fragment canvas, drag/scroll, hover preview,
 * and command input (chat).  This is where decisions happen.
 *
 * Features:
 *   - Infinite draggable/scrollable canvas
 *   - Fragment cards with thumbnails, time ranges, status (candidate/accepted/discarded)
 *   - Hover preview layer (video playback)
 *   - Bottom chat input for search/move/call commands
 *   - Log UI_ACTION/POINTER_GESTURE for audit
 *
 * Props:
 *   fragments: array of fragment objects from engine
 *   onAction: function to log UI actions to decision log
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useVideo } from '../context/VideoContext';

const CARD_W = 160;
const CARD_H = 90;
const CARD_GAP = 20;
const PREVIEW_W = 240;
const PREVIEW_H = 135;
const CMD_PLACEHOLDER = 'Search fragments, move, call…';

// Fragment status colors
const STATUS_COLORS = {
  candidate: '#1e3a5a',
  accepted: '#0d2318',
  discarded: '#3a1e1a',
};

// Simple grid layout for demo
function layoutCards(frags, viewport) {
  const cols = Math.max(1, Math.floor((viewport.width + CARD_GAP) / (CARD_W + CARD_GAP)));
  return frags.map((f, i) => ({
    x: (i % cols) * (CARD_W + CARD_GAP) + CARD_GAP,
    y: Math.floor(i / cols) * (CARD_H + CARD_GAP) + CARD_GAP,
    w: CARD_W,
    h: CARD_H,
    fragment: f,
  }));
}

export default function Workspace({ fragments = [], onAction }) {
  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [hoveredId, setHoveredId] = useState(null);
  const [hoverPos, setHoverPos] = useState({ top: 0, left: 0 });
  const [selectedId, setSelectedId] = useState(null);
  const [command, setCommand] = useState('');
  const [viewport, setViewport] = useState({ width: 800, height: 600 });

  const { hoverPlay, hoverStop } = useVideo();

  // Update viewport on resize
  useEffect(() => {
    const update = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      setViewport({ width: rect.width, height: rect.height });
    };
    update();
    const r = new ResizeObserver(update);
    r.observe(containerRef.current);
    return () => r.disconnect();
  }, []);

  // Layout fragments
  const cards = layoutCards(fragments, viewport);

  // Canvas pan (drag background)
  const onCanvasMouseDown = useCallback((e) => {
    if (e.target !== canvasRef.current) return;
    setDragging(true);
    setDragStart({ x: e.clientX - offset.x, y: e.clientY - offset.y });
    onAction?.({ type: 'UI_ACTION', payload: { action: 'canvas_pan_start', point: { x: e.clientX, y: e.clientY } } });
  }, [offset, onAction]);

  const onCanvasMouseMove = useCallback((e) => {
    if (!dragging) return;
    setOffset({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  }, [dragging, dragStart]);

  const onCanvasMouseUp = useCallback(() => {
    if (dragging) {
      onAction?.({ type: 'UI_ACTION', payload: { action: 'canvas_pan_end', offset } });
      setDragging(false);
    }
  }, [dragging, offset, onAction]);

  // Fragment interactions
  const onFragmentClick = useCallback((frag, e) => {
    setSelectedId(frag.id === selectedId ? null : frag.id);
    onAction?.({ type: 'POINTER_GESTURE', payload: { action: 'fragment_select', fragment_id: frag.id, point: { x: e.clientX, y: e.clientY } } });
  }, [selectedId, onAction]);

  const onFragmentHover = useCallback((frag, e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    setHoveredId(frag.id);
    setHoverPos({
      top: Math.max(8, rect.top - PREVIEW_H - 8),
      left: Math.max(8, Math.min(rect.left + rect.width / 2 - PREVIEW_W / 2, window.innerWidth - PREVIEW_W - 8)),
    });
    // Trigger video preview (requires src attribute on fragment)
    if (frag.src) {
      hoverPlay(frag.id, frag.src, frag.start || 0, rect);
    }
    onAction?.({ type: 'POINTER_GESTURE', payload: { action: 'fragment_hover', fragment_id: frag.id, point: { x: e.clientX, y: e.clientY } } });
  }, [hoverPlay, onAction]);

  const onFragmentLeave = useCallback((frag) => {
    setHoveredId(null);
    hoverStop(frag.id);
    onAction?.({ type: 'POINTER_GESTURE', payload: { action: 'fragment_unhover', fragment_id: frag.id } });
  }, [hoverStop, onAction]);

  // Command input
  const onCommandSubmit = useCallback((e) => {
    e.preventDefault();
    if (!command.trim()) return;
    onAction?.({ type: 'UI_ACTION', payload: { action: 'workspace_command', command } });
    // TODO: parse command (search/move/call) and apply
    setCommand('');
  }, [command, onAction]);

  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        height: '100%',
        overflow: 'hidden',
        background: '#05080f',
        cursor: dragging ? 'grabbing' : 'grab',
      }}
      onMouseMove={onCanvasMouseMove}
      onMouseUp={onCanvasMouseUp}
      onMouseLeave={onCanvasMouseUp}
    >
      {/* Workspace Canvas */}
      <div
        ref={canvasRef}
        style={{
          position: 'absolute',
          width: '200%',
          height: '200%',
          background: '#07090f',
          transform: `translate(${offset.x}px, ${offset.y}px)`,
          transition: dragging ? 'none' : 'transform 0.2s',
        }}
        onMouseDown={onCanvasMouseDown}
      >
        {/* Fragment Layer */}
        {cards.map((card) => (
          <div
            key={card.fragment.id}
            style={{
              position: 'absolute',
              left: card.x,
              top: card.y,
              width: card.w,
              height: card.h,
              background: STATUS_COLORS[card.fragment.status] || '#1e3a5a',
              border: selectedId === card.fragment.id ? '2px solid #38bdf8' : '1px solid #1e2a3a',
              borderRadius: 4,
              cursor: 'pointer',
              display: 'flex',
              flexDirection: 'column',
              padding: 8,
              boxSizing: 'border-box',
              opacity: hoveredId === card.fragment.id ? 0.85 : 1,
            }}
            onClick={(e) => onFragmentClick(card.fragment, e)}
            onMouseEnter={(e) => onFragmentHover(card.fragment, e)}
            onMouseLeave={() => onFragmentLeave(card.fragment)}
          >
            {/* Thumbnail placeholder */}
            <div
              style={{
                flex: 1,
                background: '#111820',
                borderRadius: 2,
                marginBottom: 6,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 10,
                color: '#374151',
              }}
            >
              {card.fragment.thumbnail ? (
                <img src={card.fragment.thumbnail} alt={card.fragment.id} style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: 2 }} />
              ) : (
                'No thumb'
              )}
            </div>
            {/* Time range */}
            <div style={{ fontSize: 9, color: '#6b7280' }}>
              {card.fragment.start}s – {card.fragment.end}s
            </div>
            {/* Fragment ID */}
            <div style={{ fontSize: 10, color: '#c8d0e0', fontWeight: 'bold' }}>
              {card.fragment.id}
            </div>
            {/* Status badge */}
            <div
              style={{
                marginTop: 4,
                fontSize: 8,
                color: card.fragment.status === 'accepted' ? '#4ade80' : card.fragment.status === 'discarded' ? '#f87171' : '#38bdf8',
                textTransform: 'uppercase',
              }}
            >
              {card.fragment.status || 'candidate'}
            </div>
          </div>
        ))}
      </div>

      {/* Hover Preview Layer (handled by VideoContext) */}

      {/* Command Input */}
      <form
        onSubmit={onCommandSubmit}
        style={{
          position: 'absolute',
          bottom: 12,
          left: 12,
          right: 12,
          display: 'flex',
          gap: 8,
        }}
      >
        <input
          type="text"
          value={command}
          onChange={(e) => setCommand(e.target.value)}
          placeholder={CMD_PLACEHOLDER}
          style={{
            flex: 1,
            background: '#0d1117',
            border: '1px solid #1e2a3a',
            borderRadius: 4,
            padding: '6px 12px',
            color: '#c8d0e0',
            fontSize: 12,
            fontFamily: "'Courier New', monospace",
          }}
        />
        <button
          type="submit"
          style={{
            background: '#0a1628',
            border: '1px solid #1e3a5a',
            borderRadius: 4,
            padding: '6px 16px',
            color: '#38bdf8',
            fontSize: 12,
            fontFamily: "'Courier New', monospace",
            cursor: 'pointer',
          }}
        >
          Run
        </button>
      </form>
    </div>
  );
}
