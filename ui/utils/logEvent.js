/**
 * logEvent.js
 * -----------
 * Fire-and-forget POST to /append-event.
 * Never throws, never blocks the caller.
 *
 * Usage:
 *   import { logEvent } from '../utils/logEvent.js';
 *   logEvent('BOUNDARY_ADJUSTED', { fragment_id: 'frag_0', new_start: 3.2, new_end: 7.8 });
 */

const API_BASE = 'http://localhost:8765';

export function logEvent(type, payload = {}) {
  fetch(`${API_BASE}/append-event`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ type, payload }),
  }).catch(() => {});  // intentional no-op on error
}
