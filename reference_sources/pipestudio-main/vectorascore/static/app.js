// Stage-by-stage review UI: one tab per object type, feedback records per tab.
// Coordinates: review JSON is in page points; the background PNG is scale px/pt.
(() => {
  const $ = (s) => document.querySelector(s);
  const canvas = $("#c"), ctx = canvas.getContext("2d"), view = $("#view");
  let R = null, bg = null, sheet = null, feedback = { records: [] };
  let tab = "pipes", tool = null, selected = null, drawing = null;
  let feedbackHighlight=null;
  let N = null, noiseFilter = null, layerFilter = null;   // Noise tab: /api/noise payload, bucket / layer shown alone
  let role = "admin";                             // from /api/me: "admin" or "review" (feedback only)
  const author = () => { try { return localStorage.getItem("author") || ""; } catch (e) { return ""; } };
  function askAuthor(force) { if(force) Studio.askName(); $("#who").textContent=author()||"Set reviewer name"; }
  let readonly=false, loadToken=0, refreshingVectors=false;
  let tx = 0, ty = 0, zoom = 0.25;              // screen = page_pt * scale * zoom + t

  const COLORS = {
    pipe: "#d00", circle: "#08c", tick: "#0a0", leader: "#e80", leader_unanchored: "#c9a", leader_stub: "#c9a",
    lettering: "#999", thin_other: "#bbb", unknown: "#f0f",
  };
  // buckets no stage after bucket reads (serve.py USED_BUCKETS is the complement)
  const NOISE = { architecture: "#777", duplicate: "#e80", lettering: "#aaa", thin_other: "#8ac", unknown: "#f0f", bar: "#a52",
                  frame_pointer: "#0aa", leader_stub: "#c9a", leader_unanchored: "#c6c", circle_no_leader: "#08c", wall_label: "#66a" };
  const NODE = { tee: "#a0a", tick: "#0a0", circle: "#08c", leader_end: "#e80", gap: "#888", junction: "#c00", hairpin: "#80f", wall: "#000" };
  // what each joining-point kind is on the sheet (see assemble.py for how they are found)
  const NODE_DESC = {
    tick: "A short diagonal stroke at leader weight drawn across the pipe where a leader ends: the mid-run joining point, the label describes the stretch on one side of it.",
    circle: "An open connection circle sitting on the end of a pipe line: where a stretch starts or ends at a fixture, a wall connection or a take-off.",
    leader_end: "A leader touching the pipe with no tick and no circle: the leader's free end itself is the mark.",
    gap: "Either end of a bridged break in the drawn line (wall band, valve or component symbol, crossing): the run may continue unchanged or change designation there.",
    junction: "Three or more pipe pieces meeting at one point that is not a tee (no main runs straight through).",
    hairpin: "A turn sharper than the elbow limit inside one line: almost always two pipes wrongly joined, shown so it can be reported.",
    wall: "Where the pipe meets a hatched wall: the run is cut here, what lies inside the wall is out of scope, and the piece from here to the first mark carries no label.",
  };
  const CONFIDENCE_DASH = { high: [], medium: [12, 3], low: [5, 4] };
  const TOOLS = {
    pipes: [["missing_pipe", "missing pipe (draw a line)", "line"], ["missing_split", "missing split (click the stretch)", "click"],
            ["wrong_join", "wrong join (click the stretch)", "click"], ["false_pipe", "not a pipe (click the stretch)", "click"]],
    nodes: [["node_type", "correct point type", "click"], ["missing_node", "missing joining point (click)", "point"], ["false_node", "false joining point (click the marker)", "click"]],
    leaders: [["missing_leader", "missing leader (draw a line)", "line"], ["false_leader", "false leader (click)", "click"]],
    labels: [["missing_label", "missing label (draw a rectangle)", "rect"], ["label_text", "fix text (click the box)", "click"], ["false_label", "not a label (click)", "click"]],
    bindings: [["wrong_binding", "wrong binding (click the stretch, then pick the label)", "click"]],
    unknown: [["is_pipe", "this is a pipe (click)", "click"], ["is_leader", "this is a leader (click)", "click"]],
    noise: [],
  };

  // ---------- data ----------
  async function loadSheets() {
    const list = await (await fetch("/api/sheets")).json();
    const sel = $("#sheet"); sel.innerHTML = "";
    for (const s of list) {
      const o = document.createElement("option"); o.value = s.sheet;
      o.textContent = s.sheet + (s.has_review ? "" : " (no review yet)") + (s.job && s.job.status === "running" ? " ⏳" : "");
      sel.appendChild(o);
    }
    if (!sheet && list.length) sheet = list[0].sheet;
    if (sheet) sel.value = sheet;
  }
  async function loadSheet(s, preserveView=false) {
    const camera=preserveView&&s===sheet&&R?{scale:S(),tx,ty,page:[...R.page]}:null;
    const token=++loadToken; sheet=s; readonly=false; R=null; bg=null; selected=null; N=null; feedback={records:[]};Studio.renderMethodContext();
    Studio.busy(true,'Opening '+s+'…');
    try{
      const r=await fetch('/api/review?sheet='+encodeURIComponent(s));
      if(token!==loadToken)return;
      if(!r.ok){ $('#stats').textContent='No analysis yet';$('#canvas-empty').hidden=false;draw();return; }
      const rv=await r.json();if(token!==loadToken)return;R=rv;
      // the drawing appears as soon as it is read; its saved comments are a second,
      // slower read and must not hold the picture back
      showResult(R,'/api/bg?sheet='+encodeURIComponent(s)+'&t='+Date.now(),false,camera);
      Studio.busyMessage('Loading saved feedback for '+s+'…');
      const overview=await Studio.refresh();if(token!==loadToken)return;
      feedback={records:overview.feedback.filter(f=>f.sheet===s&&f.run_id===R.metadata?.run_id&&f.status!=='dismissed')};
      Studio.styleBadge(R);          // the style picker needs the style list this refresh brought
      renderFeedback();draw();
    } finally { Studio.busy(false); }
  }
  function showResult(rv,url,ro=true,camera=null){
    readonly=ro;R=rv;selected=null;feedbackHighlight=null;N=null;bg=new Image();
    const image=bg;
    bg.onload=()=>{
      if(bg!==image)return;
      if(camera&&camera.page[0]===R.page[0]&&camera.page[1]===R.page[1]){
        zoom=camera.scale/R.scale;tx=camera.tx;ty=camera.ty;
      }else fit();
      draw();
    };bg.src=url;
    if(ro)feedback={records:[]};indexData();renderStats();renderFeedback();setTab(tab);Studio.loaded(rv);
    $('#info').textContent=ro?'Saved analysis · read only':'Select an object to review.';
  }
  let statusRequest=0;
  async function refreshAssignmentStatus(){
    if(tab!=='bindings')return;
    const request=++statusRequest,box=$('#assignment-status');
    const show=(state,title,detail)=>{box.dataset.state=state;box.dataset.runId=R?.metadata?.run_id||'';$('#assignment-state').textContent=title;$('#assignment-detail').textContent=detail;Studio.renderMethodContext();};
    if(readonly){show('legacy','Saved snapshot · read only','This is a historical or evaluation result, not the current drawing.');return;}
    if(!R){show('missing','No assignments loaded','Select a processed drawing.');return;}
    if(!box.dataset.state||box.dataset.state==='checking')show('checking','Checking result freshness…','Comparing the result with the current rules.');
    try{
      const result=await Studio.api('analysis-status?sheet='+encodeURIComponent(sheet)+'&style_id='+encodeURIComponent(Studio.style()));
      if(request!==statusRequest||tab!=='bindings')return;
      if(result.run_id!==R.metadata?.run_id){show('stale','Result out of date','A newer saved result is available. Select the drawing again to load it.');return;}
      const titles={current:'Result up to date',stale:'Result out of date',legacy:'Result out of date',preview:'Result out of date',running:'Result out of date',missing:'No result'};
      const date=result.created_at?'Last analysis: '+new Date(result.created_at).toLocaleString('en-GB')+'. ':'';
      show(result.status,titles[result.status],date+(result.reasons.join(' ')||'The result matches the current style rules and analysis engine. Expert review is still required.'));
    }catch(e){show('legacy','Freshness unavailable','Could not verify this result. '+e.message);}
  }
  setInterval(()=>{if(tab==='bindings'&&!document.hidden)refreshAssignmentStatus();},10000);
  let byId = {};
  function indexData() {
    byId = { node: {}, stretch: {}, label: {}, leader: {}, path: {}, binding: {}, noise: {} };
    for (const n of R.nodes) byId.node[n.id] = n;
    for (const s of R.stretches) byId.stretch[s.id] = s;
    for (const l of R.labels) byId.label[l.id] = l;
    for (const l of R.leaders) byId.leader[l.id] = l;
    for (const p of R.paths) byId.path[p.id] = p;
    R.owner = {};
    for (const b of R.bindings) { if (!R.owner[b.stretch] || (R.owner[b.stretch].confidence === "low" && b.confidence !== "low")) R.owner[b.stretch] = b; }
    R.labelColor = {};
    R.labels.forEach((l, i) => { R.labelColor[l.id] = `hsl(${(i * 137) % 360} 80% 45%)`; });
  }
  // the whole pipe: walk up the attachment chain to the main, then collect every branch
  function family(sid) {
    const parent = {}, children = {};
    for (const n of R.nodes) if (n.on_stretch !== null && n.on_stretch !== undefined) for (const c of n.stretches) { parent[c] = n.on_stretch; (children[n.on_stretch] = children[n.on_stretch] || []).push(c); }
    let root = sid; const up = new Set();
    while (parent[root] !== undefined && !up.has(root)) { up.add(root); root = parent[root]; }
    const out = new Set(); const stack = [root];
    while (stack.length) { const s = stack.pop(); if (out.has(s)) continue; out.add(s); for (const c of children[s] || []) stack.push(c); }
    return out;
  }
  // a label is its designation(s) PLUS what OCR read next to them (VG/CL level, count, suffix)
  function labelCaption(l) {
    const des = l.designations.map(d => (d.count > 1 ? d.count + "x" : "") + d.raw + (d.dimension === null ? " (DN?)" : "")).join(" | ") || "?";
    return des + (l.level ? "  " + l.level.raw : "");
  }
  function renderStats() {
    const s = R.stats;
    const m = R.style?.match || {}, how = R.metadata?.style_match?.selection;   // auto | manual | fallback
    const styleNote = s.new_style === undefined ? "" :
      (m.manual ? `style ${m.style||'style-1'} (chosen; no detection) ` : m.selected && how !== 'manual' ? `detected style ${m.style} (d=${m.nearest_distance}) `
        : m.selected ? (m.mismatch ? `SELECTED STYLE ${m.style} DOES NOT MATCH THIS DRAWING (it matches ${m.nearest}, d=${m.nearest_distance}) ` : `selected style ${m.style} (drawing matches it, d=${m.nearest_distance}) `)
        : s.new_style ? `NEW STYLE (no known profile within reach; result uncertain) ` : `style ${s.style} (d=${s.style_distance}) `) +
      `u=${s.u_paper} pipe family by ${s.family_method} | `;
    $("#stats").textContent = styleNote + `paths pipe=${s.paths_by_bucket.pipe || 0} leader=${s.paths_by_bucket.leader || 0} unknown=${s.paths_by_bucket.unknown || 0} | ` +
      `stretches=${s.stretches} (in wall ${s.in_wall || 0}, entry stubs ${s.entry || 0}) nodes=${Object.values(s.nodes).reduce((a, b) => a + b, 0)} | labels ${s.labels_parsed}/${s.labels} parsed | ` +
      `leaders ${s.leaders_anchored}/${s.leaders} anchored (marks without leader: ${s.marks_without_leader || 0}, Nx short: ${s.nx_short || 0}) | bindings high=${s.bindings.high || 0} med=${s.bindings.medium || 0} low=${s.bindings.low || 0} | ` +
      `unbound stretches=${s.unbound_stretches} labels=${s.unbound_labels}`;
  }
  let nodeFilter = null;                            // kind shown alone in the Joining points tab
  function renderLegend() {
    const L = $("#legend"); L.innerHTML = "";
    const add = (name, col, kind, dash=[], shape='line') => {
      const sp = document.createElement("span");
      const sample=shape==='line'
        ? `<line x1="0" y1="7" x2="48" y2="7" stroke="${col}" stroke-width="3" stroke-dasharray="${dash.join(' ')}"/>`
        : shape==='square' ? `<rect x="19" y="2" width="10" height="10" fill="${col}"/>`
        : `<circle cx="24" cy="7" r="5" stroke="${col}" stroke-width="2" fill="${shape==='ring'?'white':col}"/>`;
      sp.innerHTML = `<svg class="legend-sample" width="48" height="14" aria-hidden="true">${sample}</svg>`;
      sp.appendChild(document.createTextNode(name));
      if (kind) {
        sp.classList.add("pick"); if (nodeFilter === kind) sp.classList.add("on");
        sp.onclick = () => { nodeFilter = nodeFilter === kind ? null : kind; renderLegend(); draw(); };
        if (nodeFilter === kind) { const x = document.createElement("b"); x.textContent = " ✕"; x.title = "clear filter"; x.onclick = (e) => { e.stopPropagation(); nodeFilter = null; renderLegend(); draw(); }; sp.appendChild(x); }
      }
      L.appendChild(sp);
    };
    if (tab === "pipes") { add("Colour identifies a pipe group (main and branches), not confidence", "#d00");
      add("Black rings mark stretch ends", "#000",null,[],'ring');
      if($('#raw-pipes').checked)add("Original pipe vectors", "#00f"); }
    if (tab === "nodes") {
      for (const k in NODE) if (k !== "tee" && k !== "end") { add(`${k.replaceAll("_"," ")} (${(R?.nodes||[]).filter(n=>n.kind===k).length})`, NODE[k], k, [], k==='tick'?'square':'dot'); L.lastChild.title = NODE_DESC[k] || ""; }
      const dl = document.createElement("dl"); dl.id = "legend-desc";
      for (const k in NODE_DESC) dl.innerHTML += `<dt><i style="background:${NODE[k]}"></i>${k}</dt><dd>${NODE_DESC[k]}</dd>`;
      L.appendChild(dl);
    }
    if (tab === "leaders") {
      add("Linked to a label", COLORS.leader);
      add("Linked label is invalid or unusable", COLORS.leader,null,[6,4]);
      add("No linked label", COLORS.leader_unanchored);
      add("Label anchor", "#000",null,[],'ring');
      add("Landing matched to a joining point", "#000",null,[],'dot');
      add("Landing without a matched joining point", "#f0f",null,[],'dot');
      add("Inferred landing from an Nx bundle", "#f0f",null,[],'ring');
      add("Joining point without a leader", "#d00",null,[],'ring');
      add("Nx count: reached / expected; green = sufficient, red = short", "#0a0");
    }
    if (tab === "labels") {
      add("Valid box with a parsed designation", "#0a0");
      add("Valid box without a parsed designation", "#d00");
      add("Invalid label box", "#aaa");
      add("System name from the vector layer (blue text)", "#08c");
    }
    if (tab === "bindings") {
      add("High confidence — solid", "#2d2d2d",null,CONFIDENCE_DASH.high);
      add("Medium confidence — long dashes", "#2d2d2d",null,CONFIDENCE_DASH.medium);
      add("Low confidence — short, frequent dashes", "#2d2d2d",null,CONFIDENCE_DASH.low);
      add("Unassigned stretch", "#999");
      const note=document.createElement('p');
      note.textContent='Colour links a label to its assigned stretches. Confidence applies to pipe strokes; thin dotted connectors are visual assignment guides. Blue marks the selected stretch; yellow marks related objects.';
      L.appendChild(note);
    }
    if (tab === "unknown") {
      const labels={unknown:'Unclassified vectors',thin_other:'Other thin vectors',lettering:'Vectors classified as lettering'};
      for(const k of Object.keys(labels))add(`${labels[k]} (${(R?.paths||[]).filter(p=>p.bucket===k).length})`,COLORS[k]);
    }
    if (tab === "noise") renderNoiseLegend(L, add);
  }
  // Noise tab: what the bucket stage set aside, by bucket and by OCG layer; nothing here is reported
  function renderNoiseLegend(L, add) {
    const p = document.createElement("p"); p.className = "readonly";
    p.textContent = "Read only. Vectors excluded from the downstream vector stages, grouped by bucket. Counts refer to vector paths. Use the Unknown tab to report a missed pipe or leader.";
    L.appendChild(p);
    if (!N) { L.appendChild(document.createTextNode("loading…")); return; }
    const per = {}; for (const q of N.paths) per[q.bucket] = (per[q.bucket] || 0) + 1;
    for (const k of Object.keys(per).sort()) {
      const sp = document.createElement("span"); sp.innerHTML = `<i style="background:${NOISE[k]||"#000"}"></i>${k.replaceAll("_"," ")} (${per[k]})`;
      sp.classList.add("pick"); if (noiseFilter === k) sp.classList.add("on");
      sp.onclick = () => { noiseFilter = noiseFilter === k ? null : k; renderLegend(); draw(); };
      L.appendChild(sp);
    }
    const C = R.calibration, lay = C.layers || {};
    const t = document.createElement("table");
    t.innerHTML = `<tr><th>layer${C.has_layers ? "" : " (sheet has no usable layers - verdicts by width only)"}</th><th>paths</th><th>pipe %</th><th>verdict</th><th>buckets</th></tr>`;
    for (const [name, v] of Object.entries(lay).sort((a, b) => b[1].count - a[1].count)) {
      const tr = document.createElement("tr"); tr.classList.add("pick"); if (layerFilter === name) tr.classList.add("on");
      const verdict = !C.has_layers ? "-" : C.pipe_layers.includes(name) ? "pipe layer" : "rejected";
      const bk = Object.entries(N.layers[name] || {}).sort((a, b) => b[1] - a[1]).map(([k, n]) => `${k} ${n}`).join(", ");
      tr.innerHTML = `<td class="name" title="${name}">${name || "(none)"}</td><td class="n">${v.count}</td><td class="n">${Math.round(v.pipe_share * 100)}</td><td class="n">${verdict}</td><td class="bk">${bk}</td>`;
      tr.onclick = () => { layerFilter = layerFilter === name ? null : name; renderLegend(); draw(); };
      t.appendChild(tr);
    }
    L.appendChild(t);
  }
  const noisePaths = () => (N ? N.paths.filter(q => (noiseFilter === null || q.bucket === noiseFilter) && (layerFilter === null || (q.layer || "") === layerFilter)) : []);

  // ---------- view transform ----------
  const S = () => (R ? R.scale : 2) * zoom;
  const toScreen = (x, y) => [x * S() + tx, y * S() + ty];
  const toPage = (sx, sy) => [(sx - tx) / S(), (sy - ty) / S()];
  const pointer = e => {const rect=view.getBoundingClientRect();return [e.clientX-rect.left,e.clientY-rect.top];};
  let zoomFrame=null;
  function scheduleDraw(){if(zoomFrame===null)zoomFrame=requestAnimationFrame(()=>{zoomFrame=null;draw();});}
  function zoomAt(scale,x=view.clientWidth/2,y=view.clientHeight/2){
    if(!R||drawing)return;
    const page=toPage(x,y);zoom=Math.max(.02,Math.min(16,scale))/R.scale;
    tx=x-page[0]*S();ty=y-page[1]*S();scheduleDraw();
  }
  function updateZoomControls(){
    $('#zoom-current').textContent=Math.round(S()*100)+'%';$('#zoom-level').value='current';
    $('#zoom-out').disabled=!R||S()<=.020001;$('#zoom-in').disabled=!R||S()>=15.9999;
  }
  function fit() {
    if (!R) return;
    const w = view.clientWidth || (innerWidth - 340), h = view.clientHeight || (innerHeight - 130);
    if (w <= 0 || h <= 0) return;
    zoom = Math.max(.02,Math.min(16,Math.min((w-40)/R.page[0],(h-40)/R.page[1])))/R.scale;
    tx = (w - R.page[0] * S()) / 2; ty = (h - R.page[1] * S()) / 2;
  }
  function resize() {
    const w=view.clientWidth,h=view.clientHeight;if(w<=0||h<=0)return;
    if(canvas.width!==w||canvas.height!==h){
      // Keep the viewed position and zoom when the sidebar/window changes size.
      tx+=(w-canvas.width)/2;ty+=(h-canvas.height)/2;canvas.width=w;canvas.height=h;
    }
    draw();
  }
  window.addEventListener("resize", resize);
  new ResizeObserver(resize).observe(view);

  // ---------- drawing ----------
  function draw() {
    updateZoomControls();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.fillStyle = "#eef0f4"; ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!R || !bg) return;
    ctx.setTransform(S(), 0, 0, S(), tx, ty);
    ctx.drawImage(bg, 0, 0, R.page[0], R.page[1]);
    const dim = $("#show-others").checked;
    const lw = (w) => w / S();
    const poly = (pts) => { ctx.beginPath(); pts.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.stroke(); };
    const dot = (x, y, r, fill) => { ctx.beginPath(); ctx.arc(x, y, r / S(), 0, 7); if (fill) { ctx.fillStyle = fill; ctx.fill(); } else ctx.stroke(); };

    if (tab === "noise") {
      for (const p of noisePaths()) {
        const sel = selected && selected.type === "path" && selected.id === p.id;
        ctx.strokeStyle = sel ? "#ff0" : NOISE[p.bucket] || "#000"; ctx.lineWidth = lw(sel ? 4 : p.bucket === "unknown" ? 2.5 : 1);
        for (const s of p.segs) poly([[s[0], s[1]], [s[2], s[3]]]);
      }
    }
    if (tab === "unknown") {
      for (const p of R.paths) if (["unknown", "thin_other", "lettering"].includes(p.bucket)) {
        ctx.strokeStyle = COLORS[p.bucket]; ctx.lineWidth = lw(p.bucket === "unknown" ? 3 : 1);
        for (const s of p.segs) poly([[s[0], s[1]], [s[2], s[3]]]);
      }
    }
    if (tab === "pipes" && $("#raw-pipes").checked) {
      for (const p of R.paths) if (p.bucket === "pipe") { ctx.strokeStyle = "#00f"; ctx.lineWidth = lw(2); for (const s of p.segs) poly([[s[0], s[1]], [s[2], s[3]]]); }
    }
    if ($("#show-walls").checked) { ctx.fillStyle = "rgba(0,0,255,0.12)"; for (const w of R.walls || []) { ctx.beginPath(); for (const ring of [w.shell, ...w.holes]) { ring.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); } ctx.fill("evenodd"); } }
    // stretches: always drawn, colour depends on tab; in-wall ones hidden unless asked
    const showWall = $("#show-inwall").checked;
    for (const s of R.stretches) {
      if (s.in_wall && !showWall) continue;
      let col = "#d00", w = 3, dash = [];
      if (tab === "pipes") { col = `hsl(${(s.pipe * 47) % 360} 85% 40%)`; }   // one pipe (main + branches) = one colour
      else if (tab === "bindings") {
        const b = R.owner[s.id];
        if (b) { col = R.labelColor[b.label]; w = 4; dash = (CONFIDENCE_DASH[b.confidence] || CONFIDENCE_DASH.low).map(n=>n/S()); }
        else { col = "#999"; w = 2; }
      } else if (dim) { col = "rgba(200,0,0,0.25)"; w = 2; }
      if (selected && selected.family && selected.family.has(s.id)) { col = "#ff0"; w = 7; }
      ctx.strokeStyle = col; ctx.lineWidth = lw(w); ctx.setLineDash(dash); poly(s.points); ctx.setLineDash([]);
      if (tab === "pipes" || tab === "bindings") { // end marks
        for (const p of [s.points[0], s.points[s.points.length - 1]]) { ctx.strokeStyle = "#000"; ctx.lineWidth = lw(1); dot(p[0], p[1], 3); }
      }
    }
    if (tab === "bindings" && R.runs) {
      // flow direction per run: one light arrow on every piece (small and
      // translucent so it hides nothing), pointing the way the run flows
      for (const r of R.runs) {
        const seq = r.flow === "backward" ? [...r.stretches].reverse() : r.stretches;
        for (const p of r.pieces) {
          const sids = r.flow === "backward" ? [...p.stretches].reverse() : p.stretches;
          const pts = [];
          for (const sid of sids) {
            const st = byId.stretch[sid]; if (!st) continue;
            let q = st.points;
            if (pts.length && (Math.abs(pts[pts.length - 1][0] - q[0][0]) > 0.5 || Math.abs(pts[pts.length - 1][1] - q[0][1]) > 0.5) &&
                !(Math.abs(pts[pts.length - 1][0] - q[q.length - 1][0]) > 0.5 || Math.abs(pts[pts.length - 1][1] - q[q.length - 1][1]) > 0.5)) q = [...q].reverse();
            else if (!pts.length && sids.length > 1) { const nx = byId.stretch[sids[1]]; if (nx && (Math.abs(q[0][0] - nx.points[0][0]) < 0.5 && Math.abs(q[0][1] - nx.points[0][1]) < 0.5 || Math.abs(q[0][0] - nx.points[nx.points.length - 1][0]) < 0.5 && Math.abs(q[0][1] - nx.points[nx.points.length - 1][1]) < 0.5)) q = [...q].reverse(); }
            pts.push(...q);
          }
          if (pts.length < 2) continue;
          let total = 0; for (let i = 1; i < pts.length; i++) total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
          if (total < 6) continue;
          let acc = 0, a = pts[0], b = pts[1];
          for (let i = 1; i < pts.length; i++) { const d = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]); if (acc + d >= total / 2) { a = pts[i - 1]; b = pts[i]; break; } acc += d; }
          const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), mx = (a[0] + b[0]) / 2, my = (a[1] + b[1]) / 2, L = 5 / S();
          ctx.save(); ctx.globalAlpha = 0.45; ctx.strokeStyle = p.label === null ? "#666" : "#222"; ctx.lineWidth = lw(1.2); ctx.setLineDash([]);
          ctx.beginPath(); ctx.moveTo(mx - L * Math.cos(ang - 0.5), my - L * Math.sin(ang - 0.5)); ctx.lineTo(mx, my); ctx.lineTo(mx - L * Math.cos(ang + 0.5), my - L * Math.sin(ang + 0.5)); ctx.stroke(); ctx.restore();
        }
      }
    }
    if (tab === "bindings") {
      // helper line only for bindings that have no leader (orphan / propagated across the sheet)
      for (const b of R.bindings) {
        if (b.node !== null && b.node !== undefined) continue;
        const l = byId.label[b.label]; if (!l) continue;
        const s = byId.stretch[b.stretch]; if (!s) continue;
        if (R.leaders.some(x => x.label === b.label)) continue;
        const m = s.points[Math.floor(s.points.length / 2)];
        ctx.strokeStyle = R.labelColor[b.label]; ctx.lineWidth = lw(1); ctx.setLineDash([2 / S(), 2 / S()]);
        poly([[(l.rect[0] + l.rect[2]) / 2, (l.rect[1] + l.rect[3]) / 2], m]); ctx.setLineDash([]);
      }
    }
    if (tab === "nodes" || tab === "pipes" || tab === "bindings") {
      for (const n of R.nodes) {
        let col = NODE[n.kind] || "#000"; const r = tab === "nodes" ? 5 : 3;
        if (tab === "bindings") { const bn = R.bindings.find(b => b.node === n.id); col = bn ? R.labelColor[bn.label] : "#999"; }
        if (n.kind === "tee" || n.kind === "end") continue;   // a branch attachment / a bare pipe end is not a joining point
        if (tab === "nodes" && nodeFilter && n.kind !== nodeFilter) continue;
        ctx.fillStyle = col; ctx.strokeStyle = "#000"; ctx.lineWidth = lw(1);
        if (tab !== "nodes" && dim) ctx.globalAlpha = 0.6;
        if (n.kind === "circle") dot(n.x, n.y, r + 1, col);
        else if (n.kind === "tick") { ctx.beginPath(); ctx.rect(n.x - r / S(), n.y - r / S(), 2 * r / S(), 2 * r / S()); ctx.fill(); }
        else dot(n.x, n.y, r, col);
        if (selected && selected.type === "node" && selected.id === n.id) { ctx.strokeStyle = "#ff0"; ctx.lineWidth = lw(3); dot(n.x, n.y, r + 5); }
        ctx.globalAlpha = 1;
      }
    }
    if ($("#show-ml").checked) for (const j of R.ml_joins) { ctx.strokeStyle = "#0ff"; ctx.lineWidth = lw(1.5); dot(j.x, j.y, 7); }
    if (tab === "leaders" || tab === "labels" || tab === "bindings") {
      for (const l of R.leaders) {
        const lab = l.label !== null ? byId.label[l.label] : null;
        const unusable = lab && (lab.valid === false || lab.usable === false);
        // a leader whose label OCR could not read is still a leader: same colour, dashed
        // (the expert reported grey dashed ones as "missing leader", 2026-09-05)
        const col = tab === "bindings" && l.label !== null ? R.labelColor[l.label] : l.label !== null ? COLORS.leader : COLORS.leader_unanchored;
        if (unusable) ctx.setLineDash([6 / S(), 4 / S()]);
        const hl = selected && ((selected.type === "leader" && selected.id === l.id) || (selected.group && selected.group.leaders.has(l.id)));
        ctx.strokeStyle = hl ? "#ff0" : col;
        ctx.lineWidth = lw(hl ? 4 : tab === "leaders" ? 3 : tab === "bindings" ? 2.5 : 1.5); for (const pc of (l.pieces || [l.points])) poly(pc); ctx.setLineDash([]);
        if (tab === "leaders") { if (l.anchor) { ctx.fillStyle = "#fff"; ctx.strokeStyle = "#000"; ctx.lineWidth = lw(1); dot(l.anchor[0], l.anchor[1], 4, "#fff"); dot(l.anchor[0], l.anchor[1], 4); }
          for (const g of l.landings) { if (g.inferred) { ctx.strokeStyle = "#f0f"; ctx.lineWidth = lw(2); dot(g.point[0], g.point[1], 6); ctx.strokeStyle = "#000"; ctx.lineWidth = lw(1); } dot(g.point[0], g.point[1], 4, g.node === null ? "#f0f" : "#000"); } }
      }
    }
    if (tab === "leaders") for (const m of R.marks_without_leader || []) { ctx.strokeStyle = "#d00"; ctx.lineWidth = lw(2); dot(m.x, m.y, 7); }
    if (tab === "leaders") for (const r of R.nx_report || []) {   // Nx labels: how many joining points the leader reached
      const l = byId.label[r.label]; if (!l) continue;
      ctx.fillStyle = r.short ? "#d00" : "#0a0"; ctx.font = `bold ${10 / S()}px sans-serif`;
      ctx.fillText(`${r.expected}x: ${r.landings}/${r.expected}${r.landings > r.found ? " (" + (r.landings - r.found) + " from bundle)" : ""}`, l.rect[0], l.rect[1] - 3 / S());
    }
    if (tab === "labels" || tab === "leaders" || tab === "bindings") {
      for (const l of R.labels) {
        const ok = l.designations.length > 0;
        const valid = l.valid !== false;
        const hlab = selected && ((selected.type === "label" && selected.id === l.id) || (selected.group && selected.group.label === l.id));
        ctx.strokeStyle = hlab ? "#ff0" : (tab === "bindings" ? R.labelColor[l.id] : !valid ? "#aaa" : ok ? "#0a0" : "#d00");
        ctx.lineWidth = lw(hlab ? 4 : tab === "labels" ? 2.5 : 1.5);
        if (tab === "bindings" && R.bindings.some(b => b.label === l.id)) { ctx.fillStyle = R.labelColor[l.id]; ctx.globalAlpha = 0.18; ctx.fillRect(l.rect[0], l.rect[1], l.rect[2] - l.rect[0], l.rect[3] - l.rect[1]); ctx.globalAlpha = 1; }
        ctx.strokeRect(l.rect[0], l.rect[1], l.rect[2] - l.rect[0], l.rect[3] - l.rect[1]);
        if (tab === "labels" && l.layer_system) { ctx.fillStyle = "#08c"; ctx.font = `${10 / S()}px sans-serif`; ctx.fillText(l.layer_system, l.rect[0], l.rect[1] - 2 / S()); }
        if (tab === "labels" && zoom > 0.6) { ctx.fillStyle = ok ? "#0a0" : "#d00"; ctx.font = `${9 / S()}px sans-serif`; ctx.fillText(labelCaption(l), l.rect[0], l.rect[3] + 10 / S()); }
      }
    }
    // Draw the exact selection last so nodes, leaders and related pipes cannot obscure it.
    if(selected?.type==='stretch'){
      const st=byId.stretch[selected.id];
      if(st){ctx.setLineDash([]);ctx.strokeStyle='#fff';ctx.lineWidth=lw(12);poly(st.points);
        ctx.strokeStyle='#0074ff';ctx.lineWidth=lw(6);
        if(tab==='bindings'&&R.owner[st.id])ctx.setLineDash((CONFIDENCE_DASH[R.owner[st.id].confidence]||CONFIDENCE_DASH.low).map(n=>n/S()));
        poly(st.points);ctx.setLineDash([]);
        for(const point of [st.points[0],st.points[st.points.length-1]]){ctx.strokeStyle='#0074ff';ctx.lineWidth=lw(3);dot(point[0],point[1],7);}
        const point=st.points[Math.floor(st.points.length/2)];ctx.font=`bold ${13/S()}px sans-serif`;
        const text='SELECTED PIPE '+st.id;const width=ctx.measureText(text).width;
        ctx.fillStyle='#0074ff';ctx.fillRect(point[0]+10/S(),point[1]-28/S(),width+16/S(),24/S());
        ctx.fillStyle='#fff';ctx.fillText(text,point[0]+18/S(),point[1]-11/S());
      }
    }
    // feedback overlay
    for (const f of feedback.records) {
      ctx.strokeStyle = "#f0f"; ctx.fillStyle = "#f0f"; ctx.lineWidth = lw(2); ctx.setLineDash([4 / S(), 3 / S()]);
      if (f.points && f.points.length > 1) poly(f.points);
      if (f.rect) ctx.strokeRect(f.rect[0], f.rect[1], f.rect[2] - f.rect[0], f.rect[3] - f.rect[1]);
      if (f.point) { dot(f.point[0], f.point[1], 8); }
      ctx.setLineDash([]);
      const p = f.point || (f.points && f.points[0]) || (f.rect && [f.rect[0], f.rect[1]]);
      if (p) { ctx.font = `${10 / S()}px sans-serif`; ctx.fillText(f.type, p[0] + 6 / S(), p[1] - 6 / S()); }
    }
    if(feedbackHighlight){
      const h=feedbackHighlight;ctx.save();ctx.setLineDash([]);
      for(const [color,width] of [['#ffffff',10],['#0074ff',5]]){
        ctx.strokeStyle=color;ctx.lineWidth=lw(width);
        for(const line of h.lines)poly(line);
        if(h.rect)ctx.strokeRect(h.rect[0],h.rect[1],h.rect[2]-h.rect[0],h.rect[3]-h.rect[1]);
        if(h.point)dot(h.point[0],h.point[1],12);
      }
      const anchor=h.bounds[0];ctx.font=`600 ${12/S()}px system-ui`;
      const label='FEEDBACK',width=ctx.measureText(label).width;
      ctx.fillStyle='#0074ff';ctx.fillRect(anchor[0]+12/S(),anchor[1]-30/S(),width+16/S(),24/S());
      ctx.fillStyle='#fff';ctx.fillText(label,anchor[0]+20/S(),anchor[1]-13/S());ctx.restore();
    }
    if (drawing) {
      if (drawing.snap) for (const pid of drawing.snap) if (pid !== null) { const q = byId.path[pid]; if (q) { ctx.strokeStyle = "rgba(255,0,255,0.5)"; ctx.lineWidth = lw(6); for (const sg of q.segs) poly([[sg[0], sg[1]], [sg[2], sg[3]]]); } }
      ctx.strokeStyle = "#f0f"; ctx.lineWidth = lw(2); if (drawing.rect) ctx.strokeRect(drawing.rect[0], drawing.rect[1], drawing.rect[2] - drawing.rect[0], drawing.rect[3] - drawing.rect[1]); else poly(drawing.points);
      for (const q of drawing.points || []) dot(q[0], q[1], 4, "#f0f");
    }
  }

  function feedbackGeometry(row, result){
    const ev=row.evidence||{};
    let object;
    for(const [key,collection,saved] of [['stretch_id','stretches','stretches'],['node_id','nodes','nodes'],['leader_id','leaders','leaders'],['label_id','labels','label'],['path_id','paths','paths']]){
      if(row[key]!=null){object=(result[collection]||[]).find(o=>o.id===row[key])||ev[saved];if(object)break;}
    }
    if(object?.path_id!=null&&!object.points&&!object.segs)object=(result.paths||[]).find(p=>p.id===object.path_id)||object;
    const rect=object?.rect||row.rect;
    const point=object?.x!=null&&object?.y!=null?[object.x,object.y]:null;
    const lines=object?.points?.length?[object.points]:object?.segs?.length?object.segs.map(s=>[[s[0],s[1]],[s[2],s[3]]]):row.points?.length?[row.points]:[];
    const marker=point||(!rect&&!lines.length?row.point:null);
    const bounds=rect?[[rect[0],rect[1]],[rect[2],rect[3]]]:marker?[marker]:lines.flat();
    return bounds.length?{lines,rect,point:marker,bounds}:null;
  }
  function focusFeedback(row, reference=R){
    setTab(row.tab||'pipes');
    const shape=feedbackGeometry(row,reference);if(!shape)return false;
    feedbackHighlight=shape;
    const xs=shape.bounds.map(p=>p[0]),ys=shape.bounds.map(p=>p[1]);
    const x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
    const image=bg;
    const locate=()=>{if(bg!==image||feedbackHighlight!==shape)return;
      zoom=Math.min(2,Math.max(.05,Math.min(Math.max(view.clientWidth-160,80)/Math.max(x1-x0,40),Math.max(view.clientHeight-160,80)/Math.max(y1-y0,40))))/R.scale;
      tx=view.clientWidth/2-(x0+x1)/2*S();ty=view.clientHeight/2-(y0+y1)/2*S();draw();};
    image.addEventListener('load',locate,{once:true});if(image.complete)locate();
    return true;
  }
  // ---------- hit testing ----------
  const d2 = (a, b) => Math.hypot(a[0] - b[0], a[1] - b[1]);
  function segDist(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
    let t = L2 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2 : 0; t = Math.max(0, Math.min(1, t));
    return d2(p, [a[0] + t * dx, a[1] + t * dy]);
  }
  // the nearest vector path segment to p (within tol page pt): the point projected onto it and the path id
  function snapVec(p, tol) {
    let best = null;
    for (const q of R.paths) for (const sg of q.segs) {
      const a = [sg[0], sg[1]], b = [sg[2], sg[3]];
      const dx = b[0] - a[0], dy = b[1] - a[1], L2 = dx * dx + dy * dy;
      let t = L2 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2 : 0; t = Math.max(0, Math.min(1, t));
      const q2 = [a[0] + t * dx, a[1] + t * dy], d = d2(p, q2);
      if (d <= tol && (!best || d < best.d)) best = { point: [q2[0], q2[1]], path_id: q.id, d };
    }
    return best;
  }
  const polyDist = (p, pts) => { let m = 1e9; for (let i = 1; i < pts.length; i++) m = Math.min(m, segDist(p, pts[i - 1], pts[i])); return m; };
  function hit(p, kinds) {
    const tol = 6 / S(); let best = null;
    const cand = (type, id, d) => { if (d <= tol && (!best || d < best.d)) best = { type, id, d }; };
    if (kinds.includes("node")) for (const n of R.nodes) if (n.kind !== "tee" && n.kind !== "end" && !(tab === "nodes" && nodeFilter && n.kind !== nodeFilter)) cand("node", n.id, d2(p, [n.x, n.y]));
    if (kinds.includes("label")) for (const l of R.labels) if (p[0] >= l.rect[0] && p[0] <= l.rect[2] && p[1] >= l.rect[1] && p[1] <= l.rect[3]) cand("label", l.id, 0);
    if (kinds.includes("leader")) for (const l of R.leaders) cand("leader", l.id, polyDist(p, l.points));
    if (kinds.includes("stretch")) for (const s of R.stretches) if (!s.in_wall || $("#show-inwall").checked) cand("stretch", s.id, polyDist(p, s.points));
    if (kinds.includes("path")) for (const q of tab === "noise" ? noisePaths() : R.paths.filter(q => ["unknown", "thin_other", "lettering"].includes(q.bucket))) for (const s of q.segs) cand("path", q.id, segDist(p, [s[0], s[1]], [s[2], s[3]]));
    return best;
  }
  const HIT = { pipes: ["node", "stretch"], nodes: ["node", "stretch"], leaders: ["leader", "label", "node"], labels: ["label", "leader"], bindings: ["stretch", "label", "node"], unknown: ["path"], noise: ["path"] };

  function describe(h) {
    if (!h) return "nothing here";
    if (h.type === "stretch") { const s = byId.stretch[h.id]; const b = R.owner[s.id]; const bs = R.bindings.filter(x => x.stretch === s.id);
      return `STRETCH ${s.id}  (pipe ${s.pipe})${s.in_wall ? "  [IN WALL - hidden by default]" : s.entry ? "  [ENTRY STUB from a wall / the sheet edge to its first joining point - no label of its own, left unbound]" : ""}\nline_type: ${s.line_type}  width: ${s.width}  length: ${s.length} pt\nlayer: ${s.layer}\nnode_a: ${s.node_a} (${byId.node[s.node_a]?.kind})  node_b: ${s.node_b} (${byId.node[s.node_b]?.kind})\nink pieces: ${s.n_ink}, dash gaps: ${s.n_dash_gaps}\npaths: ${s.path_ids.join(",")}${(R.runs || []).filter(r => r.stretches.includes(s.id)).map(r => `\nRUN ${r.id}  ${r.stretches.length} stretch(es), ${r.length} pt, system ${r.system || "?"}  flow ${r.flow} [${r.direction_source}]\n  ${r.why}\n  pieces: ${r.pieces.map(p => `[${p.stretches.join(",")}] -> ${p.label === null ? "Unknown (" + p.reason + ")" : "label " + p.label}`).join("; ")}`).join("")}\n\nBINDINGS:\n` +
        (bs.length ? bs.map(b => `  label ${b.label} "${byId.label[b.label]?.designations[b.designation_idx]?.raw}${byId.label[b.label]?.level ? " " + byId.label[b.label].level.raw : ""}"  [${b.confidence}/${b.rule}]\n    ${b.reason}`).join("\n") : "  (unbound)"); }
    if (h.type === "node") { const n = byId.node[h.id]; return `NODE ${n.id}  kind: ${n.kind}${n.kind === "tee" ? "  (branch attaches to stretch " + n.on_stretch + " - main not cut)" : ""}\nat (${n.x}, ${n.y})\nsource paths: ${n.source_paths.join(",")}\nstretches: ${n.stretches.join(", ")}\n` + n.stretches.map(id => `  ${id}: ${byId.stretch[id]?.line_type} ${byId.stretch[id]?.length}pt ${R.owner[id] ? "-> label " + R.owner[id].label : "unbound"}`).join("\n"); }
    if (h.type === "label") { const l = byId.label[h.id]; const leads = R.leaders.filter(x => x.label === l.id);
      return `LABEL ${l.id}  score ${l.score}  src ${l.src}${l.valid === false ? "  [NOT A VALID LABEL - ignored]" : ""}\ntext:\n${l.text}\n\ndesignations: ${JSON.stringify(l.designations.map(d => ({ raw: d.raw, system: d.system, nr: d.number, dim: d.dimension, count: d.count, line_count: d.line_count, recognised: d.recognised })), null, 1)}\nlevel: ${l.level ? l.level.raw : "-"}\nunknown rows: ${JSON.stringify(l.unknown_rows)}\nstroke notation: ${l.stroke_notation ? (l.stroke_notation.over ? "bar over " : "") + (l.stroke_notation.under ? "bar under" : "") : "-"}\nlayer system: ${l.layer_system}\nleaders: ${leads.map(x => x.id + " -> nodes " + x.landings.map(g => g.node).join("/")).join("; ") || "none"}\nbindings: ${R.bindings.filter(b => b.label === l.id).map(b => `stretch ${b.stretch} [${b.confidence}/${b.rule}]`).join("; ") || "none"}`; }
    if (h.type === "leader") { const l = byId.leader[h.id]; return `LEADER ${l.id}  path ${l.path_id}\nlabel: ${l.label === null ? "none (unanchored)" : l.label + ' "' + (byId.label[l.label]?.text || "").split("\n")[0] + '"'}\nanchor: ${JSON.stringify(l.anchor)}\nforked: ${l.forked}\nlandings:\n` + l.landings.map(g => `  ${JSON.stringify(g.point)} -> node ${g.node === null ? "NONE (no node within 3pt)" : g.node + " " + byId.node[g.node]?.kind}`).join("\n"); }
    if (h.type === "path") { const p = (tab === "noise" && byId.noise[h.id]) || byId.path[h.id];
      return `PATH ${p.id}  bucket: ${p.bucket}\nwidth ${p.width}  layer ${p.layer}${p.kind ? "\nkind: " + ({ s: "stroke", f: "fill", fs: "fill+stroke" }[p.kind] || p.kind) + "  colour: " + JSON.stringify(p.color) : ""}\nreason: ${p.reason}\nsegments: ${p.segs.length}` + (tab === "noise" ? "\n\nNOISE - not used after the bucket stage" : ""); }
  }

  // ---------- feedback ----------
  async function addFeedback(rec) {
    return Studio.act(async()=>{
      if(readonly)throw new Error('Select the current drawing to capture feedback.');
      if(tab==='bindings'&&Studio.mode()==='astra'&&AssignmentContext.methodOf(R?.metadata)!=='llm')throw new Error('Click Ask LLM first to review an LLM result.');
      rec.tab=tab;rec.note=$('#note').value;
      const correction=await Studio.editFeedback(rec,R);if(!correction)return;
      const saved=await Studio.saveFeedback(sheet,R,{...rec,...correction});
      feedback.records.push(saved);$('#note').value='';renderFeedback();draw();await Studio.queue();
    },'Saving your comment…');
  }
  function renderFeedback(){
    $('#fb-count').textContent='('+feedback.records.length+')';const ul=$('#fb-list');ul.replaceChildren();
    for(const f of feedback.records.slice().reverse()){const li=document.createElement('li');li.textContent=Studio.scopeName(f)+' · '+f.type.replaceAll('_',' ')+' · '+(f.note||f.status||'');ul.append(li);}
  }
  async function runAssignment(binding){if(R&&!readonly)await Studio.job('replay',{sheet,style_id:Studio.style(),draft:true,binding});}
  let fableStart = null, fableClock = null, fableName = "Fable";
  const layerNav=$('#tabs'), viewSettings=layerNav.querySelector('.view-settings');
  function layoutLayerTabs(){
    if(!layerNav.clientWidth)return;
    // Measure the actual controls, so font size and translated labels also fit.
    const wasInline=viewSettings.classList.contains('inline-options'), wasOpen=viewSettings.open;
    viewSettings.classList.add('inline-options');
    viewSettings.open=true;
    const css=getComputedStyle(layerNav),gap=parseFloat(css.columnGap)||0;
    const buttons=[...layerNav.querySelectorAll(':scope > [data-tab]')];
    const required=buttons.reduce((sum,b)=>sum+b.getBoundingClientRect().width,0)
      +viewSettings.getBoundingClientRect().width+gap*(buttons.length+1)
      +(parseFloat(css.paddingLeft)||0)+(parseFloat(css.paddingRight)||0);
    const inline=required<=layerNav.clientWidth;
    viewSettings.classList.toggle('inline-options',inline);
    viewSettings.open=inline?true:wasInline?false:wasOpen;
  }
  new ResizeObserver(layoutLayerTabs).observe(layerNav);
  document.fonts.ready.then(layoutLayerTabs);
  function setTab(t) {
    tab = t; tool = null; selected = null;feedbackHighlight=null;$('#info').textContent='Select an item on the drawing';
    document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === t));
    layoutLayerTabs();
    const T = $("#tools"); T.innerHTML = t === "noise" ? "<span>read only - this tab records no feedback; use the Unknown tab to report a pipe or leader the bucket stage missed</span>" : "<span>Mark an issue</span>";
    $('#assignment-status').hidden=t!=='bindings';
    $('#assignment-usage').hidden=t!=='bindings';
    if(t==='bindings')refreshAssignmentStatus();
    for (const [id, name, mode] of TOOLS[t]) {
      const b = document.createElement("button"); b.textContent = name.split(' (')[0].replace(/^./,c=>c.toUpperCase()); b.title=name; b.setAttribute('aria-pressed','false'); b.dataset.tool = id; b.dataset.mode = mode;
      b.onclick = () => { tool = tool === id ? null : id; document.querySelectorAll("#tools button").forEach(x => x.classList.toggle("active", x.dataset.tool === tool)); view.classList.toggle("tool", !!tool);document.querySelectorAll('#tools button').forEach(x=>x.setAttribute('aria-pressed',String(x.dataset.tool===tool)));$('#tool-help').textContent=tool?(mode==='line'?'Draw along the missing line. Esc to cancel.':mode==='rect'?'Draw a box around the missing item. Esc to cancel.':'Click the item on the drawing. Esc to cancel.'):'';view.focus({preventScroll:true}); };
      T.appendChild(b);
    }
    const help=document.createElement('span');help.id='tool-help';help.setAttribute('role','status');T.append(help);
    renderLegend(); draw(); Studio.renderAssignmentUsage();
    if(t==='bindings')Studio.ensureDimension();
    if (t === "noise" && R && !N) loadNoise();
  }
  async function loadNoise() {
    const s = sheet; const j = await (await fetch("/api/noise?sheet=" + encodeURIComponent(s))).json();
    if (s !== sheet || !R) return;                         // the sheet changed while loading
    N = j; byId.noise = {}; for (const q of N.paths) byId.noise[q.id] = q;
    if (tab === "noise") { renderLegend(); draw(); }
  }
  document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));
  const toolMode = () => { const b = document.querySelector(`#tools button[data-tool="${tool}"]`); return b ? b.dataset.mode : null; };

  view.addEventListener('keydown',e=>{if(e.key==='Escape'){tool=null;drawing=null;view.classList.remove('tool');document.querySelectorAll('#tools button').forEach(b=>{b.classList.remove('active');b.setAttribute('aria-pressed','false');});if($('#tool-help'))$('#tool-help').textContent='';draw();}});
  // ---------- mouse ----------
  let drag = null;
  view.addEventListener("mousedown", (e) => {
    if(e.target.closest(".zoom-controls")||e.button!==0)return;
    view.focus({preventScroll:true});
    const p = toPage(...pointer(e));
    const mode = toolMode();
    if (tool && (mode === "line" || mode === "rect")) { if (mode === "rect") { drawing = { rect: [p[0], p[1], p[0], p[1]] }; return; }
      // a line sticks to the vector ink under the cursor: both ends snap to the nearest path (within 8 px)
      const sn = R ? snapVec(p, 8 / S()) : null;
      drawing = { points: [sn ? sn.point : p, p], snap: [sn ? sn.path_id : null, null] }; return; }
    drag = { x: e.clientX, y: e.clientY, tx, ty, moved: false };
  });
  view.addEventListener("mousemove", (e) => {
    if (drawing) { const p = toPage(...pointer(e)); if (drawing.rect) { drawing.rect[2] = p[0]; drawing.rect[3] = p[1]; } else if (e.buttons) { const sn = snapVec(p, 8 / S()); drawing.points[1] = sn ? sn.point : p; drawing.snap[1] = sn ? sn.path_id : null; } draw(); return; }
    if (drag) {
      if (!(e.buttons & 1)) { drag = null; return; }          // button released outside the view: stop panning
      if (Math.abs(e.clientX - drag.x) + Math.abs(e.clientY - drag.y) > 3) drag.moved = true;
      tx = drag.tx + e.clientX - drag.x; ty = drag.ty + e.clientY - drag.y; draw();
    }
  });
  view.addEventListener("mouseup", async (e) => {
    if(e.target.closest(".zoom-controls"))return;
    const p = toPage(...pointer(e));
    if (drawing) {
      const rec = drawing.rect ? { type: tool, rect: [Math.min(drawing.rect[0], drawing.rect[2]), Math.min(drawing.rect[1], drawing.rect[3]), Math.max(drawing.rect[0], drawing.rect[2]), Math.max(drawing.rect[1], drawing.rect[3])].map(v => +v.toFixed(2)) }
        : { type: tool, points: drawing.points.map(q => [+q[0].toFixed(2), +q[1].toFixed(2)]), path_ids: [...new Set(drawing.snap.filter(x => x !== null))] };
      drawing = null;
      if (rec.rect ? (rec.rect[2] - rec.rect[0] > 2) : d2(rec.points[0], rec.points[1]) > 2) await addFeedback(rec); else draw();
      return;
    }
    if (!drag || drag.moved) { drag = null; return; }
    drag = null;
    if (!R) return;
    const mode = toolMode();
    if (tool && mode === "point") { await addFeedback({ type: tool, point: [+p[0].toFixed(2), +p[1].toFixed(2)] }); return; }
    const targets=tool ? ({wrong_binding:["stretch"],label_text:["label"],false_label:["label"],node_type:["node"],false_node:["node"],false_pipe:["stretch"],missing_split:["stretch"],wrong_join:["stretch"],false_leader:["leader"]}[tool]||HIT[tab]) : HIT[tab];
    const h = hit(p, targets);
    if (tool && mode === "click") {
      if (!h) return;
      const rec = { type: tool, point: [+p[0].toFixed(2), +p[1].toFixed(2)] };
      if (h.type === "stretch") rec.stretch_id = h.id; if (h.type === "node") rec.node_id = h.id; if (h.type === "label") rec.label_id = h.id; if (h.type === "leader") rec.leader_id = h.id; if (h.type === "path") rec.path_id = h.id;
      await addFeedback(rec); return;
    }
    selected = h; if (h && h.type === "stretch") h.family = family(h.id);
    if (h && tab === "bindings") {
      let lab = null;
      if (h.type === "label") lab = h.id;
      else if (h.type === "leader") lab = byId.leader[h.id].label;
      else if (h.type === "stretch") { const b = R.owner[h.id]; lab = b ? b.label : null; }
      if (lab !== null && lab !== undefined) {
        h.group = { label: lab, stretches: new Set(R.bindings.filter(b => b.label === lab).map(b => b.stretch)), leaders: new Set(R.leaders.filter(l => l.label === lab).map(l => l.id)) };
        h.family = h.group.stretches;
      }
    }
    $("#info").textContent = describe(h) + (h && h.group ? `\n\nBINDING GROUP: label ${h.group.label} "${labelCaption(byId.label[h.group.label])}" — leaders ${[...h.group.leaders].join(", ") || "none"} — stretches ${[...h.group.stretches].join(", ")}` : (h && h.type === "stretch" && h.family && h.family.size > 1 ? `\n\nWHOLE PIPE (${h.family.size} stretches): ${[...h.family].join(", ")}` : "")); draw();
  });
  view.addEventListener("wheel", (e) => {
    if(e.target.closest('.zoom-controls'))return;
    e.preventDefault();if(!R||drawing)return;
    const unit=e.deltaMode===1?16:e.deltaMode===2?view.clientHeight:1;
    if(e.shiftKey&&!e.ctrlKey){tx-=e.deltaX*unit||e.deltaY*unit;ty-=e.deltaX?e.deltaY*unit:0;scheduleDraw();return;}
    // Honor gesture magnitude: tiny trackpad deltas no longer cause 20% jumps.
    const delta=Math.max(-160,Math.min(160,e.deltaY*unit));
    zoomAt(S()*Math.exp(-delta*(e.ctrlKey ? 0.01 : 0.0015)),...pointer(e));
  }, { passive: false });
  window.addEventListener("mouseup", () => { drag = null; });
  view.addEventListener("mouseleave", () => { if (drawing) return; drag = null; });
  view.addEventListener("dblclick", e => {if(e.target.closest('.zoom-controls')||tool)return;e.preventDefault();zoomAt(S()*(e.shiftKey?1/1.6:1.6),...pointer(e));});
  $('#zoom-in').onclick=()=>zoomAt(S()*1.25);
  $('#zoom-out').onclick=()=>zoomAt(S()/1.25);
  $('#zoom-level').onchange=e=>{if(e.target.value!=='current')zoomAt(Number(e.target.value));};
  $('#zoom-fit').onclick=()=>{fit();draw();};
  view.addEventListener('keydown',e=>{
    if(e.target.closest('select, input, textarea, button')||e.ctrlKey||e.metaKey||e.altKey)return;
    if(['+','=','-','0','f','F'].includes(e.key)){e.preventDefault();
      if(e.key==='f'||e.key==='F'){fit();draw();}else zoomAt(e.key==='0'?1:S()*(e.key==='-'?1/1.25:1.25));
    }
  });
  $("#rerun-vectors").onclick = () => Studio.act(async()=>{if(R&&!readonly){await Studio.job("replay",{sheet,style_id:Studio.style(),draft:true,binding:"preview"});}});
  document.querySelectorAll('[data-generate]').forEach(button=>button.onclick=()=>Studio.act(()=>runAssignment(button.dataset.generate)));
  $("#export").onclick = (e) => { e.preventDefault(); if (sheet && !readonly) location.href = "/api/export?sheet=" + encodeURIComponent(sheet); };
  ["show-others", "show-ml", "raw-pipes", "show-inwall", "show-walls"].forEach(id => $("#" + id).onchange = () => {renderLegend();draw();});

  // ---------- upload / rerun / progress ----------
  $("#file").onchange = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    Studio.busy(true,'Uploading '+f.name+'…');                       // a big PDF takes a while to reach the server
    try{
      const r = await (await fetch("/api/upload?style=auto", { method: "POST", headers: { "X-File-Name": f.name }, body: f })).json();   // Auto, or the style picked in the drawing bar
      if(r.error){Studio.notify(r.error,true);return;} sheet = r.sheet; Studio.uploaded(sheet); e.target.value=""; await loadSheets(); pollProgress(true);
    } finally { Studio.busy(false); }
  };
  $("#sheet").onchange = (e) => Studio.act(async()=>{
    const selectedSheet=e.target.value;
    refreshingVectors=true;$('#sheet').disabled=true;
    try{
      await loadSheet(selectedSheet);

    }finally{refreshingVectors=false;$('#sheet').disabled=false;}
  });
  let pollTimer = null;
  let pollAnnounced=false;
  function pollProgress(announce=false) {
    // an analysis after an upload runs for a while on a page that shows nothing else
    if(announce){Studio.busy(true,'Reading the drawing…');pollAnnounced=true;}
    clearInterval(pollTimer);
    pollTimer = setInterval(async () => {
      let j;
      try { j = await (await fetch("/api/progress?sheet=" + encodeURIComponent(sheet))).json(); }
      catch(error){ clearInterval(pollTimer); if(pollAnnounced){pollAnnounced=false;Studio.busy(false);} Studio.notify('Lost contact with the analysis — reload to reconnect.',true); return; }
      const fable = j.stage === 8 || j.started;
      if (j.provider_name) fableName = j.provider_name;
      if (fable && j.status === "running") {
        // a running clock: the request takes minutes, the reviewer should see it is alive
        if (j.started) fableStart = j.started * 1000;
        if (!fableClock) fableClock = setInterval(() => { $("#progress").textContent = `${fableName} is binding labels to pipes… ${Math.round((Date.now() - (fableStart || Date.now())) / 1000)} s`; }, 1000);
        return;
      }
      clearInterval(fableClock); fableClock = null;
      $("#progress").textContent = j.status === "running" ? `running: stage ${j.stage}/9 ${j.name}` : j.status === "error" ? "ERROR: " + j.error : "";
      if (j.status === "running") Studio.busyMessage(`Reading the drawing · step ${j.stage} of 9 · ${j.name}`);
      if (j.status !== "running") {
        clearInterval(pollTimer);
        if (pollAnnounced) { pollAnnounced = false; Studio.busy(false); }
        if (j.status === "done") {
          await loadSheets(); loadSheet(sheet);
          if (fable) $("#progress").textContent = `${fableName} done: ${Math.round(j.seconds ?? (Date.now() - fableStart) / 1000)} s, $${(j.usd || 0).toFixed(2)}`;
        }
      }
    }, 1500);
  }

  for(const [button,type] of [['confirm-object','correct'],['wrong-object','wrong'],['uncertain-object','uncertain']]) $('#'+button).onclick=()=>{
    if(!selected){Studio.notify('Select an object first.',true);return;}
    if(tab==='bindings'&&selected.type!=='stretch'){Studio.notify('Select the pipe stretch to review its assignment.',true);return;}
    const feedbackType=type==='wrong'&&tab==='bindings'?'wrong_binding':type;
    addFeedback({type:feedbackType,[selected.type+'_id']:selected.id});
  };
  window.PipeReview={openDrawing:async s=>{$("#sheet").value=s;await loadSheet(s);},setTab,focusFeedback,refreshStatus:refreshAssignmentStatus,state:()=>({sheet,R,readonly,tab,role,refreshingVectors}),reload:(preserveView=false)=>loadSheet(sheet,preserveView),showResult,
    focusAt:(point,t)=>{
      setTab(t);const image=bg;
      const locate=()=>{if(bg!==image)return;zoom=2/R.scale;tx=view.clientWidth/2-point[0]*S();ty=view.clientHeight/2-point[1]*S();draw();};
      bg.addEventListener('load',locate,{once:true});if(bg.complete)locate();
    },
    focus:(point,t,sid)=>{
      setTab(t);const st=byId.stretch[sid];if(!st)return;selected={type:'stretch',id:sid};
      const owner=R.owner[sid],label=owner?byId.label[owner.label]:null;
      selected.group={label:owner?.label,stretches:new Set([sid]),leaders:new Set(R.leaders.filter(l=>l.label===owner?.label).map(l=>l.id))};
      let points=st.points;if(label)points=[...points,[label.rect[0],label.rect[1]],[label.rect[2],label.rect[3]]];
      const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),x0=Math.min(...xs),x1=Math.max(...xs),y0=Math.min(...ys),y1=Math.max(...ys);
      zoom=Math.min(3,Math.max(.15,Math.min((view.clientWidth-140)/Math.max(x1-x0,40),(view.clientHeight-140)/Math.max(y1-y0,40))/R.scale));
      tx=view.clientWidth/2-(x0+x1)/2*S();ty=view.clientHeight/2-(y0+y1)/2*S();
      $('#info').textContent='SELECTED PIPE '+sid+' — blue outline on drawing\n'+describe(selected);draw();
    }};

  window.__dbg = () => ({ zoom, tx, ty, hasR: !!R, bgOk: !!(bg && bg.complete), cw: canvas.width, vw: view.clientWidth });
  $("#who").onclick = () => askAuthor(true);
  (async () => {
    try { role = (await (await fetch("/api/me")).json()).role || "admin"; } catch (e) {}
    document.body.classList.toggle("review", role !== "admin");
    askAuthor(false);
    await loadSheets(); resize(); setTab("pipes"); if (sheet) loadSheet(sheet);
  })();
})();
