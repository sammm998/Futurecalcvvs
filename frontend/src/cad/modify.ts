/* Ändringskommandona: flytta, kopiera, rotera, spegla, skala, förskjut, mönster, trimma och förläng.
 *
 * Det som gör ett ritprogram till ett ritprogram är inte vad man kan rita utan vad man kan göra med det som
 * redan står där. Varje kommando här är en ren funktion från objekt till objekt: ingen vet om sidan, ingen
 * skriver i dokumentet. Sidan gör en transaktion av svaret, så allt går att ångra som allt annat.
 *
 * En geometrisk avbildning (flytt, vridning, spegling, skalning) appliceras på varje punkt objektet har -
 * hörn, banor, nockar - och på det som inte är punkter men ändå hör till formen: en cirkels radie, en texts
 * vinkel, en bågs start- och slutvinkel. Det som sitter i en vägg (dörr, fönster, öppning) har ingen egen
 * plats; det följer väggen och lämnas orört. */

import { type CadDocument, type Entity, type Pt, uid } from "./building";
import { segmentsOf } from "./plan";

/** En likformig avbildning av planet: p -> s·R(θ)·M·(p - o) + o + t, där M speglar i x-axeln om `flip`. */
export type Map2 = { o: Pt; t: Pt; theta: number; s: number; flip: boolean };
const ID: Map2 = { o: [0, 0], t: [0, 0], theta: 0, s: 1, flip: false };

export const translation = (dx: number, dy: number): Map2 => ({ ...ID, t: [dx, dy] });
export const rotation = (o: Pt, theta: number): Map2 => ({ ...ID, o, theta });
export const scaling = (o: Pt, s: number): Map2 => ({ ...ID, o, s });
/** Spegling i linjen genom a och b: vrid linjen till x-axeln, spegla, vrid tillbaka. */
export const mirroring = (a: Pt, b: Pt): Map2 => ({ ...ID, o: a, theta: 2 * Math.atan2(b[1] - a[1], b[0] - a[0]), flip: true });

export function apply(m: Map2, p: Pt): Pt {
  const x = p[0] - m.o[0], y = (p[1] - m.o[1]) * (m.flip ? -1 : 1);
  const c = Math.cos(m.theta), s = Math.sin(m.theta);
  return [m.o[0] + m.t[0] + m.s * (x * c - y * s), m.o[1] + m.t[1] + m.s * (x * s + y * c)];
}

const deg = (r: number) => (r * 180) / Math.PI;
/** En vinkel i grader genom avbildningen: speglingen vänder riktningen, vridningen lägger till. */
const turnDeg = (m: Map2, a = 0) => (((m.flip ? -a : a) + deg(m.theta)) % 360 + 360) % 360;
const turnRad = (m: Map2, a: number) => (m.flip ? -a : a) + m.theta;

/** Objektet genom avbildningen. Punkterna flyttas, och mått som hör till formen följer med. */
export function transformed(e: Entity, m: Map2): Entity {
  const P = (p: Pt): Pt => apply(m, p);
  const P3 = (q: number[]): any => { const r = apply(m, [q[0], q[1]]); return q.length > 2 ? [r[0], r[1], q[2]] : r; };
  const x = e as any;
  switch (e.type) {
    case "door": case "window": case "opening": return e;
    case "pipe": case "duct": case "cable_tray": case "conduit": return { ...x, path: x.path.map(P3) };
    case "terrain": return { ...x, points: x.points.map(P3) };
    case "roof": return { ...x, p: x.p.map(P), ridge: x.ridge ? [P(x.ridge[0]), P(x.ridge[1])] : x.ridge };
    case "circle": return { ...x, p: [P(x.p[0])], r: x.r * m.s };
    case "arc": {
      // speglingen byter bågens löpriktning: start och slut byter plats
      const a0 = turnRad(m, x.a0), a1 = turnRad(m, x.a1);
      return { ...x, p: [P(x.p[0])], r: x.r * m.s, a0: m.flip ? a1 : a0, a1: m.flip ? a0 : a1 };
    }
    case "ellipse": return { ...x, p: [P(x.p[0])], rx: x.rx * m.s, ry: x.ry * m.s, rot: turnDeg(m, x.rot ?? 0) };
    case "rect": {
      // en rektangel är axelrät; vriden eller speglad snett blir den en sluten polylinje med samma hörn
      const [[x0, y0], [x1, y1]] = x.p;
      const corners: Pt[] = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]].map((q) => P(q as Pt));
      const square = Math.abs(Math.sin(2 * m.theta)) < 1e-9;
      if (square) {
        const xs = corners.map((q) => q[0]), ys = corners.map((q) => q[1]);
        return { ...x, p: [[Math.min(...xs), Math.min(...ys)], [Math.max(...xs), Math.max(...ys)]] };
      }
      return { ...x, type: "polyline", p: corners, closed: true };
    }
    case "text": case "mtext": return { ...x, p: [P(x.p[0])], h: x.h * m.s, ...(x.w ? { w: x.w * m.s } : {}), rot: turnDeg(m, x.rot ?? 0) };
    case "block": return { ...x, p: [P(x.p[0])], rot: turnDeg(m, x.rot ?? 0), scale: (x.scale ?? 1) * m.s };
    case "fitting": case "equipment": case "device": case "mesh":
      return { ...x, p: [P3(x.p[0])], rot: turnDeg(m, x.rot ?? 0), ...(e.type === "mesh" ? { scale: (x.scale ?? 1) * m.s } : {}) };
    case "column": case "underlay": return { ...x, p: [P(x.p[0])], rot: turnDeg(m, x.rot ?? 0), ...(e.type === "underlay" && x.mm_per_px ? { mm_per_px: x.mm_per_px * m.s } : {}) };
    case "hatch": return { ...x, p: x.p.map(P), angle: turnDeg(m, x.angle ?? 0) };
    default: return Array.isArray(x.p) ? { ...x, p: x.p.map((q: any) => (q.length > 2 ? P3(q) : P(q))) } : e;
  }
}

/** En kopia med ett nytt id. Det som sitter i en kopierad vägg kopieras med och flyttas till den nya väggen. */
export function copies(doc: CadDocument, ids: string[], m: Map2): Entity[] {
  const out: Entity[] = [];
  const newId = new Map<string, string>();
  for (const e of doc.entities) if (ids.includes(e.id)) newId.set(e.id, uid());
  for (const e of doc.entities) {
    if (ids.includes(e.id)) out.push({ ...transformed(e, m), id: newId.get(e.id)! } as Entity);
    else if ("host" in e && (e as any).host && newId.has((e as any).host) && !ids.includes(e.id)) {
      // dörrar och fönster i en kopierad vägg: en ny dörr i den nya väggen, på samma ställe längs den
      out.push({ ...(e as any), id: uid(), host: newId.get((e as any).host) } as Entity);
    }
  }
  return out;
}

/** Rader × kolumner kopior på avståndet dx, dy; originalet är den första. */
export function arrayed(doc: CadDocument, ids: string[], cols: number, rows: number, dx: number, dy: number): Entity[] {
  const out: Entity[] = [];
  for (let r = 0; r < Math.max(1, rows); r++) for (let c = 0; c < Math.max(1, cols); c++) {
    if (r === 0 && c === 0) continue;
    out.push(...copies(doc, ids, translation(c * dx, r * dy)));
  }
  return out;
}

// ---------------------------------------------------------------- förskjut

const sub = (a: Pt, b: Pt): Pt => [a[0] - b[0], a[1] - b[1]];
const len = (v: Pt) => Math.hypot(v[0], v[1]);
const cross = (a: Pt, b: Pt) => a[0] * b[1] - a[1] * b[0];

/** En polylinje förskjuten d åt vänster (d > 0) eller höger: varje led parallellt, hörnen där leden möts. */
export function offsetPath(p: Pt[], d: number, closed = false): Pt[] {
  const n = p.length;
  if (n < 2) return p.slice();
  const segs: [Pt, Pt][] = [];
  for (let i = 0; i < n - 1 + (closed ? 1 : 0); i++) {
    const a = p[i], b = p[(i + 1) % n], v = sub(b, a), L = len(v) || 1;
    const nrm: Pt = [-v[1] / L * d, v[0] / L * d];
    segs.push([[a[0] + nrm[0], a[1] + nrm[1]], [b[0] + nrm[0], b[1] + nrm[1]]]);
  }
  const meet = (s: [Pt, Pt], t: [Pt, Pt]): Pt => {
    const r = sub(s[1], s[0]), q = sub(t[1], t[0]), den = cross(r, q);
    if (Math.abs(den) < 1e-9) return s[1];                       // raka fortsättningen: leden möts där de slutar
    const u = cross(sub(t[0], s[0]), q) / den;
    return [s[0][0] + u * r[0], s[0][1] + u * r[1]];
  };
  const out: Pt[] = [];
  if (closed) {
    for (let i = 0; i < segs.length; i++) out.push(meet(segs[(i - 1 + segs.length) % segs.length], segs[i]));
  } else {
    out.push(segs[0][0]);
    for (let i = 1; i < segs.length; i++) out.push(meet(segs[i - 1], segs[i]));
    out.push(segs[segs.length - 1][1]);
  }
  return out;
}

/** Vilken sida av objektet punkten ligger på: +1 vänster om dess första led, -1 höger. */
export function sideOf(path: Pt[], at: Pt): number {
  let best = Infinity, side = 1;
  for (let i = 0; i < path.length - 1; i++) {
    const a = path[i], b = path[i + 1], v = sub(b, a), L2 = v[0] * v[0] + v[1] * v[1] || 1;
    const t = Math.max(0, Math.min(1, ((at[0] - a[0]) * v[0] + (at[1] - a[1]) * v[1]) / L2));
    const q: Pt = [a[0] + t * v[0], a[1] + t * v[1]], dd = len(sub(at, q));
    if (dd < best) { best = dd; side = cross(v, sub(at, a)) >= 0 ? 1 : -1; }
  }
  return side;
}

/** Objektet förskjutet avståndet d mot punkten `toward`, som ett nytt objekt. Null när formen inte går att förskjuta. */
export function offsetEntity(e: Entity, d: number, toward: Pt): Entity | null {
  const x = e as any;
  const id = uid();
  switch (e.type) {
    case "line": case "wall": case "beam": case "curtain_wall": case "polyline": case "railing": case "site": case "spline": {
      const s = sideOf(x.p, toward) * d;
      return { ...x, id, p: offsetPath(x.p, s, !!x.closed) };
    }
    case "pipe": case "duct": case "cable_tray": case "conduit": {
      const flat: Pt[] = x.path.map((q: number[]) => [q[0], q[1]] as Pt);
      const s = sideOf(flat, toward) * d;
      const moved = offsetPath(flat, s);
      return { ...x, id, path: moved.map((q, i) => [q[0], q[1], x.path[i]?.[2] ?? 0]) };
    }
    case "rect": {
      const [[x0, y0], [x1, y1]] = x.p;
      const inside = toward[0] > x0 && toward[0] < x1 && toward[1] > y0 && toward[1] < y1;
      const k = inside ? -d : d;
      if (x1 - x0 + 2 * k <= 0 || y1 - y0 + 2 * k <= 0) return null;
      return { ...x, id, p: [[x0 - k, y0 - k], [x1 + k, y1 + k]] };
    }
    case "circle": case "arc": {
      const outside = len(sub(toward, x.p[0])) > x.r;
      const r = x.r + (outside ? d : -d);
      return r > 0 ? { ...x, id, r } : null;
    }
    case "floor": case "roof": case "ceiling": case "room": case "hatch": {
      const s = sideOf([...x.p, x.p[0]], toward) * d;
      return { ...x, id, p: offsetPath(x.p, s, true) };
    }
    default: return null;
  }
}

// ---------------------------------------------------------------- trimma och förläng

/** Där sträckan a-b korsar sträckan c-d: parametern längs a-b (0..1) eller null. */
function cut(a: Pt, b: Pt, c: Pt, d: Pt, infinite = false): number | null {
  const r = sub(b, a), s = sub(d, c), den = cross(r, s);
  if (Math.abs(den) < 1e-12) return null;
  const t = cross(sub(c, a), s) / den, u = cross(sub(c, a), r) / den;
  if (u < -1e-9 || u > 1 + 1e-9) return null;
  if (!infinite && (t < -1e-9 || t > 1 + 1e-9)) return null;
  return t;
}

/** Alla andra synliga objekts sträckor: det som trimmas och förlängs mot. */
function edges(doc: CadDocument, skip: string, visible: (e: Entity) => boolean): [Pt, Pt][] {
  const out: [Pt, Pt][] = [];
  for (const e of doc.entities) if (e.id !== skip && visible(e)) for (const s of segmentsOf(doc, e)) out.push(s as [Pt, Pt]);
  return out;
}

/** Linjära objekt med två punkter - det trimma och förläng arbetar på. */
const LINEAR = new Set(["line", "wall", "beam", "curtain_wall"]);
export const trimmable = (e: Entity) => LINEAR.has(e.type) || e.type === "polyline" || ["pipe", "duct", "cable_tray", "conduit"].includes(e.type);
const pathOf = (e: Entity): Pt[] => ((e as any).path ? (e as any).path.map((q: number[]) => [q[0], q[1]] as Pt) : (e as any).p);
const withPath = (e: Entity, p: Pt[]): Entity => {
  const x = e as any;
  return x.path ? { ...x, path: p.map((q, i) => [q[0], q[1], x.path[Math.min(i, x.path.length - 1)]?.[2] ?? 0]) } : { ...x, p };
};

/**
 * Trimma: biten av objektet mellan de närmaste skärningarna på var sida om klicket tas bort. Ett objekt som
 * inte korsas av något lämnas; en bit mitt i delar objektet i två. Svaret är det objektet blir: inget (hela
 * togs bort), ett eller två.
 */
export function trim(doc: CadDocument, e: Entity, at: Pt, visible: (e: Entity) => boolean): Entity[] | null {
  if (!trimmable(e)) return null;
  const p = pathOf(e);
  // vilken led klicket gäller och var längs den
  let seg = 0, tAt = 0, best = Infinity;
  for (let i = 0; i < p.length - 1; i++) {
    const a = p[i], b = p[i + 1], v = sub(b, a), L2 = v[0] * v[0] + v[1] * v[1] || 1;
    const t = Math.max(0, Math.min(1, ((at[0] - a[0]) * v[0] + (at[1] - a[1]) * v[1]) / L2));
    const dd = len(sub(at, [a[0] + t * v[0], a[1] + t * v[1]]));
    if (dd < best) { best = dd; seg = i; tAt = t; }
  }
  const a = p[seg], b = p[seg + 1];
  const ts = edges(doc, e.id, visible).map(([c, d]) => cut(a, b, c, d)).filter((t): t is number => t !== null && t > 1e-6 && t < 1 - 1e-6);
  const before = ts.filter((t) => t < tAt), after = ts.filter((t) => t > tAt);
  const lo = before.length ? Math.max(...before) : null, hi = after.length ? Math.min(...after) : null;
  if (lo === null && hi === null) return null;
  const at_ = (t: number): Pt => [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
  const head = lo !== null ? [...p.slice(0, seg + 1), at_(lo)] : seg > 0 ? p.slice(0, seg + 1) : null;
  const tail = hi !== null ? [at_(hi), ...p.slice(seg + 1)] : seg + 1 < p.length - 1 ? p.slice(seg + 1) : null;
  const out: Entity[] = [];
  if (head && head.length >= 2) out.push(withPath(e, head));
  if (tail && tail.length >= 2) out.push({ ...withPath(e, tail), id: head && head.length >= 2 ? uid() : e.id } as Entity);
  return out;
}

/** Förläng: änden närmast klicket dras ut till den närmaste sträckan i sin riktning. Null när ingen finns. */
export function extend(doc: CadDocument, e: Entity, at: Pt, visible: (e: Entity) => boolean): Entity | null {
  if (!trimmable(e)) return null;
  const p = pathOf(e);
  const first = len(sub(at, p[0])) < len(sub(at, p[p.length - 1]));
  const a = first ? p[1] : p[p.length - 2], b = first ? p[0] : p[p.length - 1];   // a -> b pekar ut genom änden
  const ts = edges(doc, e.id, visible).map(([c, d]) => cut(a, b, c, d, true)).filter((t): t is number => t !== null && t > 1 + 1e-6);
  if (!ts.length) return null;
  const t = Math.min(...ts);
  const q: Pt = [a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])];
  const np = p.slice();
  if (first) np[0] = q; else np[np.length - 1] = q;
  return withPath(e, np);
}

// ---------------------------------------------------------------- mät

/** En uppmätt kedja: längden längs den och, när den sluter en yta, ytan (mm, mm²). */
export function measure(p: Pt[]): { length: number; area: number | null } {
  let L = 0;
  for (let i = 1; i < p.length; i++) L += len(sub(p[i], p[i - 1]));
  if (p.length < 3) return { length: L, area: null };
  let A = 0;
  for (let i = 0; i < p.length; i++) { const q = p[i], r = p[(i + 1) % p.length]; A += q[0] * r[1] - r[0] * q[1]; }
  return { length: L, area: Math.abs(A) / 2 };
}

// ---------------------------------------------------------------- kommandoraden

export type ModCmd = "flytta" | "kopiera" | "rotera" | "spegla" | "skala" | "forskjut" | "monster" | "trimma" | "forlang" | "mat";
/** Kommandonamn och de förkortningar en ritare redan har i fingrarna - svenska och de vanliga engelska. */
export const COMMAND_ALIASES: Record<string, ModCmd> = {
  flytta: "flytta", fl: "flytta", m: "flytta", move: "flytta",
  kopiera: "kopiera", ko: "kopiera", co: "kopiera", cp: "kopiera", copy: "kopiera",
  rotera: "rotera", ro: "rotera", rotate: "rotera",
  spegla: "spegla", sp: "spegla", mi: "spegla", mirror: "spegla",
  skala: "skala", sk: "skala", sc: "skala", scale: "skala",
  "förskjut": "forskjut", forskjut: "forskjut", "fö": "forskjut", o: "forskjut", offset: "forskjut",
  "mönster": "monster", monster: "monster", "mö": "monster", ar: "monster", array: "monster",
  trimma: "trimma", tr: "trimma", trim: "trimma",
  "förläng": "forlang", forlang: "forlang", "förl": "forlang", ex: "forlang", extend: "forlang",
  "mät": "mat", mat: "mat", di: "mat", dist: "mat", measure: "mat",
};
export const COMMANDS: { id: ModCmd; label: string; alias: string; needsSelection: boolean; hint: string }[] = [
  { id: "flytta", label: "Flytta", alias: "FL / M", needsSelection: true, hint: "baspunkt → ny plats (eller skriv ett avstånd)" },
  { id: "kopiera", label: "Kopiera", alias: "KO / CO", needsSelection: true, hint: "baspunkt → plats för varje kopia; Enter slutar" },
  { id: "rotera", label: "Rotera", alias: "RO", needsSelection: true, hint: "vridpunkt → vinkel i grader och Enter, eller klicka riktningen" },
  { id: "spegla", label: "Spegla", alias: "SP / MI", needsSelection: true, hint: "två punkter på speglingslinjen; en spegelvänd kopia skapas" },
  { id: "skala", label: "Skala", alias: "SK / SC", needsSelection: true, hint: "baspunkt → skalfaktor och Enter" },
  { id: "forskjut", label: "Förskjut", alias: "FÖ / O", needsSelection: false, hint: "skriv avståndet och Enter, klicka objektet, klicka sidan" },
  { id: "monster", label: "Mönster", alias: "MÖ / AR", needsSelection: true, hint: "kolumner, rader och avstånd i rutan" },
  { id: "trimma", label: "Trimma", alias: "TR", needsSelection: false, hint: "klicka den bit som ska bort; den kapas vid närmaste korsning" },
  { id: "forlang", label: "Förläng", alias: "FÖRL / EX", needsSelection: false, hint: "klicka nära änden som ska dras ut till nästa linje" },
  { id: "mat", label: "Mät", alias: "MÄT / DI", needsSelection: false, hint: "klicka punkter; längd och yta visas, inget ritas" },
];
export const commandOf = (typed: string): ModCmd | null => COMMAND_ALIASES[typed.trim().toLowerCase()] ?? null;
