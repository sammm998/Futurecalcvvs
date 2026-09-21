import { locale } from "../i18n";
/* Ritbordets geometri: vad ett blad består av, och hur pekaren hittar rätt på det.
 *
 * Ritobjekten ligger i byggets egna millimeter. En vägg är 3 000 mm lång vare sig bladet skrivs ut i 1:50
 * eller 1:100, och skalan hör till pappret - inte till väggen. Det är hela skillnaden mot att rita i bildpunkter:
 * ett blad som ritats i punkter måste ritas om när skalan byts, ett blad som ritats i millimeter behöver det
 * aldrig.
 *
 * Objektfångst är inte en bekvämlighet utan det som gör ritningen riktig. Utan fångst möts två linjer nästan,
 * och "nästan" går inte att mäta: en slinga som inte sluter sig är inte en slinga, och två rör som nästan möts
 * är två rör. Därför fångas ändpunkt, mittpunkt, centrum, kvadrant, skärning, vinkelrät fot och närmaste punkt
 * på en linje, och den fångade punkten sägs ut i gränssnittet så att den som ritar ser vad hon fick.
 */

export type Pt = [number, number];

export type EntityType = "line" | "polyline" | "rect" | "circle" | "arc" | "text" | "dim" | "pipe";

export type Entity = {
  id: string;
  type: EntityType;
  layer: string;
  p: Pt[];
  r?: number;            // cirkel och båge: radie i mm
  a0?: number;           // båge: startvinkel i grader
  a1?: number;           // båge: slutvinkel
  h?: number;            // text: höjd i mm på pappret
  closed?: boolean;      // polylinje: sluten slinga
  text?: string;
  dn?: number;           // rör: dimension
  designation?: string;  // rör: beteckning, så att bladet kan mängdas per beteckning
  system?: string;
};

export type Layer = {
  id: string; name: string; color: string; visible: boolean; locked: boolean; width: number;
};

export type Sheet = {
  id: string; name: string; paper: string; width_mm: number; height_mm: number; scale_ratio: number;
  content: { version: number; layers: Layer[]; entities: Entity[] };
  drawing_id?: string | null;
  summary?: { rows: { key: string; n: number; m: number }[]; entities: number; total_m: number };
};

export const uid = () => Math.random().toString(36).slice(2, 10);

export const dist = (a: Pt, b: Pt) => Math.hypot(b[0] - a[0], b[1] - a[1]);

/** Bladets yttermått i byggets millimeter: pappret gånger skalan. */
export const worldSize = (s: { width_mm: number; height_mm: number; scale_ratio: number }): Pt =>
  [s.width_mm * s.scale_ratio, s.height_mm * s.scale_ratio];

// ---------------------------------------------------------------- vad ett objekt består av

/** Objektets sträcka som räta segment - det bågarna och cirklarna approximeras med när något ska mätas mot dem. */
export function segmentsOf(e: Entity): [Pt, Pt][] {
  const out: [Pt, Pt][] = [];
  const push = (pts: Pt[], closed = false) => {
    const ring = closed && pts.length > 2 ? [...pts, pts[0]] : pts;
    for (let i = 0; i + 1 < ring.length; i++) out.push([ring[i], ring[i + 1]]);
  };
  if (e.type === "line" || e.type === "polyline" || e.type === "pipe" || e.type === "dim") push(e.p, !!e.closed);
  else if (e.type === "rect" && e.p.length >= 2) {
    const [[x0, y0], [x1, y1]] = e.p;
    push([[x0, y0], [x1, y0], [x1, y1], [x0, y1]] as Pt[], true);
  } else if ((e.type === "circle" || e.type === "arc") && e.p.length && e.r) {
    const a0 = e.type === "circle" ? 0 : (e.a0 ?? 0), a1 = e.type === "circle" ? 360 : (e.a1 ?? 360);
    const n = Math.max(12, Math.round(Math.abs(a1 - a0) / 6));
    const pts: Pt[] = [];
    for (let i = 0; i <= n; i++) {
      const a = (a0 + ((a1 - a0) * i) / n) * Math.PI / 180;
      pts.push([e.p[0][0] + e.r * Math.cos(a), e.p[0][1] + e.r * Math.sin(a)]);
    }
    push(pts);
  }
  return out;
}

/** Längden i meter - det som mäts när bladet summeras. Servern räknar om samma sak; det här är förhandsvisningen. */
export function lengthM(e: Entity): number {
  return segmentsOf(e).reduce((s, [a, b]) => s + dist(a, b), 0) / 1000;
}

export function bboxOf(e: Entity): [number, number, number, number] {
  const pts: Pt[] = e.type === "circle" || e.type === "arc"
    ? segmentsOf(e).flat() as Pt[]
    : e.type === "rect" && e.p.length >= 2
      ? [[Math.min(e.p[0][0], e.p[1][0]), Math.min(e.p[0][1], e.p[1][1])],
         [Math.max(e.p[0][0], e.p[1][0]), Math.max(e.p[0][1], e.p[1][1])]]
      : e.p;
  if (!pts.length) return [0, 0, 0, 0];
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

// ---------------------------------------------------------------- fångst

export type SnapKind = "andpunkt" | "mittpunkt" | "centrum" | "kvadrant" | "skarning" | "vinkelrat" | "narmast" | "rutnat" | "fri";
export type Snap = { p: Pt; kind: SnapKind; from?: string };

export type SnapSettings = {
  on: boolean;
  grid: number;            // rutnätets steg i mm, 0 = av
  kinds: Record<Exclude<SnapKind, "fri">, boolean>;
};

export const defaultSnaps: SnapSettings = {
  on: true, grid: 100,
  kinds: { andpunkt: true, mittpunkt: true, centrum: true, kvadrant: true, skarning: true, vinkelrat: true, narmast: true, rutnat: true },
};

/** Foten för vinkelräten från p mot segmentet a-b, och hur långt bort den ligger. */
function foot(p: Pt, a: Pt, b: Pt): { q: Pt; t: number } {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const L2 = vx * vx + vy * vy;
  if (!L2) return { q: a, t: 0 };
  const t = ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L2;
  return { q: [a[0] + vx * t, a[1] + vy * t], t };
}

function crossing(a: Pt, b: Pt, c: Pt, d: Pt): Pt | null {
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]];
  const den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-9) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den;
  const u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return [a[0] + r[0] * t, a[1] + r[1] * t];
}

/** Punkten pekaren egentligen menar: den fångade om någon ligger inom `tol` millimeter, annars pekarens egen.
 *
 * Ordningen är den ett ritprogram har: en ändpunkt slår en mittpunkt slår en skärning slår en linje. Den som
 * ritar siktar på hörnet, och då är hörnet svaret även om linjen råkar ligga en hårsmån närmare. */
export function snapPoint(raw: Pt, entities: Entity[], layers: Layer[], set: SnapSettings, tol: number,
                          ref?: Pt | null): Snap {
  if (!set.on) return { p: raw, kind: "fri" };
  const visible = new Set(layers.filter((l) => l.visible).map((l) => l.id));
  const cands: Snap[] = [];
  const near: [Pt, Pt][] = [];
  for (const e of entities) {
    if (!visible.has(e.layer)) continue;
    const [x0, y0, x1, y1] = bboxOf(e);
    if (raw[0] < x0 - tol || raw[0] > x1 + tol || raw[1] < y0 - tol || raw[1] > y1 + tol) continue;
    if (set.kinds.centrum && (e.type === "circle" || e.type === "arc") && e.p.length)
      cands.push({ p: e.p[0], kind: "centrum", from: e.id });
    if (set.kinds.kvadrant && e.type === "circle" && e.p.length && e.r)
      for (const [dx, dy] of [[1, 0], [0, 1], [-1, 0], [0, -1]])
        cands.push({ p: [e.p[0][0] + dx * e.r, e.p[0][1] + dy * e.r], kind: "kvadrant", from: e.id });
    for (const [a, b] of segmentsOf(e)) {
      near.push([a, b]);
      if (set.kinds.andpunkt) { cands.push({ p: a, kind: "andpunkt", from: e.id }); cands.push({ p: b, kind: "andpunkt", from: e.id }); }
      if (set.kinds.mittpunkt) cands.push({ p: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2], kind: "mittpunkt", from: e.id });
      if (set.kinds.narmast) {
        const { q, t } = foot(raw, a, b);
        if (t >= 0 && t <= 1) cands.push({ p: q, kind: "narmast", from: e.id });
      }
      if (set.kinds.vinkelrat && ref) {
        const { q, t } = foot(ref, a, b);
        if (t >= 0 && t <= 1) cands.push({ p: q, kind: "vinkelrat", from: e.id });
      }
    }
  }
  if (set.kinds.skarning) {
    for (let i = 0; i < near.length; i++)
      for (let j = i + 1; j < near.length; j++) {
        const q = crossing(near[i][0], near[i][1], near[j][0], near[j][1]);
        if (q && dist(q, raw) <= tol) cands.push({ p: q, kind: "skarning" });
      }
  }
  const rank: Record<SnapKind, number> = { andpunkt: 0, skarning: 1, mittpunkt: 2, centrum: 3, kvadrant: 4, vinkelrat: 5, narmast: 6, rutnat: 7, fri: 8 };
  let best: Snap | null = null, bestScore = Infinity;
  for (const c of cands) {
    const d = dist(c.p, raw);
    if (d > tol) continue;
    const score = rank[c.kind] * tol + d;      // en bättre sorts fångst vinner över en närmare sämre
    if (score < bestScore) { best = c; bestScore = score; }
  }
  if (best) return best;
  if (set.kinds.rutnat && set.grid > 0) {
    const g: Pt = [Math.round(raw[0] / set.grid) * set.grid, Math.round(raw[1] / set.grid) * set.grid];
    if (dist(g, raw) <= tol) return { p: g, kind: "rutnat" };
  }
  return { p: raw, kind: "fri" };
}

/** Punkten låst mot ortho eller polär vinkel från `from`. 0 = av, 90 = ortho, 45 = polär. */
export function constrain(from: Pt | null | undefined, to: Pt, step: number): Pt {
  if (!from || !step) return to;
  const d = dist(from, to);
  if (!d) return to;
  const a = Math.atan2(to[1] - from[1], to[0] - from[0]);
  const q = Math.round(a / (step * Math.PI / 180)) * (step * Math.PI / 180);
  return [from[0] + d * Math.cos(q), from[1] + d * Math.sin(q)];
}

// ---------------------------------------------------------------- träff och markering

/** Ligger punkten på objektet, inom `tol` millimeter? */
export function hits(e: Entity, p: Pt, tol: number): boolean {
  if (e.type === "text") return dist(e.p[0] ?? [0, 0], p) <= tol * 2;
  for (const [a, b] of segmentsOf(e)) {
    const { q, t } = foot(p, a, b);
    const d = t < 0 ? dist(p, a) : t > 1 ? dist(p, b) : dist(p, q);
    if (d <= tol) return true;
  }
  return false;
}

export function insideBox(e: Entity, box: [number, number, number, number]): boolean {
  const [x0, y0, x1, y1] = bboxOf(e);
  return x0 >= box[0] && y0 >= box[1] && x1 <= box[2] && y1 <= box[3];
}

export function moveEntity(e: Entity, dx: number, dy: number): Entity {
  return { ...e, p: e.p.map(([x, y]) => [x + dx, y + dy] as Pt) };
}

/** Objektets greppunkter: det man drar i för att ändra formen utan att rita om den. */
export function gripsOf(e: Entity): Pt[] {
  if (e.type === "circle" || e.type === "arc") return e.p.slice(0, 1);
  if (e.type === "rect" && e.p.length >= 2) {
    const [[x0, y0], [x1, y1]] = e.p;
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]] as Pt[];
  }
  return e.p;
}

// ---------------------------------------------------------------- text

export const fmtM = (mm: number) =>
  `${(mm / 1000).toLocaleString(locale(), { minimumFractionDigits: 3, maximumFractionDigits: 3 })} m`;

export const SNAP_LABEL: Record<SnapKind, string> = {
  andpunkt: "ändpunkt", mittpunkt: "mittpunkt", centrum: "centrum", kvadrant: "kvadrant",
  skarning: "skärning", vinkelrat: "vinkelrät", narmast: "närmast", rutnat: "rutnät", fri: "fri",
};
