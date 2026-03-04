import React, { useState } from 'react';
import { LayoutProvider } from './context/LayoutContext.js';
import { VideoProvider } from './context/VideoContext.js';
import MainLayout from './layout/MainLayout.jsx';

export default function App() {
  const [fragments, setFragments] = useState([]);

  return (
    <LayoutProvider>
      <VideoProvider>
        <MainLayout fragments={fragments} onFragments={setFragments} />
      </VideoProvider>
    </LayoutProvider>
  );
}
