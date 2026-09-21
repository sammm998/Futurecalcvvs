// Rendering engine.
//
// Performance strategy (smooth with thousands of objects):
//   • Path2D objects are built once per polygon in WORLD space and reused at
//     every zoom level — panning/zooming never rebuilds geometry.
//   • The canvas transform is set once per frame, so the GPU-backed 2D
//     rasteriser does the projection.
//   • A uniform grid culls to the visible rectangle; off-screen objects cost
//     nothing.
//   • Frames are scheduled through requestAnimationFrame and coalesced, so a
//     burst of state changes still produces a single repaint.
//   • Geometry cache entries are invalidated per object, not globally.

import { PALETTE, classColor, polyBounds } from './util.js';
import { buildIndex } from './spatial.js';

export class Renderer {
  constructor(canvas, store, viewport) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d', { alpha: false, desynchronized: true });
    this.store = store;
    this.vp = viewport;

    this.bg = null;                 // background Image
    this.paths = new Map();         // pipe id -> Path2D (world space)
    this.index = null;
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);

    this._raf = null;
    this._needsFrame = false;
    this.stats = { drawn: 0, ms: 0 };

    // transient visuals owned by tools
    this.overlay = {
      marquee: null,        // [x0,y0,x1,y1] world
      draft: null,          // {points:[], closing:bool}
      snap: null,           // [x,y] snap preview
      vertices: null,       // {pipeId, active:index}
      rubber: null,         // {a:[x,y], b:[x,y]} link-tool rubber band
    };
  }

  /* ── lifecycle ────────────────────────────────────────────────────────── */
  setBackground(img) { this.bg = img; this.invalidate(); }

  rebuildIndex() { this.index = buildIndex(this.store); }

  rebuildAll() {
    this.paths.clear();
    this.rebuildIndex();
    this.invalidate();
  }

  invalidateObject(kind, id) {
    if (kind === 'pipe') this.paths.delete(id);
    if (!this.index) return this.rebuildIndex();
    const key = `${kind}:${id}`;
    const o = this.store.get(kind, id);
    if (!o || o.deleted) { this.index.remove(key); return; }
    let bbox;
    if (kind === 'pipe') bbox = polyBounds(o.polygon);
    else if (kind === 'label') bbox = o.rect.slice();
    else if (kind === 'leader') {
      let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
      for (const [a, b] of (o.path || [])) for (const [x, y] of [a, b]) {
        if (x < x0) x0 = x; if (y < y0) y0 = y;
        if (x > x1) x1 = x; if (y > y1) y1 = y;
      }
      bbox = [x0 - 1, y0 - 1, x1 + 1, y1 + 1];
    } else {
      const r = Math.max(3, o.radius ?? 6);
      bbox = [o.point[0] - r, o.point[1] - r, o.point[0] + r, o.point[1] + r];
    }
    this.index.update(key, bbox);
  }

  resize() {
    const r = this.canvas.parentElement.getBoundingClientRect();
    this.dpr = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.max(1, Math.round(r.width * this.dpr));
    this.canvas.height = Math.max(1, Math.round(r.height * this.dpr));
    this.canvas.style.width = r.width + 'px';
    this.canvas.style.height = r.height + 'px';
    this.vp.resize(r.width, r.height);
    this.invalidate();
  }

  invalidate() {
    if (this._needsFrame) return;
    this._needsFrame = true;
    this._raf = requestAnimationFrame(() => {
      this._needsFrame = false;
      this.draw();
    });
  }

  /* ── geometry cache ───────────────────────────────────────────────────── */
  pathFor(pipe) {
    let p = this.paths.get(pipe.id);
    if (!p) {
      p = new Path2D();
      const pts = pipe.polygon;
      if (pts.length) {
        p.moveTo(pts[0][0], pts[0][1]);
        for (let i = 1; i < pts.length; i++) p.lineTo(pts[i][0], pts[i][1]);
        p.closePath();
      }
      this.paths.set(pipe.id, p);
    }
    return p;
  }

  /* ── frame ────────────────────────────────────────────────────────────── */
  draw() {
    const t0 = performance.now();
    const ctx = this.ctx, vp = this.vp, st = this.store;
    if (!this.index) this.rebuildIndex();

    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    ctx.fillStyle = '#0d0f13';
    ctx.fillRect(0, 0, vp.width, vp.height);

    // world transform for the rest of the frame
    ctx.setTransform(this.dpr * vp.z, 0, 0, this.dpr * vp.z,
                     -vp.x * vp.z * this.dpr, -vp.y * vp.z * this.dpr);

    const vis = vp.visibleBounds();
    const L = st.layers;
    const px = 1 / vp.z;                 // one screen pixel in world units
    let drawn = 0;

    // ── background PDF ────────────────────────────────────────────────
    if (this.bg && L.background.on) {
      ctx.globalAlpha = L.background.opacity;
      ctx.imageSmoothingEnabled = vp.z < 2;
      const s = 1 / st.doc.scale;
      ctx.drawImage(this.bg, 0, 0, this.bg.width * s, this.bg.height * s);
      ctx.globalAlpha = 1;
    }

    // ── wall regions ──────────────────────────────────────────────────
    if (L.wall.on && st.doc.wall?.length) {
      ctx.globalAlpha = L.wall.opacity;
      ctx.fillStyle = PALETTE.wall;
      ctx.strokeStyle = 'rgba(251,191,36,.3)';
      ctx.lineWidth = px;
      for (const ring of st.doc.wall) {
        ctx.beginPath();
        ctx.moveTo(ring[0][0], ring[0][1]);
        for (let i = 1; i < ring.length; i++) ctx.lineTo(ring[i][0], ring[i][1]);
        ctx.closePath();
        ctx.fill(); ctx.stroke();
      }
      ctx.globalAlpha = 1;
    }

    const visKeys = this.index.query(vis);

    // ── connection (leader) lines ─────────────────────────────────────
    // The drawing already contains the line from the label to the pipe, so we
    // never draw a second one over it — hovering or selecting a connection
    // highlights the existing line instead (see _outline).  The only thing
    // painted here is a connection that has NO line in the drawing, shown as a
    // faint dashed hint so a hand-made link is still visible.
    if (L.leaders?.on && st.leaders?.length) {
      ctx.globalAlpha = L.leaders.opacity * 0.6;
      ctx.lineCap = 'round';
      ctx.setLineDash([3 * px, 3 * px]);
      ctx.lineWidth = 0.8 * px;
      for (const e of st.leaders) {
        if (e.deleted || !e.path?.length || e.drawn !== false) continue;
        if (!st.leaderVisible(e)) continue;   // its joining point / label is filtered
        ctx.strokeStyle = classColor(e.code);
        ctx.beginPath();
        for (const [a, b] of e.path) { ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); }
        ctx.stroke();
        drawn++;
      }
      ctx.setLineDash([]);
      ctx.lineCap = 'butt';
      ctx.globalAlpha = 1;
    }

    // ── pipes ─────────────────────────────────────────────────────────
    if (L.pipes.on) {
      ctx.globalAlpha = L.pipes.opacity;
      for (const key of visKeys) {
        if (!key.startsWith('pipe:')) continue;
        const p = st.pipeById.get(key.slice(5));
        if (!p || p.deleted) continue;
        const path = this.pathFor(p);
        ctx.fillStyle = classColor(p.type);
        ctx.fill(path);
        drawn++;
      }
      // deleted pipes as ghosts, so they can be found and restored
      for (const p of st.pipes) {
        if (!p.deleted || p.polygon.length < 3) continue;
        const b = polyBounds(p.polygon);
        if (b[2] < vis[0] || b[0] > vis[2] || b[3] < vis[1] || b[1] > vis[3]) continue;
        ctx.fillStyle = PALETTE.deleted;
        ctx.fill(this.pathFor(p));
        drawn++;
      }
      ctx.globalAlpha = 1;
    }

    // ── labels ────────────────────────────────────────────────────────
    if (L.labels.on) {
      ctx.globalAlpha = L.labels.opacity;
      ctx.lineWidth = 1.4 * px;
      for (const key of visKeys) {
        if (!key.startsWith('label:')) continue;
        const l = st.labelById.get(key.slice(6));
        if (!l || l.deleted || !st.labelVisible(l)) continue;
        const [x0, y0, x1, y1] = l.rect;
        ctx.strokeStyle = classColor(l.code);
        ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
        if (vp.z > 1.5) {
          ctx.fillStyle = classColor(l.code);
          ctx.font = `${6.5 * px * vp.z > 12 ? 6.5 : 6.5}px ui-monospace, monospace`;
          ctx.fillText(l.code, x0, y0 - 1.5);
        }
        drawn++;
      }
      ctx.globalAlpha = 1;
    }

    // ── joining points ────────────────────────────────────────────────
    if (L.joins.on) {
      ctx.globalAlpha = L.joins.opacity;
      for (const key of visKeys) {
        if (!key.startsWith('join:')) continue;
        const j = st.joinById.get(key.slice(5));
        if (!j || j.deleted || !st.joinVisible(j)) continue;
        // a hand-placed joining point is black; the detector's wear their class
        const c = j.source === 'manual' ? '#111111' : classColor(j.code);
        // the circle IS the capture radius, in world units, so what you see
        // is exactly what the joining point will take in
        const r = Math.max(j.radius ?? 6, 1.5 * px);
        // no line is drawn back to the label: the drawing's own leader line
        // already shows that link (hover it to highlight it)
        ctx.strokeStyle = c;
        ctx.lineWidth = 1.2 * px;
        ctx.beginPath();
        ctx.arc(j.point[0], j.point[1], r, 0, 6.2832);
        ctx.stroke();
        // centre mark so a large radius still reads as a point
        ctx.fillStyle = c;
        ctx.beginPath();
        ctx.arc(j.point[0], j.point[1], 1.3 * px, 0, 6.2832);
        ctx.fill();
        if (!j.pipeId) {                 // orphan join — warn
          ctx.strokeStyle = PALETTE.hover;
          ctx.lineWidth = 1 * px;
          ctx.setLineDash([2.5 * px, 2 * px]);
          ctx.beginPath();
          ctx.arc(j.point[0], j.point[1], r + 2.5 * px, 0, 6.2832);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        drawn++;
      }
      ctx.globalAlpha = 1;
    }

    // ── hover + selection ─────────────────────────────────────────────
    if (st.hover) this._outline(st.hover, PALETTE.hover, 1.6 * px);
    const sel = st.selectionList();
    for (const s of sel) {
      this._outline({ kind: s.kind, id: s.id }, PALETTE.selected, 2.2 * px);
    }

    // ── resize handle for a single selected joining point ─────────────
    if (sel.length === 1 && sel[0].kind === 'join') {
      const j = sel[0].obj;
      const r = this.joinRadius(j);
      const hs = 3.2 * px;
      ctx.fillStyle = '#0d0f13';
      ctx.strokeStyle = PALETTE.selected;
      ctx.lineWidth = 1.6 * px;
      ctx.beginPath();
      ctx.rect(j.point[0] + r - hs, j.point[1] - hs, hs * 2, hs * 2);
      ctx.fill();
      ctx.stroke();
    }

    this._drawOverlay(ctx, px);

    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0);
    this.stats = { drawn, ms: performance.now() - t0 };
  }

  _outline(ref, color, width) {
    const ctx = this.ctx;
    const o = this.store.get(ref.kind, ref.id);
    if (!o) return;
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.shadowColor = color;
    ctx.shadowBlur = 6 / this.vp.z;
    if (ref.kind === 'pipe') {
      ctx.stroke(this.pathFor(o));
    } else if (ref.kind === 'label') {
      const [x0, y0, x1, y1] = o.rect;
      const m = width;
      ctx.strokeRect(x0 - m, y0 - m, x1 - x0 + m * 2, y1 - y0 + m * 2);
    } else if (ref.kind === 'leader') {
      // highlight the line the drawing already has, rather than adding one
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.globalAlpha = 0.45;
      ctx.lineWidth = width * 3.5;
      ctx.beginPath();
      for (const [a, b] of (o.path || [])) {
        ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.lineWidth = width;
      ctx.stroke();
    } else {
      ctx.beginPath();
      ctx.arc(o.point[0], o.point[1], this.joinRadius(o), 0, 6.2832);
      ctx.stroke();
    }
    ctx.restore();
  }

  /** Capture radius in world units, never smaller than a visible dot. */
  joinRadius(j) {
    return Math.max(j.radius ?? 6, 1.5 / this.vp.z);
  }

  /** The resize handle of the single selected joining point, if hit. */
  joinHandleAt(wx, wy, tolPx = 9) {
    const sel = this.store.selectionList();
    if (sel.length !== 1 || sel[0].kind !== 'join') return null;
    const j = sel[0].obj;
    if (this.store.layers.joins.locked) return null;
    const r = this.joinRadius(j);
    const d = Math.hypot(wx - (j.point[0] + r), wy - j.point[1]);
    return d <= tolPx / this.vp.z ? j : null;
  }

  _drawOverlay(ctx, px) {
    const ov = this.overlay;

    if (ov.marquee) {
      const [x0, y0, x1, y1] = ov.marquee;
      ctx.fillStyle = 'rgba(34,211,238,.10)';
      ctx.strokeStyle = PALETTE.selected;
      ctx.lineWidth = 1.2 * px;
      ctx.fillRect(x0, y0, x1 - x0, y1 - y0);
      ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
    }

    if (ov.draft?.points?.length) {
      const pts = ov.draft.points;
      ctx.strokeStyle = PALETTE.selected;
      ctx.lineWidth = 1.8 * px;
      ctx.setLineDash([5 * px, 4 * px]);
      ctx.beginPath();
      ctx.moveTo(pts[0][0], pts[0][1]);
      for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
      if (ov.draft.cursor) ctx.lineTo(ov.draft.cursor[0], ov.draft.cursor[1]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = PALETTE.selected;
      for (const p of pts) {
        ctx.beginPath();
        ctx.arc(p[0], p[1], 2.6 * px, 0, 6.2832);
        ctx.fill();
      }
    }

    if (ov.vertices) {
      const p = this.store.pipeById.get(ov.vertices.pipeId);
      if (p) {
        const r = 3.2 * px;
        for (let i = 0; i < p.polygon.length - 1; i++) {
          const [x, y] = p.polygon[i];
          const active = ov.vertices.active === i;
          ctx.fillStyle = active ? PALETTE.hover : '#0d0f13';
          ctx.strokeStyle = active ? PALETTE.hover : PALETTE.vertex;
          ctx.lineWidth = 1.4 * px;
          ctx.beginPath();
          ctx.rect(x - r, y - r, r * 2, r * 2);
          ctx.fill(); ctx.stroke();
        }
      }
    }

    if (ov.rubber?.a && ov.rubber?.b) {
      const { a, b } = ov.rubber;
      ctx.strokeStyle = PALETTE.selected;
      ctx.lineWidth = 1.4 * px;
      ctx.setLineDash([5 * px, 3 * px]);
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
      ctx.setLineDash([]);
    }

    if (ov.snap) {
      ctx.strokeStyle = PALETTE.hover;
      ctx.lineWidth = 1.4 * px;
      ctx.beginPath();
      ctx.arc(ov.snap[0], ov.snap[1], 6 * px, 0, 6.2832);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(ov.snap[0] - 9 * px, ov.snap[1]);
      ctx.lineTo(ov.snap[0] + 9 * px, ov.snap[1]);
      ctx.moveTo(ov.snap[0], ov.snap[1] - 9 * px);
      ctx.lineTo(ov.snap[0], ov.snap[1] + 9 * px);
      ctx.stroke();
    }

  }

  /* ── hit testing ──────────────────────────────────────────────────────── */
  /** Topmost object at a world point; joins > labels > pipes. */
  hitTest(wx, wy, { tolPx = 6 } = {}) {
    const st = this.store, L = st.layers;
    const tol = tolPx / this.vp.z;
    const keys = this.index.queryPoint(wx, wy, tol + 4);

    let best = null, bestD = Infinity;

    // joins first — they sit on top of pipes.  Hit the centre mark or the
    // radius ring; the interior stays click-through so pipes underneath a
    // large capture circle remain selectable.
    let bestJoin = null, bestJoinD = Infinity;
    for (const key of keys) {
      if (!key.startsWith('join:')) continue;
      if (!L.joins.on || L.joins.locked) continue;
      const o = st.joinById.get(key.slice(5));
      if (!o || o.deleted || !st.joinVisible(o)) continue;
      const d = Math.hypot(o.point[0] - wx, o.point[1] - wy);
      const ring = Math.abs(d - this.joinRadius(o));
      const score = Math.min(d, ring);
      if ((d <= Math.max(tol, 4) || ring <= Math.max(tol, 3)) &&
          score < bestJoinD) {
        bestJoinD = score;
        bestJoin = { kind: 'join', id: o.id, obj: o };
      }
    }
    if (bestJoin) return bestJoin;
    for (const key of keys) {
      const [kind, ...r] = key.split(':');
      if (kind !== 'label') continue;
      const id = r.join(':');
      if (!L.labels.on || L.labels.locked) continue;
      const o = st.labelById.get(id);
      if (!o || o.deleted || !st.labelVisible(o)) continue;
      const [x0, y0, x1, y1] = o.rect;
      if (wx >= x0 - tol && wx <= x1 + tol && wy >= y0 - tol && wy <= y1 + tol) {
        return { kind: 'label', id, obj: o };
      }
    }
    if (L.leaders?.on && !L.leaders?.locked) {
      let best = null, bestD = Infinity;
      for (const key of keys) {
        if (!key.startsWith('leader:')) continue;
        const o = st.leaderById.get(key.slice(7));
        if (!o || o.deleted || !st.leaderVisible(o)) continue;
        for (const [a, b] of (o.path || [])) {
          const d = this._distPointSeg(wx, wy, a[0], a[1], b[0], b[1]);
          if (d <= Math.max(tol, 2) && d < bestD) {
            bestD = d; best = { kind: 'leader', id: o.id, obj: o };
          }
        }
      }
      if (best) return best;
    }

    for (const key of keys) {
      const [kind, ...r] = key.split(':');
      if (kind !== 'pipe') continue;
      const id = r.join(':');
      if (!L.pipes.on || L.pipes.locked) continue;
      const o = st.pipeById.get(id);
      if (!o || o.deleted) continue;
      if (this.ctx.isPointInPath(this.pathFor(o), wx, wy)) {
        return { kind: 'pipe', id, obj: o };
      }
      // near-miss on thin pipes
      const d = this._distToRing(wx, wy, o.polygon);
      if (d < bestD && d <= tol) { bestD = d; best = { kind: 'pipe', id, obj: o }; }
    }
    return best;
  }

  _distPointSeg(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
    let t = L ? ((px - x1) * dx + (py - y1) * dy) / L : 0;
    t = Math.max(0, Math.min(1, t));
    return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
  }

  _distToRing(px, py, pts) {
    let d = Infinity;
    for (let i = 0; i + 1 < pts.length; i++) {
      const x1 = pts[i][0], y1 = pts[i][1], x2 = pts[i + 1][0], y2 = pts[i + 1][1];
      const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
      let t = L ? ((px - x1) * dx + (py - y1) * dy) / L : 0;
      t = Math.max(0, Math.min(1, t));
      d = Math.min(d, Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy)));
    }
    return d;
  }

  /** Everything whose bbox falls inside a world rect. */
  hitRect(rect) {
    const out = [];
    const st = this.store, L = st.layers;
    for (const key of this.index.query(rect)) {
      const [kind, ...r] = key.split(':');
      const id = r.join(':');
      if (!L[kind + 's']?.on || L[kind + 's']?.locked) continue;
      const o = st.get(kind, id);
      if (!o || o.deleted) continue;
      if (kind === 'label' && !st.labelVisible(o)) continue;
      if (kind === 'join' && !st.joinVisible(o)) continue;
      if (kind === 'leader' && !st.leaderVisible(o)) continue;
      out.push({ kind, id, obj: o });
    }
    return out;
  }
}
