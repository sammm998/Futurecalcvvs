/* Ett litet hus att prova på: samma hus i webbläsarens modell och på servern.
 *
 * Körs som skript (esbuild + node) skriver det ut dokumentet och webbläsarens mängder som JSON, så att servern
 * kan räkna samma hus i Python och ett prov hålla de två räkningarna lika. Det är så vi vet att det som visas
 * medan man ritar är det som exporteras och prissätts. */

import { type CadDocument, type Wall, type Door, type Window, type Floor, type Column, type Beam, type Pipe, type Roof, type Room, type Duct, newDocument } from "./building";
import { quantities, materialQuantities } from "./quantities";
import { solidsOf } from "./solids";

export function buildHouse(): CadDocument {
  const doc = newDocument("Kv Eken");
  doc.levels.push({ id: "lv_1", name: "Plan 1", elevation_mm: 3200 }, { id: "lv_roof", name: "Tak", elevation_mm: 6400 });
  const common = (id: string, discipline: any = "ARK") => ({ id, layer: "l_ark", discipline, phase: "NEW" as const, provenance: "USER_MODELLED" as const, version: 1 });
  const W = (id: string, a: [number, number], b: [number, number]): Wall => ({ ...common(id), type: "wall", p: [a, b], thickness: 300, base_level: "lv_0", top_level: "lv_1", material: "m_concrete" });
  const door: Door = { ...common("d1"), type: "door", host: "w_s", t: 0.5, width: 1000, height: 2100, swing: "left" };
  const win: Window = { ...common("f1"), type: "window", host: "w_s", t: 0.2, width: 1200, height: 1200, sill: 900 };
  const floor: Floor = { ...common("fl0"), type: "floor", p: [[0, 0], [10000, 0], [10000, 15000], [0, 15000]], thickness: 200, level: "lv_0", material: "m_concrete", structural: true };
  const col: Column = { ...common("c1", "KONSTR"), type: "column", p: [[5000, 7500]], profile: { kind: "rect", w: 300, d: 300 }, base_level: "lv_0", top_level: "lv_1", material: "m_concrete" };
  const beam: Beam = { ...common("b1", "KONSTR"), type: "beam", p: [[0, 7500], [10000, 7500]], profile: { kind: "rect", w: 300, d: 500 }, level: "lv_1", material: "m_steel", supports: ["c1"] };
  const roof: Roof = { ...common("r1"), type: "roof", p: [[0, 0], [10000, 0], [10000, 15000], [0, 15000]], kind: "pitched", slope_deg: 27, ridge: [[5000, 0], [5000, 15000]], thickness: 250, level: "lv_roof", material: "m_wood" };
  const room: Room = { ...common("rm1"), type: "room", p: [[300, 300], [4700, 300], [4700, 7200], [300, 7200]], level: "lv_0", name: "Kontor", number: "101" };
  const pipe: Pipe = { ...common("p1", "VVS"), type: "pipe", path: [[-2000, 3000, 1000], [12000, 3000, 1000]], system: "KV", dn: 25, level: "lv_0", material: "m_copper" };
  const duct: Duct = { ...common("k1", "VENT"), type: "duct", path: [[500, 500, 2600], [500, 14500, 2600]], system: "TL", shape: "rect", w: 400, h: 200, level: "lv_0" };
  doc.entities.push(W("w_s", [0, 0], [10000, 0]), W("w_e", [10000, 0], [10000, 15000]), W("w_n", [10000, 15000], [0, 15000]), W("w_w", [0, 15000], [0, 0]),
    door, win, floor, col, beam, roof, room, pipe, duct);
  return doc;
}

// som skript: skriv ut huset och webbläsarens räkning
declare const process: any;
if (typeof process !== "undefined" && process.argv && process.argv[1] && /house\.fixture/.test(String(process.argv[1]))) {
  const doc = buildHouse();
  const q = quantities(doc);
  const solids = Object.fromEntries(doc.entities.map((e) => [e.id, solidsOf(doc, e)]));
  console.log(JSON.stringify({ doc, quantities: q, materials: materialQuantities(doc), solids }));
}
