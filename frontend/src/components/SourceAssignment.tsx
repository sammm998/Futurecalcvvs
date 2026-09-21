import { t as tr } from "../i18n";

/** Customer-facing exceptions only; engine diagnostics remain in the analysis artifacts. */
export default function SourceAssignment({ report }: { report: any }) {
  const incompleteBundles = (report?.bundle_landings ?? []).filter((b: any) => b.short > 0);
  if (!incompleteBundles.length) return null;
  const labels = report.adapter?.labels ?? {};
  return <section style={{ marginBottom: 24 }}>
    <div className="badge warn prose">
      <strong>{tr("Alla rör i märkta rörbuntar har inte hittats")}</strong>
      <ul>{incompleteBundles.map((b: any) => <li key={`${b.label}-${b.leader}`}>
        {labels[String(b.label)] ?? b.label}: {b.landings} / {b.expected} {tr("rör kopplade till beteckningen")}
      </li>)}</ul>
      {tr("Saknade rör räknas inte fram genom att multiplicera längden. Kontrollera bunten på ritningen.")}
    </div>
  </section>;
}
