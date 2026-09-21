import { t as tr } from "../i18n";

type Declarations = {
  statement: string[];
  connection_pipes: { stem: string; text: string; dn: number | null; dns: number[] }[];
};

export default function DrawingDeclarations({ declarations }: { declarations?: Declarations | null }) {
  if (!declarations?.connection_pipes?.length) return null;
  return <section className="card" aria-label={tr("Ritningens standardangivelser")}>
    <strong>{tr("Ritningens standardangivelser")}</strong>
    <p className="muted small">{tr("Avlästa regler för kopplingsledningar. De ger mängd först när rörgeometrin också kan knytas till rätt system.")}</p>
    <ul>{declarations.connection_pipes.map(pipe => <li key={pipe.stem}>
      <code>{pipe.text}</code>
      {pipe.dn == null && <span className="assumed"> {tr("Dimension behöver granskas")}
        {pipe.dns.length > 0 ? ` (${pipe.dns.join(" / ")})` : ""}</span>}
    </li>)}</ul>
    <details><summary>{tr("Visa avläst text")}</summary>
      <div className="small" style={{ whiteSpace: "pre-wrap" }}>{declarations.statement.join("\n")}</div>
    </details>
  </section>;
}
