/**
 * chat_ui.jsx
 * ------------
 * Simple ChatGPT-style chat UI.
 * Stub parser: 1/A/first, 2/B/second, reject, play.
 * hover_fragment_id freezes on submit.
 */

import React, { useRef, useEffect, useState } from 'react';

export default function ChatUI({ messages, input, setInput, onSend, disabled, onFileUpload, renderMode = 'all', proposals = [], onSelectProposal, videoURL }) {
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const [isDragOver, setIsDragOver] = useState(false);

  const showMessages = renderMode === 'all' || renderMode === 'messages';
  const showInput = renderMode === 'all' || renderMode === 'input';

  useEffect(() => {
    if (showMessages) {
      endRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, showMessages]);

  React.useImperativeHandle(inputRef, () => ({
    freezeHoverFragmentId: () => { },
  }));

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
      if (onFileUpload) {
        onFileUpload(file);
      } else {
        setInput(`Upload Request: ${file.name}`);
        setTimeout(() => handleSend(), 100);
      }
    }
  };

  const handlePaste = (e) => {
    if (!showInput) return;
    if (e.clipboardData?.files && e.clipboardData.files.length > 0) {
      e.preventDefault();
      const file = e.clipboardData.files[0];
      if (onFileUpload) {
        onFileUpload(file);
      } else {
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
      onPaste={handlePaste}
      style={{
        flex: showMessages ? 1 : 'none',
        display: 'flex',
        flexDirection: 'column',
        fontFamily: "Inter, Roboto, -apple-system, sans-serif",
        color: '#ececf1',
        minWidth: '260px',
        maxWidth: '800px',
        height: showMessages ? '100%' : 'auto',
        minHeight: showMessages ? '200px' : 'auto',
        margin: '0 auto',
        width: '100%',
        background: isDragOver ? '#202123' : 'transparent',
        border: isDragOver ? '2px dashed #10a37f' : 'none',
        borderRadius: '8px',
        transition: 'background 0.2s',
      }}>

      {/* Messages */}
      {showMessages && (
        <div style={{
          flex: 1,
          padding: '16px',
          overflowY: 'auto',
          background: 'transparent',
          fontSize: 14,
          lineHeight: 1.5,
          display: 'flex',
          flexDirection: 'column',
        }}>
          <div style={{ flex: 1 }} />
          {messages.map((msg, i) => (
            <div
              key={i}
              style={{
                marginBottom: 16,
                display: 'flex',
                gap: 12,
                color: msg.role === 'user' ? '#ececf1' : '#d1d5db',
              }}
            >
              <div style={{
                width: 24, height: 24, borderRadius: 2, flexShrink: 0,
                background: msg.role === 'user' ? '#5436DA' : '#10a37f',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 12, fontWeight: 'bold', color: 'white'
              }}>
                {msg.role === 'user' ? 'U' : 'AI'}
              </div>
              <div style={{ flex: 1, paddingTop: 2 }}>{msg.text}</div>
            </div>
          ))}

          {/* PROPOSALS RICH UI */}
          {proposals && proposals.length > 0 && (
            <div style={{ display: 'flex', gap: '16px', marginTop: '16px', marginBottom: '16px' }}>
              {proposals.map(p => (
                <div key={p.id} style={{ flex: 1, background: '#1e293b', borderRadius: '8px', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
                  {/* Real Video Player inside Proposal */}
                  <div style={{ height: '140px', background: '#000', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <video
                      src={videoURL}
                      controls
                      preload="metadata"
                      style={{ width: '100%', height: '100%', objectFit: 'contain', background: '#000' }}
                    />
                  </div>
                  <div style={{ padding: '12px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 'bold', color: '#10a37f' }}>{p.title}</div>
                      <div style={{ fontSize: 11, color: '#94a3b8' }}>{p.description}</div>
                    </div>
                    <button
                      onClick={() => onSelectProposal?.(p)}
                      style={{ background: '#10a37f', border: 'none', color: '#fff', padding: '6px 12px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', fontSize: 12 }}
                    >
                      {p.id} 지정
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div ref={endRef} />
        </div>
      )}

      {/* Input */}
      {showInput && (
        <div style={{
          padding: '16px',
          background: 'transparent',
        }}>
          <div style={{
            display: 'flex', gap: 8,
            background: '#40414f',
            border: '1px solid #565869',
            borderRadius: 8,
            padding: '8px 12px',
            boxShadow: '0 0 15px rgba(0,0,0,0.1)',
            alignItems: 'center'
          }}>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={disabled}
              placeholder='메시지 입력 또는 영상 드래그 앤 드롭...'
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                color: '#ececf1',
                fontSize: 14,
              }}
            />
            <button
              onClick={handleSend}
              disabled={disabled}
              style={{
                padding: '6px',
                background: disabled ? 'transparent' : '#10a37f',
                border: 'none',
                borderRadius: 4,
                color: 'white',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: disabled ? 'not-allowed' : 'pointer',
                opacity: disabled ? 0.4 : 1,
              }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M2.01 21L23 12L2.01 3L2 10L17 12L2 14L2.01 21Z" fill="currentColor" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
