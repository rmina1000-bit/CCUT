// CCUT Semantic Layer — Balloon Assist
// Standalone reference. Logic is embedded in server.py HTML.

let _semSuggestions = [];

async function loadSemantic() {
    const d = await api('/ui/semantic');
    if (!d) return;
    _semSuggestions = d.suggestions || [];
    addSemanticButtons();
}

function addSemanticButtons() {
    document.querySelectorAll('.ws-frag').forEach((el, i) => {
        if (!el.querySelector('.sem-btn')) {
            const btn = document.createElement('button');
            btn.className = 'sem-btn';
            btn.textContent = '⋯';
            btn.title = 'Semantic Assist';
            btn.onclick = (e) => { e.stopPropagation(); showBalloon(i, btn); };
            el.prepend(btn);
        }
    });
}

function showBalloon(fragIdx, anchor) {
    const frag = _wsF[fragIdx];
    if (!frag) return;
    const suggs = _semSuggestions.filter(g => g.ids.includes(frag.id));
    const balloon = document.getElementById('sem-balloon');
    const overlay = document.getElementById('balloon-overlay');

    if (!suggs.length) {
        balloon.innerHTML = `
            <h4>Semantic Assist</h4>
            <div class="balloon-reason">No suggestions for '${frag.id}'</div>
            <div class="balloon-btns">
                <button class="btn" onclick="closeBalloon()">Close</button>
            </div>`;
    } else {
        const s = suggs[0];
        balloon.innerHTML = `
            <h4>Suggested Group</h4>
            <div class="balloon-ids">${s.ids.join(' + ')}</div>
            <div class="balloon-type">${s.type}</div>
            <div class="balloon-reason">${s.reason}</div>
            <div class="balloon-btns">
                <button class="btn" onclick="acceptGroup('${s.id}')">Accept</button>
                <button class="btn" style="border-color:#333;color:#6b7280"
                    onclick="closeBalloon()">Ignore</button>
            </div>`;
    }

    const rect = anchor.getBoundingClientRect();
    balloon.style.top = (rect.bottom + 8) + 'px';
    balloon.style.left = Math.min(rect.left, window.innerWidth - 260) + 'px';
    balloon.style.display = 'block';
    overlay.style.display = 'block';
}

function closeBalloon() {
    document.getElementById('sem-balloon').style.display = 'none';
    document.getElementById('balloon-overlay').style.display = 'none';
}

async function acceptGroup(sgId) {
    closeBalloon();
    const sg = _semSuggestions.find(s => s.id === sgId);
    if (!sg) return;
    const res = await fetch('/ui/command', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            type: 'MERGE',
            payload: {ids: sg.ids, semantic_group: sgId, source: 'Assist'}
        })
    }).then(r => r.json()).catch(e => ({error: String(e)}));

    const el = document.getElementById('ws-status');
    if (res.ok) {
        el.innerHTML = `<span class="status-green">✓ Semantic group accepted — seq ${res.seq ?? '–'}</span>`;
        setTimeout(() => { loadWorkspace(); loadSemantic(); }, 500);
    } else {
        el.innerHTML = `<span class="status-red">✗ ${res.error || 'Error'}</span>`;
    }
}
