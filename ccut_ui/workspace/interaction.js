// CCUT Workspace — Fragment Drag Interaction
// Standalone reference. Logic is also embedded in server.py HTML.

let _wsFragments = [];
let _dragSrcIdx = null;

const FRAG_COLORS = ['#1e3a5a','#1a3a2a','#3a1e3a','#3a2a1a','#1a2a3a','#2a1a3a'];

async function loadWorkspace() {
    const data = await api('/ui/workspace');
    if (!data) return;
    _wsFragments = data.fragments || [];
    renderWorkspace();
    document.getElementById('ws-info').textContent =
        `${_wsFragments.length} fragment(s) — total duration: ${data.total_duration}s`;
}

function renderWorkspace() {
    const maxDur = Math.max(..._wsFragments.map(f => f.duration), 1);
    const tl = document.getElementById('ws-timeline');
    if (!_wsFragments.length) {
        tl.innerHTML = '<div class="no-issues">No fragments in projection yet</div>';
        document.getElementById('ws-detail').innerHTML = '';
        return;
    }
    tl.innerHTML = _wsFragments.map((f, i) => {
        const w = Math.max(48, Math.round((f.duration / maxDur) * 220));
        const h = Math.max(56, Math.round((f.duration / maxDur) * 110));
        const col = FRAG_COLORS[i % FRAG_COLORS.length];
        return `<div class="ws-frag"
            draggable="true"
            data-idx="${i}"
            style="width:${w}px;height:${h}px;background:${col}"
            ondragstart="fragDragStart(event,${i})"
            ondragover="fragDragOver(event)"
            ondrop="fragDrop(event,${i})"
            ondragleave="fragDragLeave(event)"
            onclick="fragSelect(${i})">
            <div class="ws-frag-label">
                <div class="ws-frag-id">${f.id}</div>
                <div class="ws-frag-dur">${f.duration}s</div>
            </div>
        </div>`;
    }).join('');

    document.getElementById('ws-detail').innerHTML =
        _wsFragments.map(f => kv(f.id, `${f.start} → ${f.end} (${f.duration}s)`)).join('');
}

function fragDragStart(e, idx) {
    _dragSrcIdx = idx;
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function fragDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    e.currentTarget.classList.add('drag-over');
}

function fragDragLeave(e) {
    e.currentTarget.classList.remove('drag-over');
}

function fragDrop(e, toIdx) {
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    if (_dragSrcIdx === null || _dragSrcIdx === toIdx) return;
    const moved = _wsFragments.splice(_dragSrcIdx, 1)[0];
    _wsFragments.splice(toIdx, 0, moved);
    _dragSrcIdx = null;
    renderWorkspace();
}

function fragSelect(idx) {
    const f = _wsFragments[idx];
    document.getElementById('ws-detail').innerHTML =
        kv('ID', f.id) +
        kv('Start', f.start) +
        kv('End', f.end) +
        kv('Duration', f.duration + 's') +
        kv('Position', `${idx + 1} of ${_wsFragments.length}`);
}

function resetLayout() {
    loadWorkspace();
    document.getElementById('ws-status').innerHTML = '';
}

async function commitLayout() {
    const order = _wsFragments.map(f => f.id);
    const result = await fetch('/ui/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({type: 'MERGE', payload: {order}})
    }).then(r => r.json()).catch(e => ({error: String(e)}));

    const el = document.getElementById('ws-status');
    if (result.ok) {
        el.innerHTML = `<span class="status-green">✓ Layout committed — seq ${result.seq ?? '–'}</span>`;
        setTimeout(() => loadWorkspace(), 500);
    } else {
        el.innerHTML = `<span class="status-red">✗ ${result.error || 'Error'}</span>`;
    }
}
