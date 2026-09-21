import { useEffect, useState } from "react";
import { api } from "../api";
import { t as tr } from "../i18n";

type Entry = { code: string; term_sv: string; term_en: string; source_file: string; notes?: string; symbol_description?: string; meaning_en?: string; takeoff_implication?: string; line_count?: number; code_field?: string };
type SourceDocument = { id: string; source: string; file: string; title: string; content: string; archived: boolean };

export default function CodeReference() {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [documents, setDocuments] = useState<SourceDocument[]>([]);
  const [documentQuery, setDocumentQuery] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    api.knowledge().then(r => { if (active) { setEntries(r.entries); setDocuments(r.documents ?? []); } })
      .catch(e => { if (active) setError(e.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const q = query.trim().toLocaleLowerCase();
  const shown = entries.filter(e => !q || `${e.code} ${e.term_sv} ${e.term_en} ${e.notes ?? ""} ${e.symbol_description ?? ""} ${e.meaning_en ?? ""} ${e.takeoff_implication ?? ""}`.toLocaleLowerCase().includes(q));
  const dq = documentQuery.trim().toLocaleLowerCase();
  const shownDocuments = documents.filter(d => !dq || `${d.title} ${d.file} ${d.content}`.toLocaleLowerCase().includes(dq));
  return <section className="card">
    <h3>{tr("Svensk VVS-kodreferens")}</h3>
    <p className="muted">{tr("Allmänna kodförklaringar från swedish-vvs-drawings. Ritningens egen förklaringslista gäller vid avvikelse. Referensen ändrar inga mängder.")}</p>
    <details><summary>{tr("Sök bland referenskoder")}</summary>
      <input aria-label={tr("Sök kod eller ord…")} placeholder={tr("Sök kod eller ord…")}
        value={query} onChange={e => setQuery(e.target.value)} />
      {loading && <p>{tr("Laddar…")}</p>}
      {error && <p role="alert">{error}</p>}
      {!loading && !error && <>
        <p className="muted small">{shown.length} / {entries.length}</p>
        <div className="tablewrap"><table className="legendtable">
          <thead><tr><th>{tr("Kod")}</th><th>{tr("Förklaring")}</th><th>{tr("Källfil")}</th></tr></thead>
          <tbody>{shown.map((e, i) => <tr key={`${e.source_file}/${e.code}/${i}`}>
            <td><code>{e.code}</code></td><td>{e.term_sv}
              {(e.notes || e.symbol_description || e.meaning_en || e.takeoff_implication || e.line_count || (e.code_field && e.code_field !== "code")) && <details>
                <summary>{tr("Betydelse och förbehåll")}</summary>
                {e.code_field && e.code_field !== "code" && <p>{e.code_field === "sensor_code" ? tr("Givare") : tr("Instrument")}</p>}
                {e.symbol_description && <p>{e.symbol_description}</p>}
                {e.meaning_en && <p>{e.meaning_en}</p>}
                {e.notes && <p>{e.notes}</p>}
                {e.takeoff_implication && <p>{e.takeoff_implication}</p>}
                {e.line_count !== undefined && <p>{tr("Antal rör enligt referenskonventionen")}: {e.line_count}. {tr("Kräver stöd i ritningens redovisning.")}</p>}
              </details>}
            </td><td className="muted small">{e.source_file}</td>
          </tr>)}</tbody>
        </table></div>
      </>}
    </details>
    <details><summary>{tr("Regler, symboler och källdokument")}</summary>
      <p className="muted small">{tr("Fullständiga källtexter från de två kodbaserna. Analysens valda läge visar vilken tilldelningsmotor som kördes. Importstatus är inte ett testresultat.")}</p>
      <input aria-label={tr("Sök i regler och källtexter…")} placeholder={tr("Sök i regler och källtexter…")}
        value={documentQuery} onChange={e => setDocumentQuery(e.target.value)} />
      {!loading && !error && <p className="muted small">{shownDocuments.length} / {documents.length}</p>}
      {shownDocuments.map(d => <details key={d.id}>
        <summary>{d.title}{d.archived ? ` (${tr("Historisk version")})` : ""}</summary>
        <p className="muted small">{d.source} / {d.file}</p>
        <pre style={{whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: "0.85em", maxHeight: 480, overflow: "auto"}}>{d.content}</pre>
      </details>)}
    </details>
  </section>;
}
