/* Geometrin bakom byggobjekten: vad de tar upp i planen, i rymden och i ett snitt.
 *
 * Allt här är analytiskt. En vägg är ett prisma över sitt fotavtryck; en öppning i den delar väggen i stycken -
 * vänster om, höger om, ovanför och under öppningen - i stället för att skära ett hål med en booleansk operation
 * som kan gå fel på en degenererad kant. Ett snitt genom ett prisma är skärningen mellan ett lodrätt plan och
 * prismats fotavtryck, lyft mellan prismats underkant och överkant. Mängder räknas ur samma fält som ritar:
 * en väggs yta är dess längd gånger dess höjd minus dess öppningar, inte summan av trianglar i ett nät. */

import {
  type CadDocument, type Entity, type Pt, type Pt3, type Wall, type CurtainWall, type Column, type Beam, type Floor, type Roof,
  type Ceiling, type Door, type Window, type Opening, type Foundation, type Stair, type Pipe, type Duct, type CableTray, type Conduit,
  dist, elevation, entity, hostedIn, verticalExtent, wallLength,
} from "./building";

export type Prism = { id: string; kind: string; poly: Pt[]; z0: number; z1: number; holes?: Pt[][]; color?: string; role?: string };
export type Solid = Prism;      // i dag är varje kropp ett prisma; ett lutande tak är ett prisma per takfall med egen z per hörn

// ---------------------------------------------------------------- polygoner

export function polygonArea(p: Pt[]): number {
  let s = 0;
  for (let i = 0; i < p.length; i++) {
    const a = p[i], b = p[(i + 1) % p.length];
    s += a[0] * b[1] - b[0] * a[1];
  }
  return Math.abs(s) / 2;
}
export function polygonCentroid(p: Pt[]): Pt {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < p.length; i++) {
    const p0 = p[i], p1 = p[(i + 1) % p.length];
    const c = p0[0] * p1[1] - p1[0] * p0[1];
    a += c; cx += (p0[0] + p1[0]) * c; cy += (p0[1] + p1[1]) * c;
  }
  if (Math.abs(a) < 1e-9) return p[0] ?? [0, 0];
  return [cx / (3 * a), cy / (3 * a)];
}
export function perimeter(p: Pt[], closed = true): number {
  let s = 0;
  for (let i = 0; i + 1 < p.length; i++) s += dist(p[i], p[i + 1]);
  if (closed && p.length > 2) s += dist(p[p.length - 1], p[0]);
  return s;
}
export function pointInPolygon(q: Pt, p: Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = p.length - 1; i < p.length; j = i++) {
    const [xi, yi] = p[i], [xj, yj] = p[j];
    if ((yi > q[1]) !== (yj > q[1]) && q[0] < ((xj - xi) * (q[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}
export function bbox2(pts: Pt[]): [number, number, number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return [x0, y0, x1, y1];
}

// ---------------------------------------------------------------- väggar

/** Väggens fotavtryck: centrumlinjen förskjuten åt båda håll, med hänsyn till hur den är justerad. */
export function wallFootprint(w: Wall | CurtainWall): Pt[] {
  const [a, b] = w.p;
  const L = wallLength(w) || 1;
  const n: Pt = [-(b[1] - a[1]) / L, (b[0] - a[0]) / L];
  const t = w.thickness;
  const [l, r] = w.alignment === "left" ? [0, t] : w.alignment === "right" ? [t, 0] : [t / 2, t / 2];
  return [
    [a[0] + n[0] * l, a[1] + n[1] * l], [b[0] + n[0] * l, b[1] + n[1] * l],
    [b[0] - n[0] * r, b[1] - n[1] * r], [a[0] - n[0] * r, a[1] - n[1] * r],
  ];
}

/** Ett stycke av en vägg mellan två andelar längs den, mellan två höjder. */
function wallSlab(w: Wall | CurtainWall, t0: number, t1: number, z0: number, z1: number, role: string): Prism | null {
  if (t1 - t0 <= 1e-9 || z1 - z0 <= 1e-9) return null;
  const [a, b] = w.p;
  const seg: Wall = { ...(w as Wall), p: [[a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0], [a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1]] };
  return { id: w.id, kind: w.type, poly: wallFootprint(seg), z0, z1, role };
}

/** Väggen som kroppar: hel där inget sitter i den, delad kring varje dörr, fönster och öppning. */
export function wallSolids(doc: CadDocument, w: Wall | CurtainWall, openings = hostedIn(doc, w.id)): Prism[] {
  const { z0, z1 } = verticalExtent(doc, w);
  const L = wallLength(w);
  if (L <= 0 || z1 <= z0) return [];
  const holes = openings
    .map((h) => ({ t0: Math.max(0, h.t - h.width / 2 / L), t1: Math.min(1, h.t + h.width / 2 / L), zb: z0 + (h.sill ?? (h.type === "door" ? 0 : 900)), zt: z0 + (h.sill ?? (h.type === "door" ? 0 : 900)) + h.height }))
    .filter((h) => h.t1 > h.t0)
    .sort((x, y) => x.t0 - y.t0);
  const out: Prism[] = [];
  let cursor = 0;
  for (const h of holes) {
    const s = wallSlab(w, cursor, h.t0, z0, z1, "wall");
    if (s) out.push(s);
    const below = wallSlab(w, h.t0, h.t1, z0, Math.min(h.zb, z1), "wall_below");
    if (below) out.push(below);
    const above = wallSlab(w, h.t0, h.t1, Math.max(h.zt, z0), z1, "wall_above");
    if (above) out.push(above);
    cursor = Math.max(cursor, h.t1);
  }
  const last = wallSlab(w, cursor, 1, z0, z1, "wall");
  if (last) out.push(last);
  return out;
}

/** Öppningens egen kropp - det som fyller hålet: dörrbladet, glaset. Ritas tunt mitt i väggen. */
export function hostedSolid(doc: CadDocument, h: Door | Window | Opening): Prism | null {
  const w = entity<Wall>(doc, h.host);
  if (!w || (w.type !== "wall" && w.type !== "curtain_wall")) return null;
  const L = wallLength(w);
  const { z0 } = verticalExtent(doc, w);
  const sill = h.sill ?? (h.type === "door" ? 0 : 900);
  const t0 = Math.max(0, h.t - h.width / 2 / L), t1 = Math.min(1, h.t + h.width / 2 / L);
  const thin: Wall = { ...w, thickness: Math.max(20, Math.min(60, w.thickness * 0.25)), alignment: "centre" };
  const s = wallSlab(thin, t0, t1, z0 + sill, z0 + sill + h.height, h.type);
  if (!s) return null;
  return { ...s, id: h.id, kind: h.type };
}

// ---------------------------------------------------------------- horisontella kroppar

export function floorSolid(doc: CadDocument, f: Floor): Prism {
  const z = elevation(doc, f.level) + (f.offset ?? 0);
  return { id: f.id, kind: "floor", poly: f.p, z0: z - f.thickness, z1: z, holes: f.holes };
}
export function ceilingSolid(doc: CadDocument, c: Ceiling): Prism {
  const z = elevation(doc, c.level) + c.height_offset;
  return { id: c.id, kind: "ceiling", poly: c.p, z0: z, z1: z + c.thickness };
}
export function foundationSolids(doc: CadDocument, f: Foundation): Prism[] {
  const z = elevation(doc, f.level) + (f.offset ?? 0);
  if (f.kind === "slab") return [{ id: f.id, kind: "foundation", poly: f.p, z0: z - f.h, z1: z }];
  if (f.kind === "isolated") {
    const [c] = f.p; const w = (f.w ?? 1000) / 2, d = (f.d ?? f.w ?? 1000) / 2;
    return [{ id: f.id, kind: "foundation", poly: [[c[0] - w, c[1] - d], [c[0] + w, c[1] - d], [c[0] + w, c[1] + d], [c[0] - w, c[1] + d]], z0: z - f.h, z1: z }];
  }
  // strip: en remsa längs polylinjen, w bred
  const out: Prism[] = [];
  const half = (f.w ?? 600) / 2;
  for (let i = 0; i + 1 < f.p.length; i++) {
    const a = f.p[i], b = f.p[i + 1]; const L = dist(a, b) || 1;
    const n: Pt = [-(b[1] - a[1]) / L * half, (b[0] - a[0]) / L * half];
    out.push({ id: f.id, kind: "foundation", poly: [[a[0] + n[0], a[1] + n[1]], [b[0] + n[0], b[1] + n[1]], [b[0] - n[0], b[1] - n[1]], [a[0] - n[0], a[1] - n[1]]], z0: z - f.h, z1: z });
  }
  return out;
}

/** Taket: platt är ett prisma; ett sadeltak är två takfall med lutande överkant (hörnens z i `top`). */
export type RoofPlane = Prism & { top?: number[] };
export function roofSolids(doc: CadDocument, r: Roof): RoofPlane[] {
  const z = elevation(doc, r.level) + (r.offset ?? 0);
  if (r.kind === "flat" || !r.ridge || !(r.slope_deg! > 0)) return [{ id: r.id, kind: "roof", poly: r.p, z0: z, z1: z + r.thickness }];
  // varje hörn lyfts med avståndet till nocken gånger lutningen: lägst vid takfoten, högst vid nocken
  const [ra, rb] = r.ridge; const L = dist(ra, rb) || 1;
  const n: Pt = [-(rb[1] - ra[1]) / L, (rb[0] - ra[0]) / L];
  const distTo = (p: Pt) => Math.abs((p[0] - ra[0]) * n[0] + (p[1] - ra[1]) * n[1]);
  const far = Math.max(...r.p.map(distTo));
  const tan = Math.tan((r.slope_deg! * Math.PI) / 180);
  // ett takfall per sida om nocken: då har varje kropp en plan överkant, och ett snitt tvärs taket får sin nock
  const halves = [clipHalf(r.p, ra, n, 1), clipHalf(r.p, ra, n, -1)].filter((h) => h.length >= 3 && polygonArea(h) > 1e-6);
  return (halves.length ? halves : [r.p]).map((h) => ({ id: r.id, kind: "roof", poly: h, z0: z, z1: z + far * tan + r.thickness, top: h.map((p) => z + (far - distTo(p)) * tan) }));
}
/** Den del av polygonen som ligger på ena sidan om linjen genom a med normalen n (Sutherland-Hodgman mot ett halvplan). */
function clipHalf(poly: Pt[], a: Pt, n: Pt, sign: 1 | -1): Pt[] {
  const side = (p: Pt) => sign * ((p[0] - a[0]) * n[0] + (p[1] - a[1]) * n[1]);
  const out: Pt[] = [];
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length];
    const sp = side(p), sq = side(q);
    if (sp >= 0) out.push(p);
    if ((sp >= 0) !== (sq >= 0)) { const t = sp / (sp - sq); out.push([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]); }
  }
  return out;
}
export function roofHeightAt(doc: CadDocument, r: Roof, p: Pt): number {
  const z = elevation(doc, r.level) + (r.offset ?? 0);
  if (r.kind === "flat" || !r.ridge || !(r.slope_deg! > 0)) return z;
  const [ra, rb] = r.ridge; const L = dist(ra, rb) || 1;
  const n: Pt = [-(rb[1] - ra[1]) / L, (rb[0] - ra[0]) / L];
  const distTo = (q: Pt) => Math.abs((q[0] - ra[0]) * n[0] + (q[1] - ra[1]) * n[1]);
  const far = Math.max(...r.p.map(distTo));
  return z + (far - distTo(p)) * Math.tan((r.slope_deg! * Math.PI) / 180);
}

// ---------------------------------------------------------------- konstruktion

export function profilePolygon(pr: Column["profile"], c: Pt, rot = 0): Pt[] {
  const R = (rot * Math.PI) / 180;
  const rotp = (x: number, y: number): Pt => [c[0] + x * Math.cos(R) - y * Math.sin(R), c[1] + x * Math.sin(R) + y * Math.cos(R)];
  if (pr.kind === "circle") {
    const n = 24, out: Pt[] = [];
    for (let i = 0; i < n; i++) out.push([c[0] + (pr.d / 2) * Math.cos((2 * Math.PI * i) / n), c[1] + (pr.d / 2) * Math.sin((2 * Math.PI * i) / n)]);
    return out;
  }
  const w = pr.w / 2, d = pr.d / 2;
  return [rotp(-w, -d), rotp(w, -d), rotp(w, d), rotp(-w, d)];
}
export function profileArea(pr: Column["profile"]): number {
  if (pr.kind === "circle") return (Math.PI * pr.d * pr.d) / 4;
  if (pr.kind === "rect") return pr.w * pr.d;
  const t = pr.t;
  switch (pr.kind) {
    case "I": case "H": return 2 * pr.w * t + (pr.d - 2 * t) * t;
    case "U": return pr.w * t * 2 + (pr.d - 2 * t) * t;
    case "L": return pr.w * t + (pr.d - t) * t;
    case "RHS": case "SHS": return pr.w * pr.d - (pr.w - 2 * t) * (pr.d - 2 * t);
  }
}
export function columnSolid(doc: CadDocument, c: Column): Prism {
  const { z0, z1 } = verticalExtent(doc, c);
  return { id: c.id, kind: "column", poly: profilePolygon(c.profile, c.p[0], c.rot ?? 0), z0, z1 };
}
export function beamSolid(doc: CadDocument, b: Beam): Prism {
  const z1 = elevation(doc, b.level) + (b.elevation_offset ?? 0);
  const depth = b.profile.kind === "circle" ? b.profile.d : b.profile.d;
  const width = b.profile.kind === "circle" ? b.profile.d : b.profile.w;
  const [a, e] = b.p; const L = dist(a, e) || 1;
  const n: Pt = [-(e[1] - a[1]) / L * width / 2, (e[0] - a[0]) / L * width / 2];
  return { id: b.id, kind: "beam", poly: [[a[0] + n[0], a[1] + n[1]], [e[0] + n[0], e[1] + n[1]], [e[0] - n[0], e[1] - n[1]], [a[0] - n[0], a[1] - n[1]]], z0: z1 - depth, z1 };
}

// ---------------------------------------------------------------- trappa

export function stairSolids(doc: CadDocument, s: Stair): Prism[] {
  const z0 = elevation(doc, s.base_level), z1 = elevation(doc, s.top_level);
  const rise = (z1 - z0) / s.risers;
  const [a, b] = s.p; const L = dist(a, b) || 1;
  const dir: Pt = [(b[0] - a[0]) / L, (b[1] - a[1]) / L];
  const n: Pt = [-dir[1] * s.width / 2, dir[0] * s.width / 2];
  const out: Prism[] = [];
  for (let i = 0; i < s.risers; i++) {
    const t0 = i * s.tread_d, t1 = (i + 1) * s.tread_d;
    const p0: Pt = [a[0] + dir[0] * t0, a[1] + dir[1] * t0], p1: Pt = [a[0] + dir[0] * t1, a[1] + dir[1] * t1];
    out.push({ id: s.id, kind: "stair", poly: [[p0[0] + n[0], p0[1] + n[1]], [p1[0] + n[0], p1[1] + n[1]], [p1[0] - n[0], p1[1] - n[1]], [p0[0] - n[0], p0[1] - n[1]]], z0: z0 + i * rise - Math.min(180, rise), z1: z0 + (i + 1) * rise });
  }
  return out;
}

// ---------------------------------------------------------------- MEP

export type Tube = { id: string; kind: string; path: Pt3[]; w: number; h: number; round: boolean; color?: string; system?: string };
export function pathTube(doc: CadDocument, e: Pipe | Duct | CableTray | Conduit): Tube {
  const z = elevation(doc, e.level) + (e.elevation ?? 0);
  const path = e.path.map((p) => [p[0], p[1], (p[2] ?? 0) + z] as Pt3);
  if (e.type === "pipe") return { id: e.id, kind: "pipe", path, w: e.dn, h: e.dn, round: true, system: e.system };
  if (e.type === "duct") return e.shape === "round"
    ? { id: e.id, kind: "duct", path, w: e.d ?? 200, h: e.d ?? 200, round: true, system: e.system }
    : { id: e.id, kind: "duct", path, w: e.w ?? 400, h: e.h ?? 200, round: false, system: e.system };
  if (e.type === "cable_tray") return { id: e.id, kind: "cable_tray", path, w: e.w, h: e.h, round: false, system: e.system };
  return { id: e.id, kind: "conduit", path, w: e.d, h: e.d, round: true, system: e.system };
}
export function pathLength(path: Pt3[]): number {
  let s = 0;
  for (let i = 0; i + 1 < path.length; i++) s += Math.hypot(path[i + 1][0] - path[i][0], path[i + 1][1] - path[i][1], path[i + 1][2] - path[i][2]);
  return s;
}

// ---------------------------------------------------------------- alla kroppar i ett dokument

export function solidsOf(doc: CadDocument, e: Entity): Prism[] {
  switch (e.type) {
    case "wall": case "curtain_wall": return wallSolids(doc, e);
    case "door": case "window": case "opening": { const s = hostedSolid(doc, e); return s ? [s] : []; }
    case "floor": return [floorSolid(doc, e)];
    case "ceiling": return [ceilingSolid(doc, e)];
    case "roof": return roofSolids(doc, e);
    case "column": return [columnSolid(doc, e)];
    case "beam": return [beamSolid(doc, e)];
    case "foundation": return foundationSolids(doc, e);
    case "stair": return stairSolids(doc, e);
    case "equipment": {
      const [c] = e.p; const [w, d, h] = e.size; const z = elevation(doc, e.level) + c[2];
      return [{ id: e.id, kind: "equipment", poly: [[c[0] - w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] - d / 2], [c[0] + w / 2, c[1] + d / 2], [c[0] - w / 2, c[1] + d / 2]], z0: z, z1: z + h }];
    }
    default: return [];
  }
}

export function aabbOfPrism(p: Prism): { min: Pt3; max: Pt3 } {
  const [x0, y0, x1, y1] = bbox2(p.poly);
  return { min: [x0, y0, p.z0], max: [x1, y1, p.z1] };
}

// ---------------------------------------------------------------- snitt

/** Ett lodrätt snittplan genom linjen a-b, sett från vänster sida av linjen: x längs linjen, y = höjd. */
export type SectionPlane = { a: Pt; b: Pt; depth: number };
export type SectionShape = { id: string; kind: string; poly: [number, number][]; role?: string };

function clipSegmentToPolygon(a: Pt, b: Pt, poly: Pt[]): [number, number][] {
  // parametrarna längs a-b där linjen går in i och ut ur polygonen (konvex eller ej: udda-jämn på korsningar)
  const ts: number[] = [];
  for (let i = 0; i < poly.length; i++) {
    const c = poly[i], d = poly[(i + 1) % poly.length];
    const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]];
    const den = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(den) < 1e-12) continue;
    const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den;
    const u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
    if (u >= -1e-9 && u <= 1 + 1e-9) ts.push(t);
  }
  // ett hörn hör till två kanter och ger samma t två gånger; en linje längs en kant ger inget alls från den
  // kanten men ett t från var och en av grannkanterna. Lika t räknas en gång, sedan paras de ihop.
  ts.sort((x, y) => x - y);
  const uniq: number[] = [];
  for (const t of ts) if (!uniq.length || Math.abs(t - uniq[uniq.length - 1]) > 1e-9) uniq.push(t);
  const out: [number, number][] = [];
  for (let i = 0; i + 1 < uniq.length; i += 2) out.push([uniq[i], uniq[i + 1]]);
  return out;
}

/** Snittet genom ett prisma: rektanglar i snittplanet där planet går genom fotavtrycket. */
export function sectionOfPrism(pl: SectionPlane, p: Prism | RoofPlane): SectionShape[] {
  const L = dist(pl.a, pl.b) || 1;
  const spans = clipSegmentToPolygon(pl.a, pl.b, p.poly);
  const out: SectionShape[] = [];
  for (const [t0, t1] of spans) {
    const x0 = t0 * L, x1 = t1 * L;
    const top = (p as RoofPlane).top;
    if (top && top.length === p.poly.length) {
      // lutande överkant: höjden i varje ände interpoleras ur hörnens z (planet skär ett lutande takfall)
      const zAt = (t: number): number => {
        const q: Pt = [pl.a[0] + (pl.b[0] - pl.a[0]) * t, pl.a[1] + (pl.b[1] - pl.a[1]) * t];
        let best = Infinity, bz = p.z1;
        for (let i = 0; i < p.poly.length; i++) { const d = dist(q, p.poly[i]); if (d < best) { best = d; bz = top[i]; } }
        return bz;
      };
      out.push({ id: p.id, kind: p.kind, role: p.role, poly: [[x0, p.z0], [x1, p.z0], [x1, zAt(t1)], [x0, zAt(t0)]] });
    } else {
      out.push({ id: p.id, kind: p.kind, role: p.role, poly: [[x0, p.z0], [x1, p.z0], [x1, p.z1], [x0, p.z1]] });
    }
  }
  return out;
}

/** Hela sektionen: allt planet skär, plus rörens och kanalernas snitt som små rutor. */
export function sectionOfDocument(doc: CadDocument, pl: SectionPlane, entities: Entity[] = doc.entities): SectionShape[] {
  const out: SectionShape[] = [];
  for (const e of entities) {
    for (const s of solidsOf(doc, e)) out.push(...sectionOfPrism(pl, s));
    if (e.type === "pipe" || e.type === "duct" || e.type === "cable_tray" || e.type === "conduit") {
      const tube = pathTube(doc, e);
      const L = dist(pl.a, pl.b) || 1;
      for (let i = 0; i + 1 < tube.path.length; i++) {
        const c: Pt = [tube.path[i][0], tube.path[i][1]], d: Pt = [tube.path[i + 1][0], tube.path[i + 1][1]];
        const r = [pl.b[0] - pl.a[0], pl.b[1] - pl.a[1]], s = [d[0] - c[0], d[1] - c[1]];
        const den = r[0] * s[1] - r[1] * s[0];
        if (Math.abs(den) < 1e-12) continue;
        const t = ((c[0] - pl.a[0]) * s[1] - (c[1] - pl.a[1]) * s[0]) / den;
        const u = ((c[0] - pl.a[0]) * r[1] - (c[1] - pl.a[1]) * r[0]) / den;
        if (t < 0 || t > 1 || u < 0 || u > 1) continue;
        const x = t * L, z = tube.path[i][2] + (tube.path[i + 1][2] - tube.path[i][2]) * u;
        out.push({ id: e.id, kind: tube.kind, poly: [[x - tube.w / 2, z - tube.h / 2], [x + tube.w / 2, z - tube.h / 2], [x + tube.w / 2, z + tube.h / 2], [x - tube.w / 2, z + tube.h / 2]] });
      }
    }
  }
  return out;
}

/** En fasad är ett snitt strax utanför byggnaden, sett inåt: allt bakom planet inom djupet projiceras. */
function elevationBodies(doc: CadDocument, entities: Entity[]): Prism[] {
  // Build once for this read, including openings outside the visible entity selection.
  // Nothing is cached across edits, undo, or changed host relationships.
  const openings = new Map<string, (Door | Window | Opening)[]>();
  for (const e of doc.entities) {
    if (e.type === "door" || e.type === "window" || e.type === "opening") {
      const group = openings.get(e.host);
      if (group) group.push(e); else openings.set(e.host, [e]);
    }
  }
  return entities.flatMap((e) => e.type === "wall" || e.type === "curtain_wall"
    ? wallSolids(doc, e, openings.get(e.id) ?? []) : solidsOf(doc, e));
}

export function elevationPlane(doc: CadDocument, dir: "N" | "S" | "E" | "W", entities: Entity[] = doc.entities): SectionPlane {
  const pts: Pt[] = [];
  for (const s of elevationBodies(doc, entities)) pts.push(...s.poly);
  if (!pts.length) return { a: [0, 0], b: [10000, 0], depth: 100000 };
  const [x0, y0, x1, y1] = bbox2(pts);
  const m = 1000;
  switch (dir) {
    case "S": return { a: [x0 - m, y1 + m], b: [x1 + m, y1 + m], depth: y1 - y0 + 2 * m };   // y växer nedåt i planen: söder är stort y
    case "N": return { a: [x1 + m, y0 - m], b: [x0 - m, y0 - m], depth: y1 - y0 + 2 * m };
    case "E": return { a: [x1 + m, y1 + m], b: [x1 + m, y0 - m], depth: x1 - x0 + 2 * m };
    case "W": return { a: [x0 - m, y0 - m], b: [x0 - m, y1 + m], depth: x1 - x0 + 2 * m };
  }
}

/** Fasaden: varje kropp projicerad på planet som den syns framifrån (dess utbredning längs planet gånger höjd). */
export function elevationOfDocument(doc: CadDocument, pl: SectionPlane, entities: Entity[] = doc.entities): SectionShape[] {
  const L = dist(pl.a, pl.b) || 1;
  const ux = (pl.b[0] - pl.a[0]) / L, uy = (pl.b[1] - pl.a[1]) / L;
  // normalen pekar mot byggnaden: den sida där det mesta av det ritade står
  const all = elevationBodies(doc, entities);
  let side = 0;
  for (const s of all) for (const q of s.poly) side += (q[0] - pl.a[0]) * -uy + (q[1] - pl.a[1]) * ux;
  const flip = side < 0 ? -1 : 1;
  const nx = -uy * flip, ny = ux * flip;
  const out: (SectionShape & { depth: number })[] = [];
  // The bodies were already computed to choose the viewing direction.
  for (const s of all) {
    let x0 = Infinity, x1 = -Infinity, dmin = Infinity;
    for (const q of s.poly) {
      const x = (q[0] - pl.a[0]) * ux + (q[1] - pl.a[1]) * uy;
      const dd = (q[0] - pl.a[0]) * nx + (q[1] - pl.a[1]) * ny;
      x0 = Math.min(x0, x); x1 = Math.max(x1, x); dmin = Math.min(dmin, dd);
    }
    if (dmin < -1 || dmin > pl.depth) continue;
    const top = (s as RoofPlane).top;
    const z1 = top ? Math.max(...top) : s.z1;
    out.push({ id: s.id, kind: s.kind, role: s.role, poly: [[x0, s.z0], [x1, s.z0], [x1, z1], [x0, z1]], depth: dmin });
  }
  // det närmaste ritas sist så att det ligger överst
  return out.sort((a, b) => b.depth - a.depth).map(({ depth: _d, ...rest }) => rest);
}
