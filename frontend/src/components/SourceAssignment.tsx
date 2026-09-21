import { t as tr } from "../i18n";

export const modeNames: Record<string, string> = { dimension: "Dimensionsregler (äldre analys)", model: "Modellbedömning (äldre analys)", compare: "Jämförelse (äldre analys)", combined: "Dimensionsregler och modellbedömning tillsammans" };

export default function SourceAssignment({ report, onZoom }: { report: any; onZoom: (bbox: number[]) => void }) {
  if (!report) return <p className="muted small">{tr("Den här äldre analysen saknar källmotorernas resultat. Starta en ny analys för att använda dem.")}</p>;
  const statuses: Record<string, string> = { COMPLETED: "Körd", NOT_REQUESTED: "Inte vald", NOT_CONFIGURED: "Anslutning saknas", FAILED: "Misslyckad" };
  const styleStatuses: Record<string, string> = { AUTO_CANDIDATE: "Automatiskt föreslagen", USER_SELECTED: "Vald manuellt", UNKNOWN: "Inte identifierad" };
  const hasDrawingImages = (report.model?.result?.usage ?? []).some((u: any) => u.drawing_images?.length > 0);
  const segments = report.dimension?.segments ?? report.model?.segments ?? [];
  const labels = report.adapter?.labels ?? {};
  const incompleteBundles = (report.bundle_landings ?? []).filter((b: any) => b.short > 0);
  const label = (pair: any) => pair == null ? tr("Utan tilldelning") : labels[String(pair[0])] ?? String(pair[0]);
  return <section style={{ marginBottom: 24 }}>
    <h3>{tr("Samlad röranalys")}</h3>
    <p>{tr("Ritningsstil")}: {report.style?.id ?? tr("Inte identifierad")} ({tr(styleStatuses[report.style?.status] ?? "Inte identifierad")})</p>
    <p>{tr("Dimensionsregler")}: {tr(statuses[report.dimension.status] ?? report.dimension.status)} · {tr("Modellbedömning")}: {tr(statuses[report.model.status] ?? report.model.status)}</p>
    {hasDrawingImages && <p>{tr("Modellbedömningen har även granskat bilder av originalritningen.")}</p>}
    <p>{tr("Mängderna nedan använder")}: <strong>{tr(modeNames[report.selected])}</strong>.</p>
    {incompleteBundles.length > 0 && <div className="badge warn prose">
      <strong>{tr("Alla rör i märkta rörbuntar har inte hittats")}</strong>
      <ul>{incompleteBundles.map((b: any) => <li key={`${b.label}-${b.leader}`}>
        {labels[String(b.label)] ?? b.label}: {b.landings} / {b.expected} {tr("rör kopplade till beteckningen")}
      </li>)}</ul>
      {tr("Saknade rör räknas inte fram genom att multiplicera längden. Kontrollera bunten på ritningen.")}
    </div>}
    {report.mode === "compare" && report.comparison_status !== "COMPLETED" &&
      <p className="badge warn">{tr("Jämförelsen kunde inte slutföras. Ingen överensstämmelse mellan motorerna är verifierad.")}</p>}
    {report.comparison_status === "COMPLETED" && <p>{tr("Sträckor med olika tilldelning")}: {report.differences.length}. {tr("Dimensionsförslag granskas av modellen med ritningens hänvisningar, topologi och stilregler. Obekräftade förslag kräver granskning.")}</p>}
    {report.combined?.boundary_reconciliation?.length > 0 && <p>{tr("Förgreningar avstämda mot beteckningskontakter")}: {report.combined.boundary_reconciliation.length}. {tr("En modellbekräftad huvudledning följs till nästa faktiska beteckningskontakt.")}</p>}
    {report.differences?.length > 0 && <details><summary>{tr("Granska skillnader på ritningen")}</summary>
      <table><thead><tr><th>{tr("Sträcka")}</th><th>{tr("Dimensionsregler")}</th><th>{tr("Modellbedömning")}</th><th>{tr("Samlat resultat")}</th></tr></thead>
        <tbody>{report.differences.map((d: any) => <tr key={d.stretch}><td><button className="link" onClick={() => {
          const points = segments.find((s: any) => s.stretch === d.stretch)?.points ?? [];
          if (points.length) onZoom([Math.min(...points.map((p: number[]) => p[0])) - 20, Math.min(...points.map((p: number[]) => p[1])) - 20,
            Math.max(...points.map((p: number[]) => p[0])) + 20, Math.max(...points.map((p: number[]) => p[1])) + 20]);
        }}>{d.stretch}</button></td><td>{label(d.dimension)}</td><td>{label(d.model)}</td><td>{report.combined?.segments?.find((s: any) => s.stretch === d.stretch)?.designation ?? tr("Utan tilldelning")}</td></tr>)}</tbody></table>
    </details>}
    <p className="muted small">{tr("Regelkälla: PipeStudio och Swedish VVS. Ritningens egenskaper bedöms automatiskt. När ingen känd stil passar används generella regler och ritningens egna hänvisningar. Osäkra sträckor visas för granskning.")}</p>
  </section>;
}
