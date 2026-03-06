import React, { useState, useCallback } from 'react';
import { LayoutProvider } from './context/LayoutContext.jsx';
import { VideoProvider } from './context/VideoContext.jsx';
import MainLayout from './layout/MainLayout.jsx';

export default function App() {
  const [fragments, setFragments] = useState([]);

  const onFragmentsLoad = useCallback((newFrags) => {
    setFragments(newFrags);
  }, []);

  const onAction = useCallback(async (action) => {
    try {
      await fetch('http://localhost:8765/append-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          type: action.type,
          payload: action.payload,
        }),
      });
    } catch (e) {
      console.warn('Failed to log UI action:', e);
    }
  }, []);

  return (
    <LayoutProvider>
      <VideoProvider>
        <MainLayout fragments={fragments} onFragments={setFragments} onAction={onAction} onFragmentsLoad={onFragmentsLoad} />
      </VideoProvider>
    </LayoutProvider>
  );
}
