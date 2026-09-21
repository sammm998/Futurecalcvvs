// Shared helpers: colours, geometry, events, DOM.

/* ── colour ─────────────────────────────────────────────────────────────── */
const COLOR_CACHE = new Map();

/** Deterministic colour per class code — stable across sheets and sessions. */
export const UNKNOWN_COLOR = '#e5342f';   // unclassified pipes read as RED

export function classColor(code) {
  if (!code || code === 'Unknown') return UNKNOWN_COLOR;
  if (COLOR_CACHE.has(code)) return COLOR_CACHE.get(code);
  let h = 0;
  for (const ch of code) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  // golden-angle hue spread, alternating lightness tiers for separability
  const hue = (h * 137.508) % 360;
  const tier = h % 3;
  const c = `hsl(${hue.toFixed(0)},${[72, 62, 82][tier]}%,${[58, 46, 66][tier]}%)`;
  COLOR_CACHE.set(code, c);
  return c;
}

export const PALETTE = {
  pipe: '#e879f9',
  label: '#60a5fa',
  join: '#fb923c',
  selected: '#22d3ee',
  hover: '#fbbf24',
  deleted: 'rgba(140,146,158,.32)',   // grey ghost, never confused with red
  wall: 'rgba(251,191,36,.13)',
  vertex: '#22d3ee',
};

/* ── geometry ───────────────────────────────────────────────────────────── */
export function polyBounds(pts) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of pts) {
    if (x < x0) x0 = x; if (y < y0) y0 = y;
    if (x > x1) x1 = x; if (y > y1) y1 = y;
  }
  return [x0, y0, x1, y1];
}

export function polyArea(pts) {
  let a = 0;
  for (let i = 0, n = pts.length; i < n; i++) {
    const [x1, y1] = pts[i], [x2, y2] = pts[(i + 1) % n];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}

export function polyPerimeter(pts) {
  let p = 0;
  for (let i = 0; i + 1 < pts.length; i++) {
    p += Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]);
  }
  return p;
}

export function pointInPoly(px, py, pts) {
  let inside = false;
  for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
    const [xi, yi] = pts[i], [xj, yj] = pts[j];
    if ((yi > py) !== (yj > py) &&
        px < ((xj - xi) * (py - yi)) / (yj - yi + 1e-12) + xi) inside = !inside;
  }
  return inside;
}

export function distToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
  let t = L ? ((px - x1) * dx + (py - y1) * dy) / L : 0;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (x1 + t * dx), py - (y1 + t * dy));
}

export function projectToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
  let t = L ? ((px - x1) * dx + (py - y1) * dy) / L : 0;
  t = Math.max(0, Math.min(1, t));
  return [x1 + t * dx, y1 + t * dy, t];
}

export function distToPoly(px, py, pts) {
  if (pointInPoly(px, py, pts)) return 0;
  let d = Infinity;
  for (let i = 0; i + 1 < pts.length; i++) {
    d = Math.min(d, distToSegment(px, py, pts[i][0], pts[i][1],
                                  pts[i + 1][0], pts[i + 1][1]));
  }
  return d;
}

export function rectsIntersect(a, b) {
  return !(a[2] < b[0] || a[0] > b[2] || a[3] < b[1] || a[1] > b[3]);
}

/** Ramer–Douglas–Peucker simplification. */
export function simplify(pts, tol) {
  if (pts.length < 4) return pts.slice();
  const keep = new Array(pts.length).fill(false);
  keep[0] = keep[pts.length - 1] = true;
  const stack = [[0, pts.length - 1]];
  while (stack.length) {
    const [s, e] = stack.pop();
    let maxD = -1, idx = -1;
    for (let i = s + 1; i < e; i++) {
      const d = distToSegment(pts[i][0], pts[i][1],
                              pts[s][0], pts[s][1], pts[e][0], pts[e][1]);
      if (d > maxD) { maxD = d; idx = i; }
    }
    if (maxD > tol && idx > 0) {
      keep[idx] = true;
      stack.push([s, idx], [idx, e]);
    }
  }
  return pts.filter((_, i) => keep[i]);
}

/** Chaikin corner-cutting; keeps the ring closed. */
export function smooth(pts, iterations = 1) {
  let out = pts.slice();
  const closed = out.length > 1 &&
    out[0][0] === out[out.length - 1][0] && out[0][1] === out[out.length - 1][1];
  if (closed) out = out.slice(0, -1);
  for (let it = 0; it < iterations; it++) {
    const next = [];
    for (let i = 0; i < out.length; i++) {
      const p = out[i], q = out[(i + 1) % out.length];
      next.push([p[0] * 0.75 + q[0] * 0.25, p[1] * 0.75 + q[1] * 0.25]);
      next.push([p[0] * 0.25 + q[0] * 0.75, p[1] * 0.25 + q[1] * 0.75]);
    }
    out = next;
  }
  if (closed) out.push([out[0][0], out[0][1]]);
  return out;
}

/* ── misc ───────────────────────────────────────────────────────────────── */
export function uid(prefix) {
  return prefix + Math.random().toString(36).slice(2, 9) +
         (Date.now() % 100000).toString(36);
}

export function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

export function fmt(n, d = 1) {
  return Number(n).toFixed(d);
}

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

/** Minimal event emitter. */
export class Emitter {
  constructor() { this._h = new Map(); }
  on(evt, fn) {
    if (!this._h.has(evt)) this._h.set(evt, new Set());
    this._h.get(evt).add(fn);
    return () => this._h.get(evt).delete(fn);
  }
  emit(evt, payload) {
    const s = this._h.get(evt);
    if (s) for (const fn of [...s]) fn(payload);
  }
}

export function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') n.className = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2).toLowerCase(), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c === null || c === undefined) continue;
    n.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return n;
}

export const isMac = navigator.platform.toUpperCase().includes('MAC');
export const modKey = (e) => (isMac ? e.metaKey : e.ctrlKey);
