/**
 * IdentityScreen.jsx
 * ------------------
 * CCUT identity surface: not a description of the engine,
 * but the engine's live state made visible.
 *
 * Data sources (real engine only — no mock):
 *   GET  /decision-log      → last 5 events
 *   GET  /decision-replay   → fragment order
 *   POST /smart-render      → diff_count
 *
 * Engine diff = 0.
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';

const API        = 'http://localhost:8765';
const POLL_MS    = 3000;

export default function IdentityScreen() {
  const [log,        setLog]        = useState([]);
  const [replay,     setReplay]     = useState(null);
  const [renderDiff, setRenderDiff] = useState(null);
  const [lastPoll,   setLastPoll]   = useState(null);
  const timerRef   = useRef(null);
  const lastSeqRef = useRef(null);   // tracks last known seq to gate smart-render

  /* ── Fetch ───────────────────────────────────────────────── */
  const fetchAll = useCallback(async () => {
    let currentSeq = null;
    try {
      const [logRes, repRes] = await Promise.all([
        fetch(`${API}/decision-log?limit=5`),
        fetch(`${API}/decision-replay`),
      ]);
      if (logRes.ok) setLog(await logRes.json());
      if (repRes.ok) {
        const repData = await repRes.json();
        setReplay(repData);
        currentSeq = repData?.last_event_seq ?? null;
      }
    } catch { /* non-blocking */ }

    // Only call smart-render when seq has actually advanced
    if (currentSeq !== null && currentSeq !== lastSeqRef.current) {
      lastSeqRef.current = currentSeq;
      try {
        const r = await fetch(`${API}/smart-render`, { method: 'POST' });
        if (r.ok) setRenderDiff(await r.json());
      } catch { /* non-blocking */ }
    }

    setLastPoll(new Date());
  }, []);

  /* ── Auto-poll ───────────────────────────────────────────── */
  useEffect(() => {
    fetchAll();
    timerRef.current = setInterval(fetchAll, POLL_MS);
    return () => clearInterval(timerRef.current);
  }, [fetchAll]);

  /* ── Derived ─────────────────────────────────────────────── */
  const fragments = replay?.order?.length
    ? replay.order
    : replay?.fragments?.map(f => f.id) ?? [];

  const lastFive = [...log].reverse().slice(0, 5);

  const pollStr = lastPoll
    ? lastPoll.toLocaleTimeString('en-GB', { hour12: false })
    : '…';

  /* ── Render ──────────────────────────────────────────────── */
  return (
    <div style={S.root}>

      {/* ── Header ─────────────────────────────────────── */}
      <div style={S.header}>
        <div style={S.brand}>CCUT</div>
        <div style={S.tagline}>
          "Not a video editor.<br />
          An event-sourced media engine."
        </div>
        <div style={S.poll}>live · {pollStr}</div>
      </div>

      <div style={S.divider} />

      {/* ── Fragment Flow ──────────────────────────────── */}
      <Section title="Fragment Flow">
        {fragments.length === 0 ? (
          <span style={S.empty}>No fragments yet — fire Init Fragments in Demo Mode</span>
        ) : (
          <div style={S.flowRow}>
            {fragments.map((id, i) => (
              <React.Fragment key={id}>
                <div style={S.fragNode}>{id}</div>
                {i < fragments.length - 1 && (
                  <span style={S.arrow}>→</span>
                )}
              </React.Fragment>
            ))}
          </div>
        )}
        {replay && (
          <div style={S.meta}>
            {replay.events_count ?? 0} events · seq {replay.last_event_seq ?? '—'}
          </div>
        )}
      </Section>

      <div style={S.divider} />

      {/* ── Decision Log ───────────────────────────────── */}
      <Section title="Decision Log  (last 5)">
        {lastFive.length === 0 ? (
          <span style={S.empty}>Log empty</span>
        ) : (
          <div style={S.logList}>
            {lastFive.map(e => (
              <div key={e.seq} style={S.logRow}>
                <span style={S.logSeq}>#{e.seq}</span>
                <span style={S.logType}>{e.type}</span>
              </div>
            ))}
          </div>
        )}
      </Section>

      <div style={S.divider} />

      {/* ── Smart Render Diff ──────────────────────────── */}
      <Section title="Smart Render Diff">
        {renderDiff == null ? (
          <span style={S.empty}>No render yet</span>
        ) : (
          <div style={S.diffBox}>
            <DiffBadge
              count={renderDiff.diff_count}
              total={renderDiff.plan?.length ?? 0}
              full={renderDiff.full_rerender}
              duration={renderDiff.total_duration}
            />
            {renderDiff.plan?.length > 0 && (
              <div style={S.planPreview}>
                {renderDiff.plan.slice(0, 4).map((seg, i) => (
                  <div key={i} style={S.planRow}>
                    <span style={S.planTime}>
                      {seg.timeline_start.toFixed(1)}–{seg.timeline_end.toFixed(1)}s
                    </span>
                    <span style={{
                      ...S.planFrag,
                      color: renderDiff.changed_segments?.some(
                        c => c.fragment_id === seg.fragment_id
                      ) ? '#f59e0b' : '#4b5563',
                    }}>
                      {seg.fragment_id}
                    </span>
                  </div>
                ))}
                {renderDiff.plan.length > 4 && (
                  <div style={S.planMore}>+{renderDiff.plan.length - 4} more</div>
                )}
              </div>
            )}
          </div>
        )}
      </Section>

    </div>
  );
}

/* ── DiffBadge ───────────────────────────────────────────────── */
function DiffBadge({ count, total, full, duration }) {
  const label = count === 0
    ? '✓ no changes'
    : full
      ? `⚡ full re-render  (${count} seg)`
      : `↻ ${count} of ${total} seg changed`;

  const color = count === 0 ? '#22c55e' : full ? '#f59e0b' : '#38bdf8';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
      <span style={{ ...S.badge, color, borderColor: color }}>{label}</span>
      {duration != null && (
        <span style={S.duration}>{duration.toFixed(1)} s total</span>
      )}
    </div>
  );
}

/* ── Section wrapper ─────────────────────────────────────────── */
function Section({ title, children }) {
  return (
    <div style={S.section}>
      <div style={S.sectionTitle}>{title}</div>
      {children}
    </div>
  );
}

/* ── Styles ──────────────────────────────────────────────────── */
const S = {
  root: {
    display:       'flex',
    flexDirection: 'column',
    background:    '#05080f',
    fontFamily:    "'Courier New', monospace",
    color:         '#c8d0e0',
    overflow:      'auto',
    maxHeight:     '60vh',
    borderTop:     '2px solid #374151',
  },
  header: {
    padding:    '16px 18px 12px',
    background: '#07090f',
    flexShrink: 0,
    position:   'relative',
  },
  brand: {
    fontSize:      22,
    fontWeight:    'bold',
    color:         '#f1f5f9',
    letterSpacing: 6,
    marginBottom:  8,
  },
  tagline: {
    fontSize:   11,
    color:      '#6b7280',
    lineHeight: 1.7,
  },
  poll: {
    position: 'absolute',
    top:      16,
    right:    18,
    fontSize: 9,
    color:    '#1f2937',
  },
  divider: {
    height:     1,
    background: '#111820',
    flexShrink: 0,
  },
  section: {
    padding:    '10px 18px',
    flexShrink: 0,
  },
  sectionTitle: {
    fontSize:      9,
    color:         '#374151',
    textTransform: 'uppercase',
    letterSpacing: 1.5,
    marginBottom:  8,
  },
  empty: {
    fontSize: 9,
    color:    '#1f2937',
  },
  flowRow: {
    display:    'flex',
    alignItems: 'center',
    flexWrap:   'wrap',
    gap:        4,
    marginBottom: 6,
  },
  fragNode: {
    padding:      '3px 10px',
    background:   '#0d1117',
    border:       '1px solid #1e3a5a',
    borderRadius: 3,
    fontSize:     11,
    color:        '#38bdf8',
    fontWeight:   'bold',
  },
  arrow: {
    color:    '#1e3a5a',
    fontSize: 12,
  },
  meta: {
    fontSize: 9,
    color:    '#1f2937',
    marginTop: 2,
  },
  logList: {
    display:       'flex',
    flexDirection: 'column',
    gap:           3,
  },
  logRow: {
    display: 'flex',
    gap:     10,
    alignItems: 'baseline',
  },
  logSeq: {
    fontSize: 9,
    color:    '#374151',
    minWidth: 28,
  },
  logType: {
    fontSize: 10,
    color:    '#c8d0e0',
    fontWeight: 'bold',
  },
  diffBox: {
    display:       'flex',
    flexDirection: 'column',
  },
  badge: {
    fontSize:     10,
    padding:      '2px 8px',
    border:       '1px solid',
    borderRadius: 3,
    fontFamily:   "'Courier New', monospace",
  },
  duration: {
    fontSize: 9,
    color:    '#374151',
  },
  planPreview: {
    display:       'flex',
    flexDirection: 'column',
    gap:           2,
    marginTop:     4,
    paddingLeft:   4,
    borderLeft:    '2px solid #111820',
  },
  planRow: {
    display: 'flex',
    gap:     8,
    alignItems: 'baseline',
  },
  planTime: {
    fontSize: 9,
    color:    '#374151',
    minWidth: 80,
  },
  planFrag: {
    fontSize: 10,
    fontWeight: 'bold',
  },
  planMore: {
    fontSize: 9,
    color:    '#1f2937',
    marginTop: 2,
  },
};
