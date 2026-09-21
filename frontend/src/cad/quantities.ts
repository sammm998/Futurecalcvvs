/* Mängder ur modellen - ur de parametriska fälten, aldrig ur ett renderat nät.
 *
 * En vägg mängdas som längd gånger höjd minus öppningarna, i m² och m³; ett bjälklag som sin kontur i m² och
 * m³; en pelare i stycken, meter och m³; dörrar och fönster i stycken (fönster även m²); rör, kanaler och
 * kabelstegar i meter längs sin väg i tre dimensioner. Materialvikt räknas bara där materialet har en angiven
 * densitet - en densitet gissas aldrig. Servern räknar samma sak i Python och exporterna tar serverns tal;
 * det här är förhandsvisningen, och ett prov håller de två lika. */

import {
  type CadDocument, type Entity, type Material, type Discipline,
  dist, heightOf, hostedIn, wallLength,
} from "./building";
import { pathLength, polygonArea, profileArea, perimeter } from "./solids";

export type QuantityRow = {
  id: string; type: Entity["type"]; name: string; discipline: Discipline; level?: string; material?: string; system?: string;
  count: number; length_m?: number; area_m2?: number; volume_m3?: number; mass_kg?: number | null; unit: string; value: number;
};

const m = (mm: number) => mm / 1000;
const m2 = (mm2: number) => mm2 / 1e6;
const m3 = (mm3: number) => mm3 / 1e9;

function mass(doc: CadDocument, matId: string | undefined, volume_m3: number | undefined): number | null {
  if (!matId || volume_m3 == null) return null;
  const mat = doc.materials.find((x) => x.id === matId);
  if (!mat || mat.density_kg_m3 == null) return null;
  return volume_m3 * mat.density_kg_m3;
}

export function quantityOf(doc: CadDocument, e: Entity): QuantityRow | null {
  const base = { id: e.id, type: e.type, name: e.name || e.type, discipline: e.discipline, level: e.level, material: e.material, count: 1 };
  switch (e.type) {
    case "wall": case "curtain_wall": {
      const L = wallLength(e), H = heightOf(doc, e);
      const openings = hostedIn(doc, e.id).reduce((s, h) => s + h.width * h.height, 0);
      const area = Math.max(0, L * H - openings);
      const vol = area * e.thickness;
      return { ...base, level: e.base_level, length_m: m(L), area_m2: m2(area), volume_m3: m3(vol), mass_kg: mass(doc, e.material, m3(vol)), unit: "m²", value: m2(area) };
    }
    case "door": return { ...base, unit: "st", value: 1, area_m2: m2(e.width * e.height) };
    case "window": return { ...base, unit: "st", value: 1, area_m2: m2(e.width * e.height) };
    case "opening": return { ...base, unit: "st", value: 1, area_m2: m2(e.width * e.height) };
    case "floor": case "ceiling": {
      const area = polygonArea(e.p) - (e.type === "floor" ? (e.holes || []).reduce((s, h) => s + polygonArea(h), 0) : 0);
      const vol = area * e.thickness;
      return { ...base, area_m2: m2(area), volume_m3: m3(vol), mass_kg: mass(doc, e.material, m3(vol)), unit: "m²", value: m2(area) };
    }
    case "roof": {
      const plan = polygonArea(e.p);
      const slope = e.kind === "pitched" && e.slope_deg ? 1 / Math.cos((e.slope_deg * Math.PI) / 180) : 1;
      const area = plan * slope;
      const vol = area * e.thickness;
      return { ...base, area_m2: m2(area), volume_m3: m3(vol), mass_kg: mass(doc, e.material, m3(vol)), unit: "m²", value: m2(area) };
    }
    case "room": {
      const area = polygonArea(e.p);
      const h = e.height ?? null;
      return { ...base, name: `${e.number ? e.number + " " : ""}${e.name || "Rum"}`, area_m2: m2(area), volume_m3: h ? m3(area * h) : undefined, unit: "m²", value: m2(area) };
    }
    case "column": {
      const H = heightOf(doc, e), A = profileArea(e.profile);
      const vol = A * H;
      return { ...base, level: e.base_level, length_m: m(H), volume_m3: m3(vol), mass_kg: mass(doc, e.material, m3(vol)), unit: "st", value: 1 };
    }
    case "beam": {
      const L = dist(e.p[0], e.p[1]), A = profileArea(e.profile);
      const vol = A * L;
      return { ...base, length_m: m(L), volume_m3: m3(vol), mass_kg: mass(doc, e.material, m3(vol)), unit: "m", value: m(L) };
    }
    case "foundation": {
      let vol = 0, area = 0;
      if (e.kind === "slab") { area = polygonArea(e.p); vol = area * e.h; }
      else if (e.kind === "isolated") { area = (e.w ?? 1000) * (e.d ?? e.w ?? 1000); vol = area * e.h; }
      else { const L = perimeter(e.p, false); area = L * (e.w ?? 600); vol = area * e.h; }
      return { ...base, area_m2: m2(area), volume_m3: m3(vol), mass_kg: mass(doc, e.material, m3(vol)), unit: "m³", value: m3(vol) };
    }
    case "stair": return { ...base, unit: "st", value: 1, length_m: m(e.risers * e.tread_d) };
    case "railing": return { ...base, length_m: m(perimeter(e.p, false)), unit: "m", value: m(perimeter(e.p, false)) };
    case "truss": return { ...base, length_m: m(dist(e.p[0], e.p[1])), unit: "st", value: 1 };
    case "pipe": case "duct": case "cable_tray": case "conduit": {
      const L = pathLength(e.path);
      const row: QuantityRow = { ...base, system: e.system, length_m: m(L), unit: "m", value: m(L) };
      if (e.type === "duct") {
        const per = e.shape === "round" ? Math.PI * (e.d ?? 0) : 2 * ((e.w ?? 0) + (e.h ?? 0));
        row.area_m2 = m2(per * L);
      }
      if (e.type === "pipe") row.name = e.designation || `${e.system || "Rör"} DN${e.dn}`;
      return row;
    }
    case "fitting": case "equipment": case "device": return { ...base, name: e.name || (e as any).kind || e.type, system: (e as any).system, unit: "st", value: 1 };
    case "site": return e.closed || e.p.length > 2 ? { ...base, area_m2: m2(polygonArea(e.p)), unit: "m²", value: m2(polygonArea(e.p)) } : { ...base, length_m: m(perimeter(e.p, false)), unit: "m", value: m(perimeter(e.p, false)) };
    case "line": case "polyline": case "arc": case "circle": case "spline": {
      const L = e.type === "circle" ? 2 * Math.PI * e.r : e.type === "arc" ? (Math.abs(e.a1 - e.a0) % 360) * Math.PI / 180 * e.r : perimeter(e.p, !!(e as any).closed);
      return { ...base, length_m: m(L), unit: "m", value: m(L) };
    }
    default: return null;
  }
}

export type QuantityGroup = { key: string; type: Entity["type"]; name: string; unit: string; count: number; length_m: number; area_m2: number; volume_m3: number; mass_kg: number | null; material?: string; system?: string; discipline: Discipline };

/** Mängderna grupperade som en mängdförteckning läser dem: per typ, material och system. */
export function quantities(doc: CadDocument, entities: Entity[] = doc.entities): { rows: QuantityRow[]; groups: QuantityGroup[] } {
  const rows: QuantityRow[] = [];
  for (const e of entities) { const q = quantityOf(doc, e); if (q) rows.push(q); }
  const groups = new Map<string, QuantityGroup>();
  for (const r of rows) {
    const mat = doc.materials.find((x) => x.id === r.material);
    const key = [r.type, r.type === "pipe" ? r.name : "", r.system || "", mat?.name || ""].join("|");
    const g = groups.get(key) || { key, type: r.type, name: r.type === "pipe" ? r.name : label(r.type), unit: r.unit, count: 0, length_m: 0, area_m2: 0, volume_m3: 0, mass_kg: 0 as number | null, material: mat?.name, system: r.system, discipline: r.discipline };
    g.count += r.count; g.length_m += r.length_m ?? 0; g.area_m2 += r.area_m2 ?? 0; g.volume_m3 += r.volume_m3 ?? 0;
    g.mass_kg = g.mass_kg == null || r.mass_kg == null ? (r.mass_kg == null && (r.volume_m3 ?? 0) > 0 ? null : g.mass_kg) : g.mass_kg + r.mass_kg;
    groups.set(key, g);
  }
  return { rows, groups: [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, "sv")) };
}

export function label(t: Entity["type"]): string {
  const L: Partial<Record<Entity["type"], string>> = {
    wall: "Väggar", curtain_wall: "Glasfasad", door: "Dörrar", window: "Fönster", opening: "Öppningar", floor: "Bjälklag", roof: "Tak",
    ceiling: "Undertak", room: "Rum", stair: "Trappor", railing: "Räcken", column: "Pelare", beam: "Balkar", foundation: "Grund", truss: "Fackverk",
    pipe: "Rör", duct: "Kanaler", cable_tray: "Kabelstegar", conduit: "Elrör", fitting: "Kopplingar", equipment: "Utrustning", device: "Apparater",
    terrain: "Terräng", site: "Mark", line: "Linjer", polyline: "Polylinjer", rect: "Rektanglar", circle: "Cirklar", arc: "Bågar", ellipse: "Ellipser",
    spline: "Kurvor", text: "Text", mtext: "Text", dim: "Mått", leader: "Hänvisningar", hatch: "Skraffering", block: "Block",
  };
  return L[t] || t;
}

/** Materialmängder: volym och vikt per material över hela byggnaden. Vikt bara där densitet finns. */
export function materialQuantities(doc: CadDocument, entities: Entity[] = doc.entities): { material: Material; volume_m3: number; area_m2: number; mass_kg: number | null; count: number }[] {
  const by = new Map<string, { material: Material; volume_m3: number; area_m2: number; mass_kg: number | null; count: number }>();
  for (const e of entities) {
    if (!e.material) continue;
    const mat = doc.materials.find((x) => x.id === e.material);
    if (!mat) continue;
    const q = quantityOf(doc, e);
    if (!q) continue;
    const g = by.get(mat.id) || { material: mat, volume_m3: 0, area_m2: 0, mass_kg: mat.density_kg_m3 == null ? null : 0, count: 0 };
    g.volume_m3 += q.volume_m3 ?? 0; g.area_m2 += q.area_m2 ?? 0; g.count += 1;
    if (g.mass_kg != null) g.mass_kg += (q.volume_m3 ?? 0) * (mat.density_kg_m3 as number);
    by.set(mat.id, g);
  }
  return [...by.values()].sort((a, b) => b.volume_m3 - a.volume_m3);
}
