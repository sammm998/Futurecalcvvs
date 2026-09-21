/* Var ett rör slutar, och varför - sagt på ritningens språk.
 *
 * Motorn ger varje kant på varje fysiskt rör ett skäl (pipes/frontier.py). Här får skälen sina svenska ord och
 * sina färger: grönt där röret slutar på rätt ställe, rött där läsningen sannolikt tappar meter, orange där den
 * lämnat något öppet med flit. Färgerna är samma som i frontier-overlay.pdf, så bladet på skärmen och bladet
 * på papper säger samma sak.
 */
import { t as tr } from "./i18n";

export type FrontierClass = "REAL" | "LOSSY" | "OPEN";

export const FRONTIER_LABELS: Record<string, string> = {
  REAL_DN_BOUNDARY: tr("Samma ledning fortsätter med en annan dimension"),
  REAL_SYSTEM_BOUNDARY: tr("Geometrin fortsätter men tillhör ett annat system"),
  REAL_DESIGNATION_BOUNDARY: tr("Samma system, annat namn eller annan isolering"),
  DECLARED_BOUNDARY: tr("Fortsättningen ägs av bladets skrivna regel, inte av en etikett"),
  AMBIGUOUS_JUNCTION: tr("Fler än en identitet gör anspråk på fortsättningen"),
  FLOW_BUDGET: tr("Namnet hade runnit för långt förbi etiketterna och togs tillbaka"),
  UNOWNED_CONTINUATION: tr("Samma penna fortsätter och ingen etikett når den"),
  REPRESENTATION_CHANGE: tr("Ledningen fortsätter på en annan penna"),
  BROKEN_CONTINUITY: tr("Samma penna fortsätter i samma riktning efter ett gap som inte överbryggades"),
  VERTICAL: tr("Röret slutar i en stigarsymbol"),
  SYMBOL: tr("Röret slutar i en ritad komponent"),
  SHEET_EDGE: tr("Röret går ut ur bladet"),
  FREE_END: tr("Linjen slutar och ingenting finns intill"),
  CLOSED_LOOP: tr("En sluten slinga utan kant"),
  UNSUPPORTED_STRUCTURE: tr("Något läsningen inte kan sätta ord på"),
};

const REAL = new Set(["REAL_DN_BOUNDARY", "REAL_SYSTEM_BOUNDARY", "REAL_DESIGNATION_BOUNDARY", "DECLARED_BOUNDARY",
  "VERTICAL", "SYMBOL", "SHEET_EDGE", "FREE_END", "CLOSED_LOOP"]);
const LOSSY = new Set(["UNOWNED_CONTINUATION", "BROKEN_CONTINUITY", "REPRESENTATION_CHANGE"]);

export function frontierClass(reason: string): FrontierClass {
  return REAL.has(reason) ? "REAL" : LOSSY.has(reason) ? "LOSSY" : "OPEN";
}

export const FRONTIER_COLORS: Record<FrontierClass, string> = { REAL: "#0f8c1a", LOSSY: "#d91a1a", OPEN: "#ff8c00" };

export function frontierColor(reason: string): string {
  return FRONTIER_COLORS[frontierClass(reason)];
}

/** En rad om en front, till "varför"-panelen: skälet, och det i detaljen som en läsare vill veta. */
export function frontierText(f: any): string {
  const d = f?.detail ?? {};
  const base = FRONTIER_LABELS[f?.reason] ?? f?.reason ?? "";
  const bits: string[] = [];
  if (d.beyond) bits.push(`bortom: ${String(d.beyond).replace("|DN", " DN")}`);
  if (Array.isArray(d.candidates) && d.candidates.length) bits.push(`kandidater: ${d.candidates.map((c: string) => c.replace("|DN", " DN")).join(", ")}`);
  if (typeof d.unowned_pt === "number") bits.push(`${d.unowned_pt.toFixed(0)} pt oägt bortom`);
  if (typeof d.gap_pt === "number") bits.push(`gap ${d.gap_pt.toFixed(1)} pt`);
  if (d.designation) bits.push(`stigare ${d.designation}`);
  if (d.family && f?.reason === "REPRESENTATION_CHANGE") bits.push(`penna ${String(d.family).split("|s|")[0] || "utan lager"}`);
  return bits.length ? `${base} (${bits.join("; ")})` : base;
}
