// Geometry tools: draw a pipe, edit its vertices, split and merge.

import { Tool } from './index.js';
import {
  insertVertexAt, localAngle, removeVertex, splitRingByLine,
} from '../polyops.js';
import { simplify, smooth } from '../util.js';

const I_DRAW = '<path d="M12 19H5a2 2 0 0 1 0-4h6a2 2 0 0 0 0-4H7"/><circle cx="19" cy="19" r="2"/><circle cx="5" cy="5" r="2"/><path d="M7 5h5a2 2 0 0 1 0 4"/>';
const I_VERT = '<path d="M4 20 20 4"/><rect x="2" y="18" width="4" height="4"/><rect x="18" y="2" width="4" height="4"/><rect x="10" y="10" width="4" height="4"/>';
const I_SPLIT = '<path d="M12 3v7m0 4v7"/><path d="M5 12h14"/><circle cx="12" cy="12" r="1.6"/>';
const I_MERGE = '<path d="M3 7h6a4 4 0 0 1 4 4v2a4 4 0 0 0 4 4h4"/><path d="m17 21 4-4-4-4"/>';

/* ── draw a new pipe ─────────────────────────────────────────────────────── */
export class DrawPipeTool extends Tool {
  static id = 'draw';
  static title = 'Draw Pipe';
  static key = 'P';
  static icon = I_DRAW;
  static cursor = 'crosshair';

  activate() {
    this.points = [];
    this.renderer.overlay.draft = { points: this.points, cursor: null };
  }

  deactivate() {
    this.points = [];
    this.renderer.overlay.draft = null;
    this.renderer.invalidate();
  }

  onPointerDown(e, w) {
    this.points.push([+w[0].toFixed(2), +w[1].toFixed(2)]);
    this.renderer.overlay.draft = { points: this.points, cursor: w };
    this.renderer.invalidate();
  }

  onPointerMove(e, w) {
    if (!this.points.length) return;
    this.renderer.overlay.draft.cursor = w;
    this.renderer.invalidate();
  }

  onDoubleClick() { this.finish(); }

  onKeyDown(e) {
    if (e.key === 'Enter') { this.finish(); return true; }
    if (e.key === 'Escape') {
      this.points = [];
      this.renderer.overlay.draft = { points: this.points, cursor: null };
      this.renderer.invalidate();
      return true;
    }
    if (e.key === 'Backspace' && this.points.length) {
      this.points.pop();
      this.renderer.invalidate();
      return true;
    }
    return false;
  }

  /**
   * The drawn path is a centreline; give it the median width of existing
   * pipes so a new pipe looks like the ones around it.
   */
  finish() {
    const pts = this.points;
    if (pts.length < 2) { this.points = []; return; }
    const half = this.app.medianPipeHalfWidth();
    const ring = strokeToRing(pts, half);
    this.history.begin('Draw pipe');
    const p = this.store.addPipe(ring, 'Unknown');
    this.history.commit();
    this.points = [];
    this.renderer.overlay.draft = { points: this.points, cursor: null };
    this.renderer.invalidateObject('pipe', p.id);
    this.store.select([{ kind: 'pipe', id: p.id }]);
    this.app.toast(`Pipe ${p.id} created — assign a class in the inspector`);
    this.renderer.invalidate();
  }

  status() {
    return this.points.length
      ? `${this.points.length} points · Enter or double-click to finish · Esc cancels`
      : 'Click to place the pipe centreline';
  }
}

/** Offset a polyline into a closed ribbon ring. */
export function strokeToRing(pts, half) {
  const left = [], right = [];
  for (let i = 0; i < pts.length; i++) {
    const prev = pts[Math.max(0, i - 1)], next = pts[Math.min(pts.length - 1, i + 1)];
    let dx = next[0] - prev[0], dy = next[1] - prev[1];
    const L = Math.hypot(dx, dy) || 1;
    dx /= L; dy /= L;
    const nx = -dy * half, ny = dx * half;
    left.push([pts[i][0] + nx, pts[i][1] + ny]);
    right.push([pts[i][0] - nx, pts[i][1] - ny]);
  }
  const ring = [...left, ...right.reverse()];
  ring.push([ring[0][0], ring[0][1]]);
  return ring;
}

/* ── edit vertices ───────────────────────────────────────────────────────── */
export class EditVertexTool extends Tool {
  static id = 'vertex';
  static title = 'Edit Polygon';
  static key = 'E';
  static icon = I_VERT;
  static cursor = 'crosshair';

  activate() {
    this.drag = null;
    this._sync();
  }

  deactivate() {
    this.renderer.overlay.vertices = null;
    this.renderer.invalidate();
  }

  _sync() {
    const sel = this.store.selectionList().filter(s => s.kind === 'pipe');
    this.pipe = sel.length === 1 ? sel[0].obj : null;
    this.renderer.overlay.vertices = this.pipe
      ? { pipeId: this.pipe.id, active: -1 } : null;
    this.renderer.invalidate();
  }

  _pick(w) {
    if (!this.pipe) return -1;
    const tol = 7 / this.vp.z;
    const ring = this.pipe.polygon;
    for (let i = 0; i < ring.length - 1; i++) {
      if (Math.hypot(ring[i][0] - w[0], ring[i][1] - w[1]) <= tol) return i;
    }
    return -1;
  }

  onPointerDown(e, w) {
    if (!this.pipe) {
      const hit = this.renderer.hitTest(w[0], w[1]);
      if (hit?.kind === 'pipe') {
        this.store.select([{ kind: 'pipe', id: hit.id }]);
        this._sync();
      }
      return;
    }
    const idx = this._pick(w);

    if (idx >= 0 && (e.altKey || e.metaKey || e.ctrlKey)) {
      this.history.begin('Delete vertex');
      if (removeVertex(this.pipe.polygon, idx)) {
        this.store.recomputeStats(this.pipe);
        this.store.touch('pipe:geometry', this.pipe.id);
        this.renderer.invalidateObject('pipe', this.pipe.id);
        this.history.commit();
      } else {
        this.history.cancel();
        this.app.toast('A polygon needs at least three vertices', 'error');
      }
      this.renderer.invalidate();
      return;
    }

    if (idx >= 0) {
      this.history.begin('Move vertex');
      this.drag = { idx, moved: false };
      this.renderer.overlay.vertices = { pipeId: this.pipe.id, active: idx };
      this.renderer.invalidate();
      return;
    }

    // click on an edge inserts a vertex
    const near = this.app.distanceToRing(w, this.pipe.polygon);
    if (near <= 8 / this.vp.z) {
      this.history.begin('Add vertex');
      const at = insertVertexAt(this.pipe.polygon, w[0], w[1]);
      this.store.touch('pipe:geometry', this.pipe.id);
      this.renderer.invalidateObject('pipe', this.pipe.id);
      this.history.commit();
      this.drag = { idx: at, moved: false };
      this.renderer.overlay.vertices = { pipeId: this.pipe.id, active: at };
      this.history.begin('Move vertex');
      this.renderer.invalidate();
      return;
    }

    // otherwise pick another pipe
    const hit = this.renderer.hitTest(w[0], w[1]);
    if (hit?.kind === 'pipe') {
      this.store.select([{ kind: 'pipe', id: hit.id }]);
      this._sync();
    }
  }

  onPointerMove(e, w) {
    if (!this.drag || !this.pipe) {
      if (this.pipe) {
        const i = this._pick(w);
        const ov = this.renderer.overlay.vertices;
        if (ov && ov.active !== i) { ov.active = i; this.renderer.invalidate(); }
      }
      return;
    }
    const ring = this.pipe.polygon;
    ring[this.drag.idx] = [+w[0].toFixed(2), +w[1].toFixed(2)];
    // keep the closing vertex in sync
    if (this.drag.idx === 0) ring[ring.length - 1] = [w[0], w[1]];
    if (this.drag.idx === ring.length - 1) ring[0] = [w[0], w[1]];
    this.drag.moved = true;
    this.renderer.invalidateObject('pipe', this.pipe.id);
    this.renderer.invalidate();
  }

  onPointerUp() {
    if (!this.drag) return;
    if (this.drag.moved) {
      this.store.recomputeStats(this.pipe);
      this.store.touch('pipe:geometry', this.pipe.id);
      this.history.commit();
    } else {
      this.history.cancel();
    }
    this.drag = null;
  }

  status() {
    return this.pipe
      ? 'Drag vertices · Click an edge to insert · Alt-click removes'
      : 'Select a pipe to edit its polygon';
  }
}

/* ── split ───────────────────────────────────────────────────────────────── */
export class SplitTool extends Tool {
  static id = 'split';
  static title = 'Split Pipe';
  static key = 'X';
  static icon = I_SPLIT;
  static cursor = 'crosshair';

  onPointerMove(e, w) {
    const hit = this.renderer.hitTest(w[0], w[1]);
    this.store.setHover(hit?.kind === 'pipe' ? { kind: 'pipe', id: hit.id } : null);
    this.renderer.overlay.snap = hit?.kind === 'pipe' ? w : null;
    this.renderer.invalidate();
  }

  onPointerDown(e, w) {
    const hit = this.renderer.hitTest(w[0], w[1]);
    if (hit?.kind !== 'pipe') {
      this.app.toast('Click on the pipe where it should be split', 'error');
      return;
    }
    const pipe = hit.obj;
    const ang = localAngle(pipe.polygon, w);   // square to the leg clicked
    const parts = splitRingByLine(pipe.polygon, w, ang + Math.PI / 2);
    if (!parts) {
      this.app.toast('Could not split there — try nearer the middle', 'error');
      return;
    }
    this.history.begin('Split pipe');
    pipe.deleted = true;
    const a = this.store.addPipe(parts[0], pipe.type);
    const b = this.store.addPipe(parts[1], pipe.type);
    for (const p of [a, b]) p.source = pipe.source;
    this.store.touch('pipe:split', pipe.id);
    this.history.commit();
    this.renderer.rebuildAll();
    this.store.select([{ kind: 'pipe', id: a.id }, { kind: 'pipe', id: b.id }]);
    this.app.toast(`Split into ${a.id} and ${b.id}`);
  }

  deactivate() { this.renderer.overlay.snap = null; }
  status() { return 'Click a pipe at the point where it should be split'; }
}

/* ── merge ───────────────────────────────────────────────────────────────── */
export class MergeTool extends Tool {
  static id = 'merge';
  static title = 'Merge Pipes';
  static key = 'M';
  static icon = I_MERGE;
  static cursor = 'crosshair';

  // Merge is an action, not a mode: it runs on the current selection and hands
  // the canvas straight back to Select.  Switching back has to wait until the
  // merge has finished, otherwise the tool manager is re-entered mid-activate.
  activate() {
    const sel = this.store.selectionList().filter(s => s.kind === 'pipe');
    const back = () => this.app.tools.activate('select');
    if (sel.length < 2) {
      this.app.toast('Select two or more pipes, then use Merge');
      queueMicrotask(back);
      return;
    }
    Promise.resolve(this.app.mergeSelectedPipes()).finally(back);
  }

  status() { return 'Select two or more pipes to merge'; }
}
