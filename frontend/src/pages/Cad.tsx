import { useEffect, useMemo, useRef, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import PdfViewer, { type ViewerHandle } from "../components/PdfViewer";
import MarkupsList, { STATUSES, TOOL_LABEL, measureText, sourceLabel, type MarkupRow } from "../components/MarkupsList";

/* CAD-rummet: handlingen, det som ritas på den, och listan man arbetar i.
 *
 * Det här är inte mängdning och inte läsning. Här ritas på bladet - ett moln runt något som inte stämmer, en
 * anteckning, ett kontrollmått, en linje - och sedan arbetar man listan tills varje sak har ett svar.
 * Frågan lever i hela handlingen och inte på ett blad, så listan visar alla sidor och säger vilken sida raden
 * hör hemma på; att välja en rad bläddrar dit och zoomar in på markeringen.
 *
 * Måtten räknas på servern av samma mätmotor som mängdningen använder. En granskning som räknade själv skulle
 * kunna komma till ett annat tal än mängden, och då vore den ingen granskning.
 */

type Tool = "moln" | "text" | "langd" | "area" | "antal" | "frihand" | "rektangel" | "polylinje" | null;

const TOOLS: { id: Exclude<Tool, null>; label: string; hint: string }[] = [
  { id: "moln", label: "Moln", hint: "Ringa in det som ska granskas. Klicka runt området, dubbelklick avslutar." },
  { id: "text", label: "Anteckning", hint: "Klicka där anteckningen ska sitta och skriv den." },
  { id: "frihand", label: "Frihand", hint: "Dra med musen för att stryka under eller peka ut." },
  { id: "langd", label: "Längd", hint: "Kontrollmät en sträcka. Dubbelklick avslutar." },
  { id: "polylinje", label: "Polylinje", hint: "En sträcka med många knäckar." },
  { id: "area", label: "Yta", hint: "Klicka runt ytan; den sluts automatiskt." },
  { id: "rektangel", label: "Rektangel", hint: "Två hörn räcker för en rätvinklig yta." },
  { id: "antal", label: "Antal", hint: "Klicka på varje sak som ska räknas." },
];

const bbox = (pts: number[][]): number[] => {
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
};

export default function CadPage() {
  const { id } = useParams();
  const drawingId = id!;
  const [drawing, setDrawing] = useState<any>(null);
  const [data, setData] = useState<ArrayBuffer | null>(null);
  const [page, setPage] = useState(0);
  const [nPages, setNPages] = useState(1);
  const [list, setList] = useState<any>(null);
  const [tool, setTool] = useState<Tool>(null);
  const [draft, setDraft] = useState<{ points: number[][]; meters: number } | null>(null);
  const [layer, setLayer] = useState("Granskning");
  const [subject, setSubject] = useState("");
  const [note, setNote] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const viewer = useRef<ViewerHandle>(null);

  useEffect(() => {
    api.drawing(drawingId).then(setDrawing).catch((e) => setErr(e.message));
    api.fetchBlob(api.fileUrl(drawingId)).then((b) => b.arrayBuffer()).then(setData).catch((e) => setErr(e.message));
  }, [drawingId]);

  const load = () => api.allMarkups(drawingId).then(setList).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [drawingId]);
  useEffect(() => { setDraft(null); }, [page, tool]);

  const rows: MarkupRow[] = useMemo(() => list?.rows ?? [], [list]);
  const onPage = useMemo(() => rows.filter((r) => r.page === page), [rows, page]);
  const chosen = useMemo(() => rows.find((r) => r.id === selected) ?? null, [rows, selected]);
  const counts = list?.status_counts ?? {};

  // Att välja en rad är att gå dit den pekar: rätt sida framme och markeringen inzoomad. Annars måste den som
  // läser listan själv leta upp vad raden handlar om, och då är bandet mellan lista och blad bara påstått.
  const goTo = (mid: string | null) => {
    setSelected(mid);
    const r = rows.find((x) => x.id === mid);
    if (!r) return;
    if (r.page !== page) setPage(r.page);
    const pts = r.points ?? [];
    if (pts.length) window.setTimeout(() => viewer.current?.zoomTo(bbox(pts)), r.page !== page ? 320 : 0);
  };

  const save = async () => {
    if (!tool || !draft) return;
    setBusy(true); setErr("");
    try {
      const m = await api.addMarkup(drawingId, {
        page, tool, layer: layer.trim() || "Granskning",
        points: draft.points, text: tool === "text" ? note : "",
        subject: subject.trim(), comment: tool === "text" ? "" : note.trim(), status: "oppen", source: "manuell",
      });
      setDraft(null); setSubject(""); setNote("");
      await load();
      setSelected(m.id);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const patch = async (mid: string, change: any) => {
    setBusy(true); setErr("");
    try { await api.patchMarkup(drawingId, mid, change); await load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const patchMany = async (ids: string[], change: any) => {
    setBusy(true); setErr("");
    try { await api.patchMarkups(drawingId, ids, change); await load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const remove = async (mid: string) => {
    setBusy(true); setErr("");
    try {
      await api.deleteMarkup(drawingId, mid);
      if (selected === mid) setSelected(null);
      await load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const hint = TOOLS.find((t) => t.id === tool)?.hint ?? "Välj ett verktyg för att rita en fråga på bladet.";
  const scale = list?.scale_source === "UPPMÄTT" ? "Skalan är uppmätt för hand."
    : list?.scale_source === "LÄSNINGEN" ? "Skalan kommer ur läsningen av bladet."
    : "Bladet har ingen skala – kontrollmått blir i ritningens punkter.";

  return (
    <main className="review cad">
      <p className="crumb">
        <Link to="/cad">CAD</Link>
        {drawing && <> · <Link to={`/drawings/${drawingId}`}>{drawing.filename.replace(/\.pdf$/i, "")}</Link></>}
      </p>
      <div className="head">
        <div>
          <h1>CAD</h1>
          <p className="lead">
            Rita, mät och ställ frågor direkt på bladet, och arbeta listan tills var och en har ett svar.
            {" "}{scale} Det som ritas här ligger vid sidan av läsningen och ändrar den inte.
          </p>
        </div>
        <div className="row">
          <button className="secondary" onClick={async () => {
            const b = await api.fetchBlob(api.markupsCsvUrl(drawingId, page, true));
            const u = URL.createObjectURL(b); const a = document.createElement("a");
            a.href = u; a.download = "cad-markeringar.csv"; a.click(); URL.revokeObjectURL(u);
          }}>{tr("Listan som CSV")}</button>
          <Link className="secondary" to={`/mangda/${drawingId}`} style={{ textDecoration: "none" }}>{tr("Mängda bladet →")}</Link>
        </div>
      </div>

      <div className="adm-stats rv-stats">
        {STATUSES.map((s) => (
          <div className="adm-stat" key={s.id}>
            <div className="k">{s.label}</div>
            <div className="v">{counts[s.id] ?? 0}</div>
            <div className="u">{s.hint.toLowerCase()}</div>
          </div>
        ))}
      </div>

      <div className="rule" style={{ marginBottom: 16 }} />
      {err && <p className="error">{err}</p>}

      <div className="rv-grid">
        <div className="rv-sheet">
          <div className="toolbar">
            <button className="secondary small" onClick={() => viewer.current?.zoomOut()}>−</button>
            <button className="secondary small" onClick={() => viewer.current?.zoomIn()}>+</button>
            <button className="secondary small" onClick={() => viewer.current?.fitPage()}>Sida</button>
            <button className="secondary small" onClick={() => viewer.current?.fitWidth()}>Bredd</button>
            <button className="secondary small" onClick={() => viewer.current?.fullscreen()}>{tr("Helskärm")}</button>
            {nPages > 1 && (
              <select value={page} onChange={(e) => setPage(Number(e.target.value))} aria-label="Sida">
                {Array.from({ length: nPages }, (_, i) => <option key={i} value={i}>Sida {i + 1}</option>)}
              </select>
            )}
            <span className="spacer" />
            <span className="muted small">{onPage.length} på sidan · {rows.length} i handlingen</span>
          </div>
          <PdfViewer
            ref={viewer} data={data} page={page} pipes={[]} ambiguous={[]} unowned={[]} claimed={[]}
            designations={[]} leaders={[]} anchors={[]} declined={[]} selectedIdentity={null} selectedPipe={null}
            layers={{ pipes: false, ambiguous: false, unowned: false, claimed: false, designations: false,
                      leaders: false, hatched: false, declined: false } as any}
            onPipeClick={() => { /* läsningen visas inte här */ }} onPageCount={setNPages}
            editKind={(tool ? "draw" : null) as any}
            meterPerPt={list?.meters_per_pdf_point ?? null}
            onDrawn={(d: any) => setDraft({ points: d.points, meters: d.meters })}
            markups={onPage}
            selectedMarkup={selected}
            onMarkupClick={(mid) => setSelected(mid)}
          />
        </div>

        <aside className="rv-side">
          <section className="card">
            <h3 style={{ marginTop: 0 }}>{tr("Rita en fråga")}</h3>
            <div className="tk-tools">
              {TOOLS.map((t) => (
                <button key={t.id} className={tool === t.id ? "" : "secondary"} title={t.hint}
                  onClick={() => setTool(tool === t.id ? null : t.id)}>{t.label}</button>
              ))}
            </div>
            <p className="muted small" style={{ marginTop: 10 }}>{hint}</p>
            <div className="tk-fields">
              <label>Ämne
                <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={tr("Vad gäller frågan?")} />
              </label>
              <label>Lager
                <input value={layer} onChange={(e) => setLayer(e.target.value)} />
              </label>
            </div>
            <label style={{ display: "block", marginTop: 10 }}>
              {tool === "text" ? "Anteckningens text" : "Kommentar"}
              <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={3}
                placeholder={tool === "text" ? "Det som ska stå på bladet" : "Vad ska den som svarar veta?"} />
            </label>
            <div className="row" style={{ marginTop: 10 }}>
              <button disabled={!draft || busy || (tool === "text" && !note.trim())} onClick={save}>
                Spara markering
              </button>
              {draft && <button className="ghost small" onClick={() => setDraft(null)}>{tr("Ångra ritningen")}</button>}
            </div>
            {draft && <p className="muted small" style={{ marginBottom: 0 }}>
              {draft.points.length} punkter ritade{list?.meters_per_pdf_point && draft.meters
                ? ` · ${draft.meters.toLocaleString(locale(), { maximumFractionDigits: 2 })} m` : ""}
            </p>}
          </section>

          {chosen && (
            <section className="card">
              <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                <h3 style={{ margin: 0 }}>{chosen.subject || TOOL_LABEL[chosen.tool] || "Markering"}</h3>
                <button className="ghost small" onClick={() => setSelected(null)}>{tr("Stäng")}</button>
              </div>
              <table className="qty"><tbody>
                <tr><td>Sida</td><td className="num">{chosen.page + 1}</td></tr>
                <tr><td>Verktyg</td><td className="num">{TOOL_LABEL[chosen.tool] ?? chosen.tool}</td></tr>
                <tr><td>Lager</td><td className="num">{chosen.layer}</td></tr>
                {measureText(chosen.measure) && <tr><td>{tr("Mått")}</td><td className="num">{measureText(chosen.measure)}</td></tr>}
                <tr><td>{tr("Källa")}</td><td className="num">{sourceLabel(chosen.source)}</td></tr>
                <tr><td>Skapad</td><td className="num">{(chosen.created_at ?? "").slice(0, 16).replace("T", " ")}</td></tr>
              </tbody></table>
              <label style={{ display: "block", marginTop: 10 }}>Ämne
                <input defaultValue={chosen.subject ?? ""} key={`s${chosen.id}`}
                  onBlur={(e) => e.target.value !== (chosen.subject ?? "") && patch(chosen.id, { subject: e.target.value })} />
              </label>
              <label style={{ display: "block", marginTop: 10 }}>Kommentar
                <textarea defaultValue={chosen.comment ?? ""} key={`c${chosen.id}`} rows={3}
                  onBlur={(e) => e.target.value !== (chosen.comment ?? "") && patch(chosen.id, { comment: e.target.value })} />
              </label>
              <div className="row" style={{ marginTop: 10, flexWrap: "wrap" }}>
                {STATUSES.map((s) => (
                  <button key={s.id} className={(chosen.status ?? "oppen") === s.id ? "" : "secondary"}
                    disabled={busy} title={s.hint} onClick={() => patch(chosen.id, { status: s.id })}>{s.label}</button>
                ))}
              </div>
              <p className="muted small" style={{ marginTop: 10, marginBottom: 0 }}>
                Ändringar sparas när fältet lämnas. Måttet räknas om bara när markeringen ritas om på bladet.
              </p>
            </section>
          )}
        </aside>
      </div>

      <section className="card" style={{ marginTop: 16 }}>
        <h3 style={{ marginTop: 0 }}>Markeringslista</h3>
        <MarkupsList rows={rows} selected={selected} onSelect={goTo} onPatch={patch} onPatchMany={patchMany}
          onDelete={remove} busy={busy} />
      </section>
    </main>
  );
}
