import React from 'react';
import ChatUI from './chat_ui.jsx';

export default function CenterPanel({ chatProps }) {
  return (
    <div style={{
      width: '100%',
      height: '100vh',
      background: '#05080f',
      borderRight: '1px solid #1e2a3a',
      display: 'flex',
      flexDirection: 'column',
      fontFamily: "'Courier New', monospace",
      color: '#c8d0e0',
    }}>
      {chatProps && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <ChatUI {...chatProps} />
        </div>
      )}
    </div>
  );
}
