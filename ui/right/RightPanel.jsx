import React, { useState } from 'react';
import OriginalPanorama from './OriginalPanorama.jsx';
import EditStructureBox from './EditStructureBox.jsx';
import BoardArea from './BoardArea.jsx';
import ProposalPanel from '../components/ProposalPanel.jsx';
import DecisionSummary from '../components/DecisionSummary.jsx';
import DemoPanel from '../components/DemoPanel.jsx';
import IdentityScreen from '../components/IdentityScreen.jsx';

export default function RightPanel({ fragments = [], onFragmentsChange }) {
  const [demoOpen,     setDemoOpen]     = useState(false);
  const [identityOpen, setIdentityOpen] = useState(false);

  return (
    <div className="right-panel">
      <OriginalPanorama fragments={fragments} onFragmentsChange={onFragmentsChange} />
      <EditStructureBox initialFragments={fragments} />
      <BoardArea initialFragments={[]} />
      <ProposalPanel fragments={fragments} onFragmentsChange={onFragmentsChange} />
      <DecisionSummary />
      <div style={{ display: 'flex', gap: 6, padding: '6px 12px', borderTop: '1px solid #1e2a3a', background: '#07090f', flexShrink: 0 }}>
        <button
          onClick={() => { setIdentityOpen(v => !v); setDemoOpen(false); }}
          style={{ padding: '4px 12px', fontSize: 10, fontFamily: "'Courier New', monospace", background: identityOpen ? '#111820' : '#0d1117', color: identityOpen ? '#f1f5f9' : '#4b5563', border: '1px solid', borderColor: identityOpen ? '#374151' : '#1e2a3a', borderRadius: 3, cursor: 'pointer' }}
        >
          {identityOpen ? '▼ IDENTITY' : '▶ IDENTITY'}
        </button>
        <button
          onClick={() => { setDemoOpen(v => !v); setIdentityOpen(false); }}
          style={{ padding: '4px 12px', fontSize: 10, fontFamily: "'Courier New', monospace", background: demoOpen ? '#0a1f3d' : '#0d1117', color: demoOpen ? '#38bdf8' : '#4b5563', border: '1px solid', borderColor: demoOpen ? '#2d5a8e' : '#1e2a3a', borderRadius: 3, cursor: 'pointer' }}
        >
          {demoOpen ? '▼ DEMO MODE' : '▶ DEMO MODE'}
        </button>
      </div>
      {identityOpen && <IdentityScreen />}
      {demoOpen && <DemoPanel />}
    </div>
  );
}
