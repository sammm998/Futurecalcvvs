/* Kommandon och transaktioner: varje ändring av modellen är en lista av operationer som går att göra ogjord.
 *
 * Ingenting i gränssnittet skriver i dokumentet direkt. Ett verktyg bygger en transaktion - "placera dörr" är
 * tre operationer: dörren läggs till, väggen får sin öppning, relationen står i dörrens host-fält - och den
 * tillämpas som en helhet. Ångra tar tillbaka hela transaktionen, i omvänd ordning; gör om lägger tillbaka den.
 * Det gäller ritobjekt, nivåer, rutnät, lager, vyer, blad och material lika, och för agenten lika mycket som
 * för musen: det finns ingen annan väg in i modellen.
 *
 * Varje operation bär både före och efter, så att ångra inte behöver räkna ut något: den skriver tillbaka det
 * som stod där. Det är dyrare i minne än en snygg invers, och det är alltid rätt. */

import { type CadDocument, type Entity, type GridLine, type Layer, type Level, type Material, type Sheet, type View, type BlockDef, type Constraint, uid } from "./building";

export type Coll = "entities" | "levels" | "grids" | "layers" | "views" | "sheets" | "materials" | "blocks" | "constraints";
type Item = Entity | Level | GridLine | Layer | View | Sheet | Material | BlockDef | Constraint;

export type Op =
  | { kind: "add"; coll: Coll; item: Item }
  | { kind: "remove"; coll: Coll; item: Item }
  | { kind: "update"; coll: Coll; before: Item; after: Item }
  | { kind: "settings"; before: CadDocument["settings"]; after: CadDocument["settings"] }
  | { kind: "meta"; field: "project" | "building" | "site"; before: any; after: any };

export type Transaction = { id: string; label: string; at: string; user?: string; ops: Op[]; source?: "user" | "agent" | "import" };

const idOf = (x: any): string => x.id ?? `${x.kind}:${x.entity}:${x.grip ?? x.level ?? x.host ?? x.support ?? ""}`;

function replaceIn<T extends Item>(list: T[], item: T): T[] {
  const id = idOf(item);
  const i = list.findIndex((x) => idOf(x) === id);
  if (i < 0) return [...list, item];
  const out = list.slice(); out[i] = item; return out;
}
function removeFrom<T extends Item>(list: T[], item: T): T[] {
  const id = idOf(item);
  return list.filter((x) => idOf(x) !== id);
}

/** Tillämpa en operation. Dokumentet ändras aldrig på plats: det som kommer tillbaka är ett nytt dokument. */
export function applyOp(doc: CadDocument, op: Op): CadDocument {
  switch (op.kind) {
    case "add": return { ...doc, [op.coll]: replaceIn((doc as any)[op.coll], op.item) };
    case "remove": return { ...doc, [op.coll]: removeFrom((doc as any)[op.coll], op.item) };
    case "update": return { ...doc, [op.coll]: replaceIn((doc as any)[op.coll], op.after) };
    case "settings": return { ...doc, settings: op.after };
    case "meta": return { ...doc, [op.field]: op.after };
  }
}

export function invert(op: Op): Op {
  switch (op.kind) {
    case "add": return { kind: "remove", coll: op.coll, item: op.item };
    case "remove": return { kind: "add", coll: op.coll, item: op.item };
    case "update": return { kind: "update", coll: op.coll, before: op.after, after: op.before };
    case "settings": return { kind: "settings", before: op.after, after: op.before };
    case "meta": return { kind: "meta", field: op.field, before: op.after, after: op.before };
  }
}

export function applyTransaction(doc: CadDocument, tx: Transaction): CadDocument {
  let d = doc;
  for (const op of tx.ops) d = applyOp(d, op);
  return { ...d, revision: doc.revision + 1 };
}

export function undoTransaction(doc: CadDocument, tx: Transaction): CadDocument {
  let d = doc;
  for (const op of [...tx.ops].reverse()) d = applyOp(d, invert(op));
  return { ...d, revision: doc.revision + 1 };
}

/** Bygger en transaktion steg för steg. Ett update stämplar version och tid på objektet. */
export class Tx {
  ops: Op[] = [];
  constructor(public label: string, public source: Transaction["source"] = "user", public user?: string) {}
  add(coll: Coll, item: Item) { this.ops.push({ kind: "add", coll, item }); return this; }
  remove(coll: Coll, item: Item) { this.ops.push({ kind: "remove", coll, item }); return this; }
  update<T extends Item>(coll: Coll, before: T, after: T) {
    const stamped = ("version" in (after as any))
      ? { ...(after as any), version: ((before as any).version ?? 0) + 1, updated_at: new Date().toISOString(), ...(this.user ? { user: this.user } : {}) }
      : after;
    this.ops.push({ kind: "update", coll, before, after: stamped }); return this;
  }
  settings(before: CadDocument["settings"], after: CadDocument["settings"]) { this.ops.push({ kind: "settings", before, after }); return this; }
  meta(field: "project" | "building" | "site", before: any, after: any) { this.ops.push({ kind: "meta", field, before, after }); return this; }
  get empty() { return this.ops.length === 0; }
  build(): Transaction { return { id: uid(), label: this.label, at: new Date().toISOString(), user: this.user, ops: this.ops, source: this.source }; }
}

/** Historiken: det som gjorts och det som ångrats. Kapad till ett rimligt antal steg. */
export type History = { past: Transaction[]; future: Transaction[]; limit: number };
export const emptyHistory = (limit = 200): History => ({ past: [], future: [], limit });

export function commit(doc: CadDocument, hist: History, tx: Transaction): { doc: CadDocument; hist: History } {
  if (!tx.ops.length) return { doc, hist };
  return { doc: applyTransaction(doc, tx), hist: { ...hist, past: [...hist.past.slice(-(hist.limit - 1)), tx], future: [] } };
}
export function undo(doc: CadDocument, hist: History): { doc: CadDocument; hist: History; tx: Transaction | null } {
  const tx = hist.past[hist.past.length - 1];
  if (!tx) return { doc, hist, tx: null };
  return { doc: undoTransaction(doc, tx), hist: { ...hist, past: hist.past.slice(0, -1), future: [tx, ...hist.future].slice(0, hist.limit) }, tx };
}
export function redo(doc: CadDocument, hist: History): { doc: CadDocument; hist: History; tx: Transaction | null } {
  const [tx, ...rest] = hist.future;
  if (!tx) return { doc, hist, tx: null };
  return { doc: applyTransaction(doc, tx), hist: { ...hist, past: [...hist.past, tx], future: rest }, tx };
}

/** Objekten en transaktion rörde - för revisionshistorikens "Flyttade vägg och tre dörrar". */
export function touched(tx: Transaction): string[] {
  const ids = new Set<string>();
  for (const op of tx.ops) {
    if (op.kind === "add" || op.kind === "remove") ids.add(idOf(op.item));
    else if (op.kind === "update") ids.add(idOf(op.after));
  }
  return [...ids];
}
