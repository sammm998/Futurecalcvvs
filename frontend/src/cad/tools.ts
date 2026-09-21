/* Verktygen: vad ett klick blir.
 *
 * Varje verktyg vet hur många punkter det behöver och hur punkterna blir ett objekt med sina egenskaper -
 * väggen från två punkter med sin tjocklek och sina nivåer, dörren från ett klick på en vägg, pelaren från en
 * punkt och en profil. Verktygslådan byter efter disciplin, men objekten hamnar i samma modell. */

import {
  type CadDocument, type Entity, type Pt, type Pt3, type Discipline, type View, type Wall, type Profile, uid,
} from "./building";
import { wallAt } from "./plan";

export type ToolId =
  | "valj" | "vagg" | "glasfasad" | "dorr" | "fonster" | "oppning" | "bjalklag" | "tak" | "undertak" | "rum" | "trappa" | "racke"
  | "pelare" | "balk" | "grund" | "platta"
  | "ror" | "kanal" | "kabelstege" | "elror" | "utrustning" | "apparat" | "koppling"
  | "terrang" | "tomtgrans"
  | "linje" | "polylinje" | "rektangel" | "cirkel" | "bage" | "text" | "matt" | "hanvisning" | "skraffering" | "natlinje";

export type Tool = { id: ToolId; label: string; key: string; hint: string; points: number | "many" | "wall" | "one"; disciplines: Discipline[] | "all" };

export const TOOLS: Tool[] = [
  { id: "valj", label: "Välj", key: "V", hint: "klicka eller dra en ruta; dra grepp för att ändra form", points: 0, disciplines: "all" },
  { id: "vagg", label: "Vägg", key: "W", hint: "start → slut; skriv en längd i mm och Enter", points: 2, disciplines: ["ARK", "KONSTR"] },
  { id: "glasfasad", label: "Glasfasad", key: "G", hint: "start → slut", points: 2, disciplines: ["ARK"] },
  { id: "dorr", label: "Dörr", key: "D", hint: "klicka på en vägg", points: "wall", disciplines: ["ARK"] },
  { id: "fonster", label: "Fönster", key: "F", hint: "klicka på en vägg", points: "wall", disciplines: ["ARK"] },
  { id: "oppning", label: "Öppning", key: "O", hint: "klicka på en vägg", points: "wall", disciplines: ["ARK", "KONSTR"] },
  { id: "bjalklag", label: "Bjälklag", key: "B", hint: "klicka hörnen, Enter eller C sluter", points: "many", disciplines: ["ARK"] },
  { id: "tak", label: "Tak", key: "T", hint: "klicka hörnen, Enter sluter; nock och lutning i egenskaperna", points: "many", disciplines: ["ARK"] },
  { id: "undertak", label: "Undertak", key: "U", hint: "klicka hörnen, Enter sluter", points: "many", disciplines: ["ARK", "VENT"] },
  { id: "rum", label: "Rum", key: "R", hint: "klicka hörnen, Enter sluter", points: "many", disciplines: ["ARK"] },
  { id: "trappa", label: "Trappa", key: "S", hint: "start nere → riktning", points: 2, disciplines: ["ARK"] },
  { id: "racke", label: "Räcke", key: "Ä", hint: "klicka längs vägen, Enter avslutar", points: "many", disciplines: ["ARK"] },
  { id: "pelare", label: "Pelare", key: "P", hint: "klicka där pelaren står", points: "one", disciplines: ["KONSTR"] },
  { id: "balk", label: "Balk", key: "K", hint: "start → slut", points: 2, disciplines: ["KONSTR"] },
  { id: "platta", label: "Platta", key: "L", hint: "klicka hörnen, Enter sluter", points: "many", disciplines: ["KONSTR"] },
  { id: "grund", label: "Grund", key: "N", hint: "klicka längs sulan, Enter avslutar", points: "many", disciplines: ["KONSTR"] },
  { id: "ror", label: "Rör", key: "Q", hint: "klicka punkterna, Enter avslutar; DN och system i egenskaperna", points: "many", disciplines: ["VVS", "SPRINKLER"] },
  { id: "kanal", label: "Kanal", key: "A", hint: "klicka punkterna, Enter avslutar", points: "many", disciplines: ["VENT"] },
  { id: "kabelstege", label: "Kabelstege", key: "E", hint: "klicka punkterna, Enter avslutar", points: "many", disciplines: ["EL"] },
  { id: "elror", label: "Elrör", key: "J", hint: "klicka punkterna, Enter avslutar", points: "many", disciplines: ["EL"] },
  { id: "utrustning", label: "Utrustning", key: "X", hint: "klicka där den står", points: "one", disciplines: ["VVS", "VENT", "EL", "SPRINKLER", "UTRUSTNING"] },
  { id: "apparat", label: "Apparat", key: "Y", hint: "klicka där den sitter", points: "one", disciplines: ["EL", "VENT", "SPRINKLER", "BRAND"] },
  { id: "koppling", label: "Koppling", key: "I", hint: "klicka på röret", points: "one", disciplines: ["VVS", "VENT", "SPRINKLER"] },
  { id: "tomtgrans", label: "Tomtgräns", key: "Z", hint: "klicka hörnen, Enter sluter", points: "many", disciplines: ["MARK"] },
  { id: "terrang", label: "Terräng", key: "H", hint: "klicka höjdpunkter, Enter avslutar; höjden i egenskaperna", points: "many", disciplines: ["MARK"] },
  { id: "linje", label: "Linje", key: "1", hint: "start → slut", points: 2, disciplines: "all" },
  { id: "polylinje", label: "Polylinje", key: "2", hint: "klicka punkterna, Enter avslutar, C sluter", points: "many", disciplines: "all" },
  { id: "rektangel", label: "Rektangel", key: "3", hint: "två hörn", points: 2, disciplines: "all" },
  { id: "cirkel", label: "Cirkel", key: "4", hint: "centrum → radie", points: 2, disciplines: "all" },
  { id: "bage", label: "Båge", key: "5", hint: "start, en punkt på bågen, slut", points: 3, disciplines: "all" },
  { id: "text", label: "Text", key: "6", hint: "klicka där texten börjar", points: "one", disciplines: "all" },
  { id: "matt", label: "Mått", key: "M", hint: "två punkter, sedan avståndet", points: 3, disciplines: "all" },
  { id: "hanvisning", label: "Hänvisning", key: "7", hint: "från objektet till texten, Enter avslutar", points: "many", disciplines: "all" },
  { id: "skraffering", label: "Skraffering", key: "8", hint: "klicka hörnen, Enter sluter", points: "many", disciplines: "all" },
  { id: "natlinje", label: "Nätlinje", key: "9", hint: "start → slut; bokstav eller siffra i egenskaperna", points: 2, disciplines: "all" },
];

export function toolsFor(discipline: Discipline): Tool[] {
  return TOOLS.filter((t) => t.disciplines === "all" || t.disciplines.includes(discipline));
}

/** Vad ett verktyg får för egenskaper när det ritar: det senast använda, per verktyg. */
export type ToolDefaults = {
  wall: { thickness: number; height: number | null; material: string; alignment: "centre" | "left" | "right"; structural: boolean };
  door: { width: number; height: number; swing: "left" | "right" | "double" | "sliding" };
  window: { width: number; height: number; sill: number };
  opening: { width: number; height: number; sill: number };
  floor: { thickness: number; material: string; structural: boolean };
  roof: { kind: "flat" | "pitched"; slope_deg: number; thickness: number; material: string };
  ceiling: { height_offset: number; thickness: number };
  room: { name: string };
  stair: { width: number; risers: number; tread_d: number };
  railing: { height: number };
  column: { profile: Profile; material: string };
  beam: { profile: Profile; material: string };
  foundation: { kind: "isolated" | "strip" | "slab"; w: number; d: number; h: number; material: string };
  pipe: { dn: number; system: string; elevation: number; material: string };
  duct: { shape: "rect" | "round"; w: number; h: number; d: number; system: string; elevation: number };
  cable_tray: { w: number; h: number; system: string; elevation: number };
  conduit: { d: number; system: string; elevation: number };
  equipment: { kind: string; size: Pt3; system: string };
  device: { kind: "light" | "outlet" | "switch" | "panel" | "air_terminal" | "sprinkler_head" | "sensor" | "other"; system: string; elevation: number };
  text: { text: string; h: number };
  dim: { off: number };
  leader: { text: string };
  grid: { label: string };
  site: { kind: "site_boundary" | "property_boundary" | "road" | "path" | "footprint" | "other" };
  terrain: { z: number };
};

export const DEFAULTS: ToolDefaults = {
  wall: { thickness: 200, height: null, material: "m_gypsum", alignment: "centre", structural: false },
  door: { width: 900, height: 2100, swing: "left" },
  window: { width: 1200, height: 1200, sill: 900 },
  opening: { width: 1000, height: 2100, sill: 0 },
  floor: { thickness: 250, material: "m_concrete", structural: true },
  roof: { kind: "pitched", slope_deg: 27, thickness: 250, material: "m_wood" },
  ceiling: { height_offset: 2500, thickness: 30 },
  room: { name: "Rum" },
  stair: { width: 1200, risers: 18, tread_d: 280 },
  railing: { height: 1100 },
  column: { profile: { kind: "rect", w: 300, d: 300 }, material: "m_concrete" },
  beam: { profile: { kind: "rect", w: 300, d: 500 }, material: "m_concrete" },
  foundation: { kind: "strip", w: 600, d: 600, h: 400, material: "m_concrete" },
  pipe: { dn: 25, system: "KV", elevation: 2600, material: "m_copper" },
  duct: { shape: "rect", w: 400, h: 200, d: 250, system: "TL", elevation: 2700 },
  cable_tray: { w: 300, h: 60, system: "EL", elevation: 2800 },
  conduit: { d: 25, system: "EL", elevation: 2800 },
  equipment: { kind: "pump", size: [600, 400, 500], system: "" },
  device: { kind: "light", system: "EL", elevation: 2600 },
  text: { text: "Text", h: 2.5 },
  dim: { off: 500 },
  leader: { text: "" },
  grid: { label: "A" },
  site: { kind: "property_boundary" },
  terrain: { z: 0 },
};

export type Ctx = { doc: CadDocument; view: View; discipline: Discipline; layer: string; level: string; defaults: ToolDefaults; user?: string };

function common(ctx: Ctx, discipline?: Discipline) {
  return { id: uid(), layer: ctx.layer, discipline: discipline || ctx.discipline, level: ctx.level, phase: "NEW" as const, provenance: "USER_MODELLED" as const, version: 1, user: ctx.user };
}

function arcFrom3(a: Pt, b: Pt, c: Pt): { c: Pt; r: number; a0: number; a1: number } | null {
  const ax = a[0], ay = a[1], bx = b[0], by = b[1], cx = c[0], cy = c[1];
  const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
  if (Math.abs(d) < 1e-9) return null;
  const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
  const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
  const r = Math.hypot(ax - ux, ay - uy);
  const ang = (p: Pt) => (Math.atan2(p[1] - uy, p[0] - ux) * 180) / Math.PI;
  let a0 = ang(a), a1 = ang(c); const am = ang(b);
  const norm = (x: number) => ((x % 360) + 360) % 360;
  if (norm(am - a0) > norm(a1 - a0)) [a0, a1] = [a1, a0];
  if (a1 < a0) a1 += 360;
  return { c: [ux, uy], r, a0, a1 };
}

/** Objektet ett verktyg skapar av sina punkter. null när punkterna inte räcker eller inte pekar på något. */
export function build(tool: ToolId, pts: Pt[], ctx: Ctx, closed = false, wallHit?: { wall: Wall; t: number } | null): Entity | null {
  const D = ctx.defaults;
  const z = (p: Pt, e: number): Pt3 => [p[0], p[1], e];
  switch (tool) {
    case "vagg": case "glasfasad":
      if (pts.length < 2) return null;
      return { ...common(ctx, ctx.discipline === "KONSTR" ? "KONSTR" : "ARK"), type: tool === "vagg" ? "wall" : "curtain_wall", p: [pts[0], pts[1]], thickness: D.wall.thickness, base_level: ctx.level, top_level: null, height: D.wall.height, material: D.wall.material, alignment: D.wall.alignment, structural: D.wall.structural || ctx.discipline === "KONSTR" } as Entity;
    case "dorr": case "fonster": case "oppning": {
      const hit = wallHit ?? (pts[0] ? wallAt(ctx.doc, ctx.view, pts[0], 300) : null);
      if (!hit) return null;
      const d = tool === "dorr" ? D.door : tool === "fonster" ? D.window : D.opening;
      const base = { ...common(ctx, "ARK"), host: hit.wall.id, t: hit.t, width: d.width, height: d.height, level: hit.wall.base_level };
      if (tool === "dorr") return { ...base, type: "door", swing: D.door.swing } as Entity;
      if (tool === "fonster") return { ...base, type: "window", sill: D.window.sill } as Entity;
      return { ...base, type: "opening", sill: D.opening.sill, host_kind: "wall" } as Entity;
    }
    case "bjalklag": case "platta":
      if (pts.length < 3) return null;
      return { ...common(ctx, tool === "platta" ? "KONSTR" : "ARK"), type: "floor", p: pts, thickness: D.floor.thickness, material: D.floor.material, structural: tool === "platta" || D.floor.structural } as Entity;
    case "tak": {
      if (pts.length < 3) return null;
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]); const cx = (Math.min(...xs) + Math.max(...xs)) / 2;
      return { ...common(ctx, "ARK"), type: "roof", p: pts, kind: D.roof.kind, slope_deg: D.roof.slope_deg, thickness: D.roof.thickness, material: D.roof.material, ridge: D.roof.kind === "pitched" ? [[cx, Math.min(...ys)], [cx, Math.max(...ys)]] : null } as Entity;
    }
    case "undertak": if (pts.length < 3) return null; return { ...common(ctx, "ARK"), type: "ceiling", p: pts, height_offset: D.ceiling.height_offset, thickness: D.ceiling.thickness } as Entity;
    case "rum": if (pts.length < 3) return null; return { ...common(ctx, "ARK"), type: "room", p: pts, name: D.room.name } as Entity;
    case "trappa": {
      if (pts.length < 2) return null;
      const above = ctx.doc.levels.filter((l) => l.elevation_mm > (ctx.doc.levels.find((x) => x.id === ctx.level)?.elevation_mm ?? 0)).sort((a, b) => a.elevation_mm - b.elevation_mm)[0];
      if (!above) return null;
      return { ...common(ctx, "ARK"), type: "stair", kind: "straight", p: [pts[0], pts[1]], base_level: ctx.level, top_level: above.id, width: D.stair.width, risers: D.stair.risers, tread_d: D.stair.tread_d } as Entity;
    }
    case "racke": if (pts.length < 2) return null; return { ...common(ctx, "ARK"), type: "railing", p: pts, height: D.railing.height } as Entity;
    case "pelare": if (!pts[0]) return null; return { ...common(ctx, "KONSTR"), type: "column", p: [pts[0]], profile: D.column.profile, base_level: ctx.level, top_level: null, material: D.column.material } as Entity;
    case "balk": if (pts.length < 2) return null; return { ...common(ctx, "KONSTR"), type: "beam", p: [pts[0], pts[1]], profile: D.beam.profile, material: D.beam.material } as Entity;
    case "grund": if (pts.length < 2) return null; return { ...common(ctx, "KONSTR"), type: "foundation", kind: closed || pts.length > 3 ? (D.foundation.kind === "slab" ? "slab" : "strip") : D.foundation.kind, p: pts, w: D.foundation.w, d: D.foundation.d, h: D.foundation.h, material: D.foundation.material } as Entity;
    case "ror": if (pts.length < 2) return null; return { ...common(ctx, ctx.discipline === "SPRINKLER" ? "SPRINKLER" : "VVS"), type: "pipe", path: pts.map((p) => z(p, 0)), elevation: D.pipe.elevation, system: D.pipe.system, dn: D.pipe.dn, material: D.pipe.material } as Entity;
    case "kanal": if (pts.length < 2) return null; return { ...common(ctx, "VENT"), type: "duct", path: pts.map((p) => z(p, 0)), elevation: D.duct.elevation, system: D.duct.system, shape: D.duct.shape, w: D.duct.w, h: D.duct.h, d: D.duct.d } as Entity;
    case "kabelstege": if (pts.length < 2) return null; return { ...common(ctx, "EL"), type: "cable_tray", path: pts.map((p) => z(p, 0)), elevation: D.cable_tray.elevation, system: D.cable_tray.system, w: D.cable_tray.w, h: D.cable_tray.h } as Entity;
    case "elror": if (pts.length < 2) return null; return { ...common(ctx, "EL"), type: "conduit", path: pts.map((p) => z(p, 0)), elevation: D.conduit.elevation, system: D.conduit.system, d: D.conduit.d } as Entity;
    case "utrustning": if (!pts[0]) return null; return { ...common(ctx), type: "equipment", kind: D.equipment.kind, name: D.equipment.kind, p: [z(pts[0], 0)], size: D.equipment.size, system: D.equipment.system, connectors: [{ id: uid(), name: "IN", kind: "in", at: [-D.equipment.size[0] / 2, 0, D.equipment.size[2] / 2] }, { id: uid(), name: "UT", kind: "out", at: [D.equipment.size[0] / 2, 0, D.equipment.size[2] / 2] }] } as Entity;
    case "apparat": if (!pts[0]) return null; return { ...common(ctx), type: "device", kind: D.device.kind, p: [z(pts[0], D.device.elevation)], system: D.device.system } as Entity;
    case "koppling": if (!pts[0]) return null; return { ...common(ctx), type: "fitting", kind: "tee", p: [z(pts[0], D.pipe.elevation)], system: D.pipe.system, dn: D.pipe.dn } as Entity;
    case "tomtgrans": if (pts.length < 2) return null; return { ...common(ctx, "MARK"), type: "site", kind: D.site.kind, p: pts, closed: closed || pts.length > 2 } as Entity;
    case "terrang": if (pts.length < 3) return null; return { ...common(ctx, "MARK"), type: "terrain", points: pts.map((p) => z(p, D.terrain.z)) } as Entity;
    case "linje": if (pts.length < 2) return null; return { ...common(ctx), type: "line", p: [pts[0], pts[1]] } as Entity;
    case "polylinje": if (pts.length < 2) return null; return { ...common(ctx), type: "polyline", p: pts, closed } as Entity;
    case "rektangel": if (pts.length < 2) return null; return { ...common(ctx), type: "rect", p: [pts[0], pts[1]] } as Entity;
    case "cirkel": if (pts.length < 2) return null; return { ...common(ctx), type: "circle", p: [pts[0]], r: Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]) } as Entity;
    case "bage": { if (pts.length < 3) return null; const a = arcFrom3(pts[0], pts[1], pts[2]); return a ? ({ ...common(ctx), type: "arc", p: [a.c], r: a.r, a0: a.a0, a1: a.a1 } as Entity) : null; }
    case "text": if (!pts[0]) return null; return { ...common(ctx, "ALLMAN"), type: "text", p: [pts[0]], text: D.text.text, h: D.text.h } as Entity;
    case "matt": { if (pts.length < 2) return null; const [a, b] = pts; const L = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1; const off = pts[2] ? ((pts[2][0] - a[0]) * -(b[1] - a[1]) + (pts[2][1] - a[1]) * (b[0] - a[0])) / L : D.dim.off; return { ...common(ctx, "ALLMAN"), type: "dim", kind: "aligned", p: [a, b], off } as Entity; }
    case "hanvisning": if (pts.length < 2) return null; return { ...common(ctx, "ALLMAN"), type: "leader", p: pts, text: D.leader.text || "…" } as Entity;
    case "skraffering": if (pts.length < 3) return null; return { ...common(ctx, "ALLMAN"), type: "hatch", p: pts, pattern: "diag", spacing: 100, angle: 45 } as Entity;
    default: return null;
  }
}

/** Hur många punkter verktyget behöver innan det avslutar av sig självt. */
export function needed(tool: ToolId): number | "many" | "wall" | "one" | 0 {
  return TOOLS.find((t) => t.id === tool)?.points ?? 0;
}

/** Spökobjektet medan man ritar: samma bygge, med pekarens punkt som sista. */
export function ghostOf(tool: ToolId, pts: Pt[], ctx: Ctx): Entity | null {
  if (!pts.length) return null;
  const n = needed(tool);
  if (n === "one" || n === "wall") return null;
  if (typeof n === "number" && pts.length > n) return null;
  if (tool === "matt" && pts.length === 2) return build("matt", pts, ctx);
  if (["bjalklag", "platta", "tak", "undertak", "rum", "skraffering"].includes(tool) && pts.length < 3) return { ...common(ctx), type: "polyline", p: pts } as Entity;
  return build(tool, pts, ctx, false) ?? ({ ...common(ctx), type: "polyline", p: pts } as Entity);
}
