/**
 * DemoPanel.jsx
 * -------------
 * Demo Mode: shows the full decision_log → replay → render pipeline
 * with mock fragments — no real video required.
 *
 * Engine diff = 0.  Uses only:
 *   POST /append-event   (real engine, via logEvent)
 *   GET  /decision-log   (real engine)
 *   GET  /decision-replay (real engine)
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { logEvent } from '../utils/logEvent.js';

const API = 'http://localhost:8765';

/* ── Mock fragment catalogue ─────────────────────────────── */
const MOCK_FRAGS = [
  { id: 'F1', start: 0,  end: 5,  duration: 5  },
  { id: 'F2', start: 5,  end: 12, duration: 7  },
  { id: 'F3', start: 12, end: 20, duration: 8  },
  { id: 'F4', start: 20, end: 25, duration: 5  },
  { id: 'F5', start: 25, end: 32, duration: 7  },
];
const FRAG_MAP = Object.fromEntries(MOCK_FRAGS.map(f => [f.id, f]));

/* ── Quick action definitions ────────────────────────────── */
const ACTIONS = [
  {
    label:   '① Init Fragments',
    type:    'FRAGMENTS_GENERATED',
    payload: () => ({ count: MOCK_FRAGS.length, ids: MOCK_FRAGS.map(f => f.id) }),
    note:    'Seed the log with 5 mock fragments',
    color:   '#1e3a5a',
  },
  {
    label:   '② Reorder  F2 → Top',
    type:    'FRAGMENTS_REORDERED',
    payload: () => ({ new_order: ['F2', 'F1', 'F3', 'F4', 'F5'] }),
    note:    'Move F2 to position 0',
    color:   '#1a3a2a',
  },
  {
    label:   '③ Adjust  F1 Boundary',
    type:    'BOUNDARY_ADJUSTED',
    payload: () => ({ fragment_id: 'F1', new_start: 0, new_end: 6.5 }),
    note:    'Extend F1 end: 5 → 6.5 s',
    color:   '#3a2a1a',
  },
  {
    label:   '④ Generate Proposals',
    type:    'PROPOSAL_GENERATED',
    payload: () => ({
      A: ['F2', 'F1', 'F3'],
      B: ['F3', 'F5', 'F2', 'F1', 'F4'],
    }),
    note:    'Log A/B proposal sets',
    color:   '#2a1a3a',
  },
  {
    label:   '⑤ Select  Proposal A',
    type:    'PROPOSAL_SELECTED',
    payload: () => ({ selected: 'A' }),
    note:    'User chose Proposal A',
    color:   '#1a2a3a',
  },
];

/* ── Render plan builder (client-side, no engine call) ────── */
function buildRenderPlan(replayState) {
  const order = replayState?.order?.length
    ? replayState.order
    : MOCK_FRAGS.map(f => f.id);

  const lines = ['Render Plan:'];
  let cursor = 0;
  for (const id of order) {
    const f = FRAG_MAP[id];
    const dur = f ? f.duration : 5;
    lines.push(`  [${cursor.toFixed(1)} – ${(cursor + dur).toFixed(1)} s]  ${id}`);
    cursor += dur;
  }
  lines.push(`  Total: ${cursor.toFixed(1)} s`);
  return lines.join('\n');
}

/* ── Main component ──────────────────────────────────────── */
export default function DemoPanel() {
  const [log,         setLog]         = useState([]);
  const [replay,      setReplay]      = useState(null);
  const [renderOut,   setRenderOut]   = useState('');
  const [firing,      setFiring]      = useState(null);  // action label in-flight
  const [error,       setError]       = useState('');
  const logEndRef = useRef(null);

  /* ── Fetch helpers ───────────────────────────────────────── */
  const refreshLog = useCallback(async () => {
    try {
      const r = await fetch(`${API}/decision-log?limit=50`);
      if (r.ok) setLog(await r.json());
    } catch { /* non-blocking */ }
  }, []);

  const refreshReplay = useCallback(async () => {
    try {
      const r = await fetch(`${API}/decision-replay`);
      if (r.ok) {
        const data = await r.json();
        setReplay(data);
      }
    } catch { /* non-blocking */ }
  }, []);

  /* ── Fire a quick action ─────────────────────────────────── */
  const fireAction = useCallback(async (action) => {
    setFiring(action.label);
    setError('');
    try {
      await fetch(`${API}/append-event`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ type: action.type, payload: action.payload() }),
      });
      await Promise.all([refreshLog(), refreshReplay()]);
    } catch (e) {
      setError(e.message);
    } finally {
      setFiring(null);
    }
  }, [refreshLog, refreshReplay]);

  /* ── Undo / Redo ──────────────────────────────────────────── */
  const handleUndo = useCallback(async () => {
    setFiring('↺ Undo');
    setError('');
    try {
      const r = await fetch(`${API}/undo`, { method: 'POST' });
      if (!r.ok) throw new Error(`/undo → ${r.status}`);
      const data = await r.json();
      setReplay(data);
      await refreshLog();
    } catch (e) {
      setError(e.message);
    } finally {
      setFiring(null);
    }
  }, [refreshLog]);

  const handleRedo = useCallback(async () => {
    setFiring('↻ Redo');
    setError('');
    try {
      const r = await fetch(`${API}/redo`, { method: 'POST' });
      if (!r.ok) throw new Error(`/redo → ${r.status}`);
      const data = await r.json();
      setReplay(data);
      await refreshLog();
    } catch (e) {
      setError(e.message);
    } finally {
      setFiring(null);
    }
  }, [refreshLog]);

  /* ── Smart Render ───────────────────────────────────────────── */
  const handleRender = useCallback(async () => {
    setFiring('render');
    setError('');
    try {
      const r = await fetch(`${API}/smart-render`, { method: 'POST' });
      if (!r.ok) throw new Error(`/smart-render → ${r.status}`);
      const data = await r.json();
      const diffLine = data.diff_count === 0
        ? '  ✓ No changes — full render not needed'
        : data.full_rerender
          ? `  ⚡ Full re-render  (${data.diff_count} segments)`
          : `  ↻ Smart diff: ${data.diff_count} of ${data.plan.length} segment(s) changed`;
      setRenderOut(data.formatted + '\n\n' + diffLine);
    } catch (e) {
      setError(e.message);
    } finally {
      setFiring(null);
    }
  }, []);

  /* ── Auto-scroll log to bottom ───────────────────────────── */
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [log]);

  /* ── Initial load ────────────────────────────────────────── */
  useEffect(() => {
    refreshLog();
    refreshReplay();
  }, []);

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div style={S.root}>
      <div style={S.titleBar}>
        <span style={S.title}>⚡ DEMO MODE</span>
        <span style={S.subtitle}>decision_log → replay → render  |  engine diff = 0</span>
      </div>

      {error && <div style={S.error}>ERROR: {error}</div>}

      <div style={S.body}>

        {/* ── Mock Fragments ─────────────────────── */}
        <Section title="Mock Fragments">
          <div style={S.fragRow}>
            {MOCK_FRAGS.map(f => (
              <div key={f.id} style={S.fragChip}>
                <span style={S.fragId}>{f.id}</span>
                <span style={S.fragMeta}>{f.start}–{f.end}s</span>
              </div>
            ))}
          </div>
          <div style={S.hint}>No video required. IDs map to real engine events.</div>
        </Section>

        {/* ── Quick Actions ─────────────────────── */}
        <Section title="Quick Actions  (each fires a real /append-event)">
          <div style={S.actionGrid}>
            {ACTIONS.map(a => (
              <button
                key={a.label}
                style={S.actionBtn(a.color, firing === a.label)}
                onClick={() => fireAction(a)}
                disabled={!!firing}
              >
                <span style={S.actionLabel}>{a.label}</span>
                <span style={S.actionNote}>{a.note}</span>
              </button>
            ))}
          </div>
          <div style={S.undoRow}>
            <button
              style={S.undoBtn(firing === '↺ Undo')}
              onClick={handleUndo}
              disabled={!!firing}
              title="Step active_seq back — log unchanged"
            >
              ↺ Undo Last
            </button>
            <button
              style={S.undoBtn(firing === '↻ Redo')}
              onClick={handleRedo}
              disabled={!!firing}
              title="Step active_seq forward"
            >
              ↻ Redo
            </button>
            {replay?.undo_status && (
              <span style={S.undoStatus}>
                active: #{replay.undo_status.active_seq}
                &nbsp;/&nbsp;
                head: #{replay.undo_status.current_seq}
                &nbsp;·&nbsp;
                {replay.undo_status.can_undo ? 'can undo' : 'at start'}
                {replay.undo_status.can_redo ? '  ·  can redo' : ''}
              </span>
            )}
          </div>
        </Section>

        <div style={S.cols}>

          {/* ── Live Log Viewer ───────────────────── */}
          <div style={S.col}>
            <Section title={`Live Log  (${log.length} events)`} extra={
              <button style={S.refreshBtn} onClick={refreshLog}>↺</button>
            }>
              <div style={S.logBox}>
                {log.length === 0 && <div style={S.empty}>No events yet — fire an action above.</div>}
                {log.map(e => (
                  <div key={e.seq} style={S.logEntry}>
                    <span style={S.seq}>#{e.seq}</span>
                    <span style={S.evType}>{e.type}</span>
                    <span style={S.payload}>
                      {JSON.stringify(e.payload).slice(0, 60)}
                    </span>
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            </Section>
          </div>

          {/* ── Replay State Viewer ───────────────── */}
          <div style={S.col}>
            <Section title="Replay State" extra={
              <button style={S.refreshBtn} onClick={refreshReplay}>↺</button>
            }>
              {replay ? (
                <div style={S.replayBox}>
                  <div style={S.replayRow}>
                    <span style={S.rLabel}>last_seq</span>
                    <span style={S.rVal}>{replay.last_event_seq ?? '—'}</span>
                  </div>
                  <div style={S.replayRow}>
                    <span style={S.rLabel}>events</span>
                    <span style={S.rVal}>{replay.events_count}</span>
                  </div>
                  <div style={S.replayRow}>
                    <span style={S.rLabel}>order</span>
                    <span style={{ ...S.rVal, color: '#38bdf8' }}>
                      {replay.order?.join(' → ') || '(original)'}
                    </span>
                  </div>
                  <div style={{ marginTop: 8 }}>
                    <span style={S.rLabel}>raw state</span>
                    <pre style={S.pre}>
                      {JSON.stringify({ order: replay.order, events_count: replay.events_count, last_event_seq: replay.last_event_seq }, null, 2)}
                    </pre>
                  </div>
                </div>
              ) : (
                <div style={S.empty}>Waiting for replay data…</div>
              )}
            </Section>
          </div>

        </div>

        {/* ── Render Output ─────────────────────── */}
        <Section title="Render Plan  (derived from replay state)" extra={
          <button style={S.renderBtn} onClick={handleRender}>
            ▶ Compute Render
          </button>
        }>
          <pre style={renderOut ? S.renderOut : S.renderEmpty}>
            {renderOut || 'Press  ▶ Compute Render  to derive plan from current replay state.'}
          </pre>
        </Section>

      </div>
    </div>
  );
}

/* ── Section wrapper ─────────────────────────────────────── */
function Section({ title, children, extra }) {
  return (
    <div style={S.section}>
      <div style={S.sectionHeader}>
        <span style={S.sectionTitle}>{title}</span>
        {extra}
      </div>
      {children}
    </div>
  );
}

/* ── Styles ──────────────────────────────────────────────── */
const S = {
  root: {
    display:       'flex',
    flexDirection: 'column',
    background:    '#07090f',
    borderTop:     '2px solid #38bdf8',
    fontFamily:    "'Courier New', monospace",
    fontSize:      11,
    color:         '#c8d0e0',
    overflow:      'auto',
    maxHeight:     '70vh',
  },
  titleBar: {
    display:     'flex',
    alignItems:  'baseline',
    gap:         12,
    padding:     '8px 14px',
    background:  '#0d1117',
    borderBottom: '1px solid #1e2a3a',
    flexShrink:  0,
  },
  title: {
    fontSize:   13,
    fontWeight: 'bold',
    color:      '#38bdf8',
  },
  subtitle: {
    fontSize: 9,
    color:    '#374151',
  },
  error: {
    padding:    '4px 14px',
    background: '#1a0000',
    color:      '#f87171',
    fontSize:   10,
  },
  body: {
    display:       'flex',
    flexDirection: 'column',
    gap:           0,
  },
  section: {
    borderBottom: '1px solid #1e2a3a',
    padding:      '8px 14px',
  },
  sectionHeader: {
    display:        'flex',
    alignItems:     'center',
    justifyContent: 'space-between',
    marginBottom:   6,
  },
  sectionTitle: {
    fontSize:      9,
    color:         '#374151',
    textTransform: 'uppercase',
    letterSpacing: 1,
  },
  fragRow: {
    display:  'flex',
    flexWrap: 'wrap',
    gap:      6,
  },
  fragChip: {
    display:      'flex',
    flexDirection: 'column',
    alignItems:   'center',
    padding:      '4px 8px',
    background:   '#0d1117',
    border:       '1px solid #1e3a5a',
    borderRadius: 4,
  },
  fragId:   { fontWeight: 'bold', color: '#38bdf8', fontSize: 12 },
  fragMeta: { fontSize: 9, color: '#4b5563' },
  hint:     { marginTop: 4, fontSize: 9, color: '#374151' },
  actionGrid: {
    display:             'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))',
    gap:                 6,
  },
  actionBtn: (bg, loading) => ({
    display:       'flex',
    flexDirection: 'column',
    alignItems:    'flex-start',
    padding:       '6px 10px',
    background:    loading ? '#1a2030' : bg,
    border:        '1px solid #2d3748',
    borderRadius:  4,
    cursor:        loading ? 'wait' : 'pointer',
    opacity:       loading ? 0.6 : 1,
    textAlign:     'left',
    gap:           2,
  }),
  actionLabel: { fontSize: 11, color: '#c8d0e0', fontWeight: 'bold' },
  actionNote:  { fontSize: 9,  color: '#4b5563' },
  cols: {
    display: 'flex',
    gap:     0,
  },
  col: {
    flex:        1,
    borderRight: '1px solid #1e2a3a',
  },
  logBox: {
    maxHeight:  120,
    overflowY:  'auto',
    background: '#0d1117',
    borderRadius: 3,
    padding:    4,
  },
  logEntry: {
    display:     'flex',
    gap:         6,
    padding:     '2px 0',
    borderBottom: '1px solid #111820',
    alignItems:  'baseline',
    flexWrap:    'wrap',
  },
  seq:     { color: '#374151', minWidth: 28, fontSize: 9 },
  evType:  { color: '#38bdf8', fontSize: 10, minWidth: 160 },
  payload: { color: '#6b7280', fontSize: 9, wordBreak: 'break-all' },
  empty:   { color: '#374151', fontSize: 9, padding: '4px 0' },
  refreshBtn: {
    padding:    '2px 6px',
    fontSize:   10,
    background: '#0d1117',
    color:      '#4b5563',
    border:     '1px solid #1e2a3a',
    borderRadius: 3,
    cursor:     'pointer',
  },
  replayBox: {
    display:       'flex',
    flexDirection: 'column',
    gap:           4,
    background:    '#0d1117',
    borderRadius:  3,
    padding:       6,
  },
  replayRow: {
    display: 'flex',
    gap:     8,
    alignItems: 'baseline',
  },
  rLabel: { color: '#374151', minWidth: 70, fontSize: 9 },
  rVal:   { color: '#c8d0e0', fontSize: 10 },
  pre: {
    margin:      0,
    fontSize:    9,
    color:       '#6b7280',
    whiteSpace:  'pre-wrap',
    wordBreak:   'break-all',
    maxHeight:   80,
    overflowY:   'auto',
    background:  '#0a0d14',
    padding:     4,
    borderRadius: 2,
    marginTop:   4,
  },
  renderBtn: {
    padding:      '3px 10px',
    fontSize:     10,
    background:   '#0a1f3d',
    color:        '#38bdf8',
    border:       '1px solid #2d5a8e',
    borderRadius: 3,
    cursor:       'pointer',
  },
  renderOut: {
    margin:      0,
    fontSize:    11,
    color:       '#86efac',
    whiteSpace:  'pre',
    background:  '#020d07',
    padding:     8,
    borderRadius: 3,
    lineHeight:  1.6,
  },
  renderEmpty: {
    margin:      0,
    fontSize:    9,
    color:       '#374151',
    whiteSpace:  'pre',
    padding:     4,
  },
  undoRow: {
    display:    'flex',
    alignItems: 'center',
    gap:        8,
    marginTop:  8,
    paddingTop: 6,
    borderTop:  '1px solid #1e2a3a',
  },
  undoBtn: (active) => ({
    padding:      '4px 12px',
    fontSize:     10,
    fontFamily:   "'Courier New', monospace",
    background:   active ? '#1a2030' : '#0d1117',
    color:        active ? '#4b5563' : '#f59e0b',
    border:       '1px solid',
    borderColor:  active ? '#2d3748' : '#78350f',
    borderRadius: 3,
    cursor:       active ? 'wait' : 'pointer',
  }),
  undoStatus: {
    fontSize:  9,
    color:     '#4b5563',
    fontFamily: "'Courier New', monospace",
  },
};
