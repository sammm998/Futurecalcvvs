// Polygon operations used by the editing tools.

import { polyArea } from './util.js';

/** Principal (long-axis) angle of a ring, radians. */
export function principalAngle(ring) {
  let cx = 0, cy = 0, n = 0;
  for (let i = 0; i + 1 < ring.length; i++) { cx += ring[i][0]; cy += ring[i][1]; n++; }
  if (!n) return 0;
  cx /= n; cy /= n;
  let sxx = 0, syy = 0, sxy = 0;
  for (let i = 0; i + 1 < ring.length; i++) {
    const dx = ring[i][0] - cx, dy = ring[i][1] - cy;
    sxx += dx * dx; syy += dy * dy; sxy += dx * dy;
  }
  return 0.5 * Math.atan2(2 * sxy, sxx - syy);
}

/**
 * Direction of the pipe wall at the ring edge nearest `p`, radians.
 *
 * A joining point sits along the LENGTH of a pipe, where the boundary is the
 * two long parallel "rails" of the buffered stroke — the edge nearest the
 * point runs exactly along the pipe's local direction there.
 *
 * This replaced averaging the vertices within a radius of `p` (a PCA-style
 * long axis, mirroring the Python side's old `minimum_rotated_rectangle` of a
 * small disc). That estimate is unstable whenever the neighbourhood also
 * catches a branch or fitting — exactly the geometry AT a joining point,
 * since that is usually a tee or valve — and a cutter built square to the
 * wrong axis runs PARALLEL to the pipe instead of across it, splitting it
 * lengthwise into two long slivers side by side instead of two end pieces.
 */
export function localAngle(ring, p) {
  let bestD = Infinity, bestAng = 0;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[i + 1];
    const dx = x2 - x1, dy = y2 - y1;
    const L2 = dx * dx + dy * dy;
    let t = L2 ? ((p[0] - x1) * dx + (p[1] - y1) * dy) / L2 : 0;
    t = Math.max(0, Math.min(1, t));
    const px = x1 + t * dx, py = y1 + t * dy;
    const d = Math.hypot(p[0] - px, p[1] - py);
    if (d < bestD) { bestD = d; bestAng = Math.atan2(dy, dx); }
  }
  return bestAng;
}

/**
 * Split a closed ring with a line through `p` with direction `dir` (radians).
 * Returns [ringA, ringB] or null when the line does not cut it into two
 * usable pieces.
 *
 * The line is infinite, but the CUT is local: only the two crossings nearest
 * `p` — one on each rail of the pipe — are used.  A run that bends back on
 * itself (a U, a loop around a room) is crossed by the same line again
 * further along, and stitching every crossing into two rings folds the
 * polygon over itself.  Refusing the split in that case, as this used to,
 * left a joining point without its cut on exactly the pipes that need it.
 */
export function splitRingByLine(ring, p, dir) {
  // line normal
  const nx = -Math.sin(dir), ny = Math.cos(dir);
  const sd = (pt) => (pt[0] - p[0]) * nx + (pt[1] - p[1]) * ny;

  const pts = ring.length > 1 &&
    ring[0][0] === ring[ring.length - 1][0] &&
    ring[0][1] === ring[ring.length - 1][1] ? ring.slice(0, -1) : ring.slice();
  if (pts.length < 3) return null;

  // every place the line meets the ring: (edge index, position on the edge)
  const xs = [];
  for (let i = 0; i < pts.length; i++) {
    const cur = pts[i], nxt = pts[(i + 1) % pts.length];
    let dc = sd(cur), dn = sd(nxt);
    if (Math.abs(dc) < 1e-9) dc = 0;
    if (Math.abs(dn) < 1e-9) dn = 0;
    if (dc === 0) { xs.push({ i, t: 0, pt: cur }); continue; }   // a vertex on it
    if ((dc > 0 && dn < 0) || (dc < 0 && dn > 0)) {
      const t = dc / (dc - dn);
      xs.push({ i, t, pt: [cur[0] + (nxt[0] - cur[0]) * t,
                           cur[1] + (nxt[1] - cur[1]) * t] });
    }
  }
  if (xs.length < 2) return null;

  const d2 = (a) => (a.pt[0] - p[0]) ** 2 + (a.pt[1] - p[1]) ** 2;
  xs.sort((a, b) => d2(a) - d2(b));
  let [c1, c2] = xs;
  if (c1.i > c2.i || (c1.i === c2.i && c1.t > c2.t)) [c1, c2] = [c2, c1];
  if (c1.i === c2.i && c1.t === c2.t) return null;

  // ring A runs from c1 forward along the ring to c2, ring B is the rest
  const A = [c1.pt];
  for (let k = c1.i + 1; k <= c2.i; k++) A.push(pts[k]);
  A.push(c2.pt);
  const B = [c2.pt];
  for (let k = c2.i + 1; k < pts.length; k++) B.push(pts[k]);
  for (let k = 0; k <= c1.i; k++) B.push(pts[k]);
  B.push(c1.pt);

  const tidy = (r) => {
    const out = [];
    for (const q of r) {
      const last = out[out.length - 1];
      if (!last || Math.abs(last[0] - q[0]) > 1e-9 || Math.abs(last[1] - q[1]) > 1e-9)
        out.push([q[0], q[1]]);
    }
    if (out.length > 1 && Math.abs(out[0][0] - out[out.length - 1][0]) < 1e-9 &&
        Math.abs(out[0][1] - out[out.length - 1][1]) < 1e-9) out.pop();
    return out;
  };
  const a = tidy(A), b = tidy(B);
  if (a.length < 3 || b.length < 3) return null;
  const close = (r) => [...r, [r[0][0], r[0][1]]];
  const ra = close(a), rb = close(b);
  if (polyArea(ra) < 1e-6 || polyArea(rb) < 1e-6) return null;
  return [ra, rb];
}

/** Insert a vertex on the ring edge nearest to (x, y). Returns the index. */
export function insertVertexAt(ring, x, y) {
  let best = -1, bestD = Infinity, bestPt = null;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[i + 1];
    const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
    let t = L ? ((x - x1) * dx + (y - y1) * dy) / L : 0;
    t = Math.max(0, Math.min(1, t));
    const px = x1 + t * dx, py = y1 + t * dy;
    const d = Math.hypot(x - px, y - py);
    if (d < bestD) { bestD = d; best = i + 1; bestPt = [px, py]; }
  }
  if (best < 0) return -1;
  ring.splice(best, 0, bestPt);
  return best;
}

/** Remove a vertex, keeping the ring closed and valid. */
export function removeVertex(ring, index) {
  const closed = ring.length > 1 &&
    ring[0][0] === ring[ring.length - 1][0] && ring[0][1] === ring[ring.length - 1][1];
  const n = closed ? ring.length - 1 : ring.length;
  if (n <= 3) return false;
  ring.splice(index, 1);
  if (closed && index === 0) ring[ring.length - 1] = [ring[0][0], ring[0][1]];
  return true;
}

export function translateRing(ring, dx, dy) {
  for (const pt of ring) { pt[0] += dx; pt[1] += dy; }
}

/** Closest point on any ring edge — used for snapping joins to pipes. */
export function closestOnRing(ring, x, y) {
  let best = null, bestD = Infinity;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[i + 1];
    const dx = x2 - x1, dy = y2 - y1, L = dx * dx + dy * dy;
    let t = L ? ((x - x1) * dx + (y - y1) * dy) / L : 0;
    t = Math.max(0, Math.min(1, t));
    const px = x1 + t * dx, py = y1 + t * dy;
    const d = Math.hypot(x - px, y - py);
    if (d < bestD) { bestD = d; best = [px, py]; }
  }
  return { point: best, dist: bestD };
}

/** Centroid of a ring (area-weighted). */
export function centroid(ring) {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i + 1 < ring.length; i++) {
    const [x1, y1] = ring[i], [x2, y2] = ring[i + 1];
    const f = x1 * y2 - x2 * y1;
    a += f; cx += (x1 + x2) * f; cy += (y1 + y2) * f;
  }
  if (Math.abs(a) < 1e-9) {
    const n = ring.length;
    return [ring.reduce((s, p) => s + p[0], 0) / n,
            ring.reduce((s, p) => s + p[1], 0) / n];
  }
  a *= 0.5;
  return [cx / (6 * a), cy / (6 * a)];
}
