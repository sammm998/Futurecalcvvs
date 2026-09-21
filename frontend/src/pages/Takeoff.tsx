import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import PdfViewer, { type ViewerHandle } from "../components/PdfViewer";
import MarkupsList, { STATUSES, TOOL_LABEL, measureText, type MarkupRow } from "../components/MarkupsList";
import { type Snap, type SnapSettings, SNAP_LABEL, defaultSnaps } from "../cad/model";
import { InkIndex, pageInk } from "../cad/pagesnap";

/* Mängda för hand: mät, räkna, dra av och märk upp direkt på bladet.
 *
 * Det här är mängdarens eget arbete och ligger vid sidan av läsningen, aldrig i den. Motorn mäter det ritaren
 * ritade; här mäter en människa det hon ser, och de två redovisas var för sig så att ingen behöver undra
 * vilket som är vilket.
 *
 * Fyra saker skiljer ett mängdningsverktyg från en rityta, och det är de fyra en mängdare saknar när de
 * fattas: skalan ska gå att mäta upp själv, markören ska fånga ritningens eget bläck, vinklar ska gå att låsa,
 * och en yta ska kunna få hål i sig - ett schakt, en pelare, ett trapphus mitt i golvet är inte golv. Utan
 * avdrag mängdas hålet som material, och det syns inte i något tal.
 *
 * Måtten räknas på servern ur punkterna och den skala som gäller för bladet. Siffran som visas medan man ritar
 * är en förhandsvisning; den som sparas är serverns.
 */

type Tool = "langd" | "polylinje" | "area" | "volym" | "antal" | "rektangel" | "moln" | "frihand" | "text" | null;

/* `punkter` är hur många klick verktyget behöver innan måttet är taget. Längden är två: startpunkt och
   ändpunkt, och sedan är sträckan mätt. Utan tal fortsätter linjen tills man dubbelklickar eller trycker
   Enter - det är polylinjens hela poäng, och en yta vet inte på förhand hur många hörn den har. */
const TOOLS: { id: Exclude<Tool, null>; label: string; hint: string; kind: "langd" | "yta" | "antal" | "text";
               punkter?: number }[] = [
  { id: "langd", label: "Längd", hint: "Klicka startpunkt och ändpunkt. Sträckan är mätt när den andra punkten är satt.", kind: "langd", punkter: 2 },
  { id: "polylinje", label: "Polylinje", hint: "Samma som längd, för en sträcka med många knäckar. Dubbelklick avslutar, Esc avbryter.", kind: "langd" },
  { id: "frihand", label: "Frihand", hint: "Dra med musen längs en böjd sträcka.", kind: "langd" },
  { id: "area", label: "Yta", hint: "Klicka runt ytan; den sluts automatiskt.", kind: "yta" },
  { id: "rektangel", label: "Rektangel", hint: "Två hörn räcker för en rätvinklig yta.", kind: "yta" },
  { id: "volym", label: "Volym", hint: "En yta med djup: kvadratmetrarna blir kubikmeter.", kind: "yta" },
  { id: "moln", label: "Moln", hint: "Ringa in ett område som ska granskas.", kind: "yta" },
  { id: "antal", label: "Antal", hint: "Klicka på varje sak som ska räknas. Varje får sitt löpnummer.", kind: "antal" },
  { id: "text", label: "Anteckning", hint: "Klicka där anteckningen ska sitta och skriv den.", kind: "text" },
];

const n2 = (v: number | null | undefined, d = 2) =>
  v == null ? "–" : v.toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });

const AREA_TOOLS = ["area", "rektangel", "moln", "volym"];

export default function TakeoffPage() {
  const { id } = useParams();
  const drawingId = id!;
  const [drawing, setDrawing] = useState<any>(null);
  const [data, setData] = useState<ArrayBuffer | null>(null);
  const [page, setPage] = useState(0);
  const [nPages, setNPages] = useState(1);
  const [tab, setTab] = useState<"matt" | "lista">("matt");
  const [tool, setTool] = useState<Tool>("langd");
  const [draft, setDraft] = useState<{ points: number[][]; meters: number } | null>(null);
  const [list, setList] = useState<any>(null);
  const [all, setAll] = useState<any>(null);
  const [presets, setPresets] = useState<any[]>([]);
  const [layer, setLayer] = useState("Mängdning");
  const [designation, setDesignation] = useState("");
  const [subject, setSubject] = useState("");
  const [text, setText] = useState("");
  const [props, setProps] = useState<{ multiplikator?: number; tillagg_m?: number; djup_m?: number }>({});
  const [calibrating, setCalibrating] = useState(false);
  const [calLength, setCalLength] = useState("");
  const [cutting, setCutting] = useState(false);            // ritar ett avdrag i den markerade ytan
  const [selected, setSelected] = useState<string | null>(null);
  const [snaps, setSnaps] = useState<SnapSettings>({ ...defaultSnaps, grid: 0 });
  const [ortho, setOrtho] = useState(0);
  const [snapped, setSnapped] = useState<Snap | null>(null);
  const [ink, setInk] = useState<InkIndex | null>(null);
  const [inkState, setInkState] = useState<"" | "laser" | "klar" | "fel">("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const viewer = useRef<ViewerHandle>(null);

  useEffect(() => {
    api.drawing(drawingId).then(setDrawing).catch((e) => setErr(e.message));
    api.fetchBlob(api.fileUrl(drawingId)).then((b) => b.arrayBuffer()).then(setData).catch((e) => setErr(e.message));
    api.toolPresets().then((d) => setPresets(d.rows)).catch(() => { /* verktygslådan är en hjälp */ });
  }, [drawingId]);

  const load = useCallback(() => {
    api.markups(drawingId, page).then(setList).catch((e) => setErr(e.message));
    api.allMarkups(drawingId).then(setAll).catch(() => { /* listan är en vy, inte en förutsättning */ });
  }, [drawingId, page]);
  useEffect(() => { load(); setDraft(null); setCutting(false); }, [load]);

  /* Ritningens eget bläck, läst en gång per sida.
   *
   * Det är det fångsten siktar på. Läsningen är tung på ett stort blad, så den görs vid sidan av och sidan
   * fungerar under tiden - utan fångst till dess, precis som förut. */
  useEffect(() => {
    if (!data) return;
    let dead = false;
    setInk(null); setInkState("laser");
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        const doc = await pdfjs.getDocument({ data: data.slice(0) }).promise;
        const pg = await doc.getPage(page + 1);
        const segs = await pageInk(pg);
        if (dead) return;
        setInk(new InkIndex(segs));
        setInkState("klar");
      } catch {
        if (!dead) setInkState("fel");
      }
    })();
    return () => { dead = true; };
  }, [data, page]);

  const mpp = list?.meters_per_pdf_point ?? null;
  const kind = TOOLS.find((t) => t.id === tool)?.kind ?? "langd";
  const rows: MarkupRow[] = list?.rows ?? [];
  const allRows: MarkupRow[] = all?.rows ?? [];
  const sel = rows.find((r) => r.id === selected) ?? allRows.find((r) => r.id === selected) ?? null;

  const save = async () => {
    if (!tool || !draft) return;
    setBusy(true); setErr("");
    try {
      await api.addMarkup(drawingId, {
        page, tool, layer: layer.trim() || "Mängdning", designation: designation.trim() || null,
        subject: subject.trim() || "", points: draft.points, text: tool === "text" ? text : "",
        props: Object.fromEntries(Object.entries(props).filter(([, v]) => v != null && !Number.isNaN(v))),
      });
      setDraft(null); setText("");
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const calibrate = async () => {
    if (!draft || draft.points.length < 2) return;
    const len = Number(calLength.replace(",", "."));
    if (!len || len <= 0) { setErr("Skriv hur lång sträckan är i meter"); return; }
    setBusy(true); setErr("");
    try {
      const pts = [draft.points[0], draft.points[draft.points.length - 1]];
      await api.setCalibration(drawingId, { page, points: pts, length_m: len, note: "" });
      setCalibrating(false); setDraft(null); setCalLength("");
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  /* Avdraget: ett hål i en yta som redan är sparad.
   *
   * Ett schakt, en pelare, ett trapphus. Hålet går till samma rad som ytan - det är samma yta, med mindre
   * kvadratmeter - och servern räknar om måttet med hålet i sig. */
  const saveCut = async () => {
    if (!sel || !draft || draft.points.length < 3) return;
    setBusy(true); setErr("");
    try {
      const rings = [...((sel as any).props?.avdrag ?? []), draft.points];
      await api.updateMarkup(drawingId, sel.id, {
        page: sel.page, tool: sel.tool, layer: sel.layer, designation: sel.designation ?? null,
        subject: sel.subject ?? "", points: sel.points, text: sel.text ?? "",
        props: { ...((sel as any).props ?? {}), avdrag: rings },
      });
      setDraft(null); setCutting(false);
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const dropCuts = async () => {
    if (!sel) return;
    setBusy(true);
    try {
      const p = { ...((sel as any).props ?? {}) };
      delete p.avdrag;
      await api.updateMarkup(drawingId, sel.id, {
        page: sel.page, tool: sel.tool, layer: sel.layer, designation: sel.designation ?? null,
        subject: sel.subject ?? "", points: sel.points, text: sel.text ?? "", props: p,
      });
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  /** Rita om en sparad markering: samma rad, ny form, måttet räknat på nytt av servern. */
  const redraw = async () => {
    if (!sel || !draft || draft.points.length < 1) return;
    setBusy(true); setErr("");
    try {
      await api.updateMarkup(drawingId, sel.id, {
        page, tool: sel.tool, layer: sel.layer, designation: sel.designation ?? null,
        subject: sel.subject ?? "", points: draft.points, text: sel.text ?? "",
        props: (sel as any).props ?? {},
      });
      setDraft(null);
      load();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const patch = async (mid: string, change: any) => {
    setBusy(true);
    try { await api.patchMarkup(drawingId, mid, change); load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const patchMany = async (ids: string[], change: any) => {
    setBusy(true);
    try { await api.patchMarkups(drawingId, ids, change); load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const remove = async (mid: string) => {
    try { await api.deleteMarkup(drawingId, mid); if (selected === mid) setSelected(null); load(); }
    catch (e: any) { setErr(e.message); }
  };

  const applyPreset = (p: any) => {
    setTool(p.tool); setLayer(p.layer); setDesignation(p.designation ?? ""); setProps(p.props ?? {});
  };
  const savePreset = async () => {
    const name = (designation || subject || layer || tool || "Verktyg").toString();
    try {
      await api.addToolPreset({ name, tool, layer, designation: designation || null, props });
      setPresets((await api.toolPresets()).rows);
    } catch (e: any) { setErr(e.message); }
  };

  const byLayer = useMemo(() => {
    const g: Record<string, MarkupRow[]> = {};
    rows.forEach((r) => { (g[r.layer] ||= []).push(r); });
    return Object.entries(g);
  }, [rows]);

  const preview = draft && (
    calibrating ? `${Math.round(Math.hypot(draft.points[draft.points.length - 1][0] - draft.points[0][0],
      draft.points[draft.points.length - 1][1] - draft.points[0][1]))} punkter`
      : cutting ? (draft.points.length >= 3 ? "avdrag – räknas när det sparas" : "minst tre punkter")
      : kind === "antal" ? `${draft.points.length} st`
      : kind === "yta" ? (draft.points.length >= 3 ? "yta – räknas när den sparas" : "minst tre punkter")
      : mpp ? `${n2(draft.meters)} m` : `${draft.points.length} punkter · ingen skala`);

  const drawing_on = calibrating || cutting || !!tool;

  return (
    <main className="takeoff">
      <p className="crumb">
        <Link to="/mangda">{tr("Mängda")}</Link>
        {drawing && <> · <Link to={`/drawings/${drawingId}`}>{drawing.filename.replace(/\.pdf$/i, "")}</Link></>}
      </p>
      <div className="head">
        <div>
          <h1>{tr("Mängda")}</h1>
          <p className="lead">
            Mät, räkna, dra av och märk upp för hand direkt på bladet. Måtten räknas på servern ur punkterna och
            bladets skala. {list?.scale_source === "UPPMÄTT" ? "Skalan är uppmätt av dig."
              : list?.scale_source === "LÄSNINGEN" ? "Skalan kommer ur läsningen av bladet."
              : "Bladet har ingen skala ännu – mät upp den, så blir punkterna meter."}
          </p>
        </div>
        <div className="row">
          <button className={calibrating ? "" : "secondary"}
                  onClick={() => { setCalibrating(!calibrating); setCutting(false); setDraft(null); }}>
            {calibrating ? "Avbryt kalibrering" : "Kalibrera skala"}
          </button>
          <button className="secondary" onClick={async () => {
            const b = await api.fetchBlob(api.markupsCsvUrl(drawingId, page, tab === "lista"));
            const u = URL.createObjectURL(b); const a = document.createElement("a");
            a.href = u; a.download = "markeringar.csv"; a.click(); URL.revokeObjectURL(u);
          }}>{tr("Lista som CSV")}</button>
        </div>
      </div>
      <div className="rule" style={{ marginBottom: 18 }} />
      {err && <p className="error">{err}</p>}

      {/* Markeringslistan är ett arbetsbord, inte en fotnot: den lägger sig under bladet i hela bredden, så
          att kolumnerna får plats och måtten går att läsa av. Mängdningen har bladet stort och verktygen vid
          sidan, för där är handen på ritningen. */}
      <div className={`tk-grid${tab === "lista" ? " tk-listan" : ""}`}>
        <div className="tk-sheet">
          <div className="toolbar">
            <button className="secondary small" onClick={() => viewer.current?.zoomOut()}>−</button>
            <button className="secondary small" onClick={() => viewer.current?.zoomIn()}>+</button>
            <button className="secondary small" onClick={() => viewer.current?.fitPage()}>Sida</button>
            <button className="secondary small" onClick={() => viewer.current?.fitWidth()}>Bredd</button>
            <button className="secondary small" onClick={() => viewer.current?.fullscreen()}>{tr("Helskärm")}</button>
            {nPages > 1 && (
              <select value={page} onChange={(e) => setPage(Number(e.target.value))}>
                {Array.from({ length: nPages }, (_, i) => <option key={i} value={i}>Sida {i + 1}</option>)}
              </select>
            )}
            <span className="tk-sep" />
            {/* Fångst mot ritningens eget bläck: en sträcka som går bredvid röret mäter inte röret. */}
            <button className={snaps.on ? "small" : "secondary small"} disabled={inkState !== "klar"}
                    title={inkState === "klar" ? "Fånga ritningens egna linjer, ändpunkter och skärningar"
                      : inkState === "laser" ? "Läser bladets streck…" : "Bladets streck gick inte att läsa"}
                    onClick={() => setSnaps({ ...snaps, on: !snaps.on })}>
              Fångst{inkState === "laser" ? " …" : ""}
            </button>
            <button className={ortho === 90 ? "small" : "secondary small"} title={tr("Lås till vågrätt och lodrätt")}
                    onClick={() => setOrtho(ortho === 90 ? 0 : 90)}>Ortho</button>
            <button className={ortho === 45 ? "small" : "secondary small"} title={tr("Lås till 45 grader")}
                    onClick={() => setOrtho(ortho === 45 ? 0 : 45)}>45°</button>
            <span className="spacer" />
            <span className="muted small">
              {snapped ? SNAP_LABEL[snapped.kind] : list ? `${rows.length} markeringar` : "…"}
            </span>
          </div>
          <PdfViewer
            ref={viewer} data={data} page={page} pipes={[]} ambiguous={[]} unowned={[]} claimed={[]}
            designations={[]} leaders={[]} anchors={[]} declined={[]} selectedIdentity={null} selectedPipe={null}
            layers={{ pipes: false, ambiguous: false, unowned: false, claimed: false, designations: false,
                      leaders: false, hatched: false, declined: false } as any}
            onPipeClick={() => { /* ingen läsning här */ }} onPageCount={setNPages}
            editKind={(drawing_on ? "draw" : null) as any}
            meterPerPt={mpp}
            maxPoints={calibrating || cutting ? undefined : TOOLS.find((t) => t.id === tool)?.punkter}
            onDrawn={(d: any) => setDraft({ points: d.points, meters: d.meters })}
            markups={allRows.filter((r) => r.page === page) as any}
            selectedMarkup={selected}
            onMarkupClick={(mid) => setSelected(mid === selected ? null : mid)}
            pageInk={ink} snap={snaps} ortho={ortho}
            onSnapped={setSnapped}
          />
        </div>

        <aside className="tk-side">
          <div className="tk-tabs">
            <button className={tab === "matt" ? "small" : "secondary small"} onClick={() => setTab("matt")}>{tr("Mängda")}</button>
            <button className={tab === "lista" ? "small" : "secondary small"} onClick={() => setTab("lista")}>
              Markeringar{all?.rows?.length ? ` (${all.rows.length})` : ""}
            </button>
          </div>

          {tab === "matt" && (
            <>
              <section className="card">
                <h3 style={{ marginTop: 0 }}>{calibrating ? "Kalibrera skalan" : cutting ? "Avdrag" : "Mät upp"}</h3>
                {calibrating ? (
                  <>
                    <p className="muted small">
                      Dra en linje över något vars längd du vet – en dörr, ett modulmått, skalstocken – och skriv
                      vad den är i meter. Alla mått på sidan räknas om.
                    </p>
                    <label className="adm-field"><span>{tr("Sträckans längd i meter")}</span>
                      <input value={calLength} onChange={(e) => setCalLength(e.target.value)} placeholder={tr("t.ex. 1,0")} /></label>
                    <div className="row" style={{ marginTop: 10 }}>
                      <button disabled={!draft || busy} onClick={calibrate}>{tr("Spara skalan")}</button>
                      {list?.calibration && (
                        <button className="ghost small" disabled={busy}
                          onClick={async () => { await api.clearCalibration(drawingId, page); load(); }}>
                          Ta bort uppmätt skala
                        </button>
                      )}
                    </div>
                  </>
                ) : cutting ? (
                  <>
                    <p className="muted small">
                      Rita hålet inne i den markerade ytan – ett schakt, en pelare, ett trapphus. Ytan behåller sin
                      rad; kvadratmetrarna räknas om utan hålet.
                    </p>
                    <div className="row">
                      <button disabled={!draft || busy} onClick={saveCut}>{tr("Spara avdraget")}</button>
                      <button className="ghost small" onClick={() => { setCutting(false); setDraft(null); }}>Avbryt</button>
                      {preview && <span className="muted small">{preview}</span>}
                    </div>
                  </>
                ) : (
                  <>
                    <div className="tk-step"><b>1</b> {tr("Vad du mäter")}</div>
                    <div className="tk-fields">
                      <label className="adm-field"><span>Lager</span>
                        <input value={layer} onChange={(e) => setLayer(e.target.value)} list="tk-layers" />
                        <datalist id="tk-layers">{(list?.layers ?? []).map((l: string) => <option key={l} value={l} />)}</datalist>
                      </label>
                      <label className="adm-field"><span>Beteckning</span>
                        <input value={designation} onChange={(e) => setDesignation(e.target.value)} placeholder={tr("t.ex. VS21-S13-22")} /></label>
                      <label className="adm-field"><span>{tr("Ämne")}</span>
                        <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={tr("vad raden gäller")} /></label>
                      <label className="adm-field"><span>Multiplikator</span>
                        <input type="number" step="0.1" value={props.multiplikator ?? ""} placeholder="1"
                          onChange={(e) => setProps({ ...props, multiplikator: e.target.value === "" ? undefined : Number(e.target.value) })} /></label>
                      {kind === "langd" && (
                        <label className="adm-field"><span>{tr("Tillägg m")}</span>
                          <input type="number" step="0.1" value={props.tillagg_m ?? ""} placeholder="0"
                            onChange={(e) => setProps({ ...props, tillagg_m: e.target.value === "" ? undefined : Number(e.target.value) })} /></label>
                      )}
                      {kind === "yta" && (
                        <label className="adm-field"><span>{tr("Djup m")}</span>
                          <input type="number" step="0.1" value={props.djup_m ?? ""} placeholder="0"
                            onChange={(e) => setProps({ ...props, djup_m: e.target.value === "" ? undefined : Number(e.target.value) })} /></label>
                      )}
                      {tool === "text" && (
                        <label className="adm-field"><span>Text</span>
                          <input value={text} onChange={(e) => setText(e.target.value)} /></label>
                      )}
                    </div>
                    <div className="tk-step"><b>2</b> Verktyg</div>
                    <div className="tk-tools">
                      {/* Pekaren är ett verktyg som de andra: med den pekar man ut en markering som redan
                          finns - för att ändra den, dra av ur den eller ta bort den. Utan den kan ett armerat
                          ritverktyg aldrig släppa taget om bladet, och en sparad yta går inte att välja. */}
                      <button className={tool === null ? "" : "secondary"}
                              onClick={() => { setTool(null); setDraft(null); }}>{tr("Välj")}</button>
                      {TOOLS.map((t) => (
                        <button key={t.id} className={tool === t.id ? "" : "secondary"}
                                onClick={() => { setTool(t.id); setDraft(null); }}>{t.label}</button>
                      ))}
                    </div>
                    <p className="muted small">
                      {tool === null ? "Klicka på en markering på bladet för att arbeta med den."
                        : TOOLS.find((t) => t.id === tool)?.hint}
                    </p>
                    <div className="row" style={{ marginTop: 10 }}>
                      <button disabled={!draft || busy} onClick={save}>{busy ? "Sparar…" : "Spara markering"}</button>
                      {draft && <button className="ghost small" onClick={() => setDraft(null)}>Rensa</button>}
                      <button className="ghost small" onClick={savePreset}>{tr("Spara som verktyg")}</button>
                      {preview && <span className="muted small">{preview}</span>}
                    </div>
                    {presets.length > 0 && (
                      <div className="tk-presets">
                        {presets.map((p) => (
                          <span key={p.id} className="tk-preset">
                            <button className="ghost small" onClick={() => applyPreset(p)}>{p.name}</button>
                            <button className="ghost small x" title={tr("Ta bort")}
                              onClick={async () => { await api.deleteToolPreset(p.id); setPresets((await api.toolPresets()).rows); }}>✕</button>
                          </span>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </section>

              {sel && (
                <section className="card">
                  <h3 style={{ marginTop: 0 }}>Markeringen</h3>
                  <p className="muted small" style={{ marginTop: 0 }}>
                    {TOOL_LABEL[sel.tool] ?? sel.tool} · sida {sel.page + 1} · {measureText(sel.measure) || "utan mått"}
                    {((sel as any).props?.avdrag?.length ?? 0) > 0 && ` · ${(sel as any).props.avdrag.length} avdrag`}
                  </p>
                  <div className="tk-fields">
                    <label className="adm-field"><span>Lager</span>
                      <input defaultValue={sel.layer} onBlur={(e) => e.target.value !== sel.layer && patch(sel.id, { layer: e.target.value })} /></label>
                    <label className="adm-field"><span>Beteckning</span>
                      <input defaultValue={sel.designation ?? ""} onBlur={(e) => patch(sel.id, { designation: e.target.value })} /></label>
                    <label className="adm-field"><span>{tr("Ämne")}</span>
                      <input defaultValue={sel.subject ?? ""} onBlur={(e) => patch(sel.id, { subject: e.target.value })} /></label>
                    <label className="adm-field"><span>Status</span>
                      <select value={sel.status ?? "oppen"} onChange={(e) => patch(sel.id, { status: e.target.value })}>
                        {STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                      </select></label>
                  </div>
                  <div className="row" style={{ marginTop: 10, gap: 6 }}>
                    {AREA_TOOLS.includes(sel.tool) && (
                      <button className="secondary small" onClick={() => { setCutting(true); setCalibrating(false); setDraft(null); }}>
                        Rita avdrag
                      </button>
                    )}
                    {((sel as any).props?.avdrag?.length ?? 0) > 0 && (
                      <button className="ghost small" disabled={busy} onClick={dropCuts}>{tr("Ta bort avdragen")}</button>
                    )}
                    <button className="secondary small" disabled={!draft || busy} onClick={redraw}
                            title={tr("Rita formen på nytt på bladet och tryck här - raden behåller sitt namn och sin status")}>
                      Ersätt formen
                    </button>
                    <button className="ghost small" onClick={() => remove(sel.id)}>{tr("Ta bort")}</button>
                    <button className="ghost small" onClick={() => setSelected(null)}>{tr("Stäng")}</button>
                  </div>
                </section>
              )}

              <section className="card">
                <h3 style={{ marginTop: 0 }}>Summor</h3>
                <div className="adm-stats">
                  <div className="adm-stat"><div className="k">{tr("Längd")}</div><div className="v">{n2(list?.totals?.m)}</div><div className="s">meter</div></div>
                  <div className="adm-stat"><div className="k">Yta</div><div className="v">{n2(list?.totals?.kvm)}</div><div className="s">m²</div></div>
                  <div className="adm-stat"><div className="k">Volym</div><div className="v">{n2(list?.totals?.m3, 3)}</div><div className="s">m³</div></div>
                  <div className="adm-stat"><div className="k">Antal</div><div className="v">{list?.totals?.antal ?? 0}</div><div className="s">stycken</div></div>
                </div>
                {list?.unscaled > 0 && (
                  <p className="muted small" style={{ marginBottom: 0 }}>
                    {list.unscaled} markeringar saknar skala och räknas inte in i metrarna. Kalibrera bladet.
                  </p>
                )}
              </section>

              <section className="card">
                <h3 style={{ marginTop: 0 }}>{tr("Den här sidan")}</h3>
                {!rows.length && <p className="muted" style={{ marginBottom: 0 }}>{tr("Inga ännu. Välj ett verktyg och rita på bladet.")}</p>}
                {byLayer.map(([lay, items]) => (
                  <div key={lay} className="tk-layer">
                    <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
                      <b>{lay}</b>
                      <span className="muted small">
                        {n2(list.by_layer?.[lay]?.m)} m · {n2(list.by_layer?.[lay]?.kvm)} m² · {list.by_layer?.[lay]?.antal ?? 0} st
                      </span>
                    </div>
                    <table className="qty">
                      <tbody>
                        {items.map((r) => (
                          <tr key={r.id} className={`selectable${selected === r.id ? " selected" : ""}`}
                              onClick={() => setSelected(selected === r.id ? null : r.id)}>
                            <td className="lf-mono">{r.seq ? `${r.seq}. ` : ""}{r.designation || r.subject || TOOL_LABEL[r.tool] || r.tool}
                              {r.text && <div className="muted small">{r.text}</div>}</td>
                            <td className="num">{measureText(r.measure)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </section>
            </>
          )}

          {tab === "lista" && (
            <section className="card tk-listcard">
              <h3 style={{ marginTop: 0 }}>{tr("Markeringar i hela handlingen")}</h3>
              <MarkupsList rows={allRows} selected={selected} busy={busy}
                onSelect={(mid) => {
                  setSelected(mid);
                  const r = allRows.find((x) => x.id === mid);
                  if (r && r.page !== page) setPage(r.page);
                }}
                onPatch={patch} onPatchMany={patchMany} onDelete={remove} />
            </section>
          )}
        </aside>
      </div>
    </main>
  );
}
