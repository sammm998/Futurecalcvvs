// Uniform-grid spatial index: viewport culling and hit-testing stay O(visible)
// instead of O(all objects), which is what keeps interaction smooth on
// drawings with thousands of entities.

import { polyBounds, rectsIntersect } from './util.js';

export class SpatialIndex {
  constructor(cell = 64) {
    this.cell = cell;
    this.grid = new Map();
    this.bounds = new Map();      // key -> bbox
  }

  clear() { this.grid.clear(); this.bounds.clear(); }

  _cells(b) {
    const c = this.cell;
    const out = [];
    for (let gx = Math.floor(b[0] / c); gx <= Math.floor(b[2] / c); gx++) {
      for (let gy = Math.floor(b[1] / c); gy <= Math.floor(b[3] / c); gy++) {
        out.push(gx + ',' + gy);
      }
    }
    return out;
  }

  insert(key, bbox) {
    this.bounds.set(key, bbox);
    for (const c of this._cells(bbox)) {
      let s = this.grid.get(c);
      if (!s) { s = new Set(); this.grid.set(c, s); }
      s.add(key);
    }
  }

  remove(key) {
    const b = this.bounds.get(key);
    if (!b) return;
    for (const c of this._cells(b)) {
      const s = this.grid.get(c);
      if (s) { s.delete(key); if (!s.size) this.grid.delete(c); }
    }
    this.bounds.delete(key);
  }

  update(key, bbox) { this.remove(key); this.insert(key, bbox); }

  /** Keys whose bbox intersects the query rect. */
  query(rect) {
    const out = new Set();
    for (const c of this._cells(rect)) {
      const s = this.grid.get(c);
      if (!s) continue;
      for (const k of s) {
        if (rectsIntersect(this.bounds.get(k), rect)) out.add(k);
      }
    }
    return out;
  }

  queryPoint(x, y, pad = 0) {
    return this.query([x - pad, y - pad, x + pad, y + pad]);
  }

  bboxOf(key) { return this.bounds.get(key); }
}

export function buildIndex(store, cell = 64) {
  const idx = new SpatialIndex(cell);
  for (const p of store.pipes) {
    if (p.deleted || p.polygon.length < 3) continue;
    idx.insert('pipe:' + p.id, polyBounds(p.polygon));
  }
  for (const l of store.labels) {
    if (l.deleted) continue;
    idx.insert('label:' + l.id, l.rect.slice());
  }
  for (const j of store.joins) {
    if (j.deleted) continue;
    const [x, y] = j.point;
    const r = Math.max(3, j.radius ?? 6);
    idx.insert('join:' + j.id, [x - r, y - r, x + r, y + r]);
  }
  for (const e of (store.leaders || [])) {
    if (e.deleted || !e.path?.length) continue;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [a, b] of e.path) for (const [x, y] of [a, b]) {
      if (x < x0) x0 = x; if (y < y0) y0 = y;
      if (x > x1) x1 = x; if (y > y1) y1 = y;
    }
    idx.insert('leader:' + e.id, [x0 - 1, y0 - 1, x1 + 1, y1 + 1]);
  }
  return idx;
}
