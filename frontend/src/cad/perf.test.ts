/* Prestanda: en byggnad med tusentals objekt ska räknas, valideras, snittas och kollisionskontrolleras på
 * sekunder, inte minuter. Körs med node efter esbuild (engine/tests/test_the_building_model_stays_fast_...).
 *
 * Huset: ett rutnät av rum på tre plan - väggar, dörrar, fönster, bjälklag, pelare, rör och kanaler - byggt
 * genom vanliga transaktioner så att även kommandosystemet mäts. Talen skrivs ut; gränserna är rymliga nog
 * för en långsam maskin och snäva nog att fånga en kvadratisk algoritm. */

import { type CadDocument, type Entity, newDocument, validate, relations } from "./building";
import { Tx, commit, emptyHistory, undo } from "./commands";
import { solidsOf, sectionOfDocument, elevationPlane, elevationOfDocument } from "./solids";
import { quantities, materialQuantities } from "./quantities";
import { findClashes } from "./clash";
import { segmentsOf, bboxOf } from "./plan";

declare const process: any;
let failures = 0;
const t = () => Date.now();
function timed(name: string, limitMs: number, f: () => unknown): number {
  const t0 = t(); const out = f(); const ms = t() - t0;
  const ok = ms <= limitMs;
  if (!ok) failures++;
  console.log(`  ${ok ? "ok " : "FEL"} ${name}: ${ms} ms (gräns ${limitMs})${typeof out === "number" ? ` → ${out}` : ""}`);
  return ms;
}

const NX = 30, NY = 20, ROOM = 4000, LEVELS = 3;      // 600 rum per plan, ~5 500 objekt
let doc: CadDocument = newDocument("Prestandahuset");
let hist = emptyHistory();
const common = (id: string, discipline: any, level: string) => ({ id, layer: "l_ark", discipline, level, phase: "NEW" as const, provenance: "USER_MODELLED" as const, version: 1 });

const build = timed("bygg huset genom transaktioner", 4000, () => {
  const tx0 = new Tx("nivåer");
  for (let l = 1; l < LEVELS; l++) tx0.add("levels", { id: `lv_${l}`, name: `Plan ${l}`, elevation_mm: l * 3000 });
  tx0.add("levels", { id: "lv_top", name: "Tak", elevation_mm: LEVELS * 3000 });
  ({ doc, hist } = commit(doc, hist, tx0.build()));
  for (let l = 0; l < LEVELS; l++) {
    const lv = `lv_${l}`;
    const tx = new Tx(`plan ${l}`);
    for (let i = 0; i <= NX; i++) for (let j = 0; j < NY; j++) {
      const id = `w_v_${l}_${i}_${j}`;
      tx.add("entities", { ...common(id, "ARK", lv), type: "wall", p: [[i * ROOM, j * ROOM], [i * ROOM, (j + 1) * ROOM]], thickness: i === 0 || i === NX ? 300 : 120, base_level: lv, material: "m_gypsum" } as Entity);
      if (i > 0 && i < NX && j % 2 === 0) tx.add("entities", { ...common(`d_${id}`, "ARK", lv), type: "door", host: id, t: 0.5, width: 900, height: 2100 } as Entity);

    }
    for (let j = 0; j <= NY; j++) for (let i = 0; i < NX; i++) {
      const id = `w_h_${l}_${i}_${j}`;
      tx.add("entities", { ...common(id, "ARK", lv), type: "wall", p: [[i * ROOM, j * ROOM], [(i + 1) * ROOM, j * ROOM]], thickness: j === 0 || j === NY ? 300 : 120, base_level: lv, material: "m_gypsum" } as Entity);
      if ((j === 0 || j === NY) && i % 2 === 1) tx.add("entities", { ...common(`f_${id}`, "ARK", lv), type: "window", host: id, t: 0.5, width: 1200, height: 1200, sill: 900 } as Entity);

    }
    tx.add("entities", { ...common(`fl_${l}`, "ARK", lv), type: "floor", p: [[0, 0], [NX * ROOM, 0], [NX * ROOM, NY * ROOM], [0, NY * ROOM]], thickness: 250, level: lv, material: "m_concrete" } as Entity);
    for (let i = 1; i < NX; i += 2) for (let j = 1; j < NY; j += 2) tx.add("entities", { ...common(`c_${l}_${i}_${j}`, "KONSTR", lv), type: "column", p: [[i * ROOM, j * ROOM]], profile: { kind: "rect", w: 300, d: 300 }, base_level: lv, material: "m_concrete" } as Entity);
    for (let j = 0; j < NY; j++) {
      tx.add("entities", { ...common(`p_${l}_${j}`, "VVS", lv), type: "pipe", path: [[-1000, j * ROOM + 2000, 2700], [NX * ROOM + 1000, j * ROOM + 2000, 2700]], system: j % 2 ? "KV" : "VV", dn: 32, level: lv, material: "m_copper" } as Entity);
      tx.add("entities", { ...common(`k_${l}_${j}`, "VENT", lv), type: "duct", path: [[-1000, j * ROOM + 1000, 2800], [NX * ROOM + 1000, j * ROOM + 1000, 2800]], system: "TL", shape: "rect", w: 400, h: 200, level: lv } as Entity);
    }
    for (let i = 0; i < NX; i += 2) for (let j = 0; j < NY; j += 2) tx.add("entities", { ...common(`rm_${l}_${i}_${j}`, "ARK", lv), type: "room", p: [[i * ROOM + 60, j * ROOM + 60], [(i + 1) * ROOM - 60, j * ROOM + 60], [(i + 1) * ROOM - 60, (j + 1) * ROOM - 60], [i * ROOM + 60, (j + 1) * ROOM - 60]], level: lv, name: `Rum ${i}.${j}` } as Entity);
    ({ doc, hist } = commit(doc, hist, tx.build()));
  }
  return doc.entities.length;
});
void build;
console.log(`  objekt: ${doc.entities.length}, revision ${doc.revision}`);

timed("validera", 1500, () => validate(doc).length);
timed("relationer", 1500, () => relations(doc).length);
timed("kroppar för alla objekt", 3000, () => { let n = 0; for (const e of doc.entities) n += solidsOf(doc, e).length; return n; });
timed("segment + lådor i planen (det som ritas och träffas)", 3000, () => { let n = 0; for (const e of doc.entities) { n += segmentsOf(doc, e).length; bboxOf(doc, e); } return n; });
timed("mängder", 3000, () => quantities(doc).groups.length);
timed("materialmängder", 3000, () => materialQuantities(doc).length);
timed("sektion genom hela huset", 3000, () => sectionOfDocument(doc, { a: [-2000, 6100], b: [NX * ROOM + 2000, 6100], depth: 3000 }).length);
timed("fasad", 3000, () => elevationOfDocument(doc, elevationPlane(doc, "S")).length);
const mep = doc.entities.filter((e) => e.type === "pipe" || e.type === "duct");
const struct = doc.entities.filter((e) => e.type === "wall" || e.type === "column" || e.type === "floor");
timed("kollisioner rör/kanaler mot väggar, pelare och bjälklag", 8000, () => findClashes(doc, mep, struct).length);
timed("ångra ett helt plan", 1500, () => { const r = undo(doc, hist); return r.doc.entities.length; });
timed("flytta 500 väggar i en transaktion", 2000, () => {
  const tx = new Tx("flytta");
  let n = 0;
  for (const e of doc.entities) { if (e.type === "wall" && n < 500) { tx.update("entities", e, { ...e, p: [[e.p[0][0] + 10, e.p[0][1]], [e.p[1][0] + 10, e.p[1][1]]] } as Entity); n++; } }
  return commit(doc, hist, tx.build()).doc.revision;
});

console.log(failures ? `\n${failures} FEL` : "\nsnabbt nog");
process.exit(failures ? 1 : 0);
