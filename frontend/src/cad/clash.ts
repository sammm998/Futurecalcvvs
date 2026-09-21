/* Kollisioner: var två kroppar tar samma plats.
 *
 * Grovt först - kroppar vars lådor inte överlappar kan inte kollidera - och sedan fint: två prismor kolliderar
 * där deras höjdintervall överlappar och deras fotavtryck skär varandra; ett rör eller en kanal kolliderar med
 * ett prisma där ett segment av vägen går genom prismats fotavtryck på en höjd inom prismats intervall. Rör mot
 * rör: två rundade segment närmare varandra än summan av radierna.
 *
 * En dörr i sin egen vägg är ingen kollision, och det ett objekt sitter i räknas inte mot det. */

import { type CadDocument, type Discipline, type Entity, type Pt, type Pt3, MEP_PATH_TYPES } from "./building";
import { type Prism, aabbOfPrism, bbox2, pathTube, pointInPolygon, solidsOf } from "./solids";

export type Clash = {
  id: string; a: string; b: string; a_type: Entity["type"]; b_type: Entity["type"];
  a_discipline: Discipline; b_discipline: Discipline; at: Pt3; severity: "hög" | "medel" | "låg"; note: string;
};

type Body = { e: Entity; prisms: Prism[]; tube?: ReturnType<typeof pathTube> | null; box: { min: Pt3; max: Pt3 } };

function boxes(doc: CadDocument, es: Entity[]): Body[] {
  const out: Body[] = [];
  for (const e of es) {
    if (MEP_PATH_TYPES.includes(e.type)) {
      const tube = pathTube(doc, e as any);
      const xs = tube.path.map((p) => p[0]), ys = tube.path.map((p) => p[1]), zs = tube.path.map((p) => p[2]);
      const r = Math.max(tube.w, tube.h) / 2;
      out.push({ e, prisms: [], tube, box: { min: [Math.min(...xs) - r, Math.min(...ys) - r, Math.min(...zs) - r], max: [Math.max(...xs) + r, Math.max(...ys) + r, Math.max(...zs) + r] } });
      continue;
    }
    const prisms = solidsOf(doc, e).filter((p) => p.role !== "wall_below" && p.role !== "wall_above" || true);
    if (!prisms.length) continue;
    const bs = prisms.map(aabbOfPrism);
    out.push({ e, prisms, tube: null, box: { min: [Math.min(...bs.map((b) => b.min[0])), Math.min(...bs.map((b) => b.min[1])), Math.min(...bs.map((b) => b.min[2]))], max: [Math.max(...bs.map((b) => b.max[0])), Math.max(...bs.map((b) => b.max[1])), Math.max(...bs.map((b) => b.max[2]))] } });
  }
  return out;
}

const overlaps = (a: { min: Pt3; max: Pt3 }, b: { min: Pt3; max: Pt3 }, tol = 1) =>
  a.min[0] < b.max[0] - tol && a.max[0] > b.min[0] + tol && a.min[1] < b.max[1] - tol && a.max[1] > b.min[1] + tol && a.min[2] < b.max[2] - tol && a.max[2] > b.min[2] + tol;

function segsCross(a: Pt, b: Pt, c: Pt, d: Pt): Pt | null {
  const r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]];
  const den = r[0] * s[1] - r[1] * s[0];
  if (Math.abs(den) < 1e-12) return null;
  const t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den;
  const u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
  if (t < 0 || t > 1 || u < 0 || u > 1) return null;
  return [a[0] + r[0] * t, a[1] + r[1] * t];
}

/** Skär två polygoner varandra (kant mot kant, eller den ena helt inuti den andra)? Returnerar en punkt i överlappet. */
function polysOverlap(p: Pt[], q: Pt[]): Pt | null {
  for (let i = 0; i < p.length; i++) for (let j = 0; j < q.length; j++) {
    const x = segsCross(p[i], p[(i + 1) % p.length], q[j], q[(j + 1) % q.length]);
    if (x) return x;
  }
  if (pointInPolygon(p[0], q)) return p[0];
  if (pointInPolygon(q[0], p)) return q[0];
  return null;
}

function prismVsPrism(a: Prism, b: Prism): Pt3 | null {
  const z0 = Math.max(a.z0, b.z0), z1 = Math.min(a.z1, b.z1);
  if (z1 - z0 <= 1) return null;
  // ett gemensamt hörn eller en gemensam kant räknas inte: väggar möts i hörn, balkar ligger på pelare
  const x = polysOverlap(shrink(a.poly, 2), shrink(b.poly, 2));
  return x ? [x[0], x[1], (z0 + z1) / 2] : null;
}
function shrink(p: Pt[], d: number): Pt[] {
  const [x0, y0, x1, y1] = bbox2(p);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  return p.map(([x, y]) => [x + (cx > x ? d : -d), y + (cy > y ? d : -d)] as Pt);
}

function tubeVsPrism(t: NonNullable<Body["tube"]>, p: Prism): Pt3 | null {
  const r = Math.max(t.w, t.h) / 2;
  for (let i = 0; i + 1 < t.path.length; i++) {
    const a = t.path[i], b = t.path[i + 1];
    // provpunkter längs segmentet: inne i fotavtrycket och på en höjd inom prismat, med rörets radie
    const n = Math.max(2, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2]) / 50));
    for (let k = 0; k <= n; k++) {
      const s = k / n;
      const q: Pt3 = [a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, a[2] + (b[2] - a[2]) * s];
      if (q[2] + r <= p.z0 + 1 || q[2] - r >= p.z1 - 1) continue;
      if (pointInPolygon([q[0], q[1]], p.poly)) return q;
    }
  }
  return null;
}

function segDist3(a: Pt3, b: Pt3, c: Pt3, d: Pt3): { d: number; at: Pt3 } {
  // närmaste avstånd mellan två segment i rymden, provat i ett rutnät av parametrar (robust, tillräckligt fint)
  let best = Infinity, at: Pt3 = a;
  const N = 12;
  for (let i = 0; i <= N; i++) for (let j = 0; j <= N; j++) {
    const s = i / N, t = j / N;
    const p: Pt3 = [a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s, a[2] + (b[2] - a[2]) * s];
    const q: Pt3 = [c[0] + (d[0] - c[0]) * t, c[1] + (d[1] - c[1]) * t, c[2] + (d[2] - c[2]) * t];
    const dd = Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]);
    if (dd < best) { best = dd; at = [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2, (p[2] + q[2]) / 2]; }
  }
  return { d: best, at };
}
function tubeVsTube(a: NonNullable<Body["tube"]>, b: NonNullable<Body["tube"]>): Pt3 | null {
  const ra = Math.max(a.w, a.h) / 2, rb = Math.max(b.w, b.h) / 2;
  for (let i = 0; i + 1 < a.path.length; i++) for (let j = 0; j + 1 < b.path.length; j++) {
    const { d, at } = segDist3(a.path[i], a.path[i + 1], b.path[j], b.path[j + 1]);
    if (d < ra + rb - 1) return at;
  }
  return null;
}

function related(a: Entity, b: Entity): boolean {
  if ("host" in a && a.host === b.id) return true;
  if ("host" in b && b.host === a.id) return true;
  if (a.type === "beam" && a.supports?.includes(b.id)) return true;
  if (b.type === "beam" && b.supports?.includes(a.id)) return true;
  return false;
}

function severity(a: Entity, b: Entity): Clash["severity"] {
  const s = new Set([a.discipline, b.discipline]);
  if (s.has("KONSTR") && (s.has("VVS") || s.has("VENT") || s.has("EL") || s.has("SPRINKLER"))) return "hög";
  if (a.discipline !== b.discipline) return "medel";
  return "låg";
}

/** Alla kollisioner i dokumentet, eller mellan två urval av objekt (en disciplin mot en annan). */
export function findClashes(doc: CadDocument, left: Entity[] = doc.entities, right?: Entity[]): Clash[] {
  const A = boxes(doc, left), B = right ? boxes(doc, right) : A;
  const out: Clash[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < A.length; i++) {
    for (let j = right ? 0 : i + 1; j < B.length; j++) {
      const x = A[i], y = B[j];
      if (x.e.id === y.e.id || related(x.e, y.e)) continue;
      const key = [x.e.id, y.e.id].sort().join("|");
      if (seen.has(key)) continue;
      if (!overlaps(x.box, y.box)) continue;
      let at: Pt3 | null = null;
      if (x.tube && y.tube) at = tubeVsTube(x.tube, y.tube);
      else if (x.tube) { for (const p of y.prisms) { at = tubeVsPrism(x.tube, p); if (at) break; } }
      else if (y.tube) { for (const p of x.prisms) { at = tubeVsPrism(y.tube, p); if (at) break; } }
      else { outer: for (const p of x.prisms) for (const q of y.prisms) { at = prismVsPrism(p, q); if (at) break outer; } }
      if (!at) continue;
      seen.add(key);
      out.push({
        id: key, a: x.e.id, b: y.e.id, a_type: x.e.type, b_type: y.e.type, a_discipline: x.e.discipline, b_discipline: y.e.discipline,
        at: [Math.round(at[0]), Math.round(at[1]), Math.round(at[2])], severity: severity(x.e, y.e),
        note: `${x.e.name || x.e.type} korsar ${y.e.name || y.e.type}`,
      });
    }
  }
  const order = { hög: 0, medel: 1, låg: 2 };
  return out.sort((p, q) => order[p.severity] - order[q.severity]);
}

/** Där ett rör eller en kanal går genom en vägg eller ett bjälklag behövs ett hål: förslag, aldrig ett beslut. */
export type OpeningProposal = { host: string; through: string; at: Pt3; size_mm: number; note: string };
export function proposeOpenings(doc: CadDocument, clashes: Clash[]): OpeningProposal[] {
  const out: OpeningProposal[] = [];
  for (const c of clashes) {
    const [pathId, hostId] = MEP_PATH_TYPES.includes(c.a_type) ? [c.a, c.b] : MEP_PATH_TYPES.includes(c.b_type) ? [c.b, c.a] : [null, null];
    if (!pathId || !hostId) continue;
    const host = doc.entities.find((e) => e.id === hostId), path = doc.entities.find((e) => e.id === pathId);
    if (!host || !path || !(host.type === "wall" || host.type === "floor" || host.type === "roof" || host.type === "ceiling")) continue;
    const tube = pathTube(doc, path as any);
    const size = Math.ceil((Math.max(tube.w, tube.h) + 60) / 10) * 10;      // rörets mått plus spel, till närmaste tio
    out.push({ host: hostId, through: pathId, at: c.at, size_mm: size,
               note: `${path.name || tube.kind.toUpperCase()} ${tube.round ? "Ø" : ""}${tube.round ? tube.w : `${tube.w}×${tube.h}`} passerar ${host.name || host.type}. Föreslaget hål ${tube.round ? "Ø" : ""}${size} mm.` });
  }
  return out;
}
