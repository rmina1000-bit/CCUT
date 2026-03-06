import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_CORE = _ROOT / "ccut_core"
_UI = _ROOT / "ccut_ui"

for _p in [str(_CORE), str(_UI)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

os.chdir(str(_CORE))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from adapters.engine_read_adapter import (
    read_projection, read_status, read_verify,
    read_metrics, read_seal, read_audit,
    read_decision_log, read_trace, preview_replay,
)
from adapters.write_gateway import send_command, ALLOWED_TYPES
from workspace.workspace_view import build_workspace

from api.fragment_api import router as fragment_router
from proposal_engine.proposal_api import router as proposal_router
from edit_log.decision_api import router as decision_router

app = FastAPI(title="CCUT Engine Control Room", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(fragment_router)
app.include_router(proposal_router)
app.include_router(decision_router)

_DASHBOARD = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>CCUT 1.0.1 — Engine Control Room</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Courier New',monospace;background:#07090f;color:#c8d0e0;min-height:100vh}
header{background:#0d1117;border-bottom:1px solid #1e2a3a;padding:14px 28px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:10}
.logo{color:#38bdf8;font-size:17px;font-weight:bold;letter-spacing:.5px}
.logo span{color:#64748b;font-size:13px;font-weight:normal;margin-left:8px}
#seal-badge{margin-left:auto}
.badge{display:inline-flex;align-items:center;gap:5px;padding:3px 10px;border-radius:4px;font-size:11px;font-weight:bold;letter-spacing:.5px}
.badge-sealed{background:#1e1535;color:#c084fc;border:1px solid #7c3aed}
.badge-green{background:#0d2318;color:#4ade80;border:1px solid #16a34a}
.badge-yellow{background:#2a1f00;color:#facc15;border:1px solid #ca8a04}
.badge-red{background:#2a0d0d;color:#f87171;border:1px solid #dc2626}
.refresh-ts{font-size:11px;color:#374151;margin-left:8px}
.tabs{display:flex;background:#0d1117;border-bottom:1px solid #1e2a3a;padding:0 20px}
.tab{padding:12px 20px;cursor:pointer;color:#4b5563;border-bottom:2px solid transparent;font-size:12px;letter-spacing:.5px;text-transform:uppercase;transition:color .2s}
.tab:hover{color:#94a3b8}
.tab.active{color:#38bdf8;border-bottom-color:#38bdf8}
.screen{display:none;padding:24px 28px;max-width:1400px}
.screen.active{display:block}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-bottom:18px}
.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;margin-bottom:18px}
.card{background:#0d1117;border:1px solid #1e2a3a;border-radius:8px;padding:18px}
.card h3{color:#4b5563;font-size:10px;text-transform:uppercase;letter-spacing:2px;margin-bottom:14px}
.kv{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid #111827;font-size:13px}
.kv:last-child{border-bottom:none}
.kv-k{color:#6b7280}.kv-v{color:#38bdf8;text-align:right}
.status-green{color:#4ade80}.status-yellow{color:#facc15}.status-red{color:#f87171}
.status-gray{color:#6b7280}
.issue-item{font-size:12px;padding:4px 0;color:#facc15}
.issue-item.red{color:#f87171}
.no-issues{font-size:12px;color:#4ade80;padding:4px 0}
pre{background:#060810;border:1px solid #1e2a3a;border-radius:6px;padding:14px;font-size:11px;overflow:auto;max-height:420px;color:#94a3b8;line-height:1.6}
.audit-row{display:flex;gap:12px;padding:5px 0;border-bottom:1px solid #0f1723;font-size:11px}
.audit-row:last-child{border-bottom:none}
.audit-ts{color:#374151;min-width:85px}
.audit-type{color:#7dd3fc}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.dot-green{background:#4ade80}.dot-yellow{background:#facc15}.dot-red{background:#f87171}
.btn{padding:8px 18px;background:#0a1628;border:1px solid #1e3a5a;color:#38bdf8;cursor:pointer;border-radius:4px;font-family:"Courier New",monospace;font-size:12px;letter-spacing:.3px;transition:background .15s}
.btn:hover{background:#1e3a5a}.btn:active{background:#2a4a6a}
.btn-danger{border-color:#3a1e1e;color:#f87171}.btn-danger:hover{background:#3a1e1e}
.cmd-bar{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
.cmd-result{min-height:20px;font-size:12px;padding:6px 0}
.ws-timeline{display:flex;gap:8px;align-items:flex-end;overflow-x:auto;padding:16px;min-height:130px;background:#060810;border:1px solid #1e2a3a;border-radius:6px}
.ws-frag{border-radius:5px;cursor:grab;transition:opacity .15s,border .15s;position:relative;min-width:48px;display:flex;align-items:flex-end;justify-content:center;padding:6px 4px;user-select:none;border:1px solid transparent}
.ws-frag:hover{opacity:.85;border-color:#38bdf8!important}.ws-frag:active{cursor:grabbing}
.ws-frag.dragging{opacity:.35}.ws-frag.drag-over{border:2px dashed #38bdf8!important}
.ws-frag-label{text-align:center;pointer-events:none}
.ws-frag-id{font-size:11px;font-weight:bold;color:#e2e8f0;word-break:break-all}
.ws-frag-dur{font-size:10px;color:#94a3b8;margin-top:2px}
.ws-bar{display:flex;align-items:center;gap:12px;margin-top:14px}
.verify-fail-banner{background:#2a0d0d;border-bottom:2px solid #dc2626;padding:9px 28px;font-size:12px;color:#f87171;letter-spacing:.4px}
.btn-write:disabled{opacity:.35!important;pointer-events:none!important;cursor:not-allowed!important}
.sem-btn{position:absolute;top:4px;right:4px;padding:1px 5px;font-size:10px;background:#0a1628;border:1px solid #1e3a5a;color:#38bdf8;cursor:pointer;border-radius:3px;z-index:2}
.sem-btn:hover{background:#1e3a5a}
.balloon{display:none;position:fixed;background:#111827;border:1px solid #38bdf8;border-radius:8px;padding:16px;min-width:230px;z-index:200;box-shadow:0 6px 32px rgba(0,0,0,.7)}
.balloon h4{color:#38bdf8;font-size:10px;text-transform:uppercase;letter-spacing:2px;margin-bottom:10px}
.balloon-ids{color:#c084fc;font-size:14px;font-weight:bold;margin-bottom:4px}
.balloon-type{color:#38bdf8;font-size:10px;margin-bottom:4px;opacity:.7}
.balloon-reason{color:#6b7280;font-size:11px;margin-bottom:14px}
.balloon-btns{display:flex;gap:8px}
#balloon-overlay{display:none;position:fixed;top:0;left:0;width:100%;height:100%;z-index:199}
</style></head><body>
<header>
  <div class="logo">⚡ CCUT 1.0.1 <span>Engine Control Room</span></div>
  <div id="seal-badge"></div>
  <div class="refresh-ts" id="rts"></div>
</header>
<div id="verify-fail-banner" class="verify-fail-banner" style="display:none">&#9888; VERIFY CHAIN FAILED &mdash; System Integrity Compromised</div>
<div class="tabs">
  <div class="tab active" onclick="go('overview')">Engine Overview</div>
  <div class="tab" onclick="go('projection')">Projection Viewer</div>
  <div class="tab" onclick="go('observability')">Observability Panel</div>
  <div class="tab" onclick="go('decisions')">Decision Timeline</div>
  <div class="tab" onclick="go('workspace')">Workspace</div>
</div>

<div id="s-overview" class="screen active">
  <div class="grid2">
    <div class="card"><h3>Engine Status</h3><div id="ov-status">Loading…</div></div>
    <div class="card"><h3>Verify Chain</h3><div id="ov-verify">Loading…</div></div>
  </div>
  <div class="grid2">
    <div class="card"><h3>Production Seal</h3><div id="ov-seal">Loading…</div></div>
    <div class="card"><h3>Audit Trail (last 5)</h3><div id="ov-audit">Loading…</div></div>
  </div>
</div>

<div id="s-projection" class="screen">
  <div class="card"><h3>Projection State — Read Only</h3><pre id="proj-pre">Loading…</pre></div>
</div>

<div id="s-observability" class="screen">
  <div class="grid2">
    <div class="card"><h3>Live Metrics</h3><div id="obs-metrics">Loading…</div></div>
    <div class="card"><h3>Trace Buffer Sizes</h3><div id="obs-buf">Loading…</div></div>
  </div>
  <div class="card"><h3>Active Issues</h3><div id="obs-issues">Loading…</div></div>
</div>

<div id="s-decisions" class="screen">
  <div class="card" style="margin-bottom:18px">
    <h3>Write Gateway — Controlled Input</h3>
    <div class="cmd-result" id="cmd-result"></div>
    <div class="cmd-bar">
      <button class="btn btn-write" onclick="sendCmd('CREATE_CUT',{id:'c_'+Date.now(),start:0,end:10})">+ CREATE_CUT</button>
      <button class="btn btn-danger btn-write" onclick="sendCmd('DELETE_CUT',{id:'c_0'})">- DELETE_CUT</button>
      <button class="btn btn-write" onclick="sendCmd('SPLIT',{id:'c_0',at:5})">&#9654; SPLIT</button>
      <button class="btn btn-write" onclick="sendCmd('MERGE',{a:'c_0',b:'c_1'})">&#9670; MERGE</button>
    </div>
  </div>
  <div class="card" style="margin-bottom:18px">
    <h3>Decision Event Timeline</h3>
    <div id="dt-badge" style="margin-bottom:14px"></div>
    <div id="dt-table">Loading…</div>
  </div>
  <div class="grid2">
    <div class="card"><h3>Replay Preview — Dry Run</h3><div id="dt-replay">Loading…</div></div>
    <div class="card"><h3>Deterministic Trace (last 10)</h3><div id="dt-trace">Loading…</div></div>
  </div>
</div>

<div id="s-workspace" class="screen">
  <div class="card" style="margin-bottom:18px">
    <h3>CCUT Fragment Workspace</h3>
    <div id="ws-info" style="font-size:12px;color:#6b7280;margin-bottom:10px"></div>
    <div id="ws-timeline" class="ws-timeline"><span class="status-gray">Loading…</span></div>
    <div class="ws-bar">
      <button class="btn btn-write" onclick="commitLayout()">&#9889; Commit Layout</button>
      <button class="btn" style="border-color:#333;color:#6b7280" onclick="resetLayout()">&#8635; Reset</button>
      <span id="ws-status" style="font-size:12px"></span>
    </div>
  </div>
  <div class="card"><h3>Fragment Detail</h3><div id="ws-detail"></div></div>
</div>
<div id="balloon-overlay" onclick="closeBalloon()"></div>
<div id="sem-balloon" class="balloon"></div>

<script>
let cur='overview';
let _gSeal=true,_gVerify=null,_lastCommitSeq=null,_projCanonical=null;
function go(t){
  document.querySelectorAll('.tab').forEach((el,i)=>{
    el.classList.toggle('active',['overview','projection','observability','decisions','workspace'][i]===t);
  });
  ['overview','projection','observability','decisions','workspace'].forEach(id=>{
    document.getElementById('s-'+id).classList.toggle('active',id===t);
  });
  cur=t; globalRefresh();
}

async function api(url){try{const r=await fetch(url);return await r.json();}catch{return null;}}

function kv(k,v){return`<div class="kv"><span class="kv-k">${k}</span><span class="kv-v">${v}</span></div>`;}

function statusBadge(s){
  if(!s)return'<span class="status-gray">–</span>';
  const cls=s==='GREEN'?'badge-green':s==='YELLOW'?'badge-yellow':'badge-red';
  const dot=s==='GREEN'?'dot-green':s==='YELLOW'?'dot-yellow':'dot-red';
  return`<span class="badge ${cls}"><span class="dot ${dot}"></span>${s}</span>`;
}

async function loadOverview(){
  const[status,verify,seal,audit]=await Promise.all([
    api('/ui/status'),api('/ui/verify'),api('/ui/seal'),api('/ui/audit')
  ]);
  if(status){
    document.getElementById('ov-status').innerHTML=
      kv('Health',statusBadge(status.health_status))+
      (status.issues?.map(i=>`<div class="issue-item">${i}</div>`).join('')||'');
  }
  if(verify){
    const ok=verify.verified;
    const badge=ok?'<span class="badge badge-green">PASS ✓</span>':'<span class="badge badge-red">FAIL ✗</span>';
    document.getElementById('ov-verify').innerHTML=
      kv('Chain',badge)+
      kv('Seq',`<span class="kv-v">${verify.seq??'–'}</span>`)+
      (verify.error?kv('Error',`<span class="status-red" style="font-size:11px">${verify.error}</span>`):'');
  }
  if(seal!==null){
    const s=seal.sealed;
    document.getElementById('ov-seal').innerHTML=
      kv('Mode',s?'<span class="badge badge-sealed">⚿ PRODUCTION</span>':'<span class="status-gray">Development</span>')+
      kv('Observability Lock',s?'<span class="status-green">ENABLED</span>':'<span class="status-gray">Unlocked</span>');
  }
  if(audit){
    document.getElementById('ov-audit').innerHTML=
      audit.length===0?'<div class="no-issues">No audit events yet</div>':
      audit.map(e=>`<div class="audit-row">
        <span class="audit-ts">${(e.timestamp||'').split('T')[1]?.slice(0,8)||'–'}</span>
        <span class="audit-type">${e.event_type||'–'}</span>
      </div>`).reverse().join('');
  }
}

async function loadProjection(){
  const data=await api('/ui/projection');
  document.getElementById('proj-pre').textContent=JSON.stringify(data,null,2);
}

async function loadObservability(){
  const[metrics,health]=await Promise.all([api('/ui/metrics'),api('/ui/status')]);
  if(metrics){
    const buf=metrics.buffer_sizes||{};
    document.getElementById('obs-metrics').innerHTML=
      kv('Observability',metrics.observability_enabled?'<span class="status-green">ON</span>':'<span class="status-red">OFF</span>')+
      kv('Decision Count',metrics.decision_count??'–')+
      kv('Render Queue',metrics.render_queue_depth??'–')+
      kv('Last Flush',(metrics.last_flush_timestamp||'').split('T')[1]?.slice(0,8)||'–')+
      kv('Last Hash',metrics.last_trace_hash?metrics.last_trace_hash.slice(0,18)+'…':'–');
    document.getElementById('obs-buf').innerHTML=
      Object.entries(buf).map(([k,v])=>kv(k,`<span class="${v>40?'status-yellow':v>20?'status-yellow':''}">${v}</span>`)).join('');
  }
  if(health){
    const issues=health.issues||[];
    document.getElementById('obs-issues').innerHTML=
      issues.length===0?'<div class="no-issues">✓ No issues — system healthy</div>':
      issues.map(i=>`<div class="issue-item">${i}</div>`).join('');
  }
}

const _FC=['#1e3a5a','#1a3a2a','#3a1e3a','#3a2a1a','#1a2a3a','#2a1a3a'];
let _wsF=[],_dragIdx=null;
async function loadWorkspace(){
  const d=await api('/ui/workspace');
  if(!d)return;
  const newCan=(d.fragments||[]).map(f=>f.id).join(',');
  if(_projCanonical!==null&&_projCanonical!==''&&_projCanonical!==newCan){
    const s=document.getElementById('ws-status');
    if(!s.innerHTML.includes('committed'))s.innerHTML='<span class="status-yellow">⧻ Projection Updated — workspace resynced</span>';
  }
  _wsF=d.fragments||[];
  _projCanonical=newCan;
  document.getElementById('ws-info').textContent=`${_wsF.length} fragment(s) — total duration: ${d.total_duration}s`;
  renderWorkspace();
}
function renderWorkspace(){
  const maxD=Math.max(..._wsF.map(f=>f.duration),1);
  const tl=document.getElementById('ws-timeline');
  if(!_wsF.length){tl.innerHTML='<div class="no-issues">No fragments yet — use CREATE_CUT to add</div>';document.getElementById('ws-detail').innerHTML='';return;}
  tl.innerHTML=_wsF.map((f,i)=>{
    const w=Math.max(48,Math.round((f.duration/maxD)*220));
    const h=Math.max(60,Math.round((f.duration/maxD)*120));
    const c=_FC[i%_FC.length];
    return `<div class="ws-frag" draggable="true" data-idx="${i}"
      style="width:${w}px;height:${h}px;background:${c};position:relative"
      ondragstart="wsDragStart(event,${i})" ondragover="wsDragOver(event)"
      ondrop="wsDrop(event,${i})" ondragleave="wsDragLeave(event)"
      onclick="wsSelect(${i})">

      <div class="ws-frag-label"><div class="ws-frag-id">${f.id}</div><div class="ws-frag-dur">${f.duration}s</div></div>
    </div>`;
  }).join('');
  document.getElementById('ws-detail').innerHTML=_wsF.map(f=>kv(f.id,`${f.start} → ${f.end} (${f.duration}s)`)).join('');

}
function wsDragStart(e,i){_dragIdx=i;e.target.classList.add('dragging');e.dataTransfer.effectAllowed='move';}
function wsDragOver(e){e.preventDefault();e.dataTransfer.dropEffect='move';e.currentTarget.classList.add('drag-over');}
function wsDragLeave(e){e.currentTarget.classList.remove('drag-over');}
function wsDrop(e,to){
  e.preventDefault();e.currentTarget.classList.remove('drag-over');
  if(_dragIdx===null||_dragIdx===to)return;
  const m=_wsF.splice(_dragIdx,1)[0];_wsF.splice(to,0,m);_dragIdx=null;renderWorkspace();
  const cur2=_wsF.map(f=>f.id).join(',');
  if(cur2!==_projCanonical){const s=document.getElementById('ws-status');if(!s.innerHTML.includes('committed'))s.innerHTML='<span class="status-yellow">⋯ Layout modified — click Commit to save</span>';}
}
function wsSelect(i){
  const f=_wsF[i];
  document.getElementById('ws-detail').innerHTML=kv('ID',f.id)+kv('Start',f.start)+kv('End',f.end)+kv('Duration',f.duration+'s')+kv('Position',`${i+1} of ${_wsF.length}`);
}


function resetLayout(){loadWorkspace();document.getElementById('ws-status').innerHTML='';}
async function commitLayout(){
  const el=document.getElementById('ws-status');
  if(_gSeal===false){el.innerHTML='<span class="status-red">✗ Write disabled — engine not sealed</span>';return;}
  const order=_wsF.map(f=>f.id);
  const res=await fetch('/ui/command',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'MERGE',payload:{order}})}).then(r=>r.json()).catch(e=>({error:String(e)}));
  if(res.ok){
    _lastCommitSeq=res.seq;
    _projCanonical=order.join(',');
    el.innerHTML=`<span class="status-green">✓ Layout committed — seq ${res.seq??'–'}</span>`;
    setTimeout(()=>globalRefresh(),500);
  } else el.innerHTML=`<span class="status-red">✗ ${res.error||'Error'}</span>`;
}

async function sendCmd(type,payload){
  const el=document.getElementById('cmd-result');
  if(_gSeal===false){el.innerHTML='<span class="status-red">✗ Write disabled — engine not sealed</span>';return;}
  el.innerHTML='<span class="status-gray">Dispatching…</span>';
  try{
    const r=await fetch('/ui/command',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({type,payload})
    });
    const data=await r.json();
    if(data.ok){
      _lastCommitSeq=data.seq;
      el.innerHTML=`<span class="status-green">✓ ${type} dispatched — seq ${data.seq??'–'}</span>`;
    } else {
      el.innerHTML=`<span class="status-red">✗ ${data.error||'Unknown error'}</span>`;
    }
  } catch(e){
    el.innerHTML=`<span class="status-red">✗ ${e}</span>`;
  }
  setTimeout(()=>globalRefresh(),400);
}

async function loadDecisions(){
  const[decisions,verify,replay,trace]=await Promise.all([
    api('/ui/decisions'),api('/ui/verify'),api('/ui/replay'),api('/ui/trace')
  ]);
  if(verify){
    document.getElementById('dt-badge').innerHTML=
      verify.verified?'<span class="badge badge-green">⛓ Chain PASS ✓</span>':'<span class="badge badge-red">⛓ Chain FAIL ✗</span>';
  }
  if(decisions&&decisions.length){
    let rows='';
    decisions.forEach((e,i)=>{
      const prev=i>0?decisions[i-1]:null;
      const chainOk=!prev||(prev.hash&&e.prev_hash&&prev.hash===e.prev_hash);
      const ts=(e.timestamp||'').split('T')[1]?.slice(0,8)||'–';
      const hash=(e.hash||'').slice(0,16)+'…';
      const type=e.type||e.event_type||'–';
      const seq=e.seq??i;
      const isLast=_lastCommitSeq!==null&&seq===_lastCommitSeq;
      rows+=`<tr style="border-bottom:1px solid #0f1723${isLast?';background:#0d2318':''}">
        <td style="padding:5px 8px;color:#38bdf8">${seq}${isLast?' <span style="color:#4ade80;font-size:9px">◄ last</span>':''}</td>
        <td style="padding:5px 8px;color:#c084fc">${type}</td>
        <td style="padding:5px 8px;color:#6b7280">${ts}</td>
        <td style="padding:5px 8px;font-family:monospace;color:#374151;font-size:10px">${hash}</td>
        <td style="padding:5px 8px" class="${chainOk?'status-green':'status-red'}">${chainOk?'✓':'✗'}</td>
      </tr>`;
    });
    document.getElementById('dt-table').innerHTML=
      `<div style="overflow:auto;max-height:360px"><table style="width:100%;border-collapse:collapse;font-size:12px">
      <tr style="color:#4b5563;border-bottom:2px solid #1e2a3a;font-size:10px;text-transform:uppercase;letter-spacing:1px;position:sticky;top:0;background:#0d1117">
        <th style="text-align:left;padding:6px 8px">Seq</th><th style="text-align:left;padding:6px 8px">Type</th>
        <th style="text-align:left;padding:6px 8px">Time</th><th style="text-align:left;padding:6px 8px">Hash</th>
        <th style="text-align:left;padding:6px 8px">Chain</th></tr>${rows}</table></div>`;
  } else {
    document.getElementById('dt-table').innerHTML='<div class="no-issues">No decision events recorded yet</div>';
  }
  if(replay){
    const types=replay.event_types||{};
    document.getElementById('dt-replay').innerHTML=
      kv('Event Count',replay.event_count??'–')+
      kv('First Seq',replay.first_seq??'–')+
      kv('Last Seq',replay.last_seq??'–')+
      kv('Mode','<span class="status-gray">DRY RUN</span>')+
      Object.entries(types).map(([k,v])=>kv(k,`<span style="color:#94a3b8">${v}</span>`)).join('');
  }
  if(trace&&trace.length){
    document.getElementById('dt-trace').innerHTML=
      trace.slice(-10).reverse().map(e=>{
        const ts=(e.timestamp||'').split('T')[1]?.slice(0,8)||'–';
        return kv(e.event_type||'–',`<span style="color:#6b7280;font-size:11px">${ts}</span>`);
      }).join('');
  } else {
    document.getElementById('dt-trace').innerHTML='<div class="status-gray" style="font-size:12px">No trace events yet</div>';
  }
}

async function checkGlobalState(){
  const[seal,verify]=await Promise.all([api('/ui/seal'),api('/ui/verify')]);
  if(seal){
    _gSeal=seal.sealed;
    document.getElementById('seal-badge').innerHTML=
      seal.sealed?'<span class="badge badge-sealed">⚿ PRODUCTION SEALED</span>':'<span class="badge badge-yellow">⚠ UNSEALED</span>';
    document.querySelectorAll('.btn-write').forEach(b=>{
      b.disabled=!seal.sealed;
      if(!seal.sealed)b.title='Write disabled — engine not sealed';
    });
  }
  if(verify){
    _gVerify=verify.verified;
    document.getElementById('verify-fail-banner').style.display=verify.verified?'none':'block';
  }
}

async function globalRefresh(){
  document.getElementById('rts').textContent='↻ '+new Date().toLocaleTimeString();
  checkGlobalState();
  if(cur==='overview') await loadOverview();
  else if(cur==='projection') await loadProjection();
  else if(cur==='observability') await loadObservability();
  else if(cur==='decisions') await loadDecisions();
  else if(cur==='workspace') await loadWorkspace();
}

globalRefresh();
setInterval(globalRefresh,3000);
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD


@app.get("/ui/projection")
def ui_projection():
    return read_projection()


@app.get("/ui/status")
def ui_status():
    return read_status()


@app.get("/ui/verify")
def ui_verify():
    return read_verify()


@app.get("/ui/metrics")
def ui_metrics():
    return read_metrics()


@app.get("/ui/seal")
def ui_seal():
    return {"sealed": read_seal()}


@app.get("/ui/audit")
def ui_audit(n: int = 20):
    return read_audit(n)


@app.get("/ui/decisions")
def ui_decisions(limit: int = 200):
    return read_decision_log(limit)


@app.get("/ui/trace")
def ui_trace(n: int = 50):
    return read_trace(n)


@app.get("/ui/replay")
def ui_replay():
    return preview_replay()


@app.post("/ui/command")
def ui_command(payload: dict):
    if payload.get("type") not in ALLOWED_TYPES:
        return {"error": f"command type '{payload.get('type')}' not allowed",
                "allowed": sorted(ALLOWED_TYPES)}
    return send_command(payload)


@app.get("/ui/workspace")
def ui_workspace():
    proj = read_projection()
    return build_workspace(proj)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8765, reload=False)
