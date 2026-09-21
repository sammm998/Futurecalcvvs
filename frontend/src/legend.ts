/* Bladets förklaringslista, som den läses på ritningen.
 *
 * Motorn avgör vad varje kod är; det här är bara matchningen tillbaka: vilken rad i listan en beteckning ute på
 * bladet öppnar med. Regeln är densamma som motorns, platshållaren `Bxxx` inräknad - `Bxxx GOLVBRUNN` skrivs
 * B1, B10, men också B12ML och B21M, och en matchning som bara läser siffror missar dem.
 */

import { t as tr } from "./i18n";

export type LegendEntry = {
  code: string; description: string; heading: string; role: string; role_from: string;
  bbox: number[]; page?: number | null;
};

export const ROLE_COLOR: Record<string, string> = {
  system: "#15803d",       // namnger rör
  component: "#b45309",    // ett föremål, aldrig meter
  material: "#4b5563",     // står mitt i beteckningen
  unused: "#9aa3af",       // listad, men bladet visar den aldrig i bruk
};

export const ROLE_LABEL: Record<string, string> = {
  system: tr("rörsystem"), component: tr("komponent"), material: tr("material"), unused: tr("oanvänd"),
};

/** Whether a label is written in the shape of a legend code, placeholder letters and all. */
export function codeMatches(label: string, code: string): boolean {
  const L = (label || "").toUpperCase(), C = (code || "").toUpperCase();
  if (!C) return false;
  if (L === C) return true;
  if (!C.slice(1).includes("X") || L.length < 2) return false;
  const esc = C.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const pat = esc.replace(/X{2,}/g, "\\d+[A-ZÅÄÖ]{0,3}");
  try { return new RegExp(`^${pat}$`).test(L); } catch { return false; }
}

/** The legend row a label on the sheet opens with — the longest code that fits, so `KV01` beats `KV`. */
export function legendOwner(entries: LegendEntry[], text: string): LegendEntry | null {
  const t = (text || "").trim().toUpperCase();
  if (!t) return null;
  const byLength = [...(entries ?? [])].sort((a, b) => b.code.length - a.code.length);
  for (const e of byLength) {
    const c = e.code.toUpperCase();
    if (t === c || t.startsWith(c) || codeMatches(t, c)) return e;
  }
  return null;
}
