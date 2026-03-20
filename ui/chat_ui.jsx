import React, { useRef, useEffect, useState, useMemo } from 'react';
import CognitiveFX from './vfx/CognitiveFX.jsx';

function ProposalVideoPlayer({ videoURL, fragmentIds, sourceFragments, onPlay, onPause, style }) {
  const playerRef = useRef(null);

  const segments = useMemo(() => {
    if (Array.isArray(fragmentIds) && typeof fragmentIds[0] === 'object') return fragmentIds;
    if (!sourceFragments || !fragmentIds) return [];
    return fragmentIds.map(id => sourceFragments.find(f => f.id === id || f.label === id)).filter(Boolean);
  }, [fragmentIds, sourceFragments]);

  const totalDuration = useMemo(() => segments.reduce((acc, seg) => acc + ((seg.end || 0) - (seg.start || 0)), 0), [segments]);

  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [globalTime, setGlobalTime] = useState(0);
  const [currentFX, setCurrentFX] = useState(null);

  const prevSegmentsRef = useRef([]);

  useEffect(() => {
    if (JSON.stringify(segments.map(s => s.id)) !== JSON.stringify(prevSegmentsRef.current.map(s => s.id))) {
      setCurrentIndex(0);
      setGlobalTime(0);
      setIsPlaying(false);
      prevSegmentsRef.current = segments;

      if (segments.length > 0 && playerRef.current) {
        playerRef.current.currentTime = segments[0].start || 0;
        playerRef.current.pause();
      }
    }
  }, [segments]);

  useEffect(() => {
    const activeSeg = segments[currentIndex];
    if (!activeSeg) return;
    if (activeSeg.fx !== currentFX) setCurrentFX(activeSeg.fx || null);
  }, [currentIndex, segments, currentFX]);

  useEffect(() => {
    const activeVideo = playerRef.current;
    if (!activeVideo || segments.length === 0) return;

    let rafId;

    const checkTime = () => {
      const activeSeg = segments[currentIndex];
      if (!activeSeg) return;

      let timeBefore = 0;
      for (let i = 0; i < currentIndex; i++) {
        timeBefore += ((segments[i].end || 0) - (segments[i].start || 0));
      }
      const timeInSeg = Math.max(0, activeVideo.currentTime - (activeSeg.start || 0));
      setGlobalTime(timeBefore + timeInSeg);

      if (activeVideo.currentTime >= (activeSeg.end || 0) && activeVideo.currentTime > 0) {
        if (currentIndex + 1 < segments.length) {
          setCurrentIndex(currentIndex + 1);
        } else {
          activeVideo.pause();
          setIsPlaying(false);
          onPause?.();
          return;
        }
      }

      if (isPlaying) {
        rafId = requestAnimationFrame(checkTime);
      }
    };

    if (isPlaying) rafId = requestAnimationFrame(checkTime);

    return () => cancelAnimationFrame(rafId);
  }, [currentIndex, segments, isPlaying, onPause]);

  useEffect(() => {
    const activeSeg = segments[currentIndex];
    if (!activeSeg || !playerRef.current) return;

    const expectedTime = activeSeg.start || 0;
    const currentSrc = playerRef.current.getAttribute('src');
    const newSrc = activeSeg.src || videoURL;

    const handleLoadedMetadata = () => {
      playerRef.current.currentTime = expectedTime;
      if (isPlaying) playerRef.current.play().catch(() => { });
    };

    if (currentSrc !== newSrc) {
      playerRef.current.pause();
      playerRef.current.setAttribute('src', newSrc);
      playerRef.current.load();
      playerRef.current.addEventListener('loadedmetadata', handleLoadedMetadata, { once: true });
    } else {
      if (Math.abs(playerRef.current.currentTime - expectedTime) > 0.5) {
        playerRef.current.currentTime = expectedTime;
      }
      if (isPlaying) playerRef.current.play().catch(() => { });
    }

    return () => playerRef.current?.removeEventListener('loadedmetadata', handleLoadedMetadata);
  }, [currentIndex, segments, isPlaying, videoURL]);

  const togglePlay = () => {
    const activeVideo = playerRef.current;
    if (!activeVideo || segments.length === 0) return;

    if (isPlaying) {
      activeVideo.pause();
      setIsPlaying(false);
      onPause?.();
    } else {
      if (currentIndex === segments.length - 1 && activeVideo.currentTime >= (segments[currentIndex].end || 0) - 0.1) {
        setCurrentIndex(0);
        if (activeVideo.getAttribute('src') === (segments[0].src || videoURL)) {
          activeVideo.currentTime = segments[0].start || 0;
          activeVideo.play().catch(() => { });
        }
      } else {
        activeVideo.play().catch(() => { });
      }
      setIsPlaying(true);
      onPlay?.();
    }
  };

  const handleGlobalSeek = (e) => {
    const seekVal = parseFloat(e.target.value);
    setGlobalTime(seekVal);

    let accumulated = 0;
    let targetIndex = 0;
    let timeOffsetInSeg = 0;

    for (let i = 0; i < segments.length; i++) {
      const dur = (segments[i].end || 0) - (segments[i].start || 0);
      if (seekVal <= accumulated + dur) {
        targetIndex = i;
        timeOffsetInSeg = seekVal - accumulated;
        break;
      }
      accumulated += dur;
      if (i === segments.length - 1) {
        targetIndex = i;
        timeOffsetInSeg = dur;
      }
    }

    if (targetIndex !== currentIndex) {
      if (playerRef.current) playerRef.current.pause();
      setCurrentIndex(targetIndex);
    } else {
      if (playerRef.current) playerRef.current.currentTime = (segments[targetIndex]?.start || 0) + timeOffsetInSeg;
    }
  };

  const videoStyle = {
    width: '100%', height: '100%', objectFit: 'contain', background: '#000',
    position: 'absolute', top: 0, left: 0,
    willChange: 'transform', transform: 'translateZ(0)'
  };

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', display: 'flex', flexDirection: 'column' }}>
      <div onClick={togglePlay} style={{ flex: 1, position: 'relative', overflow: 'hidden', background: '#000', cursor: 'pointer', transform: 'translateZ(0)' }}>
        <CognitiveFX fx={currentFX} interactive={true} style={{ width: '100%', height: '100%' }}>
          <video ref={playerRef} preload="auto" playsInline style={{ ...videoStyle, zIndex: 1 }} />
        </CognitiveFX>
        {!isPlaying && (
          <div style={{
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            zIndex: 10, width: 60, height: 60, borderRadius: '50%', background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'rgba(255, 255, 255, 0.8)',
            backdropFilter: 'blur(2px)', pointerEvents: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.3)'
          }}>
            <svg width="32" height="32" fill="currentColor" viewBox="0 0 24 24" style={{ marginLeft: 4 }}>
              <path d="M8 5v14l11-7z" />
            </svg>
          </div>
        )}
      </div>
      {segments.length > 0 && (
        <div style={{ height: '40px', background: '#18181b', borderTop: '1px solid rgba(255,255,255,0.1)', display: 'flex', alignItems: 'center', padding: '0 12px', gap: '12px', flexShrink: 0 }}>
          <button onClick={togglePlay} style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', width: 24, height: 24, padding: 0 }}>
            {isPlaying ? (
              <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z" /></svg>
            ) : (
              <svg width="18" height="18" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
            )}
          </button>
          <input type="range" min="0" max={totalDuration} step="0.01" value={globalTime} onChange={handleGlobalSeek} style={{ flex: 1, cursor: 'pointer', accentColor: '#10a37f' }} />
          <div style={{ fontSize: 11, color: '#a1a1aa', minWidth: '60px', textAlign: 'right', fontVariantNumeric: 'tabular-nums', whiteSpace: 'nowrap', userSelect: 'none' }}>
            {globalTime.toFixed(1)}s / {totalDuration.toFixed(1)}s
          </div>
        </div>
      )}
    </div>
  );
}

export default function ChatUI({ messages, input, setInput, onSend, disabled, onFileUpload, renderMode = 'all', proposals = [], onSelectProposal, videoURL, sourceFragments, selectedProposal, selectedFragments }) {
  const [previewMode, setPreviewMode] = useState('original');
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [expandedProposalId, setExpandedProposalId] = useState(null);

  const showMessages = renderMode === 'all' || renderMode === 'messages';
  const showInput = renderMode === 'all' || renderMode === 'input';

  const prevMessagesLength = useRef(messages?.length || 0);

  useEffect(() => {
    if (showMessages && messages?.length > prevMessagesLength.current) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
      prevMessagesLength.current = messages.length;
    }
  }, [messages?.length, showMessages]);

  const handleSend = () => {
    if (!input.trim() || disabled) return;
    onSend();
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleDragOver = (e) => {
    if (!showInput) return;
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e) => {
    if (!showInput) return;
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e) => {
    if (!showInput) return;
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (onFileUpload) onFileUpload(file);
      else {
        setInput(`Upload Request: ${file.name}`);
        setTimeout(() => handleSend(), 100);
      }
    }
  };

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      style={{
        flex: showMessages ? 1 : 'none', display: 'flex', flexDirection: 'column',
        fontFamily: "Inter, Roboto, sans-serif", color: '#ececf1',
        width: '100%', maxWidth: '800px', margin: '0 auto', height: '100%',
        background: isDragOver ? '#202123' : 'transparent',
        border: isDragOver ? '2px dashed #10a37f' : 'none',
        transition: 'background 0.2s', overflow: 'hidden'
      }}
    >
      {showMessages && (
        <div style={{ flex: 1, padding: '16px 24px', overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1 }} />
          {(messages || []).map((msg, i) => {
            if (!msg || (!msg.text && !msg.actions)) return null;
            const isUser = msg.role === 'user';
            return (
              <div key={i} style={{ marginBottom: 24, display: 'flex', flexDirection: 'column', alignItems: isUser ? 'flex-end' : 'flex-start', width: '100%' }}>
                <div style={{
                  maxWidth: '85%', padding: '10px 16px', borderRadius: '15px',
                  background: isUser ? '#2b2b2f' : 'transparent', color: isUser ? '#fff' : '#d1d1d6',
                  fontSize: 15, lineHeight: 1.6, wordBreak: 'break-word'
                }}>
                  {msg.text}
                </div>
                {msg.actions && (
                  <div style={{ display: 'flex', gap: '8px', marginTop: 8 }}>
                    {msg.actions.map((action, idx) => (
                      <button key={idx} onClick={() => action.onClick()} style={{
                        background: action.primary ? '#10a37f' : '#2d2d30', border: 'none', color: 'white',
                        padding: '8px 16px', borderRadius: '8px', fontSize: 13, cursor: 'pointer', fontWeight: 500
                      }}>
                        {action.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

          {proposals && proposals.length > 0 && (
            <div style={{ display: 'flex', gap: '16px', marginTop: '16px', marginBottom: '24px' }}>
              {proposals.map(p => {
                const isExpanded = expandedProposalId === p.id;
                const isSelected = selectedProposal?.id === p.id;
                return (
                  <div key={p.id} style={{
                    flex: isExpanded ? 2 : 1, background: '#1e1e20', borderRadius: '12px', overflow: 'hidden',
                    display: 'flex', flexDirection: 'column', transition: 'all 0.3s ease',
                    boxShadow: isExpanded ? '0 10px 30px rgba(0,0,0,0.5)' : 'none'
                  }}>
                    <div style={{ width: '100%', aspectRatio: '16/9', background: '#000' }}>
                      <ProposalVideoPlayer
                        videoURL={videoURL}
                        fragmentIds={(isSelected && previewMode === 'user') ? selectedFragments : p.fragments}
                        sourceFragments={sourceFragments}
                        onPlay={() => setExpandedProposalId(p.id)}
                        onPause={() => setExpandedProposalId(null)}
                      />
                    </div>
                    <div style={{ padding: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: '#252528' }}>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 'bold', color: '#fff' }}>{isSelected ? `Selected: ${p.title}` : p.title}</div>
                        <div style={{ fontSize: 11, color: '#a1a1aa' }}>{p.description}</div>
                      </div>
                      <button onClick={() => onSelectProposal?.(p)} style={{
                        background: isSelected ? '#10a37f' : '#3f3f42', border: 'none', color: '#fff',
                        padding: '6px 12px', borderRadius: '6px', fontSize: 12, fontWeight: 'bold', cursor: 'pointer'
                      }}>
                        {isSelected ? 'ACTIVE' : `${p.id} 지정`}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
          <div ref={endRef} />
        </div>
      )}

      {showInput && (
        <div style={{ padding: '24px', background: 'transparent' }}>
          <div style={{
            display: 'flex', gap: 12, background: '#2a2a2d', border: '1px solid #3e3e42',
            borderRadius: '12px', padding: '10px 16px', alignItems: 'center', boxShadow: '0 4px 20px rgba(0,0,0,0.2)'
          }}>
            <button
              onClick={() => {
                const inputEl = document.createElement('input');
                inputEl.type = 'file';
                inputEl.accept = 'video/mp4,video/quicktime,video/webm';
                inputEl.onchange = (e) => {
                  if (e.target.files && e.target.files[0]) {
                    onFileUpload?.(e.target.files[0]);
                  }
                };
                inputEl.click();
              }}
              style={{
                background: 'transparent', border: 'none', color: '#71717a',
                cursor: 'pointer', display: 'flex', alignItems: 'center', padding: 4
              }}
              onMouseEnter={(e) => e.currentTarget.style.color = '#fff'}
              onMouseLeave={(e) => e.currentTarget.style.color = '#71717a'}
            >
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
            </button>
            <input
              ref={inputRef} type="text" value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown} disabled={disabled} placeholder='메시지 입력 또는 영상 드래그...'
              style={{ flex: 1, background: 'transparent', border: 'none', outline: 'none', color: '#fff', fontSize: 15 }}
            />
            <button onClick={handleSend} disabled={disabled} style={{
              padding: '8px', background: disabled ? 'transparent' : '#10a37f', border: 'none',
              borderRadius: '8px', color: 'white', cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.5 : 1
            }}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" /></svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
