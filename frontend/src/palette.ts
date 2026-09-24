/** Shared colours for identity, dimension and recorded section levels. */
export function colorKey(key: string): string { return key; }
export type PipeColourSource = {
  identity?: string; designation?: string; dn?: number | null;
  section_levels?: { level?: { kind?: string; value?: number; ref?: string | null } }[];
};
export function pipeColorKey(pipe: PipeColourSource): string {
  const identity = pipe.identity || `${pipe.designation || "?"}|DN${pipe.dn ?? "?"}`;
  const levels = [...new Set((pipe.section_levels || []).flatMap(({ level }) =>
    level && Number.isFinite(level.value)
      ? [`${level.kind || "?"}:${Number(level.value)}:${level.ref || ""}`] : []))].sort();
  return identity + (levels.length ? `|LEVEL:${levels.join(";")}` : "");
}
export function identityColor(key: string): string {
  let h = 2166136261;
  for (const char of colorKey(key)) h = Math.imul(h ^ char.charCodeAt(0), 16777619) >>> 0;
  // Strong, saturated colours: a run and the label that names it must be easy to follow across a busy sheet,
  // and a pale tint disappears against the drawing's own black and grey line work.
  return `hsl(${h % 360}, ${82 + ((h >>> 9) % 14)}%, ${36 + ((h >>> 17) % 11)}%)`;
}
export function pipeColor(pipe: PipeColourSource): string {
  const identity = pipe.identity || `${pipe.designation || "?"}|DN${pipe.dn ?? "?"}`;
  const base = identityColor(identity);
  const key = pipeColorKey(pipe);
  if (key === identity) return base;
  let h = 2166136261;
  for (const char of key) h = Math.imul(h ^ char.charCodeAt(0), 16777619) >>> 0;
  const hue = Number(base.match(/hsl\((\d+)/)![1]);
  // Keep the same dimension recognisable across branches. Recorded levels
  // vary the shade within that hue family instead of changing to a random hue.
  return `hsl(${(hue + (h % 31) - 15 + 360) % 360}, ${80 + ((h >>> 9) % 16)}%, ${34 + ((h >>> 17) % 14)}%)`;
}

/** The pipe a label names, found by its designation text: "S1-P2" with DN 75 names the run "S1-P2-75". */
export function pipeForLabel(pipes: { designation?: string; identity?: string }[],
                             designation: string | null | undefined, dn: number | null | undefined, display?: string | null) {
  const norm = (t: string | null | undefined) => (t || "").toUpperCase().replace(/\s+/g, "");
  const byName = new Map<string, { designation?: string; identity?: string }>();
  for (const p of pipes) {
    if (p.designation) byName.set(norm(p.designation), p);
  }
  const names = [display, designation].map(norm).filter(Boolean);
  for (const n of names) {
    const withDn = dn != null && !n.endsWith(`-${dn}`) ? `${n}-${dn}` : n;
    const hit = byName.get(withDn) ?? byName.get(n);
    if (hit) return hit;
  }
  return null;
}
