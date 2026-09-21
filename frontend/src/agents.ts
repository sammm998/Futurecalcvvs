/* Who does what in a reading, said once so the live film and the finished account never disagree.
 *
 * Each stage is a reader with one question. It answers from the drawing, hands the answer to the next, and the
 * numbers quoted are the ones the reading actually worked from - a frame off the film, not a retelling.
 */

import { num, t as tr, trf } from "./i18n";

export type Agent = { stage: string; who: string; title: string; asks: string };

export const AGENTS: Agent[] = [
  { stage: "SEEING", who: tr("Synagenten"), title: tr("Tittar på sidan som bild"),
    asks: tr("Står det något där vektorläsningen inte har någon text?") },
  { stage: "READING_PDF", who: tr("Vektorläsaren"), title: tr("Läser PDF:en"), asks: tr("Vilka streck finns ritade, på vilka lager och med vilka pennor?") },
  { stage: "RECONSTRUCTING_TEXT", who: tr("Textbyggaren"), title: tr("Bygger texten ur streck"), asks: tr("Vilka av strecken är bokstäver, och vilka rader bildar de?") },
  { stage: "READING_DESIGNATIONS", who: tr("Beteckningsläsaren"), title: tr("Läser beteckningarna"), asks: tr("Vilka rader är beteckningar, och vilken dimension bär de?") },
  { stage: "FINDING_LEADERS", who: tr("Hänvisningsspåraren"), title: tr("Följer hänvisningslinjerna"), asks: tr("Vilken ritad linje utgår från vilken etikett, och var slutar den?") },
  { stage: "RESOLVING_PIPE_REPRESENTATION", who: tr("Familjeutredaren"), title: tr("Avgör vad som är rör"), asks: tr("Vilka pennor ritar rör på det här bladet, och vilka ritar byggnaden?") },
  { stage: "BUILDING_PHYSICAL_PIPES", who: tr("Rörbyggaren"), title: tr("Bygger de fysiska rören"), asks: tr("Vilka sträckor hör ihop till ett rör, och vem äger dem?") },
  { stage: "MEASURING", who: tr("Mätaren"), title: tr("Mäter"), asks: tr("Hur många meter blir det, i ritningens egen skala?") },
];

export const AGENT_SV: Record<string, string> = {
  scale: tr("Skalagranskaren"), coverage: tr("Täckningsgranskaren"), plausibility: tr("Rimlighetsgranskaren"),
  topology: tr("Topologigranskaren"), designation: tr("Beteckningsgranskaren"), ocr_crosscheck: tr("Synagentens korsprov"),
};

/* What a stage reports, from its own frame and - where the reading is finished - from the result it produced. */
export function frameSays(stage: string, f: any, result?: any): string[] {
  const c = result?.coverage ?? {};
  if (!f) return [];
  switch (stage) {
    case "SEEING":
      return [trf("Läser ruta {0} av {1} och hittar {2} ord där.", f.i, f.n, (f.words ?? []).length),
              tr("Den ser bilden, aldrig geometrin: ingenting den läser kan bli en meter.")];
    case "READING_PDF":
      return [trf("{0} ritade objekt på sidan, {1} × {2} punkter.",
                  f.n_paths, Math.round(f.page?.w ?? 0), Math.round(f.page?.h ?? 0)),
              tr("Inget är text ännu — en PDF från CAD skriver bokstäverna som streck.")];
    case "RECONSTRUCTING_TEXT":
      return [trf("{0} textrader byggda ur strecken.", f.n)];
    case "READING_DESIGNATIONS":
      return [c.with_dn != null
                ? trf("{0} beteckningar lästa, {1} av dem med en dimension på raden.", f.n, c.with_dn)
                : trf("{0} beteckningar lästa.", f.n),
              tr("Vilka av dem som namnger rör avgör ritningens egen förklaringslista.")];
    case "FINDING_LEADERS":
      return [trf("{0} hänvisningslinjer följda från etikett ut i ritningen.", f.n),
              tr("Ingen linje uppfinns: bara streck ritningen faktiskt drar räknas.")];
    case "RESOLVING_PIPE_REPRESENTATION": {
      const fams = f.families ?? [];
      return [fams.length
                ? trf("{0} ritade familjer togs som rör: {1}.", fams.length,
                      fams.map((x: any) => trf("penna {0}", x.width)).join(", "))
                : trf("{0} ritade familjer togs som rör.", fams.length),
              tr("En familj som ingen beteckning når tas inte — den ritar då något annat.")];
    }
    case "BUILDING_PHYSICAL_PIPES": {
      const out = [trf("{0} fysiska rör byggda.", f.n)];
      if (c.verified_attachments != null)
        out.push(trf("{0} beteckningar möter sitt rör, {1} är tvetydiga, {2} når inget.",
                     c.verified_attachments, c.ambiguous_attachments, c.no_attachments));
      return out;
    }
    case "MEASURING": {
      const s = result?.scale ?? f.scale ?? {};
      const tot = result?.totals?.confirmed_total_m ?? f.total_m ?? 0;
      const n = result?.quantities?.length ?? (f.quantities ?? []).length;
      const läge = s.state === "VERIFIED" ? tr("verifierad") : s.state ?? tr("okänd");
      return [s.meters_per_pdf_point
                ? trf("Skala {0} — {1} m per punkt.", läge, num(s.meters_per_pdf_point, 6))
                : trf("Skala {0}.", läge),
              trf("{0} m bekräftad längd fördelad på {1} beteckningar.", num(Number(tot), 2), n)];
    }
  }
  return [];
}
