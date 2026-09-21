/* Polygon helpers, ported from the local review tool so the two behave the
   same. Everything is in page points. */

export function polyArea(ring){
  let a = 0;
  for (let i = 0; i + 1 < ring.length; i++)
    a += ring[i][0]*ring[i+1][1] - ring[i+1][0]*ring[i][1];
  return Math.abs(a) / 2;
}

export function centroid(ring){
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i + 1 < ring.length; i++){
    const [x1,y1] = ring[i], [x2,y2] = ring[i+1];
    const f = x1*y2 - x2*y1;
    a += f; cx += (x1+x2)*f; cy += (y1+y2)*f;
  }
  if (Math.abs(a) < 1e-9){
    const n = ring.length;
    return [ring.reduce((s,p)=>s+p[0],0)/n, ring.reduce((s,p)=>s+p[1],0)/n];
  }
  a *= 0.5;
  return [cx/(6*a), cy/(6*a)];
}

/* Direction of the pipe wall at the ring edge nearest p.
   A joining point sits along the LENGTH of a pipe, so the nearest edge runs
   along the pipe's local direction — which is what a cut must be square to.
   Averaging nearby vertices instead is unstable at a tee and can come out
   perpendicular, splitting the pipe lengthwise into two slivers. */
export function localAngle(ring, p){
  let bestD = Infinity, bestAng = 0;
  for (let i = 0; i + 1 < ring.length; i++){
    const [x1,y1] = ring[i], [x2,y2] = ring[i+1];
    const dx = x2-x1, dy = y2-y1, L2 = dx*dx + dy*dy;
    let t = L2 ? ((p[0]-x1)*dx + (p[1]-y1)*dy)/L2 : 0;
    t = Math.max(0, Math.min(1, t));
    const d = Math.hypot(p[0]-(x1+t*dx), p[1]-(y1+t*dy));
    if (d < bestD){ bestD = d; bestAng = Math.atan2(dy, dx); }
  }
  return bestAng;
}

/* Split a closed ring with an infinite line through p in direction dir. */
export function splitRingByLine(ring, p, dir){
  const nx = -Math.sin(dir), ny = Math.cos(dir);
  const sd = pt => (pt[0]-p[0])*nx + (pt[1]-p[1])*ny;
  const pts = (ring.length > 1 &&
      ring[0][0] === ring[ring.length-1][0] &&
      ring[0][1] === ring[ring.length-1][1]) ? ring.slice(0,-1) : ring.slice();
  if (pts.length < 3) return null;

  const A = [], B = [];
  let crossings = 0;
  for (let i = 0; i < pts.length; i++){
    const cur = pts[i], nxt = pts[(i+1) % pts.length];
    const dc = sd(cur), dn = sd(nxt);
    (dc >= 0 ? A : B).push(cur);
    if ((dc > 0 && dn < 0) || (dc < 0 && dn > 0)){
      crossings++;
      const t = dc/(dc-dn);
      const ip = [cur[0]+(nxt[0]-cur[0])*t, cur[1]+(nxt[1]-cur[1])*t];
      A.push(ip); B.push(ip);
    }
  }
  // More than one entry/exit pair means the line also slices another leg of
  // the same run; stitching those into two rings would fold the polygon over
  // itself, so the split is refused instead.
  if (crossings !== 2 || A.length < 3 || B.length < 3) return null;
  const close = r => (r.length && (r[0][0] !== r[r.length-1][0] ||
                                   r[0][1] !== r[r.length-1][1]))
    ? [...r, [r[0][0], r[0][1]]] : r;
  const ra = close(A), rb = close(B);
  if (polyArea(ra) < 1e-6 || polyArea(rb) < 1e-6) return null;
  return [ra, rb];
}

export function closestOnRing(ring, x, y){
  let best = null, bestD = Infinity;
  for (let i = 0; i + 1 < ring.length; i++){
    const [x1,y1] = ring[i], [x2,y2] = ring[i+1];
    const dx = x2-x1, dy = y2-y1, L = dx*dx+dy*dy;
    let t = L ? ((x-x1)*dx + (y-y1)*dy)/L : 0;
    t = Math.max(0, Math.min(1, t));
    const px = x1+t*dx, py = y1+t*dy;
    const d = Math.hypot(x-px, y-py);
    if (d < bestD){ bestD = d; best = [px, py]; }
  }
  return {point: best, dist: bestD};
}

export function insertVertexAt(ring, x, y){
  let best = -1, bestD = Infinity, bestPt = null;
  for (let i = 0; i + 1 < ring.length; i++){
    const [x1,y1] = ring[i], [x2,y2] = ring[i+1];
    const dx = x2-x1, dy = y2-y1, L = dx*dx+dy*dy;
    let t = L ? ((x-x1)*dx + (y-y1)*dy)/L : 0;
    t = Math.max(0, Math.min(1, t));
    const px = x1+t*dx, py = y1+t*dy;
    const d = Math.hypot(x-px, y-py);
    if (d < bestD){ bestD = d; best = i+1; bestPt = [px, py]; }
  }
  if (best < 0) return -1;
  ring.splice(best, 0, bestPt);
  return best;
}

export function removeVertex(ring, index){
  const closed = ring.length > 1 &&
    ring[0][0] === ring[ring.length-1][0] && ring[0][1] === ring[ring.length-1][1];
  const n = closed ? ring.length - 1 : ring.length;
  if (n <= 3) return false;
  ring.splice(index, 1);
  if (closed && index === 0) ring[ring.length-1] = [ring[0][0], ring[0][1]];
  return true;
}

/* Does the segment a-b touch this ring: cross one of its edges, or have an
   endpoint inside it?  Used to find which pipes a drawn split line cuts. */
export function segCrossesRing(ring, a, b){
  const orient = (p, q, r) =>
    Math.sign((q[0]-p[0])*(r[1]-p[1]) - (q[1]-p[1])*(r[0]-p[0]));
  for (let i = 0; i + 1 < ring.length; i++){
    const c = ring[i], d = ring[i+1];
    if (orient(a,b,c) !== orient(a,b,d) && orient(c,d,a) !== orient(c,d,b))
      return true;
  }
  return pointInRing(ring, a[0], a[1]) || pointInRing(ring, b[0], b[1]);
}

export function pointInRing(ring, x, y){
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++){
    const [xi,yi] = ring[i], [xj,yj] = ring[j];
    if (((yi > y) !== (yj > y)) &&
        (x < (xj-xi)*(y-yi)/((yj-yi) || 1e-12) + xi)) inside = !inside;
  }
  return inside;
}
