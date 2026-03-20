import React, { useEffect, useRef, useCallback, useState, useMemo } from 'react';
import { useVideo } from './context/VideoContext';
import { usePanoramaEngine } from './panorama_engine.js';
import ChatUI from './chat_ui.jsx';
import './right_panel.css';

const TrashIcon = () => (
  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 6h18" />
    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </svg>
);

const FragmentItem = ({ frag, focusKey, focusedKey, isDragging, isOriginal, tier, index, onFocus, onDragStart, onDragOver, onDrop, getLabel, updateStatus, videoURL, style: customStyle }) => {
  const videoRef = useRef(null);
  const duration = frag.duration || Math.max(1, frag.end - frag.start);
  const width = isOriginal ? Math.max(120, Math.min(240, duration * 45)) : 160;
  const isFocused = focusedKey === focusKey;

  // Direct playback trigger for better reliability
  const triggerPlay = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = false;
    videoRef.current.volume = 1.0;
    videoRef.current.play().catch(e => console.warn("Auto-play blocked, retrying...", e));
  };

  const triggerStop = () => {
    if (!videoRef.current) return;
    videoRef.current.muted = true;
    videoRef.current.pause();
  };

  useEffect(() => {
    if (isFocused) {
      triggerPlay();
    } else {
      triggerStop();
    }
  }, [isFocused]);

  return (
    <>
      <div
        className={`panorama-bar ${isFocused ? 'focused' : ''} ${isOriginal ? '' : 'edit-fragment-card'} ${isDragging ? 'dragging' : ''}`}
        style={{
          width: isOriginal ? `${width}px` : (isFocused ? '320px' : '160px'),
          height: isOriginal ? undefined : (isFocused ? '180px' : '90px'),
          zIndex: isFocused ? 1000000 : (isDragging ? 5 : 1),
          transform: isFocused ? 'scale(2.2) translateY(-15%)' : 'scale(1.0)',
          transition: 'transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s',
          aspectRatio: '16/9',
          ...(isFocused ? {
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.8), 0 0 0 4000px rgba(0,0,0,0.5)',
          } : {}),
          ...customStyle
        }}
        draggable
        onDragStart={(e) => onDragStart(e, frag, tier, index)}
        onDragOver={(e) => onDragOver(e)}
        onDrop={(e) => onDrop(e, index)}
        onMouseDown={(e) => {
          if (videoRef.current) {
            videoRef.current.muted = false;
            videoRef.current.volume = 0;
          }
        }}
        onClick={(e) => {
          e.stopPropagation();
          const willFocus = focusedKey !== focusKey;
          onFocus(focusKey);
          if (willFocus) {
            triggerPlay();
          }
        }}
      >
        <video
          key={isFocused ? `playing-${frag.id}` : `static-${frag.id}`}
          ref={videoRef}
          src={`${frag.src || videoURL}#t=${frag.start}`}
          loop
          playsInline
          preload="auto"
          onLoadedMetadata={(e) => {
            e.target.currentTime = frag.start;
            if (isFocused) {
              e.target.play().catch(err => console.error("Immediate play failed:", err));
            }
          }}
          style={{
            width: '100%',
            height: '100%',
            objectFit: isFocused ? 'contain' : 'cover',
            background: isFocused ? '#000' : 'transparent'
          }}
        />
        <div className="fragment-label">
          <span>{getLabel(frag.id)}</span>
          <span>{duration.toFixed(1)}s</span>
        </div>
        {frag.status && (
          <div className={`status-badge status-${frag.status}`}>
            {frag.status.charAt(0).toUpperCase()}
          </div>
        )}
        <div className="status-controls">
          <button onClick={(e) => { e.stopPropagation(); updateStatus?.(frag.id, 'keep'); }} className="status-btn keep">K</button>
          <button onClick={(e) => { e.stopPropagation(); updateStatus?.(frag.id, 'hold'); }} className="status-btn hold">H</button>
          <button onClick={(e) => { e.stopPropagation(); updateStatus?.(frag.id, 'discard'); }} className="status-btn discard">D</button>
        </div>
      </div>
    </>
  );
};

export default function RightPanel({ sources, fragments, selectedFragments, onFragmentsChange, chatProps }) {
  const { videoURL } = useVideo();
  const engine = usePanoramaEngine(fragments || [], selectedFragments || []);
  const {
    originalFragments = [],
    editStructure = [],
    boardFragments = [],
    updateFragmentStatus,
    removeFragment,
    moveFragment,
    insertFromOriginal,
    insertFromBoard,
    moveToBoard
  } = engine || {};

  const [focusedKey, setFocusedKey] = useState(null);
  const [draggingItem, setDraggingItem] = useState(null);
  const [isOverTrash, setIsOverTrash] = useState(false);

  useEffect(() => {
    onFragmentsChange?.(editStructure);
  }, [editStructure, onFragmentsChange]);

  const sourceRows = useMemo(() => {
    const frags = originalFragments || [];
    if (!sources || sources.length === 0) {
      return [{ id: 'default', fileName: 'Source', fragments: frags }];
    }
    return sources.map(s => ({
      ...s,
      fragments: frags.filter(f => f.sourceId === s.id)
    }));
  }, [sources, originalFragments]);

  const getGlobalLabel = useCallback((fragId) => {
    const frag = originalFragments.find(f => f.id === fragId);
    if (!frag) return '??';
    const sourceIdx = sourceRows.findIndex(row => row.fragments.some(f => f.id === fragId));
    if (sourceIdx === -1) return '??';
    const prefix = String.fromCharCode(65 + sourceIdx);
    const fragIdxInSource = sourceRows[sourceIdx].fragments.findIndex(f => f.id === fragId);
    return `${prefix}${fragIdxInSource + 1}`;
  }, [originalFragments, sourceRows]);

  const handleFocus = (key) => {
    setFocusedKey(prev => (prev === key ? null : key));
  };

  const onDragStart = (e, frag, sourceTier, index) => {
    setFocusedKey(null);
    setDraggingItem({ ...frag, sourceTier, index });
    e.dataTransfer.setData('fragId', frag.id);
  };

  const onDragOver = (e) => { e.preventDefault(); };

  const onDropToTier2 = (e, hoverIndex) => {
    e.preventDefault();
    if (!draggingItem) return;
    const { id, sourceTier, index: dragIndex } = draggingItem;
    if (sourceTier === 'tier1') {
      insertFromOriginal?.(id, hoverIndex ?? editStructure.length);
    } else if (sourceTier === 'tier2') {
      if (dragIndex !== hoverIndex) {
        moveFragment?.(dragIndex, hoverIndex ?? editStructure.length);
      }
    } else if (sourceTier === 'board') {
      insertFromBoard?.(id, hoverIndex ?? editStructure.length);
    }
    setDraggingItem(null);
  };

  const onDropToBoard = (e) => {
    e.preventDefault();
    if (!draggingItem) return;
    const { id, sourceTier } = draggingItem;
    if (sourceTier === 'tier2') moveToBoard?.([id]);
    setDraggingItem(null);
  };

  const onDropToTrash = (e) => {
    e.preventDefault();
    setIsOverTrash(false);
    if (!draggingItem) return;
    const { id } = draggingItem;
    removeFragment?.(id);
    setDraggingItem(null);
  };

  return (
    <div className="right-panel-container" onClick={() => setFocusedKey(null)}>
      <div className="panorama-tier1-wrapper">
        <div className="right-panel-label">Sources</div>
        {sourceRows.map((row) => (
          <div key={row.id} className="panorama-source-row">
            <div className="source-header"><span>{row.fileName}</span></div>
            <div className="panorama-row-scroller">
              {row.fragments.map((f, i) => (
                <FragmentItem
                  key={`t1-${f.id}`}
                  frag={f}
                  focusKey={`tier1-${f.id}`}
                  focusedKey={focusedKey}
                  isOriginal={true}
                  tier="tier1"
                  index={i}
                  isDragging={draggingItem?.id === f.id}
                  onFocus={handleFocus}
                  onDragStart={onDragStart}
                  onDragOver={onDragOver}
                  onDrop={() => { }}
                  getLabel={getGlobalLabel}
                  updateStatus={updateFragmentStatus}
                  videoURL={videoURL}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="panorama-tier2" onDragOver={onDragOver} onDrop={(e) => onDropToTier2(e, editStructure.length)}>
        <div className="right-panel-label">Proposal Structure</div>
        {editStructure.length === 0 ? <div className="empty-zone">Drag fragments here.</div> :
          editStructure.map((f, i) => (
            <FragmentItem
              key={`t2-${f.id}-${i}`}
              frag={f}
              focusKey={`tier2-${f.id}-${i}`}
              focusedKey={focusedKey}
              isOriginal={false}
              tier="tier2"
              index={i}
              isDragging={draggingItem?.id === f.id}
              onFocus={handleFocus}
              onDragStart={onDragStart}
              onDragOver={onDragOver}
              onDrop={onDropToTier2}
              getLabel={getGlobalLabel}
              updateStatus={updateFragmentStatus}
              videoURL={videoURL}
            />
          ))
        }
      </div>

      <div className="panorama-tier3">
        <div className="right-panel-label">Board / Decision Area</div>
        <div className="board-fragments-area" onDragOver={onDragOver} onDrop={onDropToBoard}>
          {boardFragments.map((f, i) => (
            <FragmentItem
              key={`board-${f.id}`}
              frag={f}
              focusKey={`board-${f.id}`}
              focusedKey={focusedKey}
              isOriginal={false}
              tier="board"
              index={i}
              isDragging={draggingItem?.id === f.id}
              onFocus={handleFocus}
              onDragStart={onDragStart}
              onDragOver={onDragOver}
              onDrop={() => { }}
              getLabel={getGlobalLabel}
              updateStatus={updateFragmentStatus}
              videoURL={videoURL}
              style={{
                transform: `rotate(${(i % 2 === 0 ? 1 : -1) * 2}deg)`,
                boxShadow: draggingItem?.id === f.id ? '0 10px 20px rgba(0,0,0,0.6)' : '0 4px 6px rgba(0,0,0,0.4)',
                opacity: draggingItem?.id === f.id ? 0.6 : 1
              }}
            />
          ))}
          {boardFragments.length === 0 && <div className="board-placeholder">Hold fragments here.</div>}
        </div>
        <div
          className={`trash-zone ${isOverTrash ? 'pulse' : ''}`}
          onDragOver={onDragOver}
          onDragEnter={() => setIsOverTrash(true)}
          onDragLeave={() => setIsOverTrash(false)}
          onDrop={onDropToTrash}
          style={isOverTrash ? { borderColor: '#ef4444', color: '#ef4444', transform: 'scale(1.15)', background: 'rgba(239, 68, 68, 0.15)' } : {}}
        >
          <TrashIcon />
          <span>Trash</span>
        </div>
      </div>

      {chatProps && <div className="bottom-chat-layer"><ChatUI {...chatProps} /></div>}
    </div>
  );
}
