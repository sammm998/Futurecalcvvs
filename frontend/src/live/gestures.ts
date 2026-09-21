export type Point = { x: number; y: number };
export type Motion = { dx: number; dy: number; factor: number };
const distance = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y);

export function pinchedHands(hands: Point[][]): Point[] {
return hands.filter(h => h.length >= 21 && h.every(p => Number.isFinite(p.x) && Number.isFinite(p.y)))
      .filter(h => distance(h[4], h[8]) < distance(h[0], h[9]) * 0.3)
      .map(h => ({ x: 1 - (h[4].x + h[8].x) / 2, y: (h[4].y + h[8].y) / 2 }))
      .sort((a, b) => a.x - b.x).slice(0, 2);
}

/** Pinch is relative to palm size. Reacquisition and mode changes never move the view. */
export class HandGestures {
  private previous: Point[] = [];
  private lastTime = 0;
  reset() { this.previous = []; this.lastTime = 0; }
  update(hands: Point[][], time: number): Motion | null {
    const pinches = pinchedHands(hands);
    const previous = this.previous, dt = time - this.lastTime;
    this.lastTime = time;
    if (!pinches.length || previous.length !== pinches.length || dt > 500 || dt <= 0) {
      this.previous = pinches; return null;
    }
    if (pinches.length === 2) {
      const before = distance(previous[0], previous[1]), after = distance(pinches[0], pinches[1]);
      if (before < 0.08 || Math.abs(after - before) > 0.12) { this.previous = pinches; return null; }
      const factor = Math.max(0.9, Math.min(1.1, after / before));
      if (Math.abs(factor - 1) < 0.008) return null;
      this.previous = pinches;
      return { dx: 0, dy: 0, factor };
    }
    const dx = pinches[0].x - previous[0].x, dy = pinches[0].y - previous[0].y;
    if (Math.hypot(dx, dy) > 0.12) { this.previous = pinches; return null; }
    // Accumulate deliberate slow motion across frames instead of discarding
    // every sub-threshold step. Jitter inside the dead zone remains stationary.
    if (Math.hypot(dx, dy) < 0.002) return null;
    this.previous = pinches;
    // Drag the paper with the mirrored hand, hence scroll in the opposite direction.
    return { dx: -dx * 1400, dy: -dy * 1000, factor: 1 };
  }
}

/** A directional extension must have a unique terminal on the selected physical run. */
export function extension(pipe: any, page: number, meters: number, direction: string, mpp: number) {
  if (!pipe || (pipe.page ?? 0) !== page) throw new Error('Välj ett rör på aktuellt blad först.');
  if (!Number.isFinite(meters) || meters <= 0 || meters > 100) throw new Error('Ange en längd mellan 0 och 100 meter.');
  if (!Number.isFinite(mpp) || mpp <= 0) throw new Error('Bladets skala saknas.');
  const vectors: Record<string, number[]> = { right: [1, 0], left: [-1, 0], up: [0, -1], down: [0, 1] };
  const v = vectors[direction]; if (!v) throw new Error('Ange höger, vänster, uppåt eller nedåt.');
  let ends: number[][] = [];
  if (pipe.frontiers?.length) {
    // Engine graph boundaries include bridged dashes. A dash tip or elbow is not a pipe end.
    for (const f of pipe.frontiers) if (Number.isFinite(f.x) && Number.isFinite(f.y)
      && !ends.some(p => Math.hypot(p[0] - f.x, p[1] - f.y) < 0.1)) ends.push([f.x, f.y]);
    for (const line of pipe.extensions ?? []) if (line.length > 1) {
      const start = line[0], end = line[line.length - 1];
      ends = ends.filter(p => Math.hypot(p[0] - start[0], p[1] - start[1]) >= 0.1);
      ends.push(end);
    }
  } else {
    for (const line of pipe.geometry ?? []) if (line.length > 1) ends.push(line[0], line[line.length - 1]);
  }
  // Ignore shared polyline vertices. A branch can have several terminals; ties need human selection.
  const free = ends.filter(a => ends.filter(b => Math.hypot(a[0] - b[0], a[1] - b[1]) < 0.1).length === 1);
  const ranked = free.sort((a, b) => (b[0] - a[0]) * v[0] + (b[1] - a[1]) * v[1]);
  if (!ranked.length || (ranked[1] && Math.abs((ranked[0][0] - ranked[1][0]) * v[0] + (ranked[0][1] - ranked[1][1]) * v[1]) < 0.1))
    throw new Error('Röret har ingen entydig ände i den riktningen. Välj en annan sträcka eller använd Rätta.');
  const start = ranked[0];
  return { points: [start, [start[0] + v[0] * meters / mpp, start[1] + v[1] * meters / mpp]], meters };
}

/** Display human extensions in 3D without modifying the analysis or its quantities. */
export function withPipeExtensions(result: any, corrections: any[]) {
  let count = 0;
  const pipes = (result.pipes ?? []).map((pipe: any) => {
    const extra = corrections.filter(c => !c.undone && c.kind === 'extend'
      && c.payload?.pipe_id === pipe.physical_pipe_id && c.page === (pipe.page ?? 0)
      && Array.isArray(c.payload.points) && c.payload.points.length > 1).map(c => c.payload.points);
    count += extra.length;
    return extra.length ? { ...pipe, geometry: [...(pipe.geometry ?? []), ...extra] } : pipe;
  });
  return { ...result, pipes, manualExtensions: count };
}
