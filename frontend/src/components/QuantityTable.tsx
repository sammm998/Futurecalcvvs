import { useMemo, useState } from "react";
import { identityColor, pipeColor } from "../palette";

export const identityKey = (r: any) => `${r.base}|DN${r.dn ?? "?"}`;
import { t as tr } from "../i18n";

const STATE_LABELS: Record<string, string> = { CONFIRMED: tr("BEKRÄFTAD"), AMBIGUOUS: tr("TVETYDIG"), NO_SCALE: tr("INGEN SKALA"),
  SCALE_UNSETTLED: "OAVGJORD SKALA", SCALE_FROM_THE_SET: "SKALA UR OMGÅNGEN", SCALE_GIVEN_BY_HAND: "ANGIVEN SKALA",
  UNSUPPORTED_STYLE: tr("EJ STÖDD STIL"), RISER_LABELS_ONLY: tr("ENDAST STIGARE"), IN_HATCHED_AREA: tr("I SKRAFFERAD YTA") };

/* En rad utan skala har ingen meter - och noll är inte samma sak som okänt. Tabellen skrev 0,00 i varje
   meterkolumn på ett blad vars skala aldrig blev fastställd, vilket läses som "röret är noll meter långt"
   när sanningen är "hur långt det är går inte att säga än". */
const M = (v: number | null | undefined, noScale: boolean) => (noScale || v == null ? "–" : v.toFixed(2));

export const riserCount = (r: any, source: string) => (source === "labels" ? r.riser_count_from_labels : r.riser_count) ?? 0;

export function withFloorHeight(rows: any[], floorHeight: number | null, includeHatched = false, riserSource = "labels",
                                includeDeclared = true): any[] {
  // vertical metres are never assumed by the engine; with a user-given floor height each riser counts height metres.
  // pipe drawn inside hatched areas is measured but kept out of the total unless the takeoff includes those areas.
  //
  // Förklarade kopplingsledningar är rör bladet namnger i ord i stället för med en etikett - "kopplingsledningar
  // från fördelare till apparat enligt tabell". Ritningen säger att de är där, så de räknas normalt med. Men en
  // mängdförteckning behöver inte ha dem med: de kan vara prissatta per apparat eller mätta på ett annat blad.
  // Därför går de att räkna bort, och då står kvar bara det en etikett pekat ut.
  return rows.map((r) => {
    const risers = riserCount(r, riserSource);
    const known = r.vertical_m !== "UNKNOWN" ? Number(r.vertical_m) : 0;
    const v = floorHeight && risers > 0 ? known + risers * floorHeight : (r.vertical_m === "UNKNOWN" ? null : known);
    const declared = Number(r.declared_m ?? 0);
    const h = Math.max(0, r.confirmed_horizontal_m - (includeDeclared ? 0 : declared))
      + (includeHatched ? Number(r.in_hatched_area_m ?? 0) : 0);
    return { ...r, risers_calc: risers, horizontal_calc: h, vertical_calc: v, total_calc: h + (v ?? 0) };
  });
}

export default function QuantityTable({ rows, selected, onSelect, floorHeight, includeHatched, onIncludeHatched, riserSource,
  includeDeclared = true, onIncludeDeclared, pipes = [], onPipeClick, meterPerPt }: {
    rows: any[]; selected: string | null; onSelect: (key: string | null) => void; floorHeight: number | null;
    includeHatched: boolean; onIncludeHatched: (v: boolean) => void; riserSource: string;
    includeDeclared?: boolean; onIncludeDeclared?: (v: boolean) => void;
    pipes?: any[]; onPipeClick?: (p: any) => void; meterPerPt?: number | null }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState<{ k: string; dir: 1 | -1 }>({ k: "designation", dir: 1 });
  const list = useMemo(() => {
    let l = withFloorHeight(rows, floorHeight, includeHatched, riserSource, includeDeclared).filter((r) => (!q || r.designation.toLowerCase().includes(q.toLowerCase()) || String(r.dn).includes(q)) && (!status || r.state === status));
    l = [...l].sort((a, b) => { const va = a[sort.k], vb = b[sort.k]; return (va > vb ? 1 : va < vb ? -1 : 0) * sort.dir; });
    return l;
  }, [rows, q, status, sort, floorHeight, includeHatched, riserSource, includeDeclared]);
  const hatchedTotal = rows.reduce((s, r) => s + Number(r.in_hatched_area_m ?? 0), 0);
  const declaredTotal = rows.reduce((s, r) => s + Number(r.declared_m ?? 0), 0);
  const th = (k: string, label: string, unit?: string) => (
    <th onClick={() => setSort((s) => ({ k, dir: s.k === k ? (s.dir === 1 ? -1 : 1) : 1 }))}>
      {label}{sort.k === k ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
      {unit && <span className="unit">{unit}</span>}
    </th>
  );
  const tot = (f: string) => list.reduce((s, r) => s + (typeof r[f] === "number" ? r[f] : 0), 0);
  // bladet kunde inte ge en enda meter: då är varje meterruta ett streck, inte en nolla
  const noScale = rows.length > 0 && rows.every((r) => r.state === "NO_SCALE");
  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <input placeholder={tr("Sök beteckning/DN")} value={q} onChange={(e) => setQ(e.target.value)} />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">{tr("Alla status")}</option><option value="CONFIRMED">CONFIRMED</option><option value="AMBIGUOUS">AMBIGUOUS</option><option value="NO_SCALE">NO_SCALE</option>
        </select>
        {hatchedTotal > 0 && (
          <label title={tr("Rör som är ritade inuti skrafferade ytor (väggsnitt, angränsande ritningsdel). Mäts alltid, men räknas normalt inte in i mängden.")}>
            <input type="checkbox" checked={includeHatched} onChange={(e) => onIncludeHatched(e.target.checked)} />
            {` Räkna med skrafferade ytor (${hatchedTotal.toFixed(2)} m)`}
          </label>
        )}
        {declaredTotal > 0 && onIncludeDeclared && (
          <label title={tr("Kopplingsledningar namngivna enligt ritningens standardangivelser i text eller tabell. De räknas med när geometrin har stöd för rätt system. Avmarkera om de prissätts separat per apparat.")}>
            <input type="checkbox" checked={includeDeclared} onChange={(e) => onIncludeDeclared(e.target.checked)} />
            {` Räkna med förklarade kopplingsledningar (${declaredTotal.toFixed(2)} m)`}
          </label>
        )}
      </div>
      {/* the takeoff has eleven columns and the panel beside a drawing is narrow: the table scrolls in its own
          frame, with the designation pinned, rather than pushing the panel sideways under the reader */}
      <div className="tablewrap">
      <table>
        <thead><tr>{th("designation", tr("Beteckning"))}{th("dn", "DN")}{th("label_count", tr("Etiketter"))}{th("physical_pipe_count", tr("Sträckor"))}{th("confirmed_horizontal_m", tr("Horisontellt"), "m")}{th("vertical_calc", tr("Vertikalt"), "m")}{th("total_calc", tr("Totalt"), "m")}{th("ambiguous_m", tr("Tvetydigt"), "m")}{th("in_hatched_area_m", tr("Skrafferat"), "m")}{th("risers_calc", tr("Stigare"))}{th("state", tr("Status"))}</tr></thead>
        <tbody>
          {list.flatMap((r) => [
            <tr key={identityKey(r)} className={`selectable ${selected === identityKey(r) ? "selected" : ""}`} onClick={() => onSelect(selected === identityKey(r) ? null : identityKey(r))}>
              <td><span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 2, background: identityColor(identityKey(r)), marginRight: 6, verticalAlign: "middle" }} />{r.designation}</td><td>{r.dn ?? "?"}</td><td className="num" title={(r.declared_m ?? 0) > 0
                ? `${r.label_count ?? 0} verifierade beteckningar på ritningen. ${Number(r.declared_m).toFixed(1)} m är namngivna enligt ritningens standardangivelser för kopplingsledningar.`
                : "Antal verifierade beteckningar på ritningen för denna identitet"}>
                {r.label_count ?? "–"}{(r.declared_m ?? 0) > 0 && <span className="assumed"> {tr("standardangivelse")}</span>}{(r.double_line_m ?? 0) > 0 && <span className="assumed" title={`${Number(r.double_line_m).toFixed(1)} m är rörets andra ritade kant och räknas inte: ett grövre rör ritas som två linjer.`}> dubbellinje</span>}
              </td>
              <td className="num">
                {r.physical_pipe_count > 0 ? (
                  <button className="ghost small drill" title={tr("Visa varje sträcka för sig")}
                    onClick={(e) => { e.stopPropagation(); setOpen(open === identityKey(r) ? null : identityKey(r)); }}>
                    {r.physical_pipe_count} {open === identityKey(r) ? "▾" : "▸"}
                  </button>
                ) : r.physical_pipe_count}
              </td>
              {/* En rad som bara är stigare har inga vågräta meter, och en nolla där läses som en mätning.
                  Det är den inte. Samma slags etikett används på två sätt: vid en vask eller golvbrunn finns
                  ingen ledning i planet alls - röret går ned genom bjälklaget - men den används också där ett
                  rör kommer upp ur golvet och dras vidare längs väggen, och då finns ledningen och läsningen
                  kan ha missat den. Strecket säger att ingen vågrät sträcka hittades, utan att påstå vilket
                  av de två fallen det är. */}
              <td className="num">{r.state === "IN_HATCHED_AREA" && !(r.horizontal_calc > 0)
                ? <span className="muted" title={`Hela stråket är ritat inne i en skrafferad yta (${Number(r.in_hatched_area_m ?? 0).toFixed(2)} m). Skrafferingen är hur ritningen säger att en del inte redovisas här - en angränsande byggnadsdel eller ett annat skede - och mängden räknar inte i den. Bocka i "Räkna med skrafferade ytor" om den här ritningen menar något annat med sin skraffering.`}>–</span>
                : r.state === "RISER_LABELS_ONLY" && !(r.horizontal_calc > 0)
                ? <span className="muted" title={tr("Ingen vågrät sträcka hittad för den här etiketten. Den märker ett rör som går genom bjälklaget: antingen slutar det där (en vask, en golvbrunn) och det finns ingen ledning i planet, eller så fortsätter det längs väggen och läsningen har inte hittat den. Ritningen avgör det med strecket vid dimensionssiffran.")}>–</span>
                : M(r.horizontal_calc, noScale)}</td>
              <td className="num">{noScale || r.vertical_calc == null
                ? (r.risers_calc > 0
                  ? <span className="muted" title={tr("Stigarna är hittade; ange våningshöjd för att räkna om dem till meter")}>{`${r.risers_calc} st × höjd`}</span>
                  : <span className="muted" title={tr("Ritningen anger ingen höjd och inga stigare hittades")}>{tr("okänt")}</span>)
                : <>
                    {Number(r.vertical_calc).toFixed(2)}
                    {/* a height the reader typed is an assumption about the building, not something the sheet
                        says: the metre is shown, and marked for what it is */}
                    {floorHeight && r.risers_calc > 0 && (
                      <span className="assumed" title={`Antaget: ${r.risers_calc} stigare × ${String(floorHeight).replace(".", ",")} m våningshöjd. Ritningen anger ingen höjd.`}> ant.</span>
                    )}
                  </>}</td>
              <td className="num strong">{M(r.total_calc, noScale)}</td>
              <td className="num">{!noScale && r.ambiguous_m > 0 ? r.ambiguous_m.toFixed(2) : "–"}</td>
              <td className="num">{!noScale && (r.in_hatched_area_m ?? 0) > 0 ? Number(r.in_hatched_area_m).toFixed(2) : "–"}</td>
              <td className="num" title={`Ritade stigarsymboler: ${r.riser_count ?? 0} · etiketter med dimension på raden under: ${r.riser_count_from_labels ?? 0}`}>{r.risers_calc > 0 ? r.risers_calc : "–"}</td>
              <td><span className={`badge ${r.state === "CONFIRMED" ? "ok" : r.state === "AMBIGUOUS" || r.state === "RISER_LABELS_ONLY" || r.state === "IN_HATCHED_AREA" ? "warn" : "bad"}`}>{STATE_LABELS[r.state] ?? r.state}</span></td>
            </tr>,
            ...(open === identityKey(r)
              ? pipes.filter((p: any) => p.identity === identityKey(r))
                  .sort((a: any, b: any) => (b.horizontal_m ?? 0) - (a.horizontal_m ?? 0))
                  .map((p: any, i: number) => {
                    const labels = p.supporting_anchors?.length ?? 0;
                    const bridged = (p.bridged_gap_pt ?? 0) * (meterPerPt ?? 0);
                    return (
                      <tr key={`${identityKey(r)}-run-${p.physical_pipe_id}`} className="run"
                        onClick={() => onPipeClick?.(p)}>
                        <td><span style={{ display: "inline-block", width: 12, height: 12, borderRadius: 2, background: pipeColor(p), marginRight: 6 }} />{String(i + 1).padStart(2, "0")} · sträcka</td>
                        <td colSpan={2} className="muted">
                          sida {(p.page ?? 0) + 1} · {labels} etikett{labels === 1 ? "" : "er"}
                        </td>
                        <td className="num muted">{p.graph_nodes?.length ?? ""}</td>
                        <td className="num">{p.horizontal_m == null ? "–" : p.horizontal_m.toFixed(2)}</td>
                        <td className="num muted">{typeof p.vertical_m === "number" ? p.vertical_m.toFixed(2) : "–"}</td>
                        <td className="num strong">{p.total_m == null ? "–" : p.total_m.toFixed(2)}</td>
                        <td colSpan={4} className="muted" style={{ fontSize: 12 }}>
                          {(p.section_levels ?? []).map((e: any) => `${e.level.kind}${e.level.value >= 0 ? "+" : ""}${e.level.value}`).join(" · ")}
                          {p.section_levels?.length ? " · " : ""}
                          {(p.reasons ?? []).slice(0, 2).join(" · ")}
                          {bridged > 0.005 ? `${p.reasons?.length ? " · " : ""}${bridged.toFixed(2)} m överbryggade streckglapp` : ""}
                        </td>
                      </tr>
                    );
                  })
              : []),
          ])}
        </tbody>
        <tfoot><tr><th>Summa</th><th></th><th className="num">{tot("label_count")}</th><th className="num">{tot("physical_pipe_count")}</th><th className="num">{M(tot("horizontal_calc"), noScale)}</th><th className="num">{M(tot("vertical_calc"), noScale)}</th><th className="num strong">{M(tot("total_calc"), noScale)}</th><th className="num">{M(tot("ambiguous_m"), noScale)}</th><th className="num">{M(tot("in_hatched_area_m"), noScale)}</th><th className="num">{tot("risers_calc")}</th><th></th></tr></tfoot>
      </table>
      </div>
    </div>
  );
}
