import { t as tr } from "../i18n";

type Lengths = {
  reference_pt: number; predicted_pt: number;
  reference_recovered_pt: number; prediction_supported_pt: number;
};
type Comparison = {
  tolerance_pt: number;
  totals: Lengths & { reference_coverage: number | null; prediction_support: number | null };
  rows: (Lengths & { designation: string })[];
};
type Report = {
  state: string;
  pages: { page: number; state: string; reference_annotations: number; comparisons?: Comparison[] }[];
};
const percent = (value: number | null) => value == null ? "—" : `${(value * 100).toFixed(1)} %`;

export default function ReferenceComparison({ report, page }: { report?: Report | null; page: number }) {
  const sheet = report?.pages.find(p => p.page === page);
  const comparison = sheet?.comparisons?.[0];
  if (!report) return null;
  return <section className="card" aria-label={tr("Jämförelse med mängdmarkeringar")}>
    <h3>{tr("Jämförelse med mängdmarkeringar")}</h3>
    {report.state === "UNAVAILABLE" ? <p role="status">{tr("Referensjämförelsen kunde inte genomföras. Analysens mängder är oförändrade.")}</p>
      : !comparison ? <p className="muted">{tr("Det här bladet saknar jämförbara längdmarkeringar i PDF-filen.")}</p>
        : <>
          <p className="muted">{tr("Jämförelsen gäller motorns ursprungliga analys före manuella rättelser. PDF-markeringarna påverkar inte mängdningen.")}</p>
          <div className="kpi">
            <div className="card"><div className="v">{percent(comparison.totals.reference_coverage)}</div>
              <div className="l">{tr("Referenslinjer återfunna")}</div></div>
            <div className="card"><div className="v">{percent(comparison.totals.prediction_support)}</div>
              <div className="l">{tr("Analyserade linjer med referensstöd")}</div></div>
          </div>
          <p className="muted small">{sheet?.reference_annotations} {tr("längdmarkeringar")}
            {" · "}{tr("Tolerans i PDF-punkter")}: {comparison.tolerance_pt}</p>
          <p className="muted small">{tr("Exakt beteckning och linjens läge jämförs. Skraffering, streckluckor och vertikala meter ingår inte. Beteckningar utan referens bedöms inte. Markeringarna kan vara ofullständiga eller felaktiga.")}</p>
          <details><summary>{tr("Visa jämförelse per beteckning")}</summary>
            <div className="tablewrap"><table className="legendtable">
              <thead><tr><th>{tr("Beteckning")}</th><th>{tr("Referenslinjer återfunna")}</th><th>{tr("Analyserade linjer med referensstöd")}</th></tr></thead>
              <tbody>{comparison.rows.map(row => <tr key={row.designation}>
                <td><code>{row.designation}</code></td>
                <td>{percent(row.reference_pt ? row.reference_recovered_pt / row.reference_pt : null)}</td>
                <td>{percent(row.predicted_pt ? row.prediction_supported_pt / row.predicted_pt : null)}</td>
              </tr>)}</tbody>
            </table></div>
          </details>
        </>}
  </section>;
}
