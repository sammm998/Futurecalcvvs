/* Ändringskommandona provade mot tal räknade för hand. Körs med node efter esbuild
 * (se engine/tests/test_the_cad_modify_commands_hold.py). */
import { type CadDocument, type Entity, newDocument } from "./building";
import { apply, translation, rotation, mirroring, scaling, transformed, copies, arrayed, offsetPath, offsetEntity, trim, extend, measure, commandOf } from "./modify";

declare const process: any;
let failures = 0;
const check = (name: string, ok: boolean, detail?: unknown) => {
  if (ok) console.log(`  ok  ${name}`); else { failures++; console.log(`  FEL ${name}${detail !== undefined ? ": " + JSON.stringify(detail) : ""}`); }
};
const near = (a: number, b: number, tol = 1e-6) => Math.abs(a - b) <= tol;
const nearPt = (p: number[], q: number[], tol = 1e-6) => near(p[0], q[0], tol) && near(p[1], q[1], tol);
const base = { layer: "l", discipline: "ALLMAN", level: "lv_0", phase: "NEW", provenance: "USER", version: 1 } as any;
const line = (id: string, a: number[], b: number[]): Entity => ({ ...base, id, type: "line", p: [a, b] });

// avbildningarna
check("flytt", nearPt(apply(translation(10, -5), [1, 2]), [11, -3]));
check("vridning 90° kring origo", nearPt(apply(rotation([0, 0], Math.PI / 2), [1, 0]), [0, 1]));
check("vridning kring en punkt", nearPt(apply(rotation([1, 1], Math.PI), [2, 1]), [0, 1]));
check("spegling i y-axeln", nearPt(apply(mirroring([0, 0], [0, 1]), [3, 2]), [-3, 2]));
check("spegling i diagonalen", nearPt(apply(mirroring([0, 0], [1, 1]), [2, 0]), [0, 2]));
check("skalning kring en punkt", nearPt(apply(scaling([1, 1], 2), [2, 3]), [3, 5]));

// objekt genom avbildningar
const c = transformed({ ...base, id: "c", type: "circle", p: [[0, 0]], r: 10 } as Entity, scaling([0, 0], 3)) as any;
check("cirkelns radie skalas", near(c.r, 30));
const t = transformed({ ...base, id: "t", type: "text", p: [[0, 0]], text: "A", h: 100, rot: 10 } as Entity, rotation([0, 0], Math.PI / 2)) as any;
check("textens vinkel vrids med", near(t.rot, 100));
const r = transformed({ ...base, id: "r", type: "rect", p: [[0, 0], [2, 1]] } as Entity, rotation([0, 0], Math.PI / 4)) as any;
check("snett vriden rektangel blir en sluten polylinje", r.type === "polyline" && r.closed && r.p.length === 4);
const r90 = transformed({ ...base, id: "r", type: "rect", p: [[0, 0], [2, 1]] } as Entity, rotation([0, 0], Math.PI / 2)) as any;
check("rätvinkligt vriden rektangel förblir rektangel", r90.type === "rect" && nearPt(r90.p[0], [-1, 0]) && nearPt(r90.p[1], [0, 2]));
const pipe = transformed({ ...base, id: "p", type: "pipe", path: [[0, 0, 2500], [1000, 0, 2500]], dn: 15 } as any, translation(0, 500)) as any;
check("rörets höjd följer med när det flyttas", pipe.path[0][2] === 2500 && nearPt(pipe.path[1], [1000, 500]));

// kopior och mönster
let doc: CadDocument = newDocument("prov");
doc = { ...doc, entities: [line("a", [0, 0], [1000, 0])] };
const cp = copies(doc, ["a"], translation(0, 200));
check("kopian får nytt id och ny plats", cp.length === 1 && cp[0].id !== "a" && nearPt((cp[0] as any).p[0], [0, 200]));
const arr = arrayed(doc, ["a"], 3, 2, 1500, 400);
check("mönster 3×2 ger fem nya", arr.length === 5);

// förskjut
const op = offsetPath([[0, 0], [100, 0], [100, 100]], 10);
check("förskjuten polylinje möts i hörnet", nearPt(op[0], [0, 10]) && nearPt(op[1], [90, 10]) && nearPt(op[2], [90, 100]), op);
const ol = offsetEntity(line("a", [0, 0], [1000, 0]), 250, [500, -900]) as any;
check("förskjutning åt den klickade sidan", nearPt(ol.p[0], [0, -250]) && nearPt(ol.p[1], [1000, -250]), ol.p);
const oc = offsetEntity({ ...base, id: "c", type: "circle", p: [[0, 0]], r: 100 } as Entity, 20, [0, 500]) as any;
check("cirkel förskjuten utåt", near(oc.r, 120));

// trimma och förläng
const vis = () => true;
doc = { ...doc, entities: [line("h", [0, 0], [1000, 0]), line("v1", [300, -100], [300, 100]), line("v2", [700, -100], [700, 100])] };
const mid = trim(doc, doc.entities[0], [500, 0], vis)!;
check("trimma mitten delar linjen i två", mid.length === 2 && nearPt((mid[0] as any).p[1], [300, 0]) && nearPt((mid[1] as any).p[0], [700, 0]), mid);
const end = trim(doc, doc.entities[0], [100, 0], vis)!;
check("trimma änden kapar vid korsningen", end.length === 1 && nearPt((end[0] as any).p[0], [300, 0]) && nearPt((end[0] as any).p[1], [1000, 0]), end);
doc = { ...doc, entities: [line("h", [0, 0], [500, 0]), line("wall", [800, -100], [800, 100])] };
const ex = extend(doc, doc.entities[0], [450, 0], vis) as any;
check("förläng drar änden till nästa linje", ex && nearPt(ex.p[1], [800, 0]), ex?.p);
check("förläng utan något att nå", extend({ ...doc, entities: [doc.entities[0]] }, doc.entities[0], [450, 0], vis) === null);

// mät och kommandon
const m = measure([[0, 0], [3000, 0], [3000, 4000]]);
check("mätt längd", near(m.length, 7000) && near(m.area!, 6e6));
check("förkortningar", commandOf("CO") === "kopiera" && commandOf("mi") === "spegla" && commandOf("TR") === "trimma" && commandOf("Mät") === "mat" && commandOf("xyz") === null);

console.log(failures ? `${failures} fel` : "alla ändringskommandon håller");
if (failures) process.exit(1);
