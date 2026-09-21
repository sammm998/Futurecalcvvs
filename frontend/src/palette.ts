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
  return `hsl(${h % 360}, ${65 + ((h >>> 9) % 20)}%, ${34 + ((h >>> 17) % 14)}%)`;
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
  return `hsl(${(hue + (h % 31) - 15 + 360) % 360}, ${65 + ((h >>> 9) % 25)}%, ${30 + ((h >>> 17) % 22)}%)`;
}
