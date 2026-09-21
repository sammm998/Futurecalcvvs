import { useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

/* Egna markeringar: mät, markera och anteckna direkt på ritningen.
 *
 * Det här ligger vid sidan av läsningen, aldrig i den. Motorn mäter det ritaren ritade; det här är vad
 * mängdaren lade till för hand - en sträcka verktyget inte kunde namnge, en yta, ett antal, en anteckning.
 * De två redovisas var för sig så att ingen behöver undra vilket som är vilket.
 *
 * Måtten räknas på servern ur punkterna och bladets egen skala. Siffran som visas medan man ritar är en
 * förhandsvisning; den som sparas är serverns, och utan en färdig läsning finns ingen skala - då står det
 * "ingen skala" i stället för påhittade meter.
 */

export type MarkTool = "langd" | "area" | "antal" | "text" | null;
export type MarkDraft = { points: number[][]; meters: number } | null;

const TOOLS: [Exclude<MarkTool, null>, string, string][] = [
  ["langd", "Längd", "Klicka längs det som ska mätas. Dubbelklick eller Enter avslutar, Esc avbryter."],
  ["area", "Yta", "Klicka runt ytan. Den sluts automatiskt; dubbelklick avslutar."],
  ["antal", "Antal", "Klicka på varje sak som ska räknas. Dubbelklick avslutar."],
  ["text", "Anteckning", "Klicka där anteckningen ska sitta, dubbelklicka, och skriv texten."],
];

const kr2 = (v: number) => v.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function measureText(m: any): string {
  if (!m) return "";
  if (m.scale === "INGEN_SKALA") return `${m.langd_pt ? Math.round(m.langd_pt) + " pt" : ""} · ingen skala`;
  if (typeof m.kvm === "number") return `${kr2(m.kvm)} m²`;
  if (typeof m.m === "number") return `${kr2(m.m)} m`;
  if (typeof m.antal === "number") return `${m.antal} st`;
  return "";
}

export default function Markups({ drawingId, page, tool, draft, meterPerPt, onToolChange, onDraftClear, onChanged }: {
  drawingId: string; page: number; tool: MarkTool; draft: MarkDraft; meterPerPt: number | null;
  onToolChange: (t: MarkTool) => void; onDraftClear: () => void; onChanged: (rows: any[]) => void;
}) {
  const [data, setData] = useState<any>(null);
  const [layer, setLayer] = useState("Mängdning");
  const [designation, setDesignation] = useState("");
  const [text, setText] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api.markups(drawingId, page).then((d) => { setData(d); onChanged(d.rows); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [drawingId, page]);

  const save = async () => {
    if (!tool || !draft) return;
    setBusy(true); setErr("");
    try {
      await api.addMarkup(drawingId, { page, tool, layer: layer.trim() || "Mängdning",
        designation: designation.trim() || null, points: draft.points, text: tool === "text" ? text : "" });
      onDraftClear(); setText("");
      await load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const remove = async (id: string) => {
    try { await api.deleteMarkup(drawingId, id); await load(); } catch (e: any) { setErr(e.message); }
  };

  const preview = draft && tool ? (
    tool === "antal" ? `${draft.points.length} st`
      : tool === "text" ? "anteckning"
      : tool === "area" ? (draft.points.length >= 3 ? "yta - räknas när den sparas" : "minst tre punkter")
      : meterPerPt ? `${kr2(draft.meters)} m` : `${draft.points.length} punkter · ingen skala`
  ) : null;

  const totals = data?.totals;
  return (
    <div className="card corr">
      <p className="muted" style={{ marginTop: 0 }}>
        Egna markeringar ligger vid sidan av läsningen och räknas aldrig in i den. Måtten räknas på servern ur
        bladets skala.
      </p>
      <div className="row" style={{ gap: 6 }}>
        {TOOLS.map(([k, label]) => (
          <button key={k} className={tool === k ? "small" : "secondary small"}
            onClick={() => { onToolChange(tool === k ? null : k); onDraftClear(); }}>{label}</button>
        ))}
        {tool && <button className="ghost small" onClick={() => { onToolChange(null); onDraftClear(); }}>Avmarkera</button>}
      </div>
      {tool && <p className="muted small" style={{ margin: "8px 0 0" }}>{TOOLS.find(([k]) => k === tool)?.[2]}</p>}

      {tool && (
        <div className="row" style={{ marginTop: 10 }}>
          <label className="small">Lager <input value={layer} onChange={(e) => setLayer(e.target.value)} style={{ width: 120 }} /></label>
          <label className="small">Beteckning <input value={designation} placeholder="valfritt"
            onChange={(e) => setDesignation(e.target.value)} style={{ width: 130 }} /></label>
        </div>
      )}
      {draft && tool && (
        <div className="draftbox pos" style={{ marginTop: 10 }}>
          <b>{preview}</b>
          {tool === "text" && (
            <input value={text} placeholder={tr("Texten…")} onChange={(e) => setText(e.target.value)} style={{ marginTop: 6, width: "100%" }} />
          )}
          <div className="row" style={{ marginTop: 8 }}>
            <button onClick={save} disabled={busy || (tool === "text" && !text.trim())}>{busy ? "Sparar…" : "Spara markering"}</button>
            <button className="ghost small" onClick={onDraftClear}>{tr("Gör om")}</button>
          </div>
        </div>
      )}
      {err && <p className="error">{err}</p>}

      {data && (
        <>
          <div className="row" style={{ marginTop: 14, gap: 8 }}>
            <span className="badge small">{kr2(totals.m)} m</span>
            <span className="badge small">{kr2(totals.kvm)} m²</span>
            <span className="badge small">{totals.antal} st</span>
            {data.unscaled > 0 && <span className="badge warn small">{data.unscaled} utan skala</span>}
            {!data.meters_per_pdf_point && <span className="muted small">{tr("kör en analys så får markeringarna meter")}</span>}
          </div>
          <div className="tablewrap" style={{ marginTop: 8 }}>
            <table className="qty">
              <thead><tr><th>Verktyg</th><th>Lager</th><th>Beteckning</th><th className="num">{tr("Mått")}</th><th></th></tr></thead>
              <tbody>
                {data.rows.map((r: any) => (
                  <tr key={r.id}>
                    <td>{TOOLS.find(([k]) => k === r.tool)?.[1] ?? r.tool}{r.text ? <div className="muted small">{r.text}</div> : null}</td>
                    <td className="muted">{r.layer}</td>
                    <td className="lf-mono">{r.designation ?? "–"}</td>
                    <td className="num">{measureText(r.measure)}</td>
                    <td><button className="ghost small" onClick={() => remove(r.id)}>{tr("Ta bort")}</button></td>
                  </tr>
                ))}
                {!data.rows.length && <tr><td colSpan={5} className="empty">{tr("Inga markeringar på den här sidan.")}</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
