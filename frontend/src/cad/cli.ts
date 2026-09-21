/* Byggmodellens kärna som ett kommando: läser ett dokument (JSON) på stdin och skriver vad kärnan säger om
 * det - validering, relationer, mängder, kollisioner med hålförslag, ett snitt och en fasad - som JSON på stdout.
 *
 * Så kan ett prov på servern (Python) fråga exakt samma kod som ritbordet kör, utan webbläsare: samma kroppar,
 * samma kollisioner, samma tal. Körs med node efter esbuild. */

import { type CadDocument, validate, relations } from "./building";
import { sectionOfDocument, elevationPlane, elevationOfDocument, solidsOf } from "./solids";
import { quantities, materialQuantities } from "./quantities";
import { findClashes, proposeOpenings } from "./clash";

declare const process: any;

let raw = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (c: string) => { raw += c; });
process.stdin.on("end", () => {
  const input = JSON.parse(raw);
  const doc: CadDocument = input.doc ?? input;
  const line = input.section ?? null;
  const dir = input.elevation ?? "S";
  const clashes = findClashes(doc);
  const out = {
    problems: validate(doc),
    relations: relations(doc),
    quantities: quantities(doc),
    materials: materialQuantities(doc),
    clashes,
    proposals: proposeOpenings(doc, clashes),
    section: line ? sectionOfDocument(doc, { a: line[0], b: line[1], depth: input.depth ?? 3000 }) : [],
    elevation: elevationOfDocument(doc, elevationPlane(doc, dir)),
    solids: Object.fromEntries(doc.entities.map((e) => [e.id, solidsOf(doc, e)])),
  };
  process.stdout.write(JSON.stringify(out) + "\n");
});
