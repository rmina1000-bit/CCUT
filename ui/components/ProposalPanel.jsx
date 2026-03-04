/**
 * ProposalPanel.jsx
 *
 * Renders the A/B proposal generator:
 *   [Generate Proposals] button
 *   → Proposal A card  |  Proposal B card
 *   → Select A / Select B
 *
 * Rules:
 *   - Previous proposals completely discarded on new Generate
 *   - On Select: reorder fragments by proposal ID list, call onFragmentsChange once
 *   - proposals state cleared immediately after select
 */

import React, { useState, useCallback } from 'react';
import { logEvent } from '../utils/logEvent.js';

const API_BASE = 'http://localhost:8765';

export default function ProposalPanel({ fragments = [], onFragmentsChange }) {
  const [proposals,  setProposals]  = useState(null);   // {A:[ids], B:[ids]} | null
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState('');

  /* ── Generate ─────────────────────────────────────────── */
  const handleGenerate = useCallback(async () => {
    if (!fragments.length) return;

    // Discard previous proposals unconditionally
    setProposals(null);
    setError('');
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/generate-proposals`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ fragments }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }

      const data = await res.json();
      setProposals({ A: data.A, B: data.B });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [fragments]);

  /* ── Select ───────────────────────────────────────────── */
  const handleSelect = useCallback((idList) => {
    if (!idList?.length || !onFragmentsChange) return;

    const idMap = new Map(fragments.map((f) => [f.id, f]));

    // Reorder fragments by proposal id list; append any unlisted at end
    const reordered = [
      ...idList.filter((id) => idMap.has(id)).map((id) => idMap.get(id)),
      ...fragments.filter((f) => !idList.includes(f.id)),
    ];

    // Single setFragments call, proposals discarded
    onFragmentsChange(reordered);
    logEvent('PROPOSAL_SELECTED', { selected: idList === proposals?.A ? 'A' : 'B' });
    setProposals(null);
    setError('');
  }, [fragments, onFragmentsChange]);

  /* ── Helpers ──────────────────────────────────────────── */
  const previewIds = (idList) =>
    idList.slice(0, 5).join(' → ') + (idList.length > 5 ? ` … +${idList.length - 5}` : '');

  /* ── Render ───────────────────────────────────────────── */
  return (
    <div style={S.wrap}>
      <div style={S.header}>
        <span style={S.label}>Proposals</span>
        <button
          style={S.genBtn(loading || !fragments.length)}
          onClick={handleGenerate}
          disabled={loading || !fragments.length}
        >
          {loading ? '⏳ Generating…' : '⚡ Generate A/B'}
        </button>
      </div>

      {error && <div style={S.error}>{error}</div>}

      {proposals && (
        <div style={S.cards}>
          {['A', 'B'].map((key) => (
            <div key={key} style={S.card}>
              <div style={S.cardHeader}>
                <span style={S.cardLabel}>Proposal {key}</span>
                <span style={S.cardCount}>{proposals[key].length} fragments</span>
              </div>
              <div style={S.preview}>{previewIds(proposals[key])}</div>
              <button
                style={S.selectBtn}
                onClick={() => handleSelect(proposals[key])}
              >
                ✓ Select {key}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Inline styles (no external lib) ───────────────────── */
const S = {
  wrap: {
    display:       'flex',
    flexDirection: 'column',
    gap:           8,
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
  genBtn: (disabled) => ({
    padding:      '4px 10px',
    fontSize:     10,
    fontFamily:   "'Courier New', monospace",
    background:   disabled ? '#1a2030' : '#1e3a5a',
    color:        disabled ? '#4b5563' : '#38bdf8',
    border:       '1px solid',
    borderColor:  disabled ? '#2d3748' : '#2d5a8e',
    borderRadius: 3,
    cursor:       disabled ? 'not-allowed' : 'pointer',
    whiteSpace:   'nowrap',
  }),
  error: {
    fontSize:   10,
    color:      '#f87171',
    fontFamily: "'Courier New', monospace",
    padding:    '2px 0',
  },
  cards: {
    display: 'flex',
    gap:     8,
  },
  card: {
    flex:          1,
    display:       'flex',
    flexDirection: 'column',
    gap:           6,
    padding:       '8px 10px',
    background:    '#0d1117',
    border:        '1px solid #1e2a3a',
    borderRadius:  4,
    minWidth:      0,
  },
  cardHeader: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
  },
  cardLabel: {
    fontSize:   11,
    fontWeight: 'bold',
    color:      '#c8d0e0',
    fontFamily: "'Courier New', monospace",
  },
  cardCount: {
    fontSize: 9,
    color:    '#4b5563',
    fontFamily: "'Courier New', monospace",
  },
  preview: {
    fontSize:     9,
    color:        '#6b7280',
    fontFamily:   "'Courier New', monospace",
    overflow:     'hidden',
    textOverflow: 'ellipsis',
    whiteSpace:   'nowrap',
    lineHeight:   1.5,
  },
  selectBtn: {
    padding:      '4px 0',
    fontSize:     10,
    fontFamily:   "'Courier New', monospace",
    background:   '#0a1f3d',
    color:        '#38bdf8',
    border:       '1px solid #2d5a8e',
    borderRadius: 3,
    cursor:       'pointer',
    width:        '100%',
  },
};
