/* Review workspace.
 *
 * The four detection stages on one screen, with the same editing tools as the
 * local review tool plus click-to-segment, then classification runs on what
 * the user corrected.
 *
 * Everything is in PAGE POINTS — the pipeline's own units — so nothing has to
 * be converted between here and the server.
 */
import {
  centroid, closestOnRing, insertVertexAt, pointInRing,
  polyArea, removeVertex, segCrossesRing,
} from './polyops.js';

const $ = s => document.querySelector(s);
const keyEl = $('#apikey');
keyEl.value = localStorage.getItem('pipeApiKey') || '';
keyEl.addEventListener('change', () => localStorage.setItem('pipeApiKey', keyEl.value.trim()));
const KEY = () => keyEl.value.trim();

let jobId = null, doc = null, img = null, summary = null;
let tool = 'select', sel = [], hover = null;
let view = {x:0, y:0, z:1};
const shown = new Set(['pipes','labels','joins','leaders','wall']);
/* Ids read the way the local tool's do — P12, L7, J31 — because the user sees
   them in the inspector and in the exported JSON. Deleted items still hold
   their number, so nothing is ever reused within a session. */
const ID_LIST = {P:'pipes', L:'labels', J:'joins', E:'leaders'};
function uid(prefix){
  let n = 0;
  for (const o of listOf(ID_LIST[prefix]) || []){
    const m = /^[A-Z]+(\d+)/.exec(o.id || '');
    if (m) n = Math.max(n, +m[1]);
  }
  return prefix + (n + 1);
}
const active = a => (a || []).filter(o => !o.deleted);
const listOf = k => (doc && doc[k]) || [];
const byId = (k, id) => listOf(k).find(o => o.id === id);

/* ── detector confidence ───────────────────────────────────────────────────
   The model runs at a 0.05 floor and every detection carries its score; the
   two sliders filter per class, live, before or after the results arrive.
   Filtered objects are hidden and skipped by classification (the document
   carries `thresholds`, the server honours them) but never deleted, so
   sliding back brings them back.  Hand-placed objects have no score. */
const thr = {label: 0.05, join: 0.05};
try { const s = JSON.parse(localStorage.getItem('pipeThresholds') || '{}');
      for (const k of ['label', 'join']) if (s[k] >= 0.05 && s[k] <= 1) thr[k] = s[k]; }
catch { /* first visit */ }
function visible(kind, o){
  if (kind === 'labels') return !(o.score >= 0 && o.score < thr.label - 1e-9);
  if (kind === 'joins')  return !(o.conf >= 0 && o.conf < thr.join * 100 - 1e-6);
  if (kind === 'leaders'){
    const j = o.joinId ? byId('joins', o.joinId) : null;
    const l = o.labelId ? byId('labels', o.labelId) : null;
    return (!j || visible('joins', j)) && (!l || visible('labels', l));
  }
  return true;
}
const shownObjs = kind => active(listOf(kind)).filter(o => visible(kind, o));
function bindThreshold(id, key){
  const inp = $('#' + id), out = $('#' + id + 'V');
  inp.value = Math.round(thr[key] * 100); out.textContent = thr[key].toFixed(2);
  inp.oninput = () => {
    thr[key] = inp.value / 100; out.textContent = thr[key].toFixed(2);
    localStorage.setItem('pipeThresholds', JSON.stringify(thr));
    if (!doc) return;
    doc.thresholds = {...thr};
    sel = sel.filter(s => { const o = byId(s.kind, s.id); return !o || visible(s.kind, o); });
    refresh();
    status(`Showing ${shownObjs('labels').length}/${active(doc.labels).length} labels and `
         + `${shownObjs('joins').length}/${active(doc.joins).length} joining points — `
         + `classification uses what is shown`);
  };
}
bindThreshold('thrLabel', 'label');
bindThreshold('thrJoin', 'join');

/* the size of the joining points the detector drew: a hand-placed one gets
   the same, so it does not stand out by size — only by its black colour */
function autoJoinRadius(){
  const rs = active(doc?.joins).filter(j => j.conf >= 0 && j.radius > 0)
                               .map(j => j.radius).sort((a, b) => a - b);
  return rs.length ? +rs[rs.length >> 1].toFixed(2) : 3.5;
}
const joinColour = j => j.source === 'manual' ? '#111111' : '#a855f7';

/* ── tiny history: snapshots are simple and always correct ─────────────── */
const hist = {past:[], future:[], depth: 60};
function snapshot(){
  return JSON.stringify({pipes: doc.pipes, base_pipes: doc.base_pipes,
                         labels: doc.labels, joins: doc.joins,
                         leaders: doc.leaders, wall: doc.wall});
}
function commit(label){
  hist.past.push({label, state: hist._pre});
  if (hist.past.length > hist.depth) hist.past.shift();
  hist.future.length = 0;
  hist._pre = null;
  refresh();
  // Every edit says what it did; callers with something better to say overwrite
  // this straight after, since they run once commit returns.
  status(label);
}
function begin(){ hist._pre = snapshot(); }
function act(label, fn){ begin(); fn(); commit(label); }
function restore(json){
  const s = JSON.parse(json);
  doc.pipes = s.pipes; doc.base_pipes = s.base_pipes;
  doc.labels = s.labels; doc.joins = s.joins; doc.leaders = s.leaders;
  doc.wall = s.wall || [];
  sel = []; refresh(); draw();
}
function undo(){
  if (!hist.past.length) return;
  const e = hist.past.pop();
  hist.future.push({label: e.label, state: snapshot()});
  restore(e.state);
  status(`Undo: ${e.label}`);
}
function redo(){
  if (!hist.future.length) return;
  const e = hist.future.pop();
  hist.past.push({label: e.label, state: snapshot()});
  restore(e.state);
  status(`Redo: ${e.label}`);
}

function status(m, k){ const e = $('#status'); e.textContent = m || ''; e.className = k || ''; }

// OCR text goes into innerHTML and the free-text alphabet includes < > &,
// so it is escaped before it gets there.
function esc(t){
  return String(t == null ? '' : t)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ── api ────────────────────────────────────────────────────────────────── */
async function api(path, opts = {}){
  const r = await fetch(path, {...opts,
    headers: {'X-API-Key': KEY(), ...(opts.headers || {})}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j;
}
const post = (path, body) => api(path, {method:'POST',
  headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});

/* ── upload ─────────────────────────────────────────────────────────────── */
const drop = $('#drop'), fileEl = $('#file');
drop.onclick = () => fileEl.click();
drop.ondragover = e => { e.preventDefault(); drop.classList.add('over'); };
drop.ondragleave = () => drop.classList.remove('over');
drop.ondrop = e => { e.preventDefault(); drop.classList.remove('over');
                     if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); };
fileEl.onchange = () => { if (fileEl.files[0]) upload(fileEl.files[0]); };

async function upload(file){
  if (!KEY()){ status('Enter the API key first','err'); keyEl.focus(); return; }
  doc = null; img = null; summary = null; sel = []; jobId = null;
  hist.past.length = hist.future.length = 0;
  $('#work').style.display = 'none'; $('#result').style.display = 'none';
  $('#progress').style.display = 'block';
  status(`Uploading ${file.name}…`); draw();

  const fd = new FormData(); fd.append('file', file);
  let id;
  try {
    id = (await api('/api/review', {method:'POST', body: fd})).jobId;
  } catch(e){ $('#progress').style.display='none'; status(e.message,'err'); return; }
  await track(id);
}

/* Follow a detection job to completion and put it on screen. Split out from
   `upload` so a job started elsewhere — or one whose page was reloaded — can be
   picked up by id. */
async function track(id){
  jobId = id;
  $('#progress').style.display = 'block';
  status('Detecting pipes, labels, joining points and lines…');
  const t0 = Date.now();
  for(;;){
    await new Promise(r => setTimeout(r, 900));
    let j;
    try { j = await api(`/api/review/${jobId}`); }
    catch(e){ $('#progress').style.display='none'; status(e.message,'err'); return; }
    if (j.status === 'pending'){
      if (Date.now()-t0 > 15*60*1000){
        $('#progress').style.display='none'; status('Timed out','err'); return; }
      continue;
    }
    $('#progress').style.display='none';
    if (j.status === 'error'){ status(j.error,'err'); return; }
    doc = j.document;
    doc.wall = doc.wall || [];
    doc.thresholds = {...thr};             // the sliders as set before generation
    $('#work').style.display='block'; $('#empty').style.display='none';
    status(`Detected in ${((Date.now()-t0)/1000).toFixed(1)}s — review, then classify`, 'ok');
    refresh();
    if (j.hasPreview){
      const im = new Image();
      im.onload = () => { img = im; fit(); };
      im.onerror = () => { img = null; fit(); };
      im.src = `/api/review/${jobId}/preview.png`;
    } else fit();
    return;
  }
}

/* ── stages ─────────────────────────────────────────────────────────────── */
const STAGES = [
  {id:'pipes',   name:'1 · Pipe segmentation', colour:'#ef4444'},
  {id:'labels',  name:'2 · Labels + OCR',      colour:'#22c55e'},
  {id:'joins',   name:'3 · Joining points',    colour:'#a855f7'},
  {id:'leaders', name:'4 · Connection lines',  colour:'#38bdf8'},
  {id:'wall',    name:'Walls (excluded)',      colour:'#94a3b8'},
];
function refresh(){
  if (!doc) return;
  const box = $('#stages'); box.innerHTML = '';
  for (const s of STAGES){
    const el = document.createElement('div');
    el.className = 'stage' + (shown.has(s.id) ? '' : ' off');
    const total = active(doc[s.id]).length;
    const vis = ['labels', 'joins', 'leaders'].includes(s.id) ? shownObjs(s.id).length : total;
    el.innerHTML = `<span class="sw" style="background:${s.colour}"></span>`
                 + `<span class="nm">${s.name}</span>`
                 + `<span class="ct" title="${vis < total ? 'shown / detected' : ''}">`
                 + `${vis < total ? vis + '/' + total : total}</span>`;
    el.onclick = () => { shown.has(s.id) ? shown.delete(s.id) : shown.add(s.id);
                         refresh(); draw(); };
    box.appendChild(el);
  }
  $('#undo').disabled = !hist.past.length;
  $('#redo').disabled = !hist.future.length;
  inspector();
  renderResult();
  draw();
}

/* ── tools ──────────────────────────────────────────────────────────────── */
const TOOLS = [
  {id:'select',  key:'V', name:'Select',            hint:'Click to select · Shift adds · drag a box to marquee · Delete removes'},
  {id:'pan',     key:'H', name:'Pan',               hint:'Drag to pan the drawing.'},
  {id:'addpipe', key:'A', name:'Segment pipe by click', hint:'Click anywhere on a pipe the detector missed — the whole run is traced and added. Pipes inside walls are refused.'},
  {id:'draw',    key:'P', name:'Draw pipe',         hint:'Click points along the pipe CENTRELINE · Enter to finish — the mask is built for you · Esc cancels.'},
  {id:'wall',    key:'W', name:'Draw wall',         hint:'Click the corners of the wall area · Enter to close it. Walls are excluded from segmentation and classification.'},
  {id:'vertex',  key:'E', name:'Edit outline',      hint:'Drag a vertex · click an edge to add one · Alt-click a vertex to remove it.'},
  {id:'split',   key:'X', name:'Split pipe',        hint:'Two clicks: 1st the START, 2nd the END of the split line — across a pipe to cut it, or along the gap between two wrongly-merged parallel pipes.'},
  {id:'merge',   key:'M', name:'Merge selected',    hint:'Select two or more pipes, then press this.'},
  {id:'label',   key:'L', name:'Add label',         hint:'Drag a box around the label text — the code is read for you.'},
  {id:'join',    key:'J', name:'Add joining point', hint:'Click on a pipe — it snaps to the centreline and takes the nearest label’s class.'},
  {id:'connect', key:'C', name:'Draw connection',   hint:'Click the label box, then the joining point (or the pipe) it points at. A valid connection has a label on one end and a joining point on the other.'},
  {id:'link',    key:'K', name:'Link → set class',  hint:'Click a pipe or joining point, then a label box, to set its class.'},
];
let draft = null;      // in-progress polygon / connect / link
function setTool(t){
  tool = t; draft = null;
  for (const b of document.querySelectorAll('#tools button'))
    b.classList.toggle('on', b.dataset.tool === t);
  const d = TOOLS.find(x => x.id === t);
  $('#toolHint').textContent = d ? d.hint : '';
  cv.style.cursor = (t === 'pan') ? 'grab'
                  : (t === 'select' ? 'default' : 'crosshair');
  // a tool that needs a layer turns it back on (classification hides the
  // label/join layers, which used to leave Link and Connect unable to hit
  // anything — "doesn't work")
  const need = {link: ['labels', 'pipes'], connect: ['labels', 'joins', 'pipes'],
                label: ['labels'], join: ['pipes', 'joins'],
                split: ['pipes'], vertex: ['pipes']}[t] || [];
  let changed = false;
  for (const layer of need)
    if (!shown.has(layer)){ shown.add(layer); changed = true; }
  if (changed && doc) refresh();
  draw();
}
function buildTools(){
  const box = $('#tools'); box.innerHTML = '';
  for (const t of TOOLS){
    const b = document.createElement('button');
    b.className = 'ghost tool'; b.dataset.tool = t.id;
    b.innerHTML = `${t.name} <kbd>${t.key}</kbd>`;
    b.onclick = () => (t.id === 'merge') ? mergeSelected() : setTool(t.id);
    box.appendChild(b);
  }
}

/* ── edit operations ────────────────────────────────────────────────────── */
function addPipeRing(ring, origin){
  const p = {id: uid('P'), polygon: ring, type:'Unknown', source:'auto',
             origin: origin || 'manual', deleted:false,
             area:+polyArea(ring).toFixed(2), joins:[]};
  doc.pipes.push(p);
  doc.base_pipes.push(JSON.parse(JSON.stringify(p)));
  return p;
}

/* Classification rebuilds from base_pipes, so every pipe removal must reach
   BOTH lists — otherwise merged/deleted pipes come back from the dead the
   moment classification runs. */
function killPipe(p){
  p.deleted = true;
  const b = (doc.base_pipes || []).find(x => x.id === p.id);
  if (b) b.deleted = true;
}
function syncBasePipe(p){
  const b = (doc.base_pipes || []).find(x => x.id === p.id);
  if (b) b.polygon = JSON.parse(JSON.stringify(p.polygon));
}
function removeSelected(){
  if (!sel.length) return;
  act(`Delete ${sel.length} item${sel.length===1?'':'s'}`, () => {
    const walls = sel.filter(s => s.kind === 'wall').map(s => s.id)
                     .sort((a, b) => b - a);
    for (const i of walls) doc.wall.splice(i, 1);
    for (const s of sel){
      if (s.kind === 'wall') continue;
      const o = byId(s.kind, s.id);
      if (!o) continue;
      if (s.kind === 'pipes') killPipe(o);
      else o.deleted = true;
    }
    sel = [];
  });
  status('Removed — classification will run on what is left');
}

async function segmentByClick(wx, wy){
  for (const r of doc.wall || [])
    if (r.length >= 3 && pointInRing(r, wx, wy)){
      status('That point is inside a wall region — pipes are not segmented there','err');
      return;
    }
  status('Tracing the pipe under the cursor…');
  try {
    const j = await post(`/api/review/${jobId}/segment`,
                         {x:wx, y:wy, walls: doc.wall || []});
    let p;
    act('Segment pipe by click', () => { p = addPipeRing(j.polygon, 'manual'); });
    sel = [{kind:'pipes', id:p.id}];
    refresh();
    status(`Added ${p.id} — traced ${j.segments} segments (${j.length} pt)`, 'ok');
  } catch(e){ status(e.message, 'err'); }
}

async function mergeSelected(){
  const ps = sel.filter(s => s.kind === 'pipes').map(s => byId('pipes', s.id)).filter(Boolean);
  if (ps.length < 2){ status('Select two or more pipes first','err'); return; }
  try {
    const {rings} = await post('/api/geometry/merge', {rings: ps.map(p => p.polygon)});
    if (!rings || !rings.length) throw new Error('merge produced no geometry');
    const type = ps.find(p => p.type && p.type !== 'Unknown')?.type || 'Unknown';
    act(`Merge ${ps.length} pipes`, () => {
      for (const p of ps) killPipe(p);
      for (const r of rings){ const n = addPipeRing(r, 'manual'); n.type = type; }
    });
    sel = [];
    refresh();
    status(`Merged ${ps.length} pipes into ${rings.length}`, 'ok');
  } catch(e){ status(`Merge failed: ${e.message}`,'err'); }
}

async function mergeSamePipe(){
  if (!doc) return;
  const alive = active(doc.pipes);
  status('Looking for pipes split into pieces…');
  try {
    const {groups, skipped} = await post('/api/geometry/automerge',
      {rings: alive.map(p => p.polygon)});
    const held = skipped ? ` · ${skipped} left alone` : '';
    if (!groups || !groups.length){
      status('No split pipes found — every polygon is already one pipe' + held);
      return;
    }
    let absorbed = 0;
    act(`Merge same pipe (${groups.length})`, () => {
      for (const g of groups){
        const members = g.indices.map(i => alive[i]);
        const type = members.find(p => p.type && p.type !== 'Unknown')?.type || 'Unknown';
        for (const m of members){ killPipe(m); absorbed++; }
        addPipeRing(g.ring, 'manual').type = type;
      }
    });
    refresh();
    status(`Merged ${absorbed} polygons into ${groups.length} pipes${held}`, 'ok');
  } catch(e){ status(`Merge failed: ${e.message}`,'err'); }
}

/* Split with a drawn LINE, not a point: across a pipe to cut it in two, or
   along the gap between two parallel pipes that were wrongly merged into one
   mask.  Every pipe the line touches is offered to the server; the ones it
   genuinely separates are replaced by their pieces. */
async function applySplitLine(a, b){
  const targets = active(doc.pipes).filter(p => segCrossesRing(p.polygon, a, b));
  if (!targets.length){ status('That line does not touch any pipe','err'); return; }
  status('Splitting…');
  const results = [];
  for (const p of targets){
    try {
      const {rings} = await post('/api/geometry/splitline',
                                 {ring: p.polygon, line: [a, b]});
      if (rings && rings.length >= 2) results.push({pipe: p, rings});
    } catch { /* the line does not separate this pipe; others may still split */ }
  }
  if (!results.length){
    status('Could not split there — draw the line all the way across the pipe '
         + '(or along the full gap between the two merged pipes)','err');
    return;
  }
  let made = 0;
  act('Split pipe by line', () => {
    for (const {pipe, rings} of results){
      killPipe(pipe);
      for (const r of rings){ const n = addPipeRing(r, pipe.origin); n.type = pipe.type; made++; }
    }
  });
  refresh();
  status(`Split ${results.length} pipe${results.length===1?'':'s'} into ${made} pieces`, 'ok');
}

/* Draw pipe: the user traces the CENTRELINE; the mask is buffered server-side
   the same way the automatic segmentation builds its polygons. */
async function finishDrawPipe(){
  const path = draft.points.slice();
  draft = null; draw();
  status('Building the pipe mask from the centreline…');
  try {
    const {ring} = await post('/api/geometry/buffer', {path});
    let p;
    act('Draw pipe', () => { p = addPipeRing(ring, 'manual'); });
    sel = [{kind:'pipes', id:p.id}];
    refresh();
    status(`Added ${p.id} from the drawn centreline`, 'ok');
  } catch(e){ status(e.message, 'err'); }
}

/* Draw wall: close the clicked outline into a ring, store it as an excluded
   region, and clip every pipe underneath it. */
async function finishWall(){
  const ring = [...draft.points, draft.points[0].slice()];
  draft = null; draw();
  const alive = active(doc.pipes);
  let groups = [];
  try {
    ({groups} = await post('/api/geometry/clipwall',
                           {rings: alive.map(p => p.polygon), wall: [ring]}));
  } catch(e){
    groups = [];
    status(`Wall added, but clipping the pipes under it failed: ${e.message}`,'warn');
  }
  act('Draw wall', () => {
    doc.wall.push(ring);
    for (const g of groups || []){
      const p = alive[g.index];
      if (!p) continue;
      killPipe(p);
      for (const r of g.rings){ const n = addPipeRing(r, p.origin); n.type = p.type; }
    }
  });
  refresh();
  const n = (groups || []).length;
  status(`Wall added — excluded from segmentation${n ? `, ${n} pipe${n===1?'':'s'} clipped` : ''}`, 'ok');
}

/* Box a label and the text is READ for you — no typing. The new label is left
   selected so a wrong reading is one click away in the inspector, which is the
   only place the user should ever have to type a code. */
async function addLabelBox(rect){
  status('Reading the label…');
  let code = '', failed = null;
  try { code = ((await post(`/api/review/${jobId}/ocr`, {rect})).code || '').trim(); }
  catch(e){ failed = e.message; }
  let l;
  act('Add label', () => {
    l = {id: uid('L'), code, rect, conf: code ? 100 : -1, source:'manual',
         deleted:false, block: rect.slice()};
    doc.labels.push(l);
  });
  sel = [{kind:'labels', id:l.id}];
  refresh();
  if (code) status(`Added ${l.id} — read “${code}”`, 'ok');
  else status(failed ? `${l.id} added, but OCR failed (${failed}) — set the text below`
                     : `${l.id} added, but nothing legible in that box — set the text below`,
              'warn');
}

/* nearest label within reach, so a new joining point inherits a class the way
   the local tool does rather than asking for one */
function nearestLabel(x, y, reach = 140){
  let best = null, bd = reach;
  for (const l of active(doc.labels)){
    const [x0,y0,x1,y1] = l.rect;
    const dx = Math.max(x0-x, 0, x-x1), dy = Math.max(y0-y, 0, y-y1);
    const d = Math.hypot(dx, dy);
    if (d < bd){ bd = d; best = l; }
  }
  return best;
}

function addJoinAt(wx, wy){
  const snap = snapToPipe(wx, wy);
  if (!snap){ status('Click on a pipe','err'); return; }
  const lab = nearestLabel(snap.point[0], snap.point[1]);
  let j;
  act('Add joining point', () => {
    j = {id: uid('J'), point: snap.point.map(v => +v.toFixed(2)), radius: autoJoinRadius(),
         code: lab ? lab.code : '', labelId: lab ? lab.id : null,
         pipeId: snap.pipe.id, pipeIds:[snap.pipe.id], anchor:null,
         source:'manual', labelSource:'auto', deleted:false};
    doc.joins.push(j);
    // The link IS the connection.  Classification only cuts a pipe at a
    // joining point that is connected to a label, and used to look for a
    // drawn line to prove it — a joining point placed here had none, so it
    // never split anything.  Record the link the way Draw connection does:
    // a hint line (not drawn on the sheet) from the label to the point.
    if (lab){
      const anchor = [(lab.rect[0]+lab.rect[2])/2, (lab.rect[1]+lab.rect[3])/2];
      j.anchor = anchor;
      doc.leaders.push({id: uid('E'), labelId: lab.id, joinId: j.id,
                        path: [[anchor, j.point.slice()]], code: lab.code,
                        source:'manual', drawn:false, deleted:false});
    }
  });
  sel = [{kind:'joins', id:j.id}];
  refresh();
  status(lab ? `Joining point added — splits ${snap.pipe.id} here on classification, `
             + `class “${lab.code}” from ${lab.id} (K to link another label)`
             : `Joining point added — no label nearby: it splits ${snap.pipe.id} `
             + `on classification; link a label with K to give it a class`, 'ok');
}

function snapToPipe(x, y, tol){
  tol = tol || Math.max(8, 14/view.z);
  let best = null, bd = tol;
  for (const p of active(doc.pipes)){
    const c = closestOnRing(p.polygon, x, y);
    if (c.dist < bd){ bd = c.dist; best = {point: c.point, pipe: p}; }
  }
  return best;
}

/* Draw connection onto an EXISTING joining point: label on one end, joining
   point on the other — the definition of a valid connection. */
function connectLabelToJoin(label, j){
  act('Draw connection', () => {
    j.labelId = label.id; j.code = label.code; j.labelSource = 'manual';
    const anchor = [(label.rect[0]+label.rect[2])/2, (label.rect[1]+label.rect[3])/2];
    const e = active(doc.leaders).find(x => x.joinId === j.id);
    if (e){ e.labelId = label.id; e.code = label.code;
            e.path = [[anchor, j.point.slice()]]; e.drawn = false; }
    else doc.leaders.push({id: uid('E'), labelId: label.id, joinId: j.id,
                           path: [[anchor, j.point.slice()]], code: label.code,
                           source:'manual', drawn:false, deleted:false});
  });
  refresh();
  status(`Connected “${label.code}” to ${j.id}`, 'ok');
}

function connectLabelToPipe(label, wx, wy){
  const snap = snapToPipe(wx, wy);
  if (!snap){ status('Click on the pipe the label points at','err'); return; }
  act('Draw connection', () => {
    const j = {id: uid('J'), point: snap.point.map(v => +v.toFixed(2)), radius: autoJoinRadius(),
               code: label.code, labelId: label.id, pipeId: snap.pipe.id,
               pipeIds:[snap.pipe.id], anchor:null, source:'manual',
               labelSource:'manual', deleted:false};
    doc.joins.push(j);
    const anchor = [(label.rect[0]+label.rect[2])/2, (label.rect[1]+label.rect[3])/2];
    doc.leaders.push({id: uid('E'), labelId: label.id, joinId: j.id,
                      path: [[anchor, j.point.slice()]], code: label.code,
                      source:'manual', drawn:false, deleted:false});
  });
  refresh();
  status(`Connected “${label.code}” to ${snap.pipe.id}`, 'ok');
}

function linkToLabel(target, label){
  act('Link to label', () => {
    if (target.kind === 'pipes'){
      const p = byId('pipes', target.id);
      p.type = label.code; p.source = 'manual';
    } else {
      const j = byId('joins', target.id);
      j.labelId = label.id; j.code = label.code; j.labelSource = 'manual';
      const e = active(doc.leaders).find(x => x.joinId === j.id);
      const anchor = [(label.rect[0]+label.rect[2])/2, (label.rect[1]+label.rect[3])/2];
      if (e){ e.labelId = label.id; e.code = label.code;
              e.path = [[anchor, j.point.slice()]]; e.drawn = false; }
      else doc.leaders.push({id: uid('E'), labelId: label.id, joinId: j.id,
                             path: [[anchor, j.point.slice()]], code: label.code,
                             source:'manual', drawn:false, deleted:false});
    }
  });
  refresh();
  status(`Linked to “${label.code}”`, 'ok');
}

/* ── inspector ──────────────────────────────────────────────────────────── */
function inspector(){
  const box = $('#inspect');
  if (!doc || sel.length !== 1){
    box.innerHTML = doc
      ? `<div class="muted">${sel.length ? sel.length + ' selected' : 'Nothing selected'}</div>`
      : '';
    return;
  }
  const s = sel[0];
  if (s.kind === 'wall'){
    const r = (doc.wall || [])[s.id];
    box.innerHTML = r
      ? `<div class="row"><span>Wall region</span><span>#${s.id + 1}</span></div>`
        + `<div class="row"><span>Vertices</span><span>${r.length - 1}</span></div>`
        + `<div class="muted" style="margin-top:6px">Excluded from segmentation `
        + `and classification · Delete removes it</div>`
      : '';
    return;
  }
  const o = byId(s.kind, s.id);
  if (!o){ box.innerHTML = ''; return; }
  let h = `<div class="row"><span>ID</span><span>${o.id}</span></div>`;
  if (s.kind === 'pipes'){
    h += `<div class="row"><span>Class</span><span>${o.type}</span></div>`
       + `<div class="row"><span>Source</span><span>${o.source}${o.origin==='manual'?' · drawn':''}</span></div>`
       + `<div class="row"><span>Vertices</span><span>${o.polygon.length}</span></div>`
       + `<button class="ghost tool" id="iClass">Set class…</button>`;
  } else if (s.kind === 'labels'){
    h += `<div class="row"><span>Code</span><span>${o.code || '—'}</span></div>`
       + (o.text && o.text.trim() !== (o.code || '').trim()
            ? `<div class="row"><span>Read</span><span style="white-space:pre-wrap">${esc(o.text)}</span></div>` : '')
       + (o.inherited
            ? `<div class="row"><span>Shared note</span><span title="written on the last label of the same connection line">${esc(o.inherited)}</span></div>` : '')
       + (o.score >= 0 ? `<div class="row"><span>Detector</span><span>${Math.round(o.score * 100)}%</span></div>` : '')
       + `<div class="row"><span>OCR</span><span>${o.conf >= 0 ? o.conf + '%' : '—'}</span></div>`
       + `<div class="row"><span>Elevation</span><span>${o.elevation != null ? o.elevation + ' m' : '—'}</span></div>`
       + `<button class="ghost tool" id="iText">Edit text…</button>`
       + `<button class="ghost tool" id="iElev">Set elevation…</button>`
       + `<div class="muted" style="margin-top:6px">Sewer (S) labels: the installation `
       + `elevation decides which stretch the label describes — gravity runs `
       + `higher → lower</div>`;
  } else if (s.kind === 'joins'){
    h += `<div class="row"><span>Class</span><span>${o.code || '—'}</span></div>`
       + (o.conf >= 0 ? `<div class="row"><span>Detector</span><span>${o.conf.toFixed(0)}%</span></div>` : '')
       + `<div class="row"><span>Radius</span><span>${(o.radius||6).toFixed(1)} pt</span></div>`
       + `<div class="muted" style="margin-top:6px">[ and ] resize · K links to a label</div>`;
  } else {
    h += `<div class="row"><span>Class</span><span>${o.code || '—'}</span></div>`
       + `<div class="row"><span>Drawn</span><span>${o.drawn === false ? 'hint' : 'from drawing'}</span></div>`;
  }
  box.innerHTML = h;
  const c = $('#iClass');
  if (c) c.onclick = () => {
    const v = prompt('Class code:', o.type === 'Unknown' ? '' : o.type);
    if (v === null) return;
    act('Set class', () => { o.type = v.trim() || 'Unknown'; o.source = 'manual'; });
    refresh();
  };
  const t = $('#iText');
  if (t) t.onclick = () => {
    const v = prompt('Label text:', o.code);
    if (v === null) return;
    act('Edit label text', () => { o.code = v.trim(); o.source = 'manual'; });
    refresh();
  };
  const ev = $('#iElev');
  if (ev) ev.onclick = () => {
    const v = prompt('Installation elevation in metres (empty to clear):',
                     o.elevation != null ? String(o.elevation) : '');
    if (v === null) return;
    const num = parseFloat(v.replace(',', '.'));
    if (v.trim() && !Number.isFinite(num)){ status('Not a number','err'); return; }
    act('Set label elevation', () => { o.elevation = v.trim() ? num : null; });
    refresh();
  };
}

/* ── classification ─────────────────────────────────────────────────────── */
$('#btnClassify').onclick = async () => {
  if (!doc) return;
  $('#btnClassify').disabled = true;
  status('Classifying the reviewed drawing…');
  try {
    const j = await post(`/api/review/${jobId}/classify`, {document: doc});
    doc = j.document; summary = j.summary;
    shown.delete('labels'); shown.delete('joins'); shown.delete('leaders');
    sel = [];
    hist.past.length = hist.future.length = 0;   // ids changed; snapshots stale
    refresh();
    status(`Classified ${j.summary.typedPipes} of ${active(doc.pipes).length} `
         + `pieces (${j.summary.inherited || 0} by continuation of the same pipe) — `
         + `pipes were split only at the ${j.summary.connected} joining points `
         + `connected to a label`, 'ok');
  } catch(e){ status(e.message,'err'); }
  finally { $('#btnClassify').disabled = false; }
};

function classColour(t){
  if (!t || t === 'Unknown') return '#ef4444';
  let h = 0; for (let i=0;i<t.length;i++) h = (h*31 + t.charCodeAt(i)) >>> 0;
  return `hsl(${h%360} 72% 58%)`;
}
/* The class legend is LIVE: recomputed on every refresh, so a manual Link
   moves a pipe out of Unknown immediately.  Every row is clickable and
   highlights the pipes carrying that class. */
function renderResult(){
  if (!doc) return;
  const alive = active(doc.pipes);
  const c = {};
  for (const p of alive){ const t = p.type || 'Unknown'; c[t] = (c[t]||0)+1; }
  const typedAny = Object.keys(c).some(t => t !== 'Unknown');
  if (!summary && !typedAny){ $('#result').style.display = 'none'; return; }
  const leg = $('#legend'); leg.innerHTML = '';
  Object.entries(c).sort((a,b)=>b[1]-a[1]).forEach(([t,n]) => {
    const d = document.createElement('div');
    d.style.cursor = 'pointer';
    d.title = `Click to highlight every “${t}” pipe`;
    d.innerHTML = `<span><span class="sw" style="display:inline-block;width:10px;`
                + `height:10px;border-radius:2px;background:${classColour(t)};`
                + `margin-right:7px"></span>${t}</span><span>${n}</span>`;
    d.onclick = () => {
      shown.add('pipes');
      sel = alive.filter(p => !p.deleted && (p.type || 'Unknown') === t)
                 .map(p => ({kind:'pipes', id:p.id}));
      refresh();
      status(`${sel.length} pipe${sel.length===1?'':'s'} with class “${t}” highlighted`);
    };
    leg.appendChild(d);
  });
  $('#result').style.display = 'block';
}
$('#dl').onclick = () => {
  const blob = new Blob([JSON.stringify({document:doc, summary}, null, 2)],
                        {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'review.json'; a.click();
  URL.revokeObjectURL(a.href);
};
$('#btnAutoMerge').onclick = mergeSamePipe;
$('#undo').onclick = undo;
$('#redo').onclick = redo;

/* ── canvas ─────────────────────────────────────────────────────────────── */
const cv = $('#stage'), ctx = cv.getContext('2d');
function resize(){
  const r = cv.parentElement.getBoundingClientRect();
  const dpr = Math.min(devicePixelRatio || 1, 2);
  cv.width = Math.max(1, r.width*dpr); cv.height = Math.max(1, r.height*dpr);
  cv.style.width = r.width+'px'; cv.style.height = r.height+'px';
  ctx.setTransform(dpr,0,0,dpr,0,0);
  // A fit computed while the pane had no width leaves zoom at 0 and the page
  // invisible; take the first real size instead.
  view.z > 0 ? draw() : fit();
}
addEventListener('resize', resize);
const pageW = () => doc ? doc.page[0] : 1000;
const pageH = () => doc ? doc.page[1] : 700;
function fit(){
  const r = cv.parentElement.getBoundingClientRect();
  const z = Math.min(r.width/pageW(), r.height/pageH())*0.94;
  if (!isFinite(z) || z <= 0) return;
  view.z = z;
  view.x = (r.width - pageW()*z)/2;
  view.y = (r.height - pageH()*z)/2;
  draw();
}
const toWorld = (sx, sy) => [(sx-view.x)/view.z, (sy-view.y)/view.z];
function ringPath(p){
  ctx.beginPath(); ctx.moveTo(p[0][0], p[0][1]);
  for (let i=1;i<p.length;i++) ctx.lineTo(p[i][0], p[i][1]);
  ctx.closePath();
}
const isSel = (k,id) => sel.some(s => s.kind===k && s.id===id);

function draw(){
  const r = cv.parentElement.getBoundingClientRect();
  ctx.clearRect(0,0,r.width,r.height);
  if (!doc && !img) return;
  ctx.save(); ctx.translate(view.x, view.y); ctx.scale(view.z, view.z);
  ctx.fillStyle='#fff'; ctx.fillRect(0,0,pageW(),pageH());
  if (img) ctx.drawImage(img, 0, 0, pageW(), pageH());
  if (!doc){ ctx.restore(); return; }
  const px = 1/view.z;

  if (shown.has('wall') && doc.wall && doc.wall.length){
    ctx.fillStyle = 'rgba(148,163,184,.28)';
    ctx.strokeStyle = '#94a3b8'; ctx.lineWidth = 1.2*px;
    ctx.setLineDash([6*px, 4*px]);
    for (const r of doc.wall)
      if (r.length >= 3){ ringPath(r); ctx.fill(); ctx.stroke(); }
    ctx.setLineDash([]);
  }
  if (shown.has('pipes'))
    for (const p of active(doc.pipes)){
      // a pipe with an assigned class always wears its class colour — so a
      // manual Link shows its effect immediately, before classification runs
      ctx.fillStyle = (p.type && p.type !== 'Unknown') ? classColour(p.type)
                    : (summary ? '#ef4444'
                               : (p.origin === 'manual' ? '#f59e0b' : '#ef4444'));
      ctx.globalAlpha = .85; ringPath(p.polygon); ctx.fill(); ctx.globalAlpha = 1;
    }
  if (shown.has('leaders')){
    ctx.strokeStyle='#38bdf8'; ctx.lineWidth=0.9*px; ctx.globalAlpha=.9;
    for (const e of shownObjs('leaders')){
      ctx.beginPath();
      for (const [a,b] of (e.path||[])){ ctx.moveTo(a[0],a[1]); ctx.lineTo(b[0],b[1]); }
      ctx.stroke();
    }
    ctx.globalAlpha=1;
  }
  if (shown.has('labels')){
    ctx.lineWidth=1.1*px;
    for (const l of shownObjs('labels')){
      const [x0,y0,x1,y1] = l.rect;
      ctx.strokeStyle = l.source === 'manual' ? '#111111' : '#22c55e';
      ctx.strokeRect(x0,y0,x1-x0,y1-y0);
      if (view.z > 1.1){ ctx.fillStyle='#22c55e'; ctx.font = '7px ui-monospace,monospace';
                         ctx.fillText(l.code||'', x0, y0-1.5); }
    }
  }
  if (shown.has('joins'))
    for (const j of shownObjs('joins')){
      const c = joinColour(j);           // black = placed by hand
      ctx.strokeStyle=c; ctx.lineWidth=1.1*px;
      ctx.beginPath(); ctx.arc(j.point[0], j.point[1],
        Math.max(j.radius||6, 1.5*px), 0, 6.2832); ctx.stroke();
      ctx.fillStyle=c;
      ctx.beginPath(); ctx.arc(j.point[0], j.point[1], 1.3*px, 0, 6.2832); ctx.fill();
    }

  /* vertex handles while editing an outline */
  if (tool === 'vertex' && sel.length === 1 && sel[0].kind === 'pipes'){
    const p = byId('pipes', sel[0].id);
    if (p){ ctx.fillStyle='#fff'; ctx.strokeStyle='#3b82f6'; ctx.lineWidth=1.2*px;
      for (const v of p.polygon){
        ctx.beginPath(); ctx.arc(v[0], v[1], 2.6*px, 0, 6.2832); ctx.fill(); ctx.stroke(); }
    }
  }

  /* selection + hover outlines */
  for (const s of sel) outline(s, '#fff', 2.2*px);
  if (hover && !isSel(hover.kind, hover.id)) outline(hover, '#93c5fd', 1.6*px);

  /* in-progress draft */
  if (draft && draft.points && draft.points.length){
    ctx.strokeStyle='#3b82f6'; ctx.lineWidth=1.8*px; ctx.setLineDash([5*px,4*px]);
    ctx.beginPath(); ctx.moveTo(draft.points[0][0], draft.points[0][1]);
    for (let i=1;i<draft.points.length;i++) ctx.lineTo(draft.points[i][0], draft.points[i][1]);
    if (draft.cursor) ctx.lineTo(draft.cursor[0], draft.cursor[1]);
    ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle='#3b82f6';
    for (const q of draft.points){ ctx.beginPath(); ctx.arc(q[0],q[1],2.6*px,0,6.2832); ctx.fill(); }
  }
  if (draft && draft.from && draft.cursor){
    ctx.strokeStyle='#f59e0b'; ctx.lineWidth=1.4*px; ctx.setLineDash([4*px,3*px]);
    ctx.beginPath(); ctx.moveTo(draft.from[0], draft.from[1]);
    ctx.lineTo(draft.cursor[0], draft.cursor[1]); ctx.stroke(); ctx.setLineDash([]);
  }
  if (marquee){
    ctx.fillStyle='rgba(59,130,246,.12)'; ctx.strokeStyle='#3b82f6'; ctx.lineWidth=1.2*px;
    const [a,b,c,d] = marquee;
    ctx.fillRect(a,b,c-a,d-b); ctx.strokeRect(a,b,c-a,d-b);
  }
  ctx.restore();
}

function outline(ref, colour, w){
  if (ref.kind === 'wall'){
    const r = (doc.wall || [])[ref.id]; if (!r) return;
    ctx.save(); ctx.strokeStyle = colour; ctx.lineWidth = w;
    ctx.shadowColor = colour; ctx.shadowBlur = 6/view.z;
    ringPath(r); ctx.stroke(); ctx.restore();
    return;
  }
  const o = byId(ref.kind, ref.id); if (!o) return;
  ctx.save(); ctx.strokeStyle = colour; ctx.lineWidth = w;
  ctx.shadowColor = colour; ctx.shadowBlur = 6/view.z;
  if (ref.kind === 'pipes'){ ringPath(o.polygon); ctx.stroke(); }
  else if (ref.kind === 'labels'){ const [a,b,c,d] = o.rect; ctx.strokeRect(a,b,c-a,d-b); }
  else if (ref.kind === 'joins'){ ctx.beginPath();
    ctx.arc(o.point[0], o.point[1], Math.max(o.radius||6, 2/view.z)+2/view.z, 0, 6.2832);
    ctx.stroke(); }
  else { ctx.beginPath();
    for (const [a,b] of (o.path||[])){ ctx.moveTo(a[0],a[1]); ctx.lineTo(b[0],b[1]); }
    ctx.stroke(); }
  ctx.restore();
}

/* ── hit testing: small, specific things win over big ones ──────────────── */
function hit(x, y){
  const tol = 6/view.z;
  if (shown.has('joins'))
    for (const j of shownObjs('joins'))
      if (Math.hypot(j.point[0]-x, j.point[1]-y) <= Math.max(j.radius||6, tol))
        return {kind:'joins', id:j.id};
  if (shown.has('labels'))
    for (const l of shownObjs('labels')){
      const [x0,y0,x1,y1] = l.rect;
      if (x>=x0-tol && x<=x1+tol && y>=y0-tol && y<=y1+tol) return {kind:'labels', id:l.id};
    }
  if (shown.has('leaders'))
    for (const e of shownObjs('leaders'))
      for (const [a,b] of (e.path||[])){
        const dx=b[0]-a[0], dy=b[1]-a[1], L=dx*dx+dy*dy;
        let t = L ? ((x-a[0])*dx + (y-a[1])*dy)/L : 0; t = Math.max(0, Math.min(1, t));
        if (Math.hypot(x-(a[0]+t*dx), y-(a[1]+t*dy)) <= tol) return {kind:'leaders', id:e.id};
      }
  if (shown.has('pipes'))
    for (const p of active(doc.pipes))
      if (pointInRing(p.polygon, x, y)) return {kind:'pipes', id:p.id};
  if (shown.has('wall'))
    for (let i = (doc.wall || []).length - 1; i >= 0; i--)
      if (doc.wall[i].length >= 3 && pointInRing(doc.wall[i], x, y))
        return {kind:'wall', id:i};
  return null;
}

/* ── interaction ────────────────────────────────────────────────────────── */
let drag = null, moved = false, marquee = null, vdrag = null, jdrag = null;
cv.addEventListener('pointerdown', e => {
  if (!doc){ return; }
  const r = cv.getBoundingClientRect();
  const w = toWorld(e.clientX-r.left, e.clientY-r.top);
  try { cv.setPointerCapture(e.pointerId); } catch { /* no live pointer */ }
  moved = false;
  drag = {x:e.clientX, y:e.clientY, w};

  if (tool === 'vertex' && sel.length === 1 && sel[0].kind === 'pipes'){
    const p = byId('pipes', sel[0].id);
    const tol = 5/view.z;
    for (let i = 0; i + 1 < p.polygon.length; i++){
      if (Math.hypot(p.polygon[i][0]-w[0], p.polygon[i][1]-w[1]) <= tol){
        if (e.altKey){
          begin();
          if (removeVertex(p.polygon, i)){ syncBasePipe(p); commit('Remove vertex'); }
          else { hist._pre = null; status('A polygon needs at least three points','err'); }
          drag = null; draw(); return;
        }
        begin(); vdrag = {pipe:p, i}; return;
      }
    }
    // Only a click ON the outline adds a point. Clicking away from it means
    // the user is reaching for another pipe, not asking for a vertex out in
    // open space.
    if (closestOnRing(p.polygon, w[0], w[1]).dist <= 8/view.z){
      begin();
      const idx = insertVertexAt(p.polygon, w[0], w[1]);
      if (idx >= 0) vdrag = {pipe:p, i:idx, added:true}; else hist._pre = null;
      return;
    }
  }
  if (tool === 'select' && !e.shiftKey){
    // pressing on a joining point starts a move; a release without moving
    // is an ordinary click (selection, handled on pointerup)
    const h = hit(w[0], w[1]);
    if (h && h.kind === 'joins'){
      begin();
      jdrag = {join: byId('joins', h.id), moved: false};
      return;
    }
  }
  if ((tool === 'select' || tool === 'label') && !e.shiftKey)
    marquee = [w[0], w[1], w[0], w[1]];
});

/* The point follows the mouse; a hint line to its label follows the point.
   A line traced from the drawing stays where the drawing has it. */
function moveJoinTo(j, w){
  const old = j.point.slice();
  j.point = [+w[0].toFixed(2), +w[1].toFixed(2)];
  for (const e of active(doc.leaders)){
    if (e.joinId !== j.id || e.drawn !== false) continue;
    for (const seg of (e.path || []))
      for (const pt of seg)
        if (Math.abs(pt[0]-old[0]) < 1e-6 && Math.abs(pt[1]-old[1]) < 1e-6){
          pt[0] = j.point[0]; pt[1] = j.point[1]; }
  }
}

cv.addEventListener('pointermove', e => {
  const r = cv.getBoundingClientRect();
  const w = toWorld(e.clientX-r.left, e.clientY-r.top);
  $('#coords').textContent = doc ? `x ${w[0].toFixed(1)}  y ${w[1].toFixed(1)} pt` : '';

  if (vdrag){ vdrag.pipe.polygon[vdrag.i] = [+w[0].toFixed(2), +w[1].toFixed(2)];
              if (vdrag.i === 0){ const L = vdrag.pipe.polygon.length-1;
                vdrag.pipe.polygon[L] = [+w[0].toFixed(2), +w[1].toFixed(2)]; }
              draw(); return; }

  if (draft && (draft.points || draft.from)){ draft.cursor = w; draw(); }

  if (!drag){
    if (doc && tool === 'select'){
      const h = hit(w[0], w[1]);
      if ((h && (!hover || hover.id !== h.id)) || (!h && hover)){ hover = h; draw(); }
      cv.style.cursor = (h && h.kind === 'joins') ? 'move' : 'default';
    }
    return;
  }
  if (Math.abs(e.clientX-drag.x) + Math.abs(e.clientY-drag.y) > 3) moved = true;

  if (jdrag){
    if (moved){ jdrag.moved = true; moveJoinTo(jdrag.join, w); draw(); }
    return;
  }

  if (marquee){ marquee[2] = w[0]; marquee[3] = w[1]; draw(); return; }
  // anything else that is a drag pans; the box tools returned above
  view.x += e.clientX-drag.x; view.y += e.clientY-drag.y;
  drag.x = e.clientX; drag.y = e.clientY; draw();
});

cv.addEventListener('pointerup', async e => {
  const wasDrag = moved, m = marquee, vd = vdrag, jd = jdrag;
  drag = null; marquee = null; vdrag = null; jdrag = null;
  if (!doc) return;
  const r = cv.getBoundingClientRect();
  const w = toWorld(e.clientX-r.left, e.clientY-r.top);

  if (jd){
    if (jd.moved){
      jd.join.pipeId = null; jd.join.pipeIds = [];      // recomputed by classification
      sel = [{kind:'joins', id: jd.join.id}];
      commit('Move joining point');
      status(`${jd.join.id} moved to ${jd.join.point[0]}, ${jd.join.point[1]} — `
           + `classification cuts the pipe at the new place`, 'ok');
      return;
    }
    hist._pre = null;                       // a click, not a move: select below
  }

  if (vd){ syncBasePipe(vd.pipe);
           commit(vd.added ? 'Add vertex' : 'Move vertex'); refresh(); return; }

  if (m && (Math.abs(m[2]-m[0]) > 2/view.z || Math.abs(m[3]-m[1]) > 2/view.z)){
    const [x0,y0,x1,y1] = [Math.min(m[0],m[2]), Math.min(m[1],m[3]),
                           Math.max(m[0],m[2]), Math.max(m[1],m[3])];
    if (tool === 'label'){ await addLabelBox([+x0.toFixed(2),+y0.toFixed(2),
                                              +x1.toFixed(2),+y1.toFixed(2)]); return; }
    sel = [];
    for (const p of active(doc.pipes)){
      const c = centroid(p.polygon);
      if (c[0]>=x0 && c[0]<=x1 && c[1]>=y0 && c[1]<=y1) sel.push({kind:'pipes', id:p.id});
    }
    for (const j of shownObjs('joins'))
      if (j.point[0]>=x0 && j.point[0]<=x1 && j.point[1]>=y0 && j.point[1]<=y1)
        sel.push({kind:'joins', id:j.id});
    refresh(); status(`${sel.length} selected`);
    return;
  }

  if (wasDrag) return;

  switch (tool){
    case 'split': {
      if (!draft || !draft.split){
        draft = {from: [+w[0].toFixed(2), +w[1].toFixed(2)],
                 cursor: [w[0], w[1]], split: true};
        status('Now click the END point of the split line');
      } else {
        const from = draft.from;
        draft = null; draw();
        if (Math.hypot(w[0]-from[0], w[1]-from[1]) > 2/view.z)
          await applySplitLine(from, [+w[0].toFixed(2), +w[1].toFixed(2)]);
        else
          status('Click two different points: first the start, then the end '
               + 'of the split line','err');
      }
      return;
    }
    case 'addpipe': await segmentByClick(+w[0].toFixed(2), +w[1].toFixed(2)); return;
    case 'draw':
    case 'wall': {
      draft = (draft && draft.points) ? draft : {points: []};
      draft.points.push([+w[0].toFixed(2), +w[1].toFixed(2)]);
      draw(); return;
    }
    case 'join': addJoinAt(w[0], w[1]); return;
    case 'connect': {
      const h = hit(w[0], w[1]);
      if (!draft){
        if (h && h.kind === 'labels'){ draft = {label: byId('labels', h.id), from:
            [(byId('labels',h.id).rect[0]+byId('labels',h.id).rect[2])/2,
             (byId('labels',h.id).rect[1]+byId('labels',h.id).rect[3])/2]};
          status(`Now click the joining point (or the pipe) “${draft.label.code}” points at`); }
        else if (h && h.kind === 'joins'){
          const j = byId('joins', h.id);
          draft = {join: j, from: j.point.slice()};
          status('Now click the label box this joining point connects to');
        }
        else status('Start by clicking the label box (or a joining point)','err');
      } else if (draft.label){
        if (h && h.kind === 'joins') connectLabelToJoin(draft.label, byId('joins', h.id));
        else connectLabelToPipe(draft.label, w[0], w[1]);
        draft = null;
      } else if (draft.join){
        if (h && h.kind === 'labels'){ connectLabelToJoin(byId('labels', h.id), draft.join); draft = null; }
        else status('Click a label box','err');
      }
      return;
    }
    case 'link': {
      const h = hit(w[0], w[1]);
      if (!draft){
        if (h && (h.kind === 'pipes' || h.kind === 'joins')){
          draft = {target: h, from: h.kind === 'joins'
            ? byId('joins', h.id).point.slice() : centroid(byId('pipes', h.id).polygon)};
          status('Now click the label box to take the class from');
        } else status('Click a pipe or a joining point first','err');
      } else {
        if (h && h.kind === 'labels'){ linkToLabel(draft.target, byId('labels', h.id)); draft = null; }
        else status('Click a label box','err');
      }
      return;
    }
    default: {
      const h = hit(w[0], w[1]);
      if (!h){ if (!e.shiftKey) sel = []; }
      else if (e.shiftKey){
        const i = sel.findIndex(s => s.kind===h.kind && s.id===h.id);
        i >= 0 ? sel.splice(i,1) : sel.push(h);
      } else sel = [h];
      refresh();
    }
  }
});

cv.addEventListener('wheel', e => {
  e.preventDefault();
  const r = cv.getBoundingClientRect();
  const mx = e.clientX-r.left, my = e.clientY-r.top;
  const f = e.deltaY < 0 ? 1.12 : 1/1.12;
  view.x = mx-(mx-view.x)*f; view.y = my-(my-view.y)*f; view.z *= f; draw();
}, {passive:false});

/* ── keyboard ───────────────────────────────────────────────────────────── */
addEventListener('keydown', e => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key.toLowerCase() === 'z'){ e.preventDefault(); e.shiftKey ? redo() : undo(); return; }
  if (mod && e.key.toLowerCase() === 'a'){
    e.preventDefault();
    sel = active(doc?.pipes).map(p => ({kind:'pipes', id:p.id}));
    refresh(); status(`${sel.length} selected`); return;
  }
  if (mod) return;
  const k = e.key.toLowerCase();
  const t = TOOLS.find(x => x.key.toLowerCase() === k);
  if (t){ t.id === 'merge' ? mergeSelected() : setTool(t.id); return; }
  if (e.key === 'Enter' && draft && draft.points){
    if (tool === 'draw' && draft.points.length >= 2) finishDrawPipe();
    else if (tool === 'wall' && draft.points.length >= 3) finishWall();
    else status(tool === 'wall' ? 'Click at least three corners first'
                                : 'Click at least two points along the pipe first','err');
    return;
  }
  if (e.key === 'Escape'){ draft = null; sel = []; refresh(); return; }
  if (e.key === 'Delete' || e.key === 'Backspace'){ e.preventDefault(); removeSelected(); return; }
  if (e.key === 'f' || e.key === 'F'){ fit(); return; }
  if (e.key === '[' || e.key === ']'){
    const step = e.key === '[' ? -1 : 1;
    const js = sel.filter(s => s.kind === 'joins');
    if (!js.length) return;
    act('Resize joining point', () => {
      for (const s of js){ const j = byId('joins', s.id);
        j.radius = Math.max(1.5, Math.min(60, (j.radius || 6) + step)); }
    });
    refresh();
  }
  if (e.key === '1'){ shown.has('pipes') ? shown.delete('pipes') : shown.add('pipes'); refresh(); }
  if (e.key === '2'){ shown.has('labels') ? shown.delete('labels') : shown.add('labels'); refresh(); }
  if (e.key === '3'){ shown.has('joins') ? shown.delete('joins') : shown.add('joins'); refresh(); }
  if (e.key === '4'){ shown.has('leaders') ? shown.delete('leaders') : shown.add('leaders'); refresh(); }
  if (e.key === '5'){ shown.has('wall') ? shown.delete('wall') : shown.add('wall'); refresh(); }
});

$('#zin').onclick = () => { view.z *= 1.25; draw(); };
$('#zout').onclick = () => { view.z /= 1.25; draw(); };
$('#zfit').onclick = fit;

buildTools();
setTool('select');
resize();
window.__ui = {get doc(){return doc;}, get sel(){return sel;}, setTool, track,
               get view(){return view;}, get tool(){return tool;},
               hit, fit, undo, redo, mergeSamePipe, refresh, draw,
               get hist(){return hist;}};
