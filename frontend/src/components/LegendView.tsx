import { Fragment, useMemo, useState } from "react";

import { t as tr } from "../i18n";
import CodeReference from "./CodeReference";
/* The drawing's own designation list, and what the reading made of every line in it.
 *
 * A sheet says what its codes mean before it says anything else, and every identity in the takeoff rests on that
 * reading. So it is shown whole: each code, the words beside it, the section it stands under, what the reading
 * took it for - a pipe system, a fitting, a material - and whether the page itself showed that or the section it
 * belongs to spoke for it. Then what the sheet actually did with it: how many labels open with the code, and how
 * many metres carry it.
 */

const ROLE_SV: Record<string, string> = {
  system: "Rörsystem", component: "Komponent", material: "Material", unused: "Oanvänd",
};
const ROLE_HINT: Record<string, string> = {
  system: "En beteckning som öppnar med koden namnger ett rör",
  component: "En tagg för en armatur eller enhet — blir aldrig ett rör",
  material: "Skrivs mitt i beteckningen: rörmaterial eller isolerklass",
  unused: "Listad, men bladet visar aldrig koden i bruk",
};
const FROM_SV: Record<string, string> = {
  usage: "sidan visade det", heading: "rubriken talade för koden", other_sheet: "ett annat blad i omgången",
  the_list_says_so: "ritningens förklaring", the_sheet_writes_it_as_a_pipe: "ritningens rörbeteckningar",
};

type Entry = {
  code: string; description: string; heading: string; role: string; role_from: string; bbox: number[];
  page?: number | null;
};

export default function LegendView({ legend, designations, quantities, onZoom }: {
  legend: { entries: Entry[]; n_entries?: number; own?: boolean; usage_systems?: Record<string, string[]> };
  designations: any[];
  quantities: any[];
  onZoom?: (bbox: number[]) => void;
}) {
  const [q, setQ] = useState("");
  const [only, setOnly] = useState<string>("alla");

  const stats = useMemo(() => {
    const entries = legend?.entries ?? [];
    const codes = [...entries].sort((a, b) => b.code.length - a.code.length);
    const head = (t: string) => (t || "").toUpperCase().trim();
    const owner = (text: string) => codes.find((e) => {
      const c = e.code.toUpperCase();
      const h = head(text);
      return h === c || h.startsWith(c);
    });
    const inferredLabels = new Set(Object.values(legend?.usage_systems ?? {}).flat());
    const labels: Record<string, number> = {};
    const uncovered: Record<string, number> = {};
    for (const d of designations ?? []) {
      const e = owner(d.text || "");
      if (e) labels[e.code.toUpperCase()] = (labels[e.code.toUpperCase()] ?? 0) + 1;
      else if ((d.text || "").trim() && !inferredLabels.has(d.id ?? d.did)) uncovered[(d.text || "").trim()] = (uncovered[(d.text || "").trim()] ?? 0) + 1;
    }
    const metres: Record<string, number> = {};
    for (const r of quantities ?? []) {
      const e = owner(r.designation || "");
      if (e) metres[e.code.toUpperCase()] = (metres[e.code.toUpperCase()] ?? 0) + (r.confirmed_total_m || 0);
    }
    return { labels, metres, uncovered };
  }, [legend, designations, quantities]);

  const entries = legend?.entries ?? [];
  const shown = entries.filter((e) => {
    if (only !== "alla" && e.role !== only) return false;
    if (!q.trim()) return true;
    const s = `${e.code} ${e.description} ${e.heading}`.toLowerCase();
    return s.includes(q.trim().toLowerCase());
  });
  const bySection = new Map<string, Entry[]>();
  for (const e of shown) {
    const k = (e.heading || "").trim() || "—";
    if (!bySection.has(k)) bySection.set(k, []);
    bySection.get(k)!.push(e);
  }
  const pages = [...new Set(entries.map((e) => e.page).filter((p): p is number => typeof p === "number"))]
    .sort((a, b) => a - b);
  const borrowedFrom = pages.length === 1 ? `på blad ${pages[0] + 1}`
    : pages.length > 1 ? `på blad ${pages.map((p) => p + 1).join(", ")}`
      : "på ett annat blad i handlingen";
  const counts = entries.reduce((a: Record<string, number>, e) => ({ ...a, [e.role]: (a[e.role] ?? 0) + 1 }), {});
  const uncovered = Object.entries(stats.uncovered).sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    return (
      <div className="sheetview">
        <div className="card">
          <h3>{tr("Ingen förklaringslista hittades")}</h3>
          <p className="muted">
            Varken det här bladet eller något annat blad i handlingen bär en kolumn av koder med förklaringar
            som läsningen kunde hitta. Utan listan gör läsningen inga anspråk på vad koderna betyder: varje
            beteckning får då tala för sig själv, och ingen kod avfärdas som komponent. Ladda upp bladet som
            bär listan i samma projekt, så läses den och gäller för alla ritningarna.
          </p>
        </div>
        <CodeReference />
      </div>
    );
  }

  return (
    <div className="sheetview">
      <CodeReference />
      {Object.keys(legend?.usage_systems ?? {}).length > 0 && <section className="card">
        <h3>{tr("Systemkoder utlästa ur ritningens beteckningar")}</h3>
        <p className="muted">{tr("Dessa numrerade system saknas i förklaringslistan men återkommer med dimension och listat material i ritningens rörbeteckningar. Varje beteckning måste fortfarande kunna kopplas till sitt eget rör.")}</p>
        {Object.entries(legend.usage_systems ?? {}).map(([code, ids]) => <p key={code}>
          <strong>{code}</strong> · {ids.length} {tr("beteckningar på bladet")}
        </p>)}
      </section>}
      <div className="card">
        <div className="legendhead">
          <div>
            <h3>{legend?.own === false ? "Handlingens förklaringslista" : "Ritningens egen förklaringslista"}</h3>
            <p className="muted">
              {entries.length} rader. Läsningen tog {counts.system ?? 0} som rörsystem, {counts.component ?? 0} som
              komponenter, {counts.material ?? 0} som material och {counts.unused ?? 0} står oanvända på bladet.
            </p>
            {legend?.own === false && (
              <p className="muted">
                Listan står inte på det här bladet utan {borrowedFrom}. En omgång skriver sin lista en gång och
                låter planbladen stå på den, så den gäller här — men den får bara neka en kod den själv listar.
                En kod den aldrig nämner får tala för sig själv.
              </p>
            )}
          </div>
          <div className="legendfilters">
            <input placeholder={tr("Sök kod eller ord…")} value={q} onChange={(e) => setQ(e.target.value)} />
            <select value={only} onChange={(e) => setOnly(e.target.value)}>
              <option value="alla">{tr("Alla roller")}</option>
              <option value="system">{tr("Rörsystem")}</option>
              <option value="component">Komponenter</option>
              <option value="material">Material</option>
              <option value="unused">{tr("Oanvända")}</option>
            </select>
          </div>
        </div>

        <div className="tablewrap">
          <table className="legendtable">
            <thead>
              <tr>
                <th>Kod</th><th>{tr("Ritningens förklaring")}</th><th>{tr("Läsningen tog det för")}</th>
                <th>{tr("Varifrån")}</th><th className="num">Etiketter</th><th className="num">Meter</th>
              </tr>
            </thead>
            <tbody>
              {[...bySection.entries()].map(([section, rows]) => (
                <Fragment key={section}>
                  <tr className="sectionrow"><td colSpan={6}>{section}</td></tr>
                  {rows.map((e) => {
                    const n = stats.labels[e.code.toUpperCase()] ?? 0;
                    const m = stats.metres[e.code.toUpperCase()] ?? 0;
                    return (
                      <tr key={`${section}/${e.code}`} className={e.role === "system" ? "sys" : ""}
                        onClick={() => e.bbox && onZoom?.(e.bbox)}>
                        <td><b>{e.code}</b></td>
                        <td>{e.description}</td>
                        <td title={ROLE_HINT[e.role]}><span className={`rolepill ${e.role}`}>{ROLE_SV[e.role] ?? e.role}</span></td>
                        <td className="muted">{FROM_SV[e.role_from] ?? e.role_from}</td>
                        <td className="num">{n || <span className="muted">–</span>}</td>
                        <td className="num">{m > 0 ? m.toFixed(2) : <span className="muted">–</span>}</td>
                      </tr>
                    );
                  })}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>

        {uncovered.length > 0 && (
          <div className="legendsection">
            <h4>{tr("Beteckningar bladet skriver som listan inte förklarar")}</h4>
            <p className="muted">
              Texten står på ritningen men ingen rad i listan öppnar den. Läsningen påstår ingenting om vad de är.
            </p>
            <div className="chips">
              {uncovered.slice(0, 80).map(([t, n]) => (
                <span key={t} className="chip">{t}{n > 1 ? <i> ×{n}</i> : null}</span>
              ))}
              {uncovered.length > 80 && <span className="chip muted">+{uncovered.length - 80} till</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
