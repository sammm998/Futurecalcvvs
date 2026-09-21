/* Byggmodellens kärna, provad utan webbläsare: ett litet hus byggs upp genom transaktioner, ångras, görs om,
 * mängdas, snittas och kollisionskontrolleras - och varje tal jämförs med det man räknar ut för hand.
 * Körs med node efter esbuild (se engine/tests/test_the_building_model_holds_together.py). */

import { type CadDocument, type Wall, type Door, type Window, type Floor, type Column, type Beam, type Pipe, type Roof, type Room, type Equipment, migrate, newDocument, validate, relations, visibleIn, heightOf, connections } from "./building";
import { Tx, commit, emptyHistory, redo, undo, touched } from "./commands";
import { wallSolids, sectionOfDocument, elevationPlane, elevationOfDocument, roofHeightAt, polygonArea } from "./solids";
import { quantities, materialQuantities, quantityOf } from "./quantities";
import { findClashes, proposeOpenings } from "./clash";

declare const process: any;
let failures = 0;
function check(name: string, ok: boolean, detail?: unknown) {
  if (ok) console.log(`  ok  ${name}`);
  else { failures++; console.log(`  FEL ${name}${detail !== undefined ? ": " + JSON.stringify(detail) : ""}`); }
}
const near = (a: number, b: number, tol = 1e-6) => Math.abs(a - b) <= tol;

// ---------------------------------------------------------------- huset

let doc = newDocument("Kv Eken");
let hist = emptyHistory();
const run = (label: string, f: (tx: Tx) => void) => { const tx = new Tx(label); f(tx); ({ doc, hist } = commit(doc, hist, tx.build())); };

run("Nivå 1 och tak", (tx) => {
  tx.add("levels", { id: "lv_1", name: "Plan 1", elevation_mm: 3200 });
  tx.add("levels", { id: "lv_roof", name: "Tak", elevation_mm: 6400 });
});
check("nivåerna finns", doc.levels.length === 3 && doc.revision === 1);

const common = (id: string, discipline: any = "ARK") => ({ id, layer: "l_ark", discipline, phase: "NEW" as const, provenance: "USER_MODELLED" as const, version: 1 });
const W = (id: string, a: [number, number], b: [number, number]): Wall => ({ ...common(id), type: "wall", p: [a, b], thickness: 300, base_level: "lv_0", top_level: "lv_1", material: "m_concrete" });

run("Ytterväggar 10 x 15 m", (tx) => {
  tx.add("entities", W("w_s", [0, 0], [10000, 0]));
  tx.add("entities", W("w_e", [10000, 0], [10000, 15000]));
  tx.add("entities", W("w_n", [10000, 15000], [0, 15000]));
  tx.add("entities", W("w_w", [0, 15000], [0, 0]));
});
check("fyra väggar, revision 2", doc.entities.length === 4 && doc.revision === 2);
check("väggens höjd följer nivåerna: 3200", heightOf(doc, doc.entities[0] as Wall) === 3200);

const door: Door = { ...common("d1"), type: "door", host: "w_s", t: 0.5, width: 1000, height: 2100, swing: "left" };
const win: Window = { ...common("f1"), type: "window", host: "w_s", t: 0.2, width: 1200, height: 1200, sill: 900 };
run("Dörr och fönster i sydväggen", (tx) => { tx.add("entities", door); tx.add("entities", win); });

// ---------------------------------------------------------------- ångra och gör om

const before = doc;
({ doc, hist } = undo(doc, hist));
check("ångra tar bort dörr och fönster tillsammans", doc.entities.length === 4 && !doc.entities.some((e) => e.id === "d1"));
({ doc, hist } = redo(doc, hist));
check("gör om lägger tillbaka båda", doc.entities.length === 6 && doc.entities.some((e) => e.id === "f1"));
check("dokumentet efter gör om är det som var före ångra", JSON.stringify(doc.entities) === JSON.stringify(before.entities));
check("transaktionen minns vad den rörde", touched(hist.past[hist.past.length - 1]).sort().join(",") === "d1,f1");

// uppdatera med versionsstämpel
run("Flytta dörren", (tx) => tx.update("entities", door, { ...door, t: 0.6 }));
const d1 = doc.entities.find((e) => e.id === "d1") as Door;
check("uppdatering räknar upp versionen", d1.t === 0.6 && d1.version === 2 && !!d1.updated_at);
({ doc, hist } = undo(doc, hist));
check("ångra en uppdatering skriver tillbaka det gamla", (doc.entities.find((e) => e.id === "d1") as Door).t === 0.5);
({ doc, hist } = redo(doc, hist));

// ---------------------------------------------------------------- dörren följer väggen

run("Flytta sydväggen", (tx) => tx.update("entities", doc.entities.find((e) => e.id === "w_s")!, { ...(doc.entities.find((e) => e.id === "w_s") as Wall), p: [[0, -500], [10000, -500]] }));
{
  const w = doc.entities.find((e) => e.id === "w_s") as Wall;
  const solids = wallSolids(doc, w);
  check("väggen delas kring dörr och fönster: 2 hål ⇒ 3 hela stycken + över dörr + över/under fönster", solids.length === 3 + 1 + 2, solids.map((s) => s.role));
  const overDoor = solids.find((s) => s.role === "wall_above" && Math.abs(s.poly[0][0] - (6000 - 500)) < 1);
  check("stycket över dörren börjar på 2100 mm och står över det nya läget", !!overDoor && overDoor.z0 === 2100 && overDoor.poly[0][1] > -700, overDoor);
  check("relationen HOSTED_BY finns", relations(doc).some((r) => r.kind === "HOSTED_BY" && r.from === "d1" && r.to === "w_s"));
}

// ---------------------------------------------------------------- bjälklag, pelare, balk, tak, rum, rör

const floor: Floor = { ...common("fl0"), type: "floor", p: [[0, 0], [10000, 0], [10000, 15000], [0, 15000]], thickness: 200, level: "lv_0", material: "m_concrete", structural: true };
const col: Column = { ...common("c1", "KONSTR"), type: "column", p: [[5000, 7500]], profile: { kind: "rect", w: 300, d: 300 }, base_level: "lv_0", top_level: "lv_1", material: "m_concrete" };
const beam: Beam = { ...common("b1", "KONSTR"), type: "beam", p: [[0, 7500], [10000, 7500]], profile: { kind: "rect", w: 300, d: 500 }, level: "lv_1", material: "m_concrete", supports: ["c1"] };
const roof: Roof = { ...common("r1"), type: "roof", p: [[0, 0], [10000, 0], [10000, 15000], [0, 15000]], kind: "pitched", slope_deg: 27, ridge: [[5000, 0], [5000, 15000]], thickness: 250, level: "lv_roof" };
const room: Room = { ...common("rm1"), type: "room", p: [[300, 300], [4700, 300], [4700, 7200], [300, 7200]], level: "lv_0", name: "Kontor", number: "101" };
const pipe: Pipe = { ...common("p1", "VVS"), type: "pipe", path: [[-2000, 3000, 1000], [12000, 3000, 1000]], system: "KV", dn: 25, level: "lv_0" };
run("Bjälklag, pelare, balk, tak, rum, rör", (tx) => { for (const e of [floor, col, beam, roof, room, pipe]) tx.add("entities", e); });

check("validering: inga fel i ett riktigt hus", validate(doc).length === 0, validate(doc));

// ---------------------------------------------------------------- mängder, för hand

const q = quantities(doc);
const wq = q.rows.find((r) => r.id === "w_s")!;
check("sydväggens yta = 10 × 3,2 − (1×2,1 + 1,2×1,2) = 28,46 m²", near(wq.area_m2!, 28.46, 1e-6), wq.area_m2);
check("sydväggens volym = 28,46 × 0,3 = 8,538 m³", near(wq.volume_m3!, 8.538, 1e-6), wq.volume_m3);
check("sydväggens vikt = 8,538 × 2400 kg", near(wq.mass_kg!, 8.538 * 2400, 1e-3), wq.mass_kg);
check("bjälklagets yta 150 m², volym 30 m³", near(quantityOf(doc, floor)!.area_m2!, 150) && near(quantityOf(doc, floor)!.volume_m3!, 30));
check("pelarens volym 0,3×0,3×3,2 = 0,288 m³", near(quantityOf(doc, col)!.volume_m3!, 0.288));
check("balkens längd 10 m och volym 1,5 m³", near(quantityOf(doc, beam)!.length_m!, 10) && near(quantityOf(doc, beam)!.volume_m3!, 1.5));
check("takets yta = plan 150 m² / cos 27°", near(quantityOf(doc, roof)!.area_m2!, 150 / Math.cos((27 * Math.PI) / 180), 1e-6));
check("rummets yta 4,4 × 6,9 = 30,36 m²", near(quantityOf(doc, room)!.area_m2!, 30.36));
check("rörets längd 14 m", near(quantityOf(doc, pipe)!.length_m!, 14));
check("dörrar räknas i stycken", q.groups.find((g) => g.type === "door")!.count === 1 && q.groups.find((g) => g.type === "door")!.unit === "st");
const mats = materialQuantities(doc);
const concrete = mats.find((m) => m.material.id === "m_concrete")!;
// syd 8,538 + nord 10×3,2×0,3 + öst och väst 15×3,2×0,3 vardera + bjälklag 30 + pelare 0,288 + balk 1,5
check("betong: väggar + bjälklag + pelare + balk = 78,726 m³", near(concrete.volume_m3, 8.538 + 9.6 + 14.4 + 14.4 + 30 + 0.288 + 1.5, 1e-6) && concrete.count === 7, concrete);
check("ingen densitet ⇒ ingen vikt (aldrig gissad)", (() => { const d2 = { ...doc, materials: doc.materials.map((m) => m.id === "m_concrete" ? { ...m, density_kg_m3: null } : m) }; return materialQuantities(d2).find((m) => m.material.id === "m_concrete")!.mass_kg === null; })());

// ingen dubbelmätning: samma vägg i två vyer är en vägg
check("mängden räknar varje objekt en gång", q.rows.filter((r) => r.id === "w_s").length === 1);

// ---------------------------------------------------------------- sektion och fasad

const sec = sectionOfDocument(doc, { a: [5000, -1000], b: [5000, 16000], depth: 3000 });
check("sektionen genom huset skär två väggar, bjälklaget, pelaren, balken, taket och röret", ["wall", "floor", "column", "beam", "roof", "pipe"].every((k) => sec.some((s) => s.kind === k)), sec.map((s) => s.kind));
const wallCuts = sec.filter((s) => s.kind === "wall");
check("väggsnitten är 300 mm breda och 3200 höga", wallCuts.every((s) => near(Math.abs(s.poly[1][0] - s.poly[0][0]), 300, 1e-6) && near(s.poly[2][1] - s.poly[0][1], 3200, 1e-6)), wallCuts);
check("taket är högst vid nocken: 6400 + 5000·tan 27°", near(roofHeightAt(doc, roof, [5000, 7500]), 6400 + 5000 * Math.tan((27 * Math.PI) / 180), 1e-6) && near(roofHeightAt(doc, roof, [0, 7500]), 6400, 1e-6));
const fac = elevationOfDocument(doc, elevationPlane(doc, "S"));
check("sydfasaden visar sydväggen med dörr och fönster och taket", fac.some((s) => s.kind === "door") && fac.some((s) => s.kind === "window") && fac.some((s) => s.kind === "roof"));
const southWall = doc.entities.filter((e) => e.id === "w_s");
const southPlane = elevationPlane(doc, "S", southWall);
const wallFaceArea = (model: CadDocument) => elevationOfDocument(model, southPlane, southWall)
  .reduce((sum, shape) => sum + polygonArea(shape.poly), 0);
check("dolda dörrar och fönster lämnar hål i den valda väggens fasad", near(wallFaceArea(doc), 10000 * 3200 - 1000 * 2100 - 1200 * 1200));
const withoutDoor = { ...doc, entities: doc.entities.filter((e) => e.id !== "d1") };
check("en borttagen dörr sluter hålet vid nästa fasadberäkning", near(wallFaceArea(withoutDoor) - wallFaceArea(doc), 1000 * 2100));

// sektionen följer modellen: flytta en vägg, snittet flyttar
run("Flytta nordväggen", (tx) => tx.update("entities", doc.entities.find((e) => e.id === "w_n")!, { ...(doc.entities.find((e) => e.id === "w_n") as Wall), p: [[10000, 16000], [0, 16000]] }));
const sec2 = sectionOfDocument(doc, { a: [5000, -1000], b: [5000, 18000], depth: 3000 });
check("efter flytten ligger nordväggens snitt 1 m längre bort", sec2.filter((s) => s.kind === "wall").some((s) => near(s.poly[0][0], 16850, 1e-6)), sec2.filter((s) => s.kind === "wall").map((s) => s.poly[0][0]));

// ---------------------------------------------------------------- kollisioner

const clashes = findClashes(doc);
check("röret genom öst- och västväggen ger kollisioner", clashes.filter((c) => c.a_type === "pipe" || c.b_type === "pipe").length === 2, clashes);
check("pelaren under balken (SUPPORTED_BY) är ingen kollision", !clashes.some((c) => (c.a === "c1" && c.b === "b1") || (c.a === "b1" && c.b === "c1")));
check("dörren i sin egen vägg är ingen kollision", !clashes.some((c) => c.a === "d1" || c.b === "d1"));
const props = proposeOpenings(doc, clashes);
check("två hålförslag, Ø90 för DN25 + spel, som förslag", props.length === 2 && props.every((p) => p.size_mm === 90 && /Föreslaget hål/.test(p.note)), props);

// ---------------------------------------------------------------- vyer: vad som syns i en plan

const plan0 = doc.views.find((v) => v.kind === "plan")!;
check("plan 0 visar väggar, rum och rör på plan 0", visibleIn(doc, plan0, doc.entities.find((e) => e.id === "w_s")!) && visibleIn(doc, plan0, room) && visibleIn(doc, plan0, pipe));
const plan1 = { ...plan0, id: "v_plan1", level: "lv_1" };
check("plan 1 visar inte plan 0:s rum", !visibleIn(doc, plan1, room));
check("dörren syns där dess vägg syns", visibleIn(doc, plan0, d1) && !visibleIn(doc, plan1, d1));

// ---------------------------------------------------------------- installationerna sitter ihop där de möts

{
  const pump: Equipment = { ...common("eq1", "VVS"), type: "equipment", kind: "pump", p: [[12000, 3000, 1000]], size: [600, 400, 500], connectors: [{ id: "c_in", name: "IN", kind: "in", at: [0, 0, 0] }, { id: "c_ut", name: "UT", kind: "out", at: [300, 0, 0] }] };
  const p2: Pipe = { ...common("p2", "VVS"), type: "pipe", path: [[12300, 3000, 1000], [12300, 8000, 1000]], system: "KV", dn: 25, level: "lv_0" };
  const p3: Pipe = { ...common("p3", "VVS"), type: "pipe", path: [[5000, 3000, 1000], [5000, 6000, 1000]], system: "KV", dn: 20, level: "lv_0" };
  const loose: Pipe = { ...common("p4", "VVS"), type: "pipe", path: [[5000, 6500, 1000], [5000, 9000, 1000]], system: "KV", dn: 20, level: "lv_0" };
  const wired: CadDocument = { ...doc, entities: [...doc.entities, pump, p2, p3, loose] };
  const cs = connections(wired);
  check("röret slutar i pumpens IN-anslutning", cs.some((c) => c.from === "p1" && c.to === "eq1" && c.via === "connector" && c.connector === "c_in"), cs);
  check("nästa rör börjar i pumpens UT-anslutning", cs.some((c) => c.from === "p2" && c.to === "eq1" && c.connector === "c_ut"));
  check("ett rör som börjar på ett annat rörs sträcka är ett T-stycke", cs.some((c) => c.from === "p3" && c.to === "p1" && c.via === "tee" && near(c.at[0], 5000)));
  check("ett rör 500 mm bort sitter inte ihop med något", !cs.some((c) => c.from === "p4" || c.to === "p4"));
  check("anslutningarna finns bland relationerna som CONNECTS_TO", relations(wired).filter((r) => r.kind === "CONNECTS_TO").length === cs.length);
}

// ---------------------------------------------------------------- validering fångar det som inte får sparas

const bad: CadDocument = { ...doc, entities: [...doc.entities, { ...common("d_bad"), type: "door", host: "finns_inte", t: 0.5, width: 900, height: 2100 } as Door, { ...W("w_bad", [0, 0], [0, 0]), thickness: 0 }] };
const probs = validate(bad);
check("en dörr utan vägg och en vägg utan tjocklek och längd avvisas", probs.some((p) => p.id === "d_bad") && probs.filter((p) => p.id === "w_bad").length >= 2, probs);
const nan: CadDocument = { ...doc, entities: [{ ...W("w_nan", [0, 0], [NaN, 0]) }] };
check("NaN i en punkt avvisas", validate(nan).some((p) => p.id === "w_nan" && p.field === "p"));

// ---------------------------------------------------------------- migrering av ett gammalt blad

const v1 = { version: 1, layers: [{ id: "l0", name: "Ritning", color: "#111", visible: true, locked: false, width: 0.35 }],
  entities: [{ id: "e1", type: "line", layer: "l0", p: [[0, 0], [1000, 0]] }, { id: "e2", type: "pipe", layer: "l0", p: [[0, 0], [0, 5000]], dn: 25, designation: "KV1" }] };
const mig = migrate(v1, { name: "Gammalt blad", scale_ratio: 50 });
check("v1-bladet blir ett v2-dokument med samma objekt", mig.version === 2 && mig.entities.length === 2 && mig.entities[1].type === "pipe" && (mig.entities[1] as Pipe).path[1][1] === 5000 && mig.views[0].scale_ratio === 50);
check("ett v2-dokument migreras inte om", migrate(mig) === mig);

console.log(failures ? `\n${failures} FEL` : "\nallt håller");
// Let Node flush the complete assertion log when stdout is a pipe.
process.exitCode = failures ? 1 : 0;
