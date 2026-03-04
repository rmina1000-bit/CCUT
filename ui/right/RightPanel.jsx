import React from 'react';
import OriginalPanorama from './OriginalPanorama.jsx';
import EditStructureBox from './EditStructureBox.jsx';
import BoardArea from './BoardArea.jsx';
import ProposalPanel from '../components/ProposalPanel.jsx';
import DecisionSummary from '../components/DecisionSummary.jsx';

export default function RightPanel({ fragments = [], onFragmentsChange }) {
  return (
    <div className="right-panel">
      <OriginalPanorama fragments={fragments} onFragmentsChange={onFragmentsChange} />
      <EditStructureBox initialFragments={fragments} />
      <BoardArea initialFragments={[]} />
      <ProposalPanel fragments={fragments} onFragmentsChange={onFragmentsChange} />
      <DecisionSummary />
    </div>
  );
}
