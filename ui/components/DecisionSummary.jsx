/**
 * DecisionSummary.jsx
 * -------------------
 * Displays aggregate edit decision statistics from /decision-summary.
 * Refresh is manual (button) — never blocks UI actions.
 *
 * Placed below ProposalPanel in RightPanel.
 */

import React, { useState, useCallback } from 'react';

const API_BASE = 'http://localhost:8765';

const ROW_LABELS = [
  ['total_events',         'Total Events'],
  ['fragments_generated',  'Fragments Generated'],
  ['boundary_adjustments', 'Boundary Edits'],
  ['reorders',             'Reorders'],
  ['proposals_generated',  'Proposals Generated'],
  ['proposals_selected',   'Proposals Selected'],
];

export default function DecisionSummary() {
  const [summary,  setSummary]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState('');

  const handleRefresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/decision-summary`);
      if (!res.ok) throw new Error(res.statusText);
      setSummary(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  return (
    <div style={S.wrap}>
      <div style={S.header}>
        <span style={S.label}>📜 Decision History</span>
        <button
          style={S.btn(loading)}
          onClick={handleRefresh}
          disabled={loading}
        >
          {loading ? '…' : '🔄 Refresh'}
        </button>
      </div>

      {error && <div style={S.error}>{error}</div>}

      {summary && (
        <div style={S.table}>
          {ROW_LABELS.map(([key, label]) => (
            <div key={key} style={S.row}>
              <span style={S.rowLabel}>{label}</span>
              <span style={S.rowVal}>{summary[key] ?? 0}</span>
            </div>
          ))}
          {summary.last_event_type && (
            <div style={{ ...S.row, marginTop: 4, borderTop: '1px solid #1e2a3a', paddingTop: 4 }}>
              <span style={S.rowLabel}>Last Event</span>
              <span style={{ ...S.rowVal, color: '#38bdf8', fontSize: 9 }}>
                #{summary.last_event_seq} {summary.last_event_type}
              </span>
            </div>
          )}
        </div>
      )}

      {!summary && !loading && (
        <div style={S.hint}>Press Refresh to load history</div>
      )}
    </div>
  );
}

const S = {
  wrap: {
    display:       'flex',
    flexDirection: 'column',
    gap:           6,
    padding:       '10px 12px',
    borderTop:     '1px solid #1e2a3a',
    background:    '#07090f',
    flexShrink:    0,
  },
  header: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
  },
  label: {
    fontSize:      9,
    color:         '#374151',
    textTransform: 'uppercase',
    letterSpacing: 1,
    fontFamily:    "'Courier New', monospace",
  },
  btn: (disabled) => ({
    padding:      '3px 8px',
    fontSize:     10,
    fontFamily:   "'Courier New', monospace",
    background:   disabled ? '#1a2030' : '#0d1117',
    color:        disabled ? '#4b5563' : '#6b7280',
    border:       '1px solid #1e2a3a',
    borderRadius: 3,
    cursor:       disabled ? 'not-allowed' : 'pointer',
  }),
  error: {
    fontSize: 10,
    color:    '#f87171',
    fontFamily: "'Courier New', monospace",
  },
  table: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
  },
  row: {
    display:        'flex',
    justifyContent: 'space-between',
    alignItems:     'center',
  },
  rowLabel: {
    fontSize:   10,
    color:      '#6b7280',
    fontFamily: "'Courier New', monospace",
  },
  rowVal: {
    fontSize:   10,
    fontWeight: 'bold',
    color:      '#c8d0e0',
    fontFamily: "'Courier New', monospace",
  },
  hint: {
    fontSize:   9,
    color:      '#374151',
    fontFamily: "'Courier New', monospace",
  },
};
