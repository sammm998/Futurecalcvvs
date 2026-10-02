/* Ett rör, inte dess bitar.
 *
 * Läsningen delar ett rör i sträckor vid varje knutpunkt och varje nivåmärkning, för att kunna räkna det
 * lodräta per avsnitt. För den som tittar på ritningen är det fortfarande ett rör: klickar man på det ska hela
 * röret lysa, och listan ska visa röret - inte elva bitar på några decimeter var. Bitar med samma beteckning
 * på samma sida vars ändar möts är samma rör. Mängderna räknas som förut; det här ändrar bara vad som visas
 * och markeras tillsammans. */

const TOL = 1.5; // pt: ändar så här nära varandra sitter ihop

type Pipe = { physical_pipe_id: string; identity?: string | null; page?: number; geometry?: number[][][] };

export function pipeRuns(pipes: Pipe[]): Map<string, string[]> {
  const parent = new Map<string, string>();
  const find = (a: string): string => {
    let r = a;
    while (parent.get(r) !== r) r = parent.get(r)!;
    let x = a;
    while (parent.get(x) !== r) { const n = parent.get(x)!; parent.set(x, r); x = n; }
    return r;
  };
  const union = (a: string, b: string) => { const ra = find(a), rb = find(b); if (ra !== rb) parent.set(ra, rb); };
  const cells = new Map<string, { id: string; x: number; y: number }[]>();
  for (const p of pipes) {
    parent.set(p.physical_pipe_id, p.physical_pipe_id);
    for (const pl of p.geometry ?? []) {
      if (!pl.length) continue;
      for (const [x, y] of [pl[0], pl[pl.length - 1]]) {
        const key = `${p.page ?? 0}|${p.identity ?? ""}`;
        const cx = Math.floor(x / TOL), cy = Math.floor(y / TOL);
        for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
          for (const o of cells.get(`${key}|${cx + dx}|${cy + dy}`) ?? []) {
            if (o.id !== p.physical_pipe_id && Math.hypot(o.x - x, o.y - y) <= TOL) union(o.id, p.physical_pipe_id);
          }
        }
        const k = `${key}|${cx}|${cy}`;
        (cells.get(k) ?? cells.set(k, []).get(k)!).push({ id: p.physical_pipe_id, x, y });
      }
    }
  }
  const groups = new Map<string, string[]>();
  for (const p of pipes) {
    const r = find(p.physical_pipe_id);
    (groups.get(r) ?? groups.set(r, []).get(r)!).push(p.physical_pipe_id);
  }
  const out = new Map<string, string[]>();
  for (const ids of groups.values()) for (const id of ids) out.set(id, ids);
  return out;
}

/** Rörets bitar som ett rör: summerade mått, den första biten som den man klickar på. */
export function runRows(pipes: any[], runs: Map<string, string[]>): any[] {
  const byId = new Map(pipes.map((p) => [p.physical_pipe_id, p]));
  const seen = new Set<string>();
  const rows: any[] = [];
  for (const p of pipes) {
    if (seen.has(p.physical_pipe_id)) continue;
    const ids = (runs.get(p.physical_pipe_id) ?? [p.physical_pipe_id]).filter((id) => byId.has(id));
    ids.forEach((id) => seen.add(id));
    const parts = ids.map((id) => byId.get(id));
    const sum = (f: (q: any) => any) => {
      const v = parts.map(f).filter((x) => typeof x === "number");
      return v.length ? v.reduce((a: number, b: number) => a + b, 0) : null;
    };
    rows.push({
      ...p,
      run_ids: ids,
      parts: parts.length,
      horizontal_m: sum((q) => q.horizontal_m),
      vertical_m: sum((q) => q.vertical_m),
      total_m: sum((q) => q.total_m),
      bridged_gap_pt: sum((q) => q.bridged_gap_pt) ?? 0,
      supporting_anchors: [...new Set(parts.flatMap((q) => q.supporting_anchors ?? []))],
      graph_nodes: [...new Set(parts.flatMap((q) => q.graph_nodes ?? []))],
      section_levels: parts.flatMap((q) => q.section_levels ?? []),
      reasons: [...new Set(parts.flatMap((q) => q.reasons ?? []))],
      needs_review: parts.some((q) => q.needs_review),
      geometry: parts.flatMap((q) => q.geometry ?? []),
    });
  }
  return rows;
}
