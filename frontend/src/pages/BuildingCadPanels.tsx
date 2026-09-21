import { useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { api } from "../api";
import { type CadDocument, type Entity, type Level, type Sheet, type Viewport, type Pt, uid } from "../cad/building";
import { Tx } from "../cad/commands";

/* Panelerna runt ritbordet som inte är själva ritandet: filer in och ut, ritningsblad, och agenten.
 *
 * Alla tre talar med dokumentet på ett enda sätt - genom en transaktion (apply) - så att det de gör går att
 * ångra som allt annat. Ingen av dem skriver i bladet på servern själv. */

export type Apply = (tx: Tx) => void;

const PAPER: Record<string, [number, number]> = { A0: [1189, 841], A1: [841, 594], A2: [594, 420], A3: [420, 297], A4: [297, 210] };

/** Öppna eller ladda ner en fil som kräver inloggning: hämtas som blob, visas sedan. */
export async function openAuthed(url: string, download?: string) {
  const b: Blob = await (api as any).fetchBlob(url);
  const u = URL.createObjectURL(b);
  if (download) { const a = document.createElement("a"); a.href = u; a.download = download; a.click(); }
  else window.open(u, "_blank");
}

// ---------------------------------------------------------------- filer

export function FileMenu({ sheetId, name, doc, viewId, scaleRatio, level, centre, apply, onError, onUnderlayAdded }: {
  sheetId: string; name: string; doc: CadDocument; viewId: string; scaleRatio: number; level: string; centre: () => Pt; apply: Apply; onError: (m: string) => void; onUnderlayAdded: (id: string, calibrate: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  // ett klick utanför stänger menyn
  useEffect(() => { if (!open) return; const on = (ev: MouseEvent) => { if (box.current && !box.current.contains(ev.target as Node)) setOpen(false); }; document.addEventListener("mousedown", on); return () => document.removeEventListener("mousedown", on); }, [open]);
  const [busy, setBusy] = useState("");
  const [report, setReport] = useState<string>("");
  const importRef = useRef<HTMLInputElement>(null);
  const underlayRef = useRef<HTMLInputElement>(null);
  const [drawings, setDrawings] = useState<any[] | null>(null);
  const [pick, setPick] = useState<{ drawing_id: string; page: number } | null>(null);

  const exportAs = async (fmt: "ifc" | "glb" | "svg" | "dxf" | "pdf") => {
    setBusy(fmt);
    try { await openAuthed(api.cadExportUrl(sheetId, fmt, fmt === "ifc" || fmt === "glb" ? {} : { view: viewId }), fmt === "pdf" ? undefined : `${name}.${fmt}`); }
    catch (e: any) { onError(e.message); } finally { setBusy(""); }
  };

  const importFile = async (f: File) => {
    setBusy("import"); setReport("");
    try {
      const r = await api.cadImport(sheetId, f, level, scaleRatio);
      if (r.kind === "mesh") {
        const e: Entity = { id: uid(), type: "mesh", layer: doc.layers[0].id, discipline: "ALLMAN", level, phase: "NEW", provenance: "IMPORTED_DXF", version: 1,
          p: [[...centre(), 0]], asset: r.asset, format: r.format, scale: 1000, bounds: r.bounds?.min ? { min: r.bounds.min, max: r.bounds.max } : null, filename: r.filename } as Entity;
        apply(new Tx(`Referens ${r.filename}`).add("entities", e));
        setReport(`${r.filename}: referensnät med ${r.bounds?.vertices ?? 0} punkter. Skalan är satt till 1000 mm per enhet (meter) - rätta den i egenskaperna om filen är i något annat.`);
        return;
      }
      const tx = new Tx(`Import ${r.filename}`);
      const levelMap = new Map<string, string>();
      for (const lv of (r.levels ?? []) as Level[]) {
        const same = doc.levels.find((x) => Math.abs(x.elevation_mm - lv.elevation_mm) < 1);
        if (same) levelMap.set(lv.id, same.id);
        else { tx.add("levels", lv); tx.add("views", { id: uid(), kind: "plan", name: lv.name, level: lv.id, scale_ratio: 100 }); levelMap.set(lv.id, lv.id); }
      }
      const haveLayer = new Set(doc.layers.map((l) => l.id));
      for (const ln of (r.layers ?? []) as string[]) {
        const id = `l_imp_${ln.replace(/[^A-Za-z0-9_-]/g, "_")}`;
        if (!haveLayer.has(id)) { tx.add("layers", { id, name: ln, color: "#5f6b7a", visible: true, locked: false, width: 0.25, discipline: "ALLMAN" }); haveLayer.add(id); }
      }
      const idMap = new Map<string, string>();
      for (const e of r.entities as any[]) idMap.set(e.id, e.id);
      for (const e of r.entities as any[]) {
        const c: any = { ...e, layer: `l_imp_${String(e.layer).replace(/[^A-Za-z0-9_-]/g, "_")}` };
        if (c.level && levelMap.has(c.level)) c.level = levelMap.get(c.level);
        if (c.base_level && levelMap.has(c.base_level)) c.base_level = levelMap.get(c.base_level);
        if (c.top_level && levelMap.has(c.top_level)) c.top_level = levelMap.get(c.top_level);
        if (!c.level && !c.base_level) c.level = level;
        if (c.type === "wall" && !c.base_level) c.base_level = level;
        tx.add("entities", c as Entity);
      }
      apply(tx);
      const skipped = r.skipped && Object.keys(r.skipped).length ? ` Hoppade över: ${Object.entries(r.skipped).map(([k, v]) => `${k} ×${v}`).join(", ")}.` : "";
      setReport(`${r.filename}: ${r.count} objekt på ${r.layers?.length ?? 0} lager.${(r.assumptions ?? []).length ? " " + r.assumptions.join(" ") + "." : ""}${skipped}`);
    } catch (e: any) { onError(e.message); } finally { setBusy(""); }
  };

  const addUnderlay = async (src: { file?: File; drawing_id?: string; page?: number }) => {
    setBusy("underlag"); setReport("");
    try {
      const r = await api.cadUnderlay(sheetId, src);
      const c = centre();
      const k = r.mm_per_px ?? 1;
      const e: Entity = { id: uid(), type: "underlay", layer: doc.layers[0].id, discipline: "ALLMAN", level, phase: "EXISTING", provenance: "DETECTED_FROM_PDF", version: 1,
        p: [[Math.round(c[0] - (r.px[0] * k) / 2), Math.round(c[1] - (r.px[1] * k) / 2)]], asset: r.asset, px: r.px, mm_per_px: r.mm_per_px, opacity: 0.6, scale_state: r.scale_state, source: r.source } as Entity;
      apply(new Tx("Underlag").add("entities", e));
      setReport(r.scale_state === "VERIFIED" ? "Underlaget har den lästa handlingens skala (verifierad)." : r.scale_state === "CALIBRATED" ? "Underlaget har den uppmätta skalan från handlingen." : "Underlaget saknar skala: klicka två punkter med känt avstånd och skriv avståndet.");
      onUnderlayAdded(e.id, r.scale_state === "UNCALIBRATED");
    } catch (e: any) { onError(e.message); } finally { setBusy(""); }
  };

  const loadDrawings = async () => {
    if (drawings) return;
    try {
      const sheets = await api.cadSheets();
      const me = (sheets as any[]).find((s) => s.id === sheetId);
      const p = me ? await api.project(me.project_id) : null;
      setDrawings(p?.drawings ?? []);
    } catch (e: any) { onError(e.message); setDrawings([]); }
  };

  return (
    <span className="bcad-file" ref={box}>
      <button className="ghost small" onClick={() => { setOpen((o) => !o); if (!open) loadDrawings(); }}>{tr("Fil ▾")}</button>
      {open && (
        <div className="bcad-menu">
          <div className="bcad-h">Exportera</div>
          <div className="bcad-menu-row">{(["ifc", "glb", "pdf", "svg", "dxf"] as const).map((f) => <button key={f} className="secondary small" disabled={!!busy} onClick={() => exportAs(f)}>{busy === f ? "…" : f.toUpperCase()}</button>)}</div>
          <p className="muted small">IFC och GLB är hela byggnaden; PDF, SVG och DXF är den aktiva vyn.</p>
          <div className="bcad-h">Importera</div>
          <div className="bcad-menu-row">
            <button className="secondary small" disabled={!!busy} onClick={() => importRef.current?.click()}>{busy === "import" ? "Läser…" : "DXF / SVG / IFC / GLB / OBJ / STL"}</button>
            <input ref={importRef} type="file" accept=".dxf,.svg,.ifc,.glb,.gltf,.obj,.stl" hidden onChange={(ev) => { const f = ev.target.files?.[0]; if (f) importFile(f); ev.target.value = ""; }} />
          </div>
          <p className="muted small">{tr("Det som går att förstå blir byggobjekt, resten streck. DWG stöds inte - spara som DXF eller IFC.")}</p>
          <div className="bcad-h">Underlag</div>
          <div className="bcad-menu-row">
            <button className="secondary small" disabled={!!busy} onClick={() => underlayRef.current?.click()}>{busy === "underlag" ? "Laddar…" : "PDF eller bild"}</button>
            <input ref={underlayRef} type="file" accept=".pdf,.png,.jpg,.jpeg" hidden onChange={(ev) => { const f = ev.target.files?.[0]; if (f) addUnderlay({ file: f, page: 0 }); ev.target.value = ""; }} />
          </div>
          {drawings && drawings.length > 0 && (
            <div className="bcad-menu-row">
              <select value={pick?.drawing_id ?? ""} onChange={(ev) => setPick(ev.target.value ? { drawing_id: ev.target.value, page: 0 } : null)}>
                <option value="">{tr("Ur en läst handling…")}</option>
                {drawings.map((d) => <option key={d.id} value={d.id}>{String(d.filename).replace(/\.pdf$/i, "")}{d.latest_job?.status === "COMPLETED" ? " (läst)" : ""}</option>)}
              </select>
              {pick && <input className="bcad-num" type="number" min={1} value={pick.page + 1} onChange={(ev) => setPick({ ...pick, page: Math.max(0, Number(ev.target.value) - 1) })} title="sida" />}
              {pick && <button className="secondary small" disabled={!!busy} onClick={() => addUnderlay(pick)}>{tr("Lägg in")}</button>}
            </div>
          )}
          <p className="muted small">Ett underlag ur en läst handling får läsningens skala; en fil utan skala kalibreras med två punkter.</p>
          {report && <p className="small">{report}</p>}
        </div>
      )}
    </span>
  );
}

// ---------------------------------------------------------------- ritningsblad

export function SheetsPanel({ sheetId, doc, apply, onError }: { sheetId: string; doc: CadDocument; apply: Apply; onError: (m: string) => void }) {
  const [cur, setCur] = useState<string>(doc.sheets[0]?.id ?? "");
  const sheet = doc.sheets.find((s) => s.id === cur) ?? doc.sheets[0];
  useEffect(() => { if (!sheet && doc.sheets[0]) setCur(doc.sheets[0].id); }, [doc.sheets, sheet]);
  const today = new Date().toISOString().slice(0, 10);

  const add = () => {
    const n = doc.sheets.length + 1;
    const s: Sheet = { id: uid(), name: `Blad ${n}`, paper: "A1", width_mm: 841, height_mm: 594,
      title: { number: `A-40-1-${String(n).padStart(2, "0")}`, name: doc.views[0]?.name ?? "Plan", project: doc.project.name, revision: "A", date: today, drawn_by: "", scale: "" },
      viewports: [] };
    apply(new Tx(`Blad ${s.name}`).add("sheets", s)); setCur(s.id);
  };
  const patch = (p: Partial<Sheet>, label = "Blad") => { if (!sheet) return; apply(new Tx(label).update("sheets", sheet, { ...sheet, ...p })); };
  const addViewport = () => {
    if (!sheet) return;
    const v = doc.views.find((x) => x.kind !== "3d"); if (!v) return;
    const vp: Viewport = { id: uid(), view: v.id, at: [20, 20], size: [Math.round(sheet.width_mm * 0.6), Math.round(sheet.height_mm * 0.7)], scale_ratio: v.scale_ratio ?? 100, title: v.name };
    patch({ viewports: [...sheet.viewports, vp] }, "Vyport");
  };
  const patchVp = (vp: Viewport, p: Partial<Viewport>) => { if (!sheet) return; patch({ viewports: sheet.viewports.map((x) => (x.id === vp.id ? { ...x, ...p } : x)) }, "Vyport"); };

  return (
    <div className="bcad-list">
      <div className="bcad-row">
        <select value={sheet?.id ?? ""} onChange={(ev) => setCur(ev.target.value)}>{doc.sheets.map((s) => <option key={s.id} value={s.id}>{s.title.number} {s.name}</option>)}</select>
        <button className="secondary small" onClick={add}>{tr("+ Blad")}</button>
      </div>
      {!sheet && <p className="muted">Inget ritningsblad än. Ett blad är ett papper med vyportar och namnruta; PDF:en ritas ur modellen.</p>}
      {sheet && (
        <>
          <div className="bcad-field"><label>Papper</label><select value={sheet.paper} onChange={(ev) => { const [w, h] = PAPER[ev.target.value] ?? PAPER.A1; patch({ paper: ev.target.value, width_mm: w, height_mm: h }, "Papper"); }}>{Object.keys(PAPER).map((p) => <option key={p} value={p}>{p} liggande</option>)}</select></div>
          <div className="bcad-field"><label>Namn</label><input value={sheet.name} onChange={(ev) => patch({ name: ev.target.value })} /></div>
          {(["number", "name", "project", "revision", "date", "drawn_by", "scale"] as const).map((k) => (
            <div key={k} className="bcad-field"><label>{{ number: "Ritningsnr", name: "Rubrik", project: "Projekt", revision: "Revision", date: "Datum", drawn_by: "Ritad av", scale: "Skala (text)" }[k]}</label>
              <input value={(sheet.title as any)[k] ?? ""} onChange={(ev) => patch({ title: { ...sheet.title, [k]: ev.target.value } }, "Namnruta")} /></div>
          ))}
          <div className="bcad-h">Vyportar <button className="ghost small" onClick={addViewport}>+</button></div>
          {sheet.viewports.map((vp) => (
            <div key={vp.id} className="bcad-rev">
              <select value={vp.view} onChange={(ev) => patchVp(vp, { view: ev.target.value, title: doc.views.find((v) => v.id === ev.target.value)?.name })}>{doc.views.filter((v) => v.kind !== "3d").map((v) => <option key={v.id} value={v.id}>{v.name} ({v.kind})</option>)}</select>
              <div className="bcad-row"><label>1:</label><input className="bcad-num" type="number" value={vp.scale_ratio} onChange={(ev) => patchVp(vp, { scale_ratio: Number(ev.target.value) || 100 })} />
                <label>vid</label><input className="bcad-num" type="number" value={vp.at[0]} onChange={(ev) => patchVp(vp, { at: [Number(ev.target.value), vp.at[1]] })} /><input className="bcad-num" type="number" value={vp.at[1]} onChange={(ev) => patchVp(vp, { at: [vp.at[0], Number(ev.target.value)] })} /></div>
              <div className="bcad-row"><label>storlek</label><input className="bcad-num" type="number" value={vp.size[0]} onChange={(ev) => patchVp(vp, { size: [Number(ev.target.value), vp.size[1]] })} /><input className="bcad-num" type="number" value={vp.size[1]} onChange={(ev) => patchVp(vp, { size: [vp.size[0], Number(ev.target.value)] })} />
                <button className="ghost small" onClick={() => patch({ viewports: sheet.viewports.filter((x) => x.id !== vp.id) }, "Ta bort vyport")}>×</button></div>
            </div>
          ))}
          <div className="bcad-row">
            <button className="secondary small" onClick={() => openAuthed(api.cadSheetPdfUrl(sheetId, sheet.id)).catch((e) => onError(e.message))}>{tr("Visa PDF")}</button>
            <span className="muted small">Spara först - PDF:en ritas ur det sparade bladet.</span>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- agenten

export type Proposal = { op: "add" | "update" | "remove"; collection: string; item?: any; before?: any; after?: any; why: string };
type Msg = { role: "user" | "agent"; text: string; tools?: any[] };

const QUICK = [
  { text: "Vad finns i modellen?", tool: "hamta_modell" },
  { text: "Mängder", tool: "mangder" },
  { text: "Vad skulle avvisas?", tool: "validera" },
  { text: "Alla väggar", tool: "lista_objekt", args: { typ: "wall" } },
];

function render(v: any, depth = 0): string {
  const pad = "  ".repeat(depth);
  if (v == null) return "";
  if (Array.isArray(v)) return v.length ? v.map((x) => (typeof x === "object" ? render(x, depth) : `${pad}${x}`)).join("\n") : `${pad}(inga)`;
  if (typeof v === "object") return Object.entries(v).filter(([k]) => k !== "objekt" || depth > 0).map(([k, x]) => (typeof x === "object" && x !== null ? `${pad}${k}:\n${render(x, depth + 1)}` : `${pad}${k}: ${x}`)).join("\n");
  return `${pad}${v}`;
}

export function AgentPanel({ sheetId, selection, proposals, setProposals, onApprove, onDirtyWarning }: {
  sheetId: string; selection: string[]; proposals: Proposal[]; setProposals: (p: Proposal[]) => void; onApprove: (p: Proposal[]) => void; onDirtyWarning: boolean;
}) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [msgs]);

  const ask = async (q: string, quick?: { tool: string; args?: any }) => {
    if (!quick && !q.trim()) return;
    setBusy(true); setErr("");
    if (!quick) setMsgs((m) => [...m, { role: "user", text: q }]);
    setText("");
    try {
      const history = msgs.map((m) => ({ role: m.role === "agent" ? "assistant" : "user", content: m.text }));
      const r = quick ? await api.cadAgentTool(sheetId, quick.tool, quick.args ?? {}) : await api.cadAgent(sheetId, { question: q, history, selection });
      const tools = r.verktyg ?? [];
      const body = r.svar || tools.map((t: any) => render(t.resultat)).join("\n\n") || "(inget svar)";
      setMsgs((m) => [...m, { role: "agent", text: body, tools }]);
      if (r.forslag?.length) setProposals([...proposals, ...r.forslag]);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div className="bcad-list bcad-agent">
      <p className="muted small">Agenten föreslår - väggar, dörrar, rum, rör - med de mått du ger. Den hittar inte på ett mått: saknas ett frågar den. Förslagen syns som spöken tills du godkänner dem.</p>
      {onDirtyWarning && <p className="muted small">Bladet har osparade ändringar; agenten ser det sparade.</p>}
      <div className="bcad-menu-row">{QUICK.map((qk) => <button key={qk.text} className="ghost small" disabled={busy} onClick={() => ask("", qk)}>{qk.text}</button>)}</div>
      {proposals.length > 0 && (
        <div className="bcad-proposal">
          <b>{proposals.length} förslag</b>
          <ul className="small">{proposals.map((p, i) => <li key={i}>{p.why}</li>)}</ul>
          <div className="bcad-menu-row">
            <button className="small" onClick={() => { onApprove(proposals); setProposals([]); }}>{tr("Godkänn alla")}</button>
            <button className="secondary small" onClick={() => setProposals([])}>Avvisa</button>
          </div>
        </div>
      )}
      <div className="bcad-msgs">
        {msgs.map((m, i) => <div key={i} className={`bcad-msg ${m.role}`}><pre>{m.text}</pre>{m.tools && m.tools.length > 0 && m.role === "agent" && <div className="muted small">verktyg: {m.tools.map((t: any) => t.namn).join(", ")}</div>}</div>)}
        {busy && <p className="muted small">{tr("Frågar…")}</p>}
        {err && <p className="error small">{err}</p>}
        <div ref={end} />
      </div>
      <div className="bcad-row">
        <input value={text} placeholder={tr("t.ex. rita en vägg från (0,0) till (0,6000), 200 tjock, på Plan 0")} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") ask(text); }} disabled={busy} style={{ flex: 1 }} />
        <button className="small" onClick={() => ask(text)} disabled={busy || !text.trim()}>{tr("Fråga")}</button>
      </div>
    </div>
  );
}

/** Förslagen som objekt att rita som spöken i planen (bara det som blir till eller ändras). */
export function ghostsOf(proposals: Proposal[]): Entity[] {
  return proposals.filter((p) => p.collection === "entities" && p.op !== "remove").map((p) => (p.op === "add" ? p.item : p.after) as Entity);
}

/** Godkända förslag som en transaktion: det som fanns rörs som det var när förslaget gjordes. */
export function txOf(doc: CadDocument, proposals: Proposal[]): Tx {
  const tx = new Tx(`Agentens förslag (${proposals.length})`);
  for (const p of proposals) {
    if (p.collection === "levels" && p.op === "add") { tx.add("levels", p.item); tx.add("views", { id: uid(), kind: "plan", name: p.item.name, level: p.item.id, scale_ratio: 100 }); continue; }
    if (p.collection !== "entities") continue;
    if (p.op === "add") tx.add("entities", { ...p.item, provenance: "AGENT_CREATED_APPROVED" });
    else if (p.op === "update") { const cur = doc.entities.find((e) => e.id === p.before?.id); if (cur) tx.update("entities", cur, { ...p.after, version: cur.version + 1 }); }
    else if (p.op === "remove") { const cur = doc.entities.find((e) => e.id === p.item?.id); if (cur) tx.remove("entities", cur); }
  }
  return tx;
}

export type { Pt };
