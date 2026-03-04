import React, { useState, useRef } from 'react';

const API_BASE = 'http://localhost:8765';

export default function VideoUploader({ onFragments }) {
  const [status, setStatus] = useState('idle'); // idle | uploading | done | error
  const [info,   setInfo]   = useState('');
  const objectUrlRef = useRef(null);

  const handleChange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Revoke any previous object URL to avoid memory leak
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
    }
    const objectUrl = URL.createObjectURL(file);
    objectUrlRef.current = objectUrl;

    setStatus('uploading');
    setInfo(`Analysing ${file.name}…`);

    try {
      const form = new FormData();
      form.append('file', file);

      const res = await fetch(`${API_BASE}/generate-fragments`, {
        method: 'POST',
        body: form,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }

      const data = await res.json();

      // Enrich server fragments with browser-side src + label
      const enriched = (data.fragments || []).map((f) => ({
        ...f,
        src:      objectUrl,
        label:    f.id,
        duration: f.duration ?? round2(f.end - f.start),
      }));

      onFragments(enriched);
      setStatus('done');
      setInfo(`${enriched.length} fragments — ${file.name}`);
    } catch (err) {
      setStatus('error');
      setInfo(`Error: ${err.message}`);
    }
  };

  return (
    <div style={styles.wrap}>
      <label style={styles.label(status)}>
        {status === 'uploading' ? '⏳ Processing…' : '⬆ Upload Video'}
        <input
          type="file"
          accept="video/*"
          onChange={handleChange}
          disabled={status === 'uploading'}
          style={{ display: 'none' }}
        />
      </label>
      {info && (
        <span style={styles.info(status)}>{info}</span>
      )}
    </div>
  );
}

function round2(n) {
  return Math.round(n * 1000) / 1000;
}

const styles = {
  wrap: {
    display:    'flex',
    alignItems: 'center',
    gap:        10,
    padding:    '10px 14px',
    borderBottom: '1px solid #1e2a3a',
    flexShrink: 0,
  },
  label: (status) => ({
    display:       'inline-flex',
    alignItems:    'center',
    cursor:        status === 'uploading' ? 'not-allowed' : 'pointer',
    padding:       '5px 12px',
    borderRadius:  4,
    fontSize:      11,
    fontFamily:    "'Courier New', monospace",
    background:    status === 'uploading' ? '#1a2a1a' : '#1e3a5a',
    color:         status === 'uploading' ? '#6b7280' : '#38bdf8',
    border:        '1px solid',
    borderColor:   status === 'uploading' ? '#374151' : '#2d5a8e',
    userSelect:    'none',
    whiteSpace:    'nowrap',
  }),
  info: (status) => ({
    fontSize:   10,
    fontFamily: "'Courier New', monospace",
    color:      status === 'error' ? '#f87171'
              : status === 'done'  ? '#4ade80'
              : '#6b7280',
    overflow:   'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    maxWidth:   240,
  }),
};
