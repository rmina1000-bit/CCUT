/**
 * right_panel.jsx
 * --------------
 * UI-RIGHT-01 Implementation
 * 1단: 원본 인지 파노라마 (12%) - 고정 (position: sticky)
 * 2단: 편집 구조 박스 (68%) - A B C D ... (스크롤 가능)
 * 3단: 보드 (20%) - 보류 공간 (자유 배치)
 */

import React, { useEffect, useRef, useCallback, useState } from 'react';
import { useVideo } from './context/VideoContext';
import { usePanoramaEngine } from './panorama_engine.js';
import ChatUI from './chat_ui.jsx';
import './right_panel.css';

export default function RightPanel({ isEditing, selectedProposal, fragments, onFragmentsChange, chatProps }) {
  const { videoRef, videoURL } = useVideo();
  const {
    originalFragments,
    editStructure,
    boardFragments,
    selectedIds,
    initialize,
    moveToBoard,
    restoreFromBoard,
    toggleSelect,
    applyProposal,
    moveFragment,
    insertFromBoard
  } = usePanoramaEngine(fragments || []);

  // Sync back to parent (if needed for API commit)
  useEffect(() => {
    onFragmentsChange?.(editStructure);
  }, [editStructure, onFragmentsChange]);

  // Handle initialization with Selected Proposal
  useEffect(() => {
    if (isEditing && selectedProposal) {
      applyProposal(selectedProposal.fragments); // filter edits to match proposal
    }
  }, [isEditing, selectedProposal, applyProposal]);

  const [hoverState, setHoverState] = useState({ id: null, tier: null });
  const [hasShownBoardMsg, setHasShownBoardMsg] = useState(false);
  const [boardPositions, setBoardPositions] = useState({});
  const hoverTimerRef = useRef(null);

  const handleHoverTier1 = useCallback((e, frag) => {
    clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      setHoverState({ id: frag.id, tier: 1 });
    }, 60);
  }, []);

  const handleHoverTier2 = useCallback((e, frag) => {
    clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      setHoverState({ id: frag.id, tier: 2 });
    }, 60);
  }, []);

  const handleHoverTier3 = useCallback((e, frag) => {
    clearTimeout(hoverTimerRef.current);
    hoverTimerRef.current = setTimeout(() => {
      setHoverState({ id: frag.id, tier: 3 });

      // Send chat message only once
      if (!hasShownBoardMsg && chatProps?.onBotMessage) {
        chatProps.onBotMessage('이 조각은 다시 보드에서 꺼내야 편집할 수 있습니다.');
        setHasShownBoardMsg(true);
      }
    }, 60);
  }, [hasShownBoardMsg, chatProps]);

  const handleLeave = useCallback((e, frag) => {
    clearTimeout(hoverTimerRef.current);
    setHoverState({ id: null, tier: null });
  }, []);

  const handleDragStart = (e, fragId, fromBoard = false, index = null) => {
    e.dataTransfer.setData('text/plain', fragId);
    e.dataTransfer.setData('source', fromBoard ? 'board' : 'edit');
    if (index !== null) {
      e.dataTransfer.setData('index', index);
    }
  };

  const handleDropOnBoard = (e) => {
    e.preventDefault();
    const fragId = parseInt(e.dataTransfer.getData('text/plain'), 10);
    const source = e.dataTransfer.getData('source');

    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left - 60; // offset center of 120px card
    const y = e.clientY - rect.top - 16;  // offset center of 32px card

    setBoardPositions(prev => ({ ...prev, [fragId]: { left: x, top: y } }));

    if (source === 'edit') {
      moveToBoard([fragId]);
    }
  };

  const handleDropOnEdit = (e, toIndex) => {
    e.preventDefault();
    e.stopPropagation();
    const fragId = parseInt(e.dataTransfer.getData('text/plain'), 10);
    const source = e.dataTransfer.getData('source');
    const dragIndex = parseInt(e.dataTransfer.getData('index'), 10);

    if (source === 'board') {
      insertFromBoard(fragId, toIndex);
    } else if (source === 'edit') {
      if (!isNaN(dragIndex) && dragIndex !== toIndex) {
        // Adjust toIndex if we are dragging from before to after
        const finalTargetIndex = toIndex > dragIndex ? toIndex - 1 : toIndex;
        moveFragment(dragIndex, finalTargetIndex);
      }
    }
  };

  const handleContainerDrop = (e) => {
    e.preventDefault();
    if (e.target.className.includes('panorama-tier2')) {
      handleDropOnEdit(e, editStructure.length);
    }
  };

  // Tier 1 Original Panorama Scrolling
  const tier1Ref = useRef(null);
  const scrollPanorama = (dir) => {
    if (tier1Ref.current) {
      tier1Ref.current.scrollBy({ left: dir * 300, behavior: 'smooth' });
    }
  };

  return (
    <div className="right-panel-container">
      {/* Hidden Video Engine */}
      <video
        ref={videoRef}
        src={videoURL}
        preload="metadata"
        muted
        playsInline
        style={{ width: '100%', maxHeight: '0px', visibility: 'hidden', position: 'absolute' }}
      />

      {isEditing ? (
        <>
          {/* 1단 - 원본 인지 파노라마 (18%) 고정 */}
          <div className="panorama-tier1" ref={tier1Ref}>
            <div className="panorama-scroll-btn left" onClick={() => scrollPanorama(-1)}>&lt;</div>
            {originalFragments.map((frag) => {
              const duration = frag.duration || Math.max(1, frag.end - frag.start);
              const baseWidth = Math.max(100, duration * 30); // scale factor matched with tier 2
              const isDirectHover = hoverState.id === frag.id && hoverState.tier === 1;
              const isLinkedHover = hoverState.id === frag.id && (hoverState.tier === 2 || hoverState.tier === 3);
              const width = isDirectHover ? baseWidth * 1.6 : baseWidth;

              let hoverClass = '';
              if (isDirectHover) hoverClass = 'hover-active';
              if (isLinkedHover) hoverClass = 'linked-active';

              return (
                <div
                  key={`orig-${frag.id}`}
                  className={`panorama-bar ${hoverClass}`}
                  style={{ width: `${width}px`, minWidth: `${width}px`, position: 'relative', overflow: 'hidden' }}
                  onMouseEnter={(e) => handleHoverTier1(e, frag)}
                  onMouseLeave={(e) => handleLeave(e, frag)}
                >
                  {isDirectHover && videoURL && (
                    <video
                      src={`${videoURL}#t=${frag.start}`}
                      autoPlay
                      muted
                      loop
                      onLoadedMetadata={(e) => { e.target.currentTime = frag.start; e.target.play().catch(() => { }); }}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'absolute', top: 0, left: 0, opacity: 0.5 }}
                    />
                  )}
                  <span style={{ position: 'relative', zIndex: 2 }}>{frag.id}</span>
                </div>
              );
            })}
            <div className="panorama-scroll-btn right" onClick={() => scrollPanorama(1)}>&gt;</div>
          </div>

          {/* 2단 - 편집 구조 박스 (62%, 채팅 있으면 42%) 스크롤 영역 */}
          <div
            className="panorama-tier2"
            style={{ height: chatProps ? '42%' : '62%' }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleContainerDrop}
          >
            {editStructure.map((frag, idx) => {
              const isSelected = selectedIds.includes(frag.id);
              const isActive = hoverState.id === frag.id && hoverState.tier === 2;
              const isLinkedActive = hoverState.id === frag.id && hoverState.tier === 1;

              // Make edit fragments proportional to duration to visually distinguish length
              const duration = frag.duration || Math.max(1, frag.end - frag.start);
              const baseWidth = Math.max(100, duration * 30); // scale factor for tier 2
              const cardWidth = isActive ? baseWidth * 1.6 : baseWidth;

              const combinedClasses = `edit-fragment-card ${isSelected ? 'selected' : ''} ${isActive ? 'hover-active' : ''} ${isLinkedActive ? 'linked-active' : ''}`.trim();

              return (
                <React.Fragment key={`edit-group-${frag.id}-${idx}`}>
                  <div
                    className={combinedClasses}
                    style={{ width: `${cardWidth}px`, flexShrink: 0 }}
                    draggable
                    onDragStart={(e) => handleDragStart(e, frag.id, false, idx)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => handleDropOnEdit(e, idx)}
                    onMouseEnter={(e) => handleHoverTier2(e, frag)}
                    onMouseLeave={(e) => handleLeave(e, frag)}
                    onClick={(e) => toggleSelect(frag.id, e.shiftKey)}
                  >
                    {isActive && videoURL && (
                      <video
                        src={`${videoURL}#t=${frag.start}`}
                        autoPlay
                        muted
                        loop
                        onLoadedMetadata={(e) => { e.target.currentTime = frag.start; e.target.play().catch(() => { }); }}
                        style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'absolute', top: 0, left: 0, opacity: 0.5 }}
                      />
                    )}
                    <div style={{ fontWeight: 'bold', position: 'relative', zIndex: 2 }}>{frag.id}</div>
                    <div style={{ fontSize: 9, color: '#6b7280', marginTop: 4, position: 'relative', zIndex: 2 }}>
                      {parseFloat(frag.start).toFixed(1)}s – {parseFloat(frag.end).toFixed(1)}s
                    </div>
                    <div className="edit-fragment-edge left" onMouseDown={(e) => { e.stopPropagation(); /* resize logic */ }} />
                    <div className="edit-fragment-edge right" onMouseDown={(e) => { e.stopPropagation(); /* resize logic */ }} />
                  </div>
                  {idx < editStructure.length - 1 && (
                    <div
                      className="fragment-divider"
                      onDragOver={(e) => e.preventDefault()}
                      onDrop={(e) => handleDropOnEdit(e, idx + 1)}
                      onMouseDown={(e) => { e.stopPropagation(); /* ratio adj */ }}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>

          {/* 3단 - 보드 (항상 20% 정도 고정, 채팅창이 와도 렌더링 유지) */}
          <div
            className="panorama-tier3"
            style={{ height: '20%', minHeight: '120px', flexShrink: 0 }}
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDropOnBoard}
          >
            <div className="board-label">Board</div>
            {boardFragments.length === 0 && (
              <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', fontSize: 11, color: '#4b5563' }}>
                보류할 조각을 이곳으로 드래그
              </div>
            )}
            {boardFragments.map((frag, idx) => {
              const isActive = hoverState.id === frag.id && hoverState.tier === 3;
              const isLinkedActive = hoverState.id === frag.id && hoverState.tier === 1;
              const pos = boardPositions[frag.id] || { top: 20 + (idx * 10), left: 10 + (idx * 130) };
              const combinedClasses = `board-fragment-card ${isActive ? 'hover-active' : ''} ${isLinkedActive ? 'linked-active' : ''}`.trim();

              return (
                <div
                  key={`board-${frag.id}`}
                  className={combinedClasses}
                  draggable
                  onDragStart={(e) => handleDragStart(e, frag.id, true)}
                  onMouseEnter={(e) => handleHoverTier3(e, frag)}
                  onMouseLeave={(e) => handleLeave(e, frag)}
                  style={{ top: pos.top, left: pos.left }} // Whiteboard absolute positioning
                >
                  {isActive && videoURL && (
                    <video
                      src={`${videoURL}#t=${frag.start}`}
                      autoPlay
                      muted
                      loop
                      onLoadedMetadata={(e) => { e.target.currentTime = frag.start; e.target.play().catch(() => { }); }}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', position: 'absolute', top: 0, left: 0, opacity: 0.5 }}
                    />
                  )}
                  <span style={{ position: 'relative', zIndex: 2 }}>{frag.id} ({parseFloat(frag.start).toFixed(1)}s)</span>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <div style={{ flex: 1 }}></div>
      )}

      {/* 4단 선택적 렌더링 - 채팅 영역 (중앙이 좁아져 넘어왔을 때 보드 밑에 위치) */}
      {chatProps && (
        <div style={{
          flexShrink: 0,
          borderTop: '1px solid #1e2a3a',
          background: '#05080f',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '8px 0',
          minHeight: '200px'
        }}>
          <ChatUI {...chatProps} />
        </div>
      )}
    </div>
  );
}
