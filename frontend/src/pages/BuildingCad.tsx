import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import {
  type CadDocument, type Entity, type Level, type Pt, type View, type Discipline, type Wall, type TagField, DISCIPLINES, migrate, newDocument, uid, validate, levelOf, visibleIn, connections,
} from "../cad/building";
import { Tx, commit, emptyHistory, undo as undoTx, redo as redoTx, type History } from "../cad/commands";
import { type Cam, type Snap, type SnapSettings, defaultSnaps, drawPlan, hits, gripsOf, gripped, moved, snapPoint, constrain, toWorld, toScreen, bboxOf, colourOf, wallAt } from "../cad/plan";
import { TOOLS, toolsFor, build, ghostOf, needed, DEFAULTS, type ToolId, type ToolDefaults } from "../cad/tools";
import { quantities, materialQuantities, label as qLabel } from "../cad/quantities";
import { findClashes, proposeOpenings, type Clash } from "../cad/clash";
import { sectionOfDocument, elevationPlane, elevationOfDocument, type SectionShape } from "../cad/solids";
import BuildingView3D, { type ViewName } from "../components/BuildingView3D";
import { FileMenu, SheetsPanel, AgentPanel, ghostsOf, txOf, type Proposal } from "./BuildingCadPanels";

/* Bygg-CAD: ett rum där en hel byggnad ritas - från ett tomt blad till en modell med nivåer, väggar, dörrar,
 * bjälklag, tak, stomme och installationer - i 2D och 3D på en gång.
 *
 * Sidan äger ingen geometri. Den håller ett dokument (cad/building.ts), skickar varje ändring genom en
 * transaktion (cad/commands.ts) så att den går att ångra, ritar planen ur dokumentet (cad/plan.ts) och
 * modellen ur samma dokument (BuildingView3D), och sparar det med sin revision. Verktygen (cad/tools.ts) vet
 * vad ett klick blir. Egenskapspanelen byter efter vad som är valt, och en siffra som skrivs där är en
 * transaktion som alla andra. */

type Mode = "2d" | "3d" | "split";
const DISC_LABEL = Object.fromEntries(DISCIPLINES.map((d) => [d.id, d.label])) as Record<Discipline, string>;
const fmtMm = (v: number) => `${Math.round(v).toLocaleString(locale())} mm`;

/* Verktyg som ritar en sluten yta. Dubbelklick och högerklick sluter dem; en linje bara avslutas. */
const AREA_TOOLS = new Set(["bjalklag", "platta", "tak", "undertak", "rum", "skraffering", "tomtgrans"]);

/* Verktyg där nästa objekt börjar där det förra slutade. En vägg ritas nästan aldrig ensam. */

export default function BuildingCadPage() {
  const { id } = useParams();
  const sheetId = id!;
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);

  const [meta, setMeta] = useState<any>(null);
  const [doc, setDoc] = useState<CadDocument>(() => newDocument());
  const [hist, setHist] = useState<History>(() => emptyHistory());
  const [mode, setMode] = useState<Mode>("split");
  const [discipline, setDiscipline] = useState<Discipline>("ARK");
  // Panelerna går att fälla undan. En ritning som ska granskas vill ha hela rutan, och verktygslådan står i
  // vägen så snart man slutat rita. Läget ligger kvar mellan besök: den som ritar i fullskärm gör det ofta.
  const [bare, setBare] = useState(() => {
    try { return localStorage.getItem("bcad_bare") === "1"; } catch { return false; }
  });
  useEffect(() => { try { localStorage.setItem("bcad_bare", bare ? "1" : "0"); } catch { /* privat läge */ } }, [bare]);
  const [tool, setTool] = useState<ToolId>("valj");
  const [draft, setDraft] = useState<Pt[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const [hover, setHover] = useState<Snap | null>(null);
  const [cam, setCam] = useState<Cam>({ s: 0.05, ox: 60, oy: 60 });
  const [snaps, setSnaps] = useState<SnapSettings>(defaultSnaps);
  const [ortho, setOrtho] = useState(0);
  const [typed, setTyped] = useState("");
  const [typedAngle, setTypedAngle] = useState<string | null>(null);
  const [defaults, setDefaults] = useState<ToolDefaults>(DEFAULTS);
  const [panel, setPanel] = useState<"egenskaper" | "mangder" | "kollisioner" | "revisioner" | "snitt" | "agent" | "blad">("egenskaper");
  const [saving, setSaving] = useState<"" | "sparar" | "sparat" | "krock">("");
  const [err, setErr] = useState("");
  const [clashes, setClashes] = useState<Clash[] | null>(null);
  const [revisions, setRevisions] = useState<any[]>([]);
  const [view3d, setView3d] = useState<ViewName | null>("iso");
  const [ortho3d, setOrtho3d] = useState(false);
  const [wire, setWire] = useState(false);
  const [sectionBoxOn, setSectionBoxOn] = useState(false);
  const [transp, setTransp] = useState<Partial<Record<Discipline, number>>>({});
  const [sectionLine, setSectionLine] = useState<[Pt, Pt] | null>(null);
  const [elevDir, setElevDir] = useState<"N" | "S" | "E" | "W">("S");
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [calib, setCalib] = useState<{ id: string; pts: Pt[] } | null>(null);
  const images = useRef(new Map<string, HTMLImageElement | null>());
  const [imgTick, setImgTick] = useState(0);
  const drag = useRef<{ kind: "pan" | "move" | "grip" | "box"; from: Pt; screen: [number, number]; ids?: string[]; grip?: { id: string; i: number }; box?: [Pt, Pt]; before?: Entity[] } | null>(null);
  const dirty = useRef(false);
  const savedRevision = useRef(0);

  const level = doc.settings.active_level;
  const view: View = useMemo(() => doc.views.find((v) => v.id === doc.settings.active_view && v.kind === "plan") ?? { id: "v_tmp", kind: "plan", name: "Plan", level }, [doc, level]);
  const tools = useMemo(() => toolsFor(discipline), [discipline]);
  const layerFor = useMemo(() => doc.layers.find((l) => l.discipline === discipline)?.id ?? doc.layers[0]?.id ?? "l_ark", [doc.layers, discipline]);
  const ctx = useMemo(() => ({ doc, view, discipline, layer: layerFor, level, defaults }), [doc, view, discipline, layerFor, level, defaults]);
  const selected = useMemo(() => new Set(sel), [sel]);
  const tol = 10 / cam.s;

  // ---------------------------------------------------------------- hämta och spara

  useEffect(() => {
    api.cadSheet(sheetId).then((s: any) => {
      const d = migrate(s.content, { name: s.name, scale_ratio: s.scale_ratio });
      setMeta(s); setDoc(d); savedRevision.current = d.revision || 0;
      setHist(emptyHistory());
    }).catch((e) => setErr(e.message));
  }, [sheetId]);

  const apply = useCallback((tx: Tx) => {
    if (tx.empty) return;
    // associativa mått: ett mått som hänger på ett objekt följer med när objektet rör sig, i samma transaktion
    const preview = commit(doc, emptyHistory(), tx.build()).doc;
    for (const d of preview.entities) {
      if (d.type !== "dim" || !d.refs?.length) continue;
      const pts = d.p.map((q, i) => { const r = d.refs![i]; if (!r) return q; const t = preview.entities.find((e) => e.id === r.id); const gp = t ? gripsOf(t)[r.grip ?? 0] : undefined; return gp ?? q; });
      if (pts.some((q, i) => q[0] !== d.p[i][0] || q[1] !== d.p[i][1])) { const cur = doc.entities.find((e) => e.id === d.id); if (cur) tx.update("entities", cur, { ...d, p: pts }); }
    }
    const r = commit(doc, hist, tx.build());
    setDoc(r.doc); setHist(r.hist); dirty.current = true;
  }, [doc, hist]);

  // underlagens bilder: hämtas en gång per fil, med inloggningen gjord
  useEffect(() => {
    for (const e of doc.entities) {
      if (e.type !== "underlay" || images.current.has(e.asset)) continue;
      images.current.set(e.asset, null);
      api.cadAssetUrl(e.asset).then((u) => { const im = new Image(); im.onload = () => { images.current.set(e.asset, im); setImgTick((n) => n + 1); }; im.src = u; }).catch(() => undefined);
    }
  }, [doc.entities]);

  /* Att välja verktyg är att bestämma vad man ritar, och det som avgör vad det blir - rörets DN och system,
     väggens tjocklek - står i verktygets inställningar. De ska fram innan första punkten sätts, inte efteråt
     i egenskaperna på något som redan är ritat. Därför följer panelen med dit när ett ritverktyg armeras. */
  const pickTool = useCallback((id: ToolId) => {
    setTool(id); setDraft([]);
    if (id !== "valj") { setSel([]); setPanel("egenskaper"); }
  }, []);

  const undo = useCallback(() => { const r = undoTx(doc, hist); if (r.tx) { setDoc(r.doc); setHist(r.hist); dirty.current = true; setDraft([]); } }, [doc, hist]);
  const redo = useCallback(() => { const r = redoTx(doc, hist); if (r.tx) { setDoc(r.doc); setHist(r.hist); dirty.current = true; setDraft([]); } }, [doc, hist]);

  useEffect(() => {
    if (!meta || !dirty.current) return;
    const t = setTimeout(async () => {
      dirty.current = false;
      const problems = validate(doc);
      if (problems.length) { setErr(`Sparas inte: ${problems[0].message}${problems.length > 1 ? ` (+${problems.length - 1})` : ""}`); return; }
      setSaving("sparar"); setErr("");
      try {
        const label = hist.past.length ? hist.past[hist.past.length - 1].label : undefined;
        const s = await api.cadSave(sheetId, { content: { ...doc, revision: savedRevision.current }, label, base_revision: savedRevision.current });
        savedRevision.current = s.content?.revision ?? savedRevision.current;
        setDoc((d) => ({ ...d, revision: savedRevision.current }));
        setMeta(s); setSaving("sparat"); setTimeout(() => setSaving(""), 1400);
      } catch (e: any) {
        if (/409/.test(e.message)) { setSaving("krock"); setErr("Bladet har sparats av någon annan. Ladda om för att fortsätta på den senaste versionen."); }
        else { setErr(e.message); setSaving(""); }
      }
    }, 900);
    return () => clearTimeout(t);
  }, [doc, meta, sheetId, hist]);

  const loadRevisions = useCallback(() => { api.cadRevisions(sheetId).then((r: any) => setRevisions(r.rows)).catch(() => { /* valfritt */ }); }, [sheetId]);
  useEffect(() => { if (panel === "revisioner") loadRevisions(); }, [panel, loadRevisions]);

  // ---------------------------------------------------------------- vy

  const fit = useCallback(() => {
    const el = wrap.current; if (!el) return;
    const r = el.getBoundingClientRect();
    const ents = doc.entities;
    let x0 = 0, y0 = 0, x1 = 12000, y1 = 8000;
    if (ents.length) { x0 = Infinity; y0 = Infinity; x1 = -Infinity; y1 = -Infinity; for (const e of ents) { const b = bboxOf(doc, e); x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3]); } }
    if (!isFinite(x0)) { x0 = 0; y0 = 0; x1 = 12000; y1 = 8000; }
    const w = Math.max(1000, x1 - x0), h = Math.max(1000, y1 - y0);
    const s = Math.min((r.width - 80) / w, (r.height - 80) / h);
    setCam({ s, ox: (r.width - w * s) / 2 - x0 * s, oy: (r.height - h * s) / 2 - y0 * s });
  }, [doc]);
  useLayoutEffect(() => { if (meta) fit(); }, [meta?.id, mode]);

  const paint = useCallback(() => {
    const c = canvas.current, el = wrap.current; if (!c || !el) return;
    const r = el.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    if (c.width !== Math.round(r.width * dpr) || c.height !== Math.round(r.height * dpr)) { c.width = Math.round(r.width * dpr); c.height = Math.round(r.height * dpr); c.style.width = `${r.width}px`; c.style.height = `${r.height}px`; }
    const g = c.getContext("2d"); if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    const pts = hover && draft.length ? [...draft, hover.p] : draft;
    const ghost = draft.length ? ghostOf(tool, pts, ctx) : null;
    drawPlan(g, doc, view, { colour: (e) => colourOf(doc, e), selected, hover, ghost, cam, scale_ratio: view.scale_ratio ?? 100, showGrid: snaps.grid, ghosts: ghostsOf(proposals), images: images.current }, [r.width, r.height]);
    void imgTick;
    // kalibreringens punkter
    if (calib) { g.fillStyle = "#e8590c"; for (const q of calib.pts) { const P = toScreen(cam, q); g.beginPath(); g.arc(P[0], P[1], 5, 0, Math.PI * 2); g.fill(); } g.font = "12px system-ui, sans-serif"; g.fillText(calib.pts.length ? "klicka den andra punkten" : "kalibrera: klicka en punkt med känt avstånd till en annan", 12, 20); }
    // snittlinjen
    if (sectionLine) { const A = toScreen(cam, sectionLine[0]), B = toScreen(cam, sectionLine[1]); g.strokeStyle = "#e8590c"; g.setLineDash([10, 5]); g.lineWidth = 2; g.beginPath(); g.moveTo(A[0], A[1]); g.lineTo(B[0], B[1]); g.stroke(); g.setLineDash([]); g.font = "12px ui-monospace"; g.fillStyle = "#e8590c"; g.fillText("A", A[0] - 14, A[1] - 6); g.fillText("A", B[0] + 6, B[1] - 6); }
    // markeringsrutan och måttet som ritas
    const d = drag.current;
    if (d?.kind === "box" && d.box) { const A = toScreen(cam, d.box[0]), B = toScreen(cam, d.box[1]); g.strokeStyle = "#1f6feb"; g.setLineDash([4, 3]); g.lineWidth = 1; g.strokeRect(Math.min(A[0], B[0]), Math.min(A[1], B[1]), Math.abs(B[0] - A[0]), Math.abs(B[1] - A[1])); g.fillStyle = "rgba(31,111,235,0.07)"; g.fillRect(Math.min(A[0], B[0]), Math.min(A[1], B[1]), Math.abs(B[0] - A[0]), Math.abs(B[1] - A[1])); g.setLineDash([]); }
    if (pts.length >= 2) { const a = pts[pts.length - 2], b = pts[pts.length - 1]; const B = toScreen(cam, b); const L = Math.hypot(b[0] - a[0], b[1] - a[1]); const ang = ((Math.atan2(b[1] - a[1], b[0] - a[0]) * 180) / Math.PI + 360) % 360; g.fillStyle = "#0b7285"; g.font = "12px ui-monospace, monospace"; g.fillText(`${typed ? typed + " mm" : fmtMm(L)}  ${typedAngle !== null ? typedAngle + "°" : ang.toFixed(1) + "°"}`, B[0] + 12, B[1] - 10); }
  }, [doc, view, selected, hover, draft, tool, ctx, cam, snaps.grid, sectionLine, typed, typedAngle, proposals, calib, imgTick]);
  useEffect(() => { paint(); }, [paint]);
  useEffect(() => { const on = () => paint(); window.addEventListener("resize", on); return () => window.removeEventListener("resize", on); }, [paint]);

  // ---------------------------------------------------------------- pekaren

  const snapAt = useCallback((x: number, y: number): Snap => {
    const raw = toWorld(cam, x, y);
    const ref = draft.length ? draft[draft.length - 1] : null;
    const s = snapPoint(doc, view, raw, snaps, tol, ref);
    if (s.kind === "fri" && ref && ortho) return { p: constrain(ref, raw, ortho), kind: "fri" };
    return s;
  }, [cam, draft, doc, view, snaps, tol, ortho]);

  const finish = useCallback((pts: Pt[], closed = false) => {
    const wallHit = needed(tool) === "wall" && pts[0] ? wallAt(doc, view, pts[0], Math.max(tol, 300)) : null;
    const e = build(tool, pts, ctx, closed, wallHit);
    if (!e) { if (needed(tool) === "wall") setErr("Klicka på en vägg."); setDraft([]); return; }
    if (tool === "natlinje") {
      apply(new Tx("Nätlinje").add("grids", { id: uid(), label: defaults.grid.label, p: [pts[0], pts[1]] }));
      setDefaults((d) => ({ ...d, grid: { label: nextLabel(d.grid.label) } }));
    } else {
      apply(new Tx(`${TOOLS.find((t) => t.id === tool)?.label ?? "Objekt"}`).add("entities", e));
      setSel([e.id]);
    }
    // Ett objekt i taget. Väggen fortsatte förut där den slutade, så att nästa vägg började av sig själv - men
    // då tog ritandet aldrig slut, och den som satt en vägg fick en till på köpet som måste avbrytas. Satt start
    // och slut är väggen färdig, och nästa klick börjar en ny. Fångsten sätter ändå nästa vägg på den förras
    // ände, så kedjan går att rita lika fort - skillnaden är att den slutar när man slutar.
    setDraft([]);
    setTyped(""); setTypedAngle(null); setErr("");
  }, [tool, doc, view, tol, ctx, apply, defaults.grid.label]);

  /** Avsluta det som ritas: sluter ytan om verktyget ritar en yta, annars bara avslutar linjen. */
  const closeDraft = useCallback(() => {
    if (draft.length >= 2) finish(draft, AREA_TOOLS.has(tool) && draft.length >= 3);
    else setDraft([]);
  }, [draft, finish, tool]);

  const cancelDraft = useCallback(() => { setDraft([]); setTyped(""); setTypedAngle(null); setErr(""); }, []);

  const onDown = (ev: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
    if (ev.button === 1 || ev.altKey) { drag.current = { kind: "pan", from: toWorld(cam, x, y), screen: [x, y] }; return; }
    if (ev.button !== 0) return;          // högerklick tas av onContextMenu, som avslutar eller avbryter
    if (calib) {
      // två punkter i underlaget och ett känt avstånd: skalan följer, och underlaget är uppmätt
      const q = toWorld(cam, x, y);
      const pts = [...calib.pts, q];
      if (pts.length < 2) { setCalib({ ...calib, pts }); return; }
      const u = doc.entities.find((e) => e.id === calib.id);
      const raw = window.prompt("Avståndet mellan punkterna i millimeter", "");
      setCalib(null);
      const known = Number((raw ?? "").replace(",", "."));
      if (!u || u.type !== "underlay" || !isFinite(known) || known <= 0) return;
      const measured = Math.hypot(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]);
      if (measured <= 0) return;
      const k = (u.mm_per_px ?? 1) * (known / measured);
      apply(new Tx("Kalibrera underlag").update("entities", u, { ...u, mm_per_px: k, scale_state: "CALIBRATED", version: u.version + 1 }));
      return;
    }
    const s = snapAt(x, y);
    if (tool === "valj") {
      const grip = sel.flatMap((eid) => { const e = doc.entities.find((q) => q.id === eid); return e ? gripsOf(e).map((gp, i) => ({ id: eid, i, d: Math.hypot(gp[0] - s.p[0], gp[1] - s.p[1]) })) : []; }).sort((a, b) => a.d - b.d)[0];
      if (grip && grip.d <= tol) { drag.current = { kind: "grip", from: s.p, screen: [x, y], grip: { id: grip.id, i: grip.i }, before: doc.entities.filter((e) => e.id === grip.id) }; return; }
      const hit = [...doc.entities].reverse().find((e) => { const l = doc.layers.find((k) => k.id === e.layer); return l?.locked !== true && hits(doc, e, s.p, tol) && visibleFor(doc, view, e); });
      if (hit) {
        const next = ev.shiftKey ? (sel.includes(hit.id) ? sel.filter((i) => i !== hit.id) : [...sel, hit.id]) : (sel.includes(hit.id) ? sel : [hit.id]);
        setSel(next);
        drag.current = { kind: "move", from: s.p, screen: [x, y], ids: next, before: doc.entities.filter((e) => next.includes(e.id)) };
      } else { if (!ev.shiftKey) setSel([]); drag.current = { kind: "box", from: s.p, screen: [x, y], box: [s.p, s.p] }; }
      return;
    }
    const n = needed(tool);
    const pts = [...draft, s.p];
    if (n === "one" || n === "wall") return finish(pts);
    if (typeof n === "number" && pts.length >= n) return finish(pts);
    setDraft(pts);
  };

  const onMove = (ev: React.PointerEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    const d = drag.current;
    if (d) {
      const w = toWorld(cam, x, y);
      if (d.kind === "pan") { setCam((v) => ({ ...v, ox: v.ox + (x - d.screen[0]), oy: v.oy + (y - d.screen[1]) })); d.screen = [x, y]; }
      else if (d.kind === "box") { d.box = [d.from, w]; paint(); }
      else if (d.kind === "move" && d.ids) { const dx = w[0] - d.from[0], dy = w[1] - d.from[1]; d.from = w; setDoc((cur) => ({ ...cur, entities: cur.entities.map((e) => (d.ids!.includes(e.id) ? moved(e, dx, dy) : e)) })); }
      else if (d.kind === "grip" && d.grip) { const s = snapAt(x, y); setDoc((cur) => ({ ...cur, entities: cur.entities.map((e) => (e.id === d.grip!.id ? gripped(e, d.grip!.i, s.p) : e)) })); }
      return;
    }
    setHover(snapAt(x, y));
  };

  const onUp = () => {
    const d = drag.current; drag.current = null;
    if (!d) return;
    if (d.kind === "box" && d.box) {
      const [a, b] = d.box; const box: [number, number, number, number] = [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])];
      const inside = doc.entities.filter((e) => { const bb = bboxOf(doc, e); return visibleFor(doc, view, e) && bb[0] >= box[0] && bb[1] >= box[1] && bb[2] <= box[2] && bb[3] <= box[3]; }).map((e) => e.id);
      if (inside.length) setSel((s) => Array.from(new Set([...s, ...inside])));
      paint();
    }
    if ((d.kind === "move" || d.kind === "grip") && d.before) {
      // den direkta flytten skrev i dokumentet medan man drog; nu blir den en transaktion som går att ångra
      const tx = new Tx(d.kind === "move" ? "Flytta" : "Ändra form");
      for (const b of d.before) { const after = doc.entities.find((e) => e.id === b.id); if (after && JSON.stringify(after) !== JSON.stringify(b)) tx.update("entities", b, after); }
      if (!tx.empty) { const r = commit({ ...doc, entities: doc.entities.map((e) => d.before!.find((b) => b.id === e.id) ?? e) }, hist, tx.build()); setDoc(r.doc); setHist(r.hist); dirty.current = true; }
    }
  };

  const onWheel = (ev: React.WheelEvent) => {
    const r = canvas.current!.getBoundingClientRect();
    const x = ev.clientX - r.left, y = ev.clientY - r.top;
    const k = Math.exp(-(ev.deltaMode === 1 ? ev.deltaY * 16 : ev.deltaY) * 0.0016);
    setCam((v) => { const s = Math.min(4, Math.max(0.0005, v.s * k)); return { s, ox: x - (x - v.ox) * (s / v.s), oy: y - (y - v.oy) * (s / v.s) }; });
  };

  /** Exakt inmatning: ett tal är en längd i millimeter från förra punkten, Tab lägger till en vinkel. */
  const applyTyped = useCallback(() => {
    const from = draft[draft.length - 1]; if (!from) return;
    const len = parseFloat(typed); if (!isFinite(len) || len <= 0) return;
    const base = hover?.p ?? from;
    let ang = typedAngle !== null && typedAngle !== "" ? (parseFloat(typedAngle) * Math.PI) / 180 : Math.atan2(base[1] - from[1], base[0] - from[0]);
    if (!isFinite(ang)) ang = 0;
    const p: Pt = [from[0] + len * Math.cos(ang), from[1] + len * Math.sin(ang)];
    const pts = [...draft, p];
    const n = needed(tool);
    setTyped(""); setTypedAngle(null);
    if (typeof n === "number" && pts.length >= n) finish(pts); else setDraft(pts);
  }, [draft, typed, typedAngle, hover, tool, finish]);

  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const t = ev.target as HTMLElement;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
      const k = ev.key;
      if ((ev.ctrlKey || ev.metaKey) && k.toLowerCase() === "z") { ev.preventDefault(); if (ev.shiftKey) redo(); else undo(); return; }
      if ((ev.ctrlKey || ev.metaKey) && k.toLowerCase() === "y") { ev.preventDefault(); redo(); return; }
      if (k === "Escape") { setDraft([]); setTyped(""); setTypedAngle(null); setSel([]); setSectionLine(null); return; }
      if (k === "Delete") { if (sel.length) { ev.preventDefault(); const tx = new Tx(`Ta bort ${sel.length} objekt`); for (const e of doc.entities) if (sel.includes(e.id) || ("host" in e && sel.includes((e as any).host))) tx.remove("entities", e); apply(tx); setSel([]); } return; }
      if (k === "Enter") { if (typed && draft.length) { ev.preventDefault(); applyTyped(); return; } if (draft.length >= 2) { ev.preventDefault(); finish(draft, ["bjalklag", "platta", "tak", "undertak", "rum", "skraffering", "tomtgrans"].includes(tool)); } return; }
      if (k === "Tab" && draft.length) { ev.preventDefault(); setTypedAngle((a) => (a === null ? "" : a)); return; }
      if (/^[0-9.,]$/.test(k) && draft.length) { if (typedAngle !== null) setTypedAngle((a) => (a ?? "") + k.replace(",", ".")); else setTyped((v) => v + k.replace(",", ".")); return; }
      if (k === "Backspace") { if (typedAngle !== null && typedAngle) setTypedAngle((a) => (a ?? "").slice(0, -1)); else setTyped((v) => v.slice(0, -1)); return; }
      if (k === "F8") { ev.preventDefault(); setOrtho((o) => (o === 90 ? 0 : 90)); return; }
      if (k === "F3") { ev.preventDefault(); setSnaps((s) => ({ ...s, on: !s.on })); return; }
      if (k.toLowerCase() === "c" && draft.length >= 3) { ev.preventDefault(); finish(draft, true); return; }
      const hit = tools.find((x) => x.key.toLowerCase() === k.toLowerCase());
      if (hit && !ev.ctrlKey && !ev.metaKey && !ev.altKey) { pickTool(hit.id); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo, sel, doc, apply, draft, typed, typedAngle, tool, finish, applyTyped, tools, pickTool]);

  // ---------------------------------------------------------------- ändringar från panelerna

  const updateEntity = useCallback((e: Entity, patch: Partial<Entity>, label = "Egenskap") => {
    apply(new Tx(label).update("entities", e, { ...e, ...patch } as Entity));
  }, [apply]);
  const on3dSelect = useCallback((ids: string[], additive: boolean) => setSel((s) => (additive ? Array.from(new Set([...s, ...ids])) : ids)), []);
  const on3dMove = useCallback((eid: string, dx: number, dy: number, dz: number) => {
    const e = doc.entities.find((q) => q.id === eid); if (!e) return;
    let after: Entity = moved(e, dx, dy);
    if (dz && (after.type === "pipe" || after.type === "duct" || after.type === "cable_tray" || after.type === "conduit")) after = { ...after, elevation: (after.elevation ?? 0) + dz } as Entity;
    if (dz && (after.type === "wall" || after.type === "column")) after = { ...after, base_offset: (after.base_offset ?? 0) + dz, top_offset: (after.top_offset ?? 0) + dz } as Entity;
    if (dz && (after.type === "floor" || after.type === "roof")) after = { ...after, offset: (after.offset ?? 0) + dz } as Entity;
    if (dz && after.type === "mesh") after = { ...after, p: [[after.p[0][0], after.p[0][1], after.p[0][2] + dz]] } as Entity;
    apply(new Tx("Flytta i 3D").update("entities", e, after));
  }, [doc, apply]);

  const addLevel = () => {
    const top = Math.max(...doc.levels.map((l) => l.elevation_mm));
    const raw = window.prompt("Nivåns höjd i mm (över noll)", String(top + 3000));
    if (raw == null) return;
    const z = Number(raw.replace(",", "."));
    if (!isFinite(z)) { setErr("Höjden ska vara ett tal i millimeter."); return; }
    const name = window.prompt("Nivåns namn", `Plan ${doc.levels.length}`) || `Nivå ${z}`;
    const lv: Level = { id: uid(), name, elevation_mm: z };
    const pv: View = { id: uid(), kind: "plan", name, level: lv.id, scale_ratio: 100 };
    apply(new Tx(`Nivå ${name}`).add("levels", lv).add("views", pv));
  };
  const setLevelElevation = (lv: Level, z: number) => { if (!isFinite(z)) return; apply(new Tx(`Nivå ${lv.name} → ${z} mm`).update("levels", lv, { ...lv, elevation_mm: z })); };
  const setActiveLevel = (lv: Level) => {
    const pv = doc.views.find((v) => v.kind === "plan" && v.level === lv.id);
    const s = { ...doc.settings, active_level: lv.id, active_view: pv?.id ?? doc.settings.active_view };
    setDoc((d) => ({ ...d, settings: s })); setSel([]);
  };
  const copyLevel = (from: Level) => {
    const to = doc.levels.find((l) => l.id !== from.id && l.elevation_mm > from.elevation_mm) ?? null;
    if (!to) { setErr("Skapa nivån ovanför först."); return; }
    const tx = new Tx(`Kopiera ${from.name} till ${to.name}`);
    const map = new Map<string, string>();
    const toAbove = doc.levels.filter((l) => l.elevation_mm > to.elevation_mm).sort((a, b) => a.elevation_mm - b.elevation_mm)[0];
    for (const e of doc.entities) {
      const onLevel = ("base_level" in e && e.base_level === from.id) || (!("base_level" in e) && e.level === from.id && e.type !== "door" && e.type !== "window" && e.type !== "opening");
      if (!onLevel) continue;
      const nid = uid(); map.set(e.id, nid);
      const c: any = { ...e, id: nid, version: 1, provenance: "USER_MODELLED" };
      if ("base_level" in c) { c.base_level = to.id; c.top_level = c.top_level ? (toAbove?.id ?? null) : null; }
      if (c.level) c.level = to.id;
      tx.add("entities", c);
    }
    for (const e of doc.entities) if ((e.type === "door" || e.type === "window" || e.type === "opening") && map.has(e.host)) tx.add("entities", { ...e, id: uid(), host: map.get(e.host)!, level: to.id, version: 1 } as Entity);
    apply(tx);
  };

  const runClashes = () => { setClashes(findClashes(doc)); setPanel("kollisioner"); };
  const q = useMemo(() => (panel === "mangder" ? quantities(doc) : null), [doc, panel]);
  const mats = useMemo(() => (panel === "mangder" ? materialQuantities(doc) : null), [doc, panel]);
  const section = useMemo(() => (sectionLine ? sectionOfDocument(doc, { a: sectionLine[0], b: sectionLine[1], depth: 3000 }) : null), [doc, sectionLine]);
  const elevation = useMemo(() => (panel === "snitt" && !sectionLine ? elevationOfDocument(doc, elevationPlane(doc, elevDir)) : null), [doc, panel, sectionLine, elevDir]);

  const selEntities = doc.entities.filter((e) => selected.has(e.id));
  const one = selEntities.length === 1 ? selEntities[0] : null;
  const sectionBox = useMemo(() => {
    if (!sectionBoxOn) return null;
    const lv = levelOf(doc, level); const z0 = lv?.elevation_mm ?? 0;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const e of doc.entities) { const b = bboxOf(doc, e); x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[2]); y1 = Math.max(y1, b[3]); }
    if (!isFinite(x0)) return null;
    return { min: [x0 - 500, y0 - 500, z0 - 100] as [number, number, number], max: [x1 + 500, y1 + 500, z0 + 1500] as [number, number, number] };
  }, [sectionBoxOn, doc, level]);

  if (!meta) return <main>{err ? <p className="error">{err}</p> : "Laddar…"}</main>;
  const curTool = TOOLS.find((t) => t.id === tool)!;

  return (
    <div className={`bcad${bare ? " bare" : ""}`}>
      <header className="bcad-top">
        <div className="bcad-crumb"><Link to="/cad">CAD</Link> / <b>{meta.name}</b> <span className="muted small">· {doc.project.name} · {doc.building.name}</span></div>
        <div className="bcad-tools">
          {/* Vilken disciplin man ritar i bestämmer vilka verktyg som finns. Den låg bara i vänsterpanelen
              bland genomskinlighetsreglagen, så "rita ett rör" krävde att man först hittade VVS i en lista
              som ser ut att handla om vad som syns i 3D. Nu står den först i verktygsraden. */}
          <select className="bcad-disc" value={discipline} aria-label={tr("Disciplin att rita i")}
            onChange={(e) => { setDiscipline(e.target.value as Discipline); setTool("valj"); setDraft([]); }}>
            {DISCIPLINES.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
          </select>
          {tools.map((t) => <button key={t.id} className={`bcad-tool${tool === t.id ? " on" : ""}`} title={`${t.hint} (${t.key})`} onClick={() => pickTool(t.id)}>{t.label}<kbd>{t.key}</kbd></button>)}
        </div>
        <div className="bcad-right">
          <FileMenu sheetId={sheetId} name={meta.name} doc={doc} viewId={view.id} scaleRatio={view.scale_ratio ?? 100} level={level} centre={() => { const r = wrap.current?.getBoundingClientRect(); return r ? toWorld(cam, r.width / 2, r.height / 2) : [0, 0]; }} apply={apply} onError={setErr} onUnderlayAdded={(uid_, cal) => { setSel([uid_]); if (cal) setCalib({ id: uid_, pts: [] }); }} />
          <button className="ghost small" onClick={undo} disabled={!hist.past.length} title={tr("Ångra (Ctrl+Z)")}>↶</button>
          <button className="ghost small" onClick={redo} disabled={!hist.future.length} title={tr("Gör om (Ctrl+Y)")}>↷</button>
          <button className={`ghost small${snaps.on ? " on" : ""}`} onClick={() => setSnaps((s) => ({ ...s, on: !s.on }))} title={tr("Fångst (F3)")}>{tr("Fångst")}</button>
          <button className={`ghost small${ortho ? " on" : ""}`} onClick={() => setOrtho((o) => (o === 90 ? 0 : 90))} title={tr("Ortho (F8)")}>Ortho</button>
          <span className="bcad-modes">
            {(["2d", "split", "3d"] as Mode[]).map((m) => <button key={m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>{m === "2d" ? "2D" : m === "3d" ? "3D" : "Delad"}</button>)}
          </span>
          <button className={`ghost small${bare ? " on" : ""}`} onClick={() => setBare((b) => !b)}
            title={bare ? "Visa panelerna" : "Dölj panelerna och rita i hela rutan"}>
            {bare ? "Visa paneler" : "Fullskärm"}
          </button>
          <span className={`badge ${saving === "krock" ? "bad" : saving ? "ok" : ""}`}>{saving === "sparar" ? "sparar…" : saving === "sparat" ? "sparat" : saving === "krock" ? "krock" : `rev ${doc.revision}`}</span>
        </div>
      </header>

      <aside className="bcad-browser">
        <div className="bcad-sec">
          <div className="bcad-h">Disciplin</div>
          {DISCIPLINES.map((d) => (
            <div key={d.id} className={`bcad-row${discipline === d.id ? " on" : ""}`}>
              <button className="bcad-link" onClick={() => { setDiscipline(d.id); setTool("valj"); }}>{d.label}</button>
              <input type="range" min={0} max={100} value={Math.round((transp[d.id] ?? 1) * 100)} title={tr("Genomskinlighet i 3D")} onChange={(e) => setTransp((t) => ({ ...t, [d.id]: Number(e.target.value) / 100 }))} />
            </div>
          ))}
        </div>
        <div className="bcad-sec">
          <div className="bcad-h">{tr("Nivåer")} <button className="ghost small" onClick={addLevel}>+</button></div>
          {[...doc.levels].sort((a, b) => b.elevation_mm - a.elevation_mm).map((lv) => (
            <div key={lv.id} className={`bcad-row${level === lv.id ? " on" : ""}`}>
              <button className="bcad-link" onClick={() => setActiveLevel(lv)}>{lv.name}</button>
              <input className="bcad-num" type="number" step={100} value={lv.elevation_mm} onChange={(e) => setLevelElevation(lv, Number(e.target.value))} title={tr("höjd i mm")} />
              <button className="ghost small" title={tr("Kopiera nivåns objekt till nivån ovanför")} onClick={() => copyLevel(lv)}>⧉</button>
            </div>
          ))}
        </div>
        <div className="bcad-sec">
          <div className="bcad-h">Vyer</div>
          {doc.views.map((v) => <div key={v.id} className={`bcad-row${doc.settings.active_view === v.id ? " on" : ""}`}><button className="bcad-link" onClick={() => { if (v.kind === "plan" && v.level) { setDoc((d) => ({ ...d, settings: { ...d.settings, active_view: v.id, active_level: v.level! } })); setMode("2d"); } else if (v.kind === "3d") setMode("3d"); }}>{v.name} <span className="muted small">{v.kind}</span></button></div>)}
          <div className="bcad-row"><button className="bcad-link" onClick={() => { setPanel("snitt"); setSectionLine(null); }}>Fasad</button><button className="bcad-link" onClick={() => { setPanel("snitt"); setTool("valj"); setSectionLine(sectionLine ?? [[0, 7500], [12000, 7500]]); }}>{tr("Sektion A-A")}</button></div>
        </div>
        <div className="bcad-sec">
          <div className="bcad-h">Lager</div>
          {doc.layers.map((l) => <div key={l.id} className="bcad-row"><label><input type="checkbox" checked={l.visible} onChange={() => apply(new Tx(`Lager ${l.name}`).update("layers", l, { ...l, visible: !l.visible }))} /> <span style={{ color: l.color }}>■</span> {l.name}</label></div>)}
        </div>
        <div className="bcad-sec">
          <div className="bcad-h">Verktyg</div>
          <p className="muted small">{curTool.label}: {curTool.hint}. Skriv ett tal för exakt längd, Tab för vinkel, Enter för att avsluta, Esc avbryter.</p>
          <p className="muted small">{hover && hover.kind !== "fri" ? `fångst: ${hover.kind}` : ortho ? "ortho" : ""}</p>
        </div>
      </aside>

      {/* Det som ritas just nu, och vägen ut ur det.
          Enter och Esc fanns, men bara i tangentbordet. Den som ritar med musen såg ingenting som sade hur
          man avslutar en yta, och klickade vidare tills figuren blev orimlig - det var det som kändes som att
          klicket inte tog. */}
      {!!draft.length && (
        <div className="bcad-doing" role="status">
          <span className="bcad-doing-t">
            {curTool.label} · {draft.length} {draft.length === 1 ? "punkt" : "punkter"}
            {typed && ` · ${typed} mm`}
          </span>
          {draft.length >= 2 && (
            <button className="bcad-doing-b on" onClick={closeDraft}>
              {AREA_TOOLS.has(tool) && draft.length >= 3 ? "Slut ytan" : "Klart"} <kbd>Enter</kbd>
            </button>
          )}
          <button className="bcad-doing-b" onClick={cancelDraft}>Avbryt <kbd>Esc</kbd></button>
        </div>
      )}

      <main className="bcad-stage">
        {mode !== "3d" && (
          <div ref={wrap} className={`bcad-plan${mode === "split" ? " half" : ""}`}>
            <canvas ref={canvas} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerLeave={() => setHover(null)} onWheel={onWheel} onDoubleClick={closeDraft} onContextMenu={(e) => { e.preventDefault(); if (draft.length) closeDraft(); else { setTool("valj"); setSel([]); } }} style={{ display: "block", cursor: tool === "valj" ? "default" : "crosshair", touchAction: "none" }} />
            <div className="bcad-planbar"><span>{levelOf(doc, level)?.name}</span><button className="ghost small" onClick={fit}>Anpassa</button><span className="muted small">1 px = {(1 / cam.s).toFixed(0)} mm</span></div>
          </div>
        )}
        {mode !== "2d" && (
          <div className={`bcad-3d${mode === "split" ? " half" : ""}`}>
            <BuildingView3D doc={doc} view={view} selected={sel} onSelect={on3dSelect} onMove={on3dMove} transparency={transp} sectionBox={sectionBox} standardView={view3d} ortho={ortho3d} wire={wire} />
            <div className="bcad-3dbar">
              {(["iso", "top", "front", "back", "left", "right"] as ViewName[]).map((v) => <button key={v} className={view3d === v ? "on" : ""} onClick={() => { setView3d(null); setTimeout(() => setView3d(v), 0); }}>{{ iso: "Iso", top: "Ovan", front: "Fram", back: "Bak", left: "Vänster", right: "Höger", bottom: "Under" }[v]}</button>)}
              <button className={ortho3d ? "on" : ""} onClick={() => setOrtho3d((o) => !o)}>Orto</button>
              <button className={sectionBoxOn ? "on" : ""} onClick={() => setSectionBoxOn((o) => !o)}>Sektionsbox</button>
              <button className={wire ? "on" : ""} onClick={() => setWire((w) => !w)}>{tr("Tråd")}</button>
            </div>
          </div>
        )}
      </main>

      <aside className="bcad-props">
        <div className="bcad-tabs">
          {(["egenskaper", "mangder", "kollisioner", "revisioner", "snitt", "blad", "agent"] as const).map((p) => <button key={p} className={panel === p ? "on" : ""} onClick={() => { setPanel(p); if (p === "kollisioner" && !clashes) setClashes(findClashes(doc)); }}>{{ egenskaper: "Egenskaper", mangder: "Mängder", kollisioner: "Kollisioner", revisioner: "Revisioner", snitt: "Snitt", blad: "Blad", agent: "Agent" }[p]}</button>)}
        </div>
        {err && <p className="error small">{err}</p>}
        {panel === "egenskaper" && (one ? <Properties doc={doc} e={one} onChange={(patch, label) => updateEntity(one, patch, label)} onCalibrate={() => { setCalib({ id: one.id, pts: [] }); setTool("valj"); }} /> : selEntities.length > 1 ? <p className="muted">{selEntities.length} objekt valda. Delete tar bort dem.</p> : <ToolDefaultsPanel tool={tool} defaults={defaults} setDefaults={setDefaults} materials={doc.materials} />)}
        {panel === "blad" && <SheetsPanel sheetId={sheetId} doc={doc} apply={apply} onError={setErr} />}
        {panel === "agent" && <AgentPanel sheetId={sheetId} selection={sel} proposals={proposals} setProposals={setProposals} onDirtyWarning={dirty.current} onApprove={(ps) => { apply(txOf(doc, ps)); }} />}
        {panel === "mangder" && q && (
          <div className="bcad-list">
            <table className="qty"><thead><tr><th>Objekt</th><th>Antal</th><th>m</th><th>m²</th><th>m³</th><th>kg</th></tr></thead>
              <tbody>{q.groups.map((g) => <tr key={g.key}><td>{g.name}{g.material ? <span className="muted small"> · {g.material}</span> : null}{g.system ? <span className="muted small"> · {g.system}</span> : null}</td><td className="num">{g.count}</td><td className="num">{g.length_m ? g.length_m.toFixed(2) : ""}</td><td className="num">{g.area_m2 ? g.area_m2.toFixed(2) : ""}</td><td className="num">{g.volume_m3 ? g.volume_m3.toFixed(3) : ""}</td><td className="num">{g.mass_kg == null ? (g.volume_m3 ? "okänt" : "") : g.mass_kg.toFixed(0)}</td></tr>)}</tbody></table>
            <h4>Material</h4>
            <table className="qty"><thead><tr><th>Material</th><th>m²</th><th>m³</th><th>kg</th></tr></thead>
              <tbody>{mats!.map((m) => <tr key={m.material.id}><td>{m.material.name}</td><td className="num">{m.area_m2.toFixed(1)}</td><td className="num">{m.volume_m3.toFixed(2)}</td><td className="num">{m.mass_kg == null ? "ingen densitet" : m.mass_kg.toFixed(0)}</td></tr>)}</tbody></table>
            <p className="muted small">{tr("Ur modellens egna mått. Servern räknar samma tal för exporten och kalkylen.")}</p>
          </div>
        )}
        {panel === "kollisioner" && (
          <div className="bcad-list">
            <button className="secondary small" onClick={runClashes}>{tr("Sök igen")}</button>
            {clashes && clashes.length === 0 && <p className="muted">{tr("Inga kollisioner.")}</p>}
            {clashes?.map((c) => <div key={c.id} className={`bcad-clash ${c.severity}`} onClick={() => setSel([c.a, c.b])}><b>{c.severity}</b> {c.note}<div className="muted small">{DISC_LABEL[c.a_discipline]} × {DISC_LABEL[c.b_discipline]} · vid ({c.at[0]}, {c.at[1]}, {c.at[2]})</div></div>)}
            {clashes && proposeOpenings(doc, clashes).map((p, i) => (
              <div key={i} className="bcad-proposal">{p.note}
                <div><button className="secondary small" onClick={() => { const host = doc.entities.find((e) => e.id === p.host) as Wall | undefined; if (!host || host.type !== "wall") return; const L = Math.hypot(host.p[1][0] - host.p[0][0], host.p[1][1] - host.p[0][1]) || 1; const t = ((p.at[0] - host.p[0][0]) * (host.p[1][0] - host.p[0][0]) + (p.at[1] - host.p[0][1]) * (host.p[1][1] - host.p[0][1])) / (L * L); const z0 = levelOf(doc, host.base_level)?.elevation_mm ?? 0; apply(new Tx("Godkänt hål").add("entities", { id: uid(), type: "opening", layer: host.layer, discipline: "KONSTR", level: host.base_level, phase: "NEW", provenance: "AGENT_CREATED_APPROVED", version: 1, host: host.id, t: Math.max(0, Math.min(1, t)), width: p.size_mm, height: p.size_mm, sill: p.at[2] - z0 - p.size_mm / 2, host_kind: "wall" } as Entity)); setClashes(null); }}>{tr("Godkänn")}</button></div>
              </div>
            ))}
          </div>
        )}
        {panel === "revisioner" && (
          <div className="bcad-list">
            {revisions.map((r) => <div key={r.id} className="bcad-rev"><b>Revision {r.revision}</b> <span className="muted small">{new Date(r.created_at).toLocaleString(locale())}</span><div>{r.label}</div><div className="muted small">{(r.touched || []).slice(0, 6).join(", ")}{(r.touched || []).length > 6 ? "…" : ""}</div>{r.revision !== doc.revision && <button className="ghost small" onClick={async () => { const s = await api.cadRestore(sheetId, r.revision); const d = migrate(s.content); setDoc(d); savedRevision.current = d.revision; setHist(emptyHistory()); loadRevisions(); }}>{tr("Återställ")}</button>}</div>)}
            {!revisions.length && <p className="muted">{tr("Inga revisioner än.")}</p>}
          </div>
        )}
        {panel === "snitt" && (
          <div className="bcad-list">
            {sectionLine ? <p className="muted small">Sektion A-A genom ({Math.round(sectionLine[0][0])}, {Math.round(sectionLine[0][1])}) – ({Math.round(sectionLine[1][0])}, {Math.round(sectionLine[1][1])}). <button className="ghost small" onClick={() => setSectionLine(null)}>{tr("Fasad i stället")}</button></p>
              : <p className="muted small">Fasad {(["N", "S", "E", "W"] as const).map((d) => <button key={d} className={`ghost small${elevDir === d ? " on" : ""}`} onClick={() => setElevDir(d)}>{d}</button>)}</p>}
            <SectionSvg shapes={section ?? elevation ?? []} />
            {sectionLine && <div className="bcad-row"><label>{tr("Snittlinje y")} <input className="bcad-num" type="number" step={500} value={sectionLine[0][1]} onChange={(e) => setSectionLine([[sectionLine[0][0], Number(e.target.value)], [sectionLine[1][0], Number(e.target.value)]])} /></label></div>}
          </div>
        )}
      </aside>
    </div>
  );
}

function visibleFor(doc: CadDocument, view: View, e: Entity): boolean {
  // samma regel som ritningen: det som inte syns i planen kan inte väljas där
  const layer = doc.layers.find((l) => l.id === e.layer);
  if (layer && !layer.visible) return false;
  return visibleIn(doc, view, e);
}

function nextLabel(s: string): string {
  if (/^\d+$/.test(s)) return String(Number(s) + 1);
  if (/^[A-Z]$/.test(s)) return s === "Z" ? "AA" : String.fromCharCode(s.charCodeAt(0) + 1);
  return s + "'";
}

// ---------------------------------------------------------------- egenskaper

function Num({ v, onChange, step = 10, min }: { v: number | null | undefined; onChange: (n: number) => void; step?: number; min?: number }) {
  const [s, setS] = useState(v == null ? "" : String(v));
  useEffect(() => { setS(v == null ? "" : String(v)); }, [v]);
  return <input className="bcad-num" type="number" step={step} min={min} value={s} onChange={(e) => setS(e.target.value)} onBlur={() => { const n = Number(s.replace(",", ".")); if (isFinite(n) && n !== v) onChange(n); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />;
}

function Properties({ doc, e, onChange, onCalibrate }: { doc: CadDocument; e: Entity; onChange: (patch: any, label?: string) => void; onCalibrate?: () => void }) {
  const levels = doc.levels;
  const mats = doc.materials;
  const F = (label: string, node: any) => <div className="bcad-field"><label>{label}</label>{node}</div>;
  const LevelSel = (k: string, v: string | null | undefined, allowNone = false) => <select value={v ?? ""} onChange={(ev) => onChange({ [k]: ev.target.value || null }, `${qLabel(e.type)}: ${k}`)}>{allowNone && <option value="">(höjd)</option>}{levels.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select>;
  const MatSel = <select value={e.material ?? ""} onChange={(ev) => onChange({ material: ev.target.value || undefined }, "Material")}><option value="">–</option>{mats.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>;
  const common = (
    <>
      {F("Namn", <input value={e.name ?? ""} onChange={(ev) => onChange({ name: ev.target.value }, "Namn")} />)}
      {F("Disciplin", <select value={e.discipline} onChange={(ev) => onChange({ discipline: ev.target.value }, "Disciplin")}>{DISCIPLINES.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}</select>)}
      {F("Lager", <select value={e.layer} onChange={(ev) => onChange({ layer: ev.target.value }, "Lager")}>{doc.layers.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select>)}
      {F("Skede", <select value={e.phase} onChange={(ev) => onChange({ phase: ev.target.value }, "Skede")}><option value="NEW">Nytt</option><option value="EXISTING">Befintligt</option><option value="DEMOLISH">Rivs</option></select>)}
      {"level" in e && !("base_level" in e) && e.type !== "door" && e.type !== "window" && e.type !== "opening" && F("Nivå", LevelSel("level", e.level))}
      {e.type !== "room" && e.type !== "text" && e.type !== "dim" && F("Material", MatSel)}
    </>
  );
  let specific: any = null;
  switch (e.type) {
    case "wall": case "curtain_wall":
      specific = <>{F("Tjocklek", <Num v={e.thickness} onChange={(n) => onChange({ thickness: n }, "Tjocklek")} />)}{F("Undre nivå", LevelSel("base_level", e.base_level))}{F("Övre nivå", LevelSel("top_level", e.top_level, true))}{!e.top_level && F("Höjd", <Num v={e.height ?? null} step={100} onChange={(n) => onChange({ height: n }, "Höjd")} />)}{F("Justering", <select value={e.alignment ?? "centre"} onChange={(ev) => onChange({ alignment: ev.target.value }, "Justering")}><option value="centre">Centrum</option><option value="left">{tr("Vänster")}</option><option value="right">{tr("Höger")}</option></select>)}{F("Brandklass", <input value={e.fire_rating ?? ""} onChange={(ev) => onChange({ fire_rating: ev.target.value }, "Brandklass")} placeholder={tr("EI 60")} />)}{F("Ljudklass", <input value={e.sound_rating ?? ""} onChange={(ev) => onChange({ sound_rating: ev.target.value }, "Ljudklass")} placeholder="R'w 52" />)}{F("Bärande", <input type="checkbox" checked={!!e.structural} onChange={(ev) => onChange({ structural: ev.target.checked }, "Bärande")} />)}{F("Längd", <span className="muted">{fmtMm(Math.hypot(e.p[1][0] - e.p[0][0], e.p[1][1] - e.p[0][1]))}</span>)}</>;
      break;
    case "door":
      specific = <>{F("Bredd", <Num v={e.width} onChange={(n) => onChange({ width: n }, "Dörrbredd")} />)}{F("Höjd", <Num v={e.height} onChange={(n) => onChange({ height: n }, "Dörrhöjd")} />)}{F("Slag", <select value={e.swing ?? "left"} onChange={(ev) => onChange({ swing: ev.target.value }, "Slag")}><option value="left">{tr("Vänster")}</option><option value="right">{tr("Höger")}</option><option value="double">Par</option><option value="sliding">Skjut</option></select>)}{F("Läge på väggen", <Num v={Math.round(e.t * 1000) / 1000} step={0.01} onChange={(n) => onChange({ t: Math.max(0, Math.min(1, n)) }, "Läge")} />)}{F("Brandklass", <input value={e.fire_rating ?? ""} onChange={(ev) => onChange({ fire_rating: ev.target.value }, "Brandklass")} />)}{F("Typ", <input value={e.door_type ?? ""} onChange={(ev) => onChange({ door_type: ev.target.value }, "Typ")} />)}</>;
      break;
    case "window": case "opening":
      specific = <>{F("Bredd", <Num v={e.width} onChange={(n) => onChange({ width: n }, "Bredd")} />)}{F("Höjd", <Num v={e.height} onChange={(n) => onChange({ height: n }, "Höjd")} />)}{F("Bröstning", <Num v={e.sill ?? 0} onChange={(n) => onChange({ sill: n }, "Bröstning")} />)}{F("Läge på väggen", <Num v={Math.round(e.t * 1000) / 1000} step={0.01} onChange={(n) => onChange({ t: Math.max(0, Math.min(1, n)) }, "Läge")} />)}</>;
      break;
    case "floor": case "ceiling":
      specific = <>{F("Tjocklek", <Num v={e.thickness} onChange={(n) => onChange({ thickness: n }, "Tjocklek")} />)}{e.type === "floor" ? F("Förskjutning", <Num v={e.offset ?? 0} onChange={(n) => onChange({ offset: n }, "Förskjutning")} />) : F("Höjd över nivå", <Num v={e.height_offset} onChange={(n) => onChange({ height_offset: n }, "Undertakshöjd")} />)}{e.type === "floor" && F("Bärande", <input type="checkbox" checked={!!e.structural} onChange={(ev) => onChange({ structural: ev.target.checked }, "Bärande")} />)}</>;
      break;
    case "roof":
      specific = <>{F("Typ", <select value={e.kind} onChange={(ev) => onChange({ kind: ev.target.value }, "Taktyp")}><option value="flat">Platt</option><option value="pitched">Sadel</option></select>)}{F("Lutning °", <Num v={e.slope_deg ?? 0} step={1} onChange={(n) => onChange({ slope_deg: n }, "Taklutning")} />)}{F("Tjocklek", <Num v={e.thickness} onChange={(n) => onChange({ thickness: n }, "Tjocklek")} />)}{F("Förskjutning", <Num v={e.offset ?? 0} onChange={(n) => onChange({ offset: n }, "Förskjutning")} />)}{e.ridge && F("Nock x", <Num v={e.ridge[0][0]} step={100} onChange={(n) => onChange({ ridge: [[n, e.ridge![0][1]], [n, e.ridge![1][1]]] }, "Nock")} />)}</>;
      break;
    case "room":
      specific = <>{F("Nummer", <input value={e.number ?? ""} onChange={(ev) => onChange({ number: ev.target.value }, "Rumsnummer")} />)}{F("Användning", <input value={e.use ?? ""} onChange={(ev) => onChange({ use: ev.target.value }, "Användning")} />)}{F("Rumshöjd", <Num v={e.height ?? null} step={100} onChange={(n) => onChange({ height: n }, "Rumshöjd")} />)}</>;
      break;
    case "stair":
      specific = <>{F("Typ", <select value={e.kind} onChange={(ev) => onChange({ kind: ev.target.value }, "Trapptyp")}><option value="straight">Rak</option><option value="L">L-trappa</option><option value="U">U-trappa</option></select>)}{F("Bredd", <Num v={e.width} onChange={(n) => onChange({ width: n }, "Trappbredd")} />)}{F("Antal steg", <Num v={e.risers} step={1} min={2} onChange={(n) => onChange({ risers: Math.max(2, Math.round(n)) }, "Steg")} />)}{F("Stegdjup", <Num v={e.tread_d} onChange={(n) => onChange({ tread_d: n }, "Stegdjup")} />)}{F("Från nivå", LevelSel("base_level", e.base_level))}{F("Till nivå", LevelSel("top_level", e.top_level))}{F("Steghöjd", <span className="muted">{fmtMm(((levelOf(doc, e.top_level)?.elevation_mm ?? 0) - (levelOf(doc, e.base_level)?.elevation_mm ?? 0)) / e.risers)}</span>)}</>;
      break;
    case "column":
      specific = <>{F("Profil", <select value={e.profile.kind} onChange={(ev) => onChange({ profile: ev.target.value === "circle" ? { kind: "circle", d: (e.profile as any).w ?? (e.profile as any).d ?? 300 } : { kind: ev.target.value, w: (e.profile as any).w ?? 300, d: (e.profile as any).d ?? 300, t: 10 } }, "Profil")}>{["rect", "circle", "I", "H", "U", "L", "RHS", "SHS"].map((k) => <option key={k} value={k}>{k}</option>)}</select>)}{e.profile.kind === "circle" ? F("Diameter", <Num v={e.profile.d} onChange={(n) => onChange({ profile: { kind: "circle", d: n } }, "Diameter")} />) : <>{F("Bredd", <Num v={(e.profile as any).w} onChange={(n) => onChange({ profile: { ...e.profile, w: n } }, "Profilbredd")} />)}{F("Djup", <Num v={(e.profile as any).d} onChange={(n) => onChange({ profile: { ...e.profile, d: n } }, "Profildjup")} />)}</>}{F("Undre nivå", LevelSel("base_level", e.base_level))}{F("Övre nivå", LevelSel("top_level", e.top_level, true))}{F("Vridning °", <Num v={e.rot ?? 0} step={15} onChange={(n) => onChange({ rot: n }, "Vridning")} />)}</>;
      break;
    case "beam": case "truss":
      specific = <>{e.profile.kind === "circle" ? F("Diameter", <Num v={e.profile.d} onChange={(n) => onChange({ profile: { kind: "circle", d: n } }, "Diameter")} />) : <>{F("Bredd", <Num v={(e.profile as any).w} onChange={(n) => onChange({ profile: { ...e.profile, w: n } }, "Profilbredd")} />)}{F("Höjd", <Num v={(e.profile as any).d} onChange={(n) => onChange({ profile: { ...e.profile, d: n } }, "Profilhöjd")} />)}</>}{e.type === "beam" && F("Höjdförskjutning", <Num v={e.elevation_offset ?? 0} onChange={(n) => onChange({ elevation_offset: n }, "Höjd")} />)}{F("Längd", <span className="muted">{fmtMm(Math.hypot(e.p[1][0] - e.p[0][0], e.p[1][1] - e.p[0][1]))}</span>)}</>;
      break;
    case "foundation":
      specific = <>{F("Typ", <select value={e.kind} onChange={(ev) => onChange({ kind: ev.target.value }, "Grundtyp")}><option value="isolated">Punktplint</option><option value="strip">Sula</option><option value="slab">Platta</option></select>)}{F("Bredd", <Num v={e.w ?? 600} onChange={(n) => onChange({ w: n }, "Bredd")} />)}{F("Djup/längd", <Num v={e.d ?? e.w ?? 600} onChange={(n) => onChange({ d: n }, "Djup")} />)}{F("Höjd", <Num v={e.h} onChange={(n) => onChange({ h: n }, "Höjd")} />)}</>;
      break;
    case "pipe":
      specific = <>{F("System", <input value={e.system} onChange={(ev) => onChange({ system: ev.target.value }, "System")} />)}{F("DN", <Num v={e.dn} step={1} onChange={(n) => onChange({ dn: n }, "DN")} />)}{F("Beteckning", <input value={e.designation ?? ""} onChange={(ev) => onChange({ designation: ev.target.value }, "Beteckning")} />)}{F("Höjd över nivå", <Num v={e.elevation ?? 0} step={100} onChange={(n) => onChange({ elevation: n }, "Rörhöjd")} />)}{F("Isolering", <Num v={e.insulation ?? 0} onChange={(n) => onChange({ insulation: n }, "Isolering")} />)}</>;
      break;
    case "duct":
      specific = <>{F("System", <input value={e.system} onChange={(ev) => onChange({ system: ev.target.value }, "System")} />)}{F("Form", <select value={e.shape} onChange={(ev) => onChange({ shape: ev.target.value }, "Kanalform")}><option value="rect">{tr("Rektangulär")}</option><option value="round">{tr("Cirkulär")}</option></select>)}{e.shape === "rect" ? <>{F("Bredd", <Num v={e.w ?? 400} onChange={(n) => onChange({ w: n }, "Kanalbredd")} />)}{F("Höjd", <Num v={e.h ?? 200} onChange={(n) => onChange({ h: n }, "Kanalhöjd")} />)}</> : F("Diameter", <Num v={e.d ?? 250} onChange={(n) => onChange({ d: n }, "Diameter")} />)}{F("Höjd över nivå", <Num v={e.elevation ?? 0} step={100} onChange={(n) => onChange({ elevation: n }, "Kanalhöjd")} />)}</>;
      break;
    case "cable_tray": case "conduit":
      specific = <>{F("System", <input value={e.system} onChange={(ev) => onChange({ system: ev.target.value }, "System")} />)}{e.type === "cable_tray" ? <>{F("Bredd", <Num v={e.w} onChange={(n) => onChange({ w: n }, "Bredd")} />)}{F("Höjd", <Num v={e.h} onChange={(n) => onChange({ h: n }, "Höjd")} />)}</> : F("Diameter", <Num v={e.d} onChange={(n) => onChange({ d: n }, "Diameter")} />)}{F("Höjd över nivå", <Num v={e.elevation ?? 0} step={100} onChange={(n) => onChange({ elevation: n }, "Höjd")} />)}</>;
      break;
    case "equipment":
      specific = <>{F("Slag", <input value={e.kind} onChange={(ev) => onChange({ kind: ev.target.value }, "Slag")} />)}{F("System", <input value={e.system ?? ""} onChange={(ev) => onChange({ system: ev.target.value }, "System")} />)}{F("B × D × H", <span className="muted">{e.size.map((v) => Math.round(v)).join(" × ")}</span>)}{F("Anslutningar", <span className="muted">{e.connectors.map((c) => c.name).join(", ") || "–"}</span>)}</>;
      break;
    case "device": case "fitting":
      specific = <>{F("Slag", <input value={e.kind} onChange={(ev) => onChange({ kind: ev.target.value }, "Slag")} />)}{F("System", <input value={e.system ?? ""} onChange={(ev) => onChange({ system: ev.target.value }, "System")} />)}{F("Höjd", <Num v={e.p[0][2]} step={100} onChange={(n) => onChange({ p: [[e.p[0][0], e.p[0][1], n]] }, "Höjd")} />)}</>;
      break;
    case "text": case "mtext":
      specific = <>{<>{F("Text", <input value={e.text} onChange={(ev) => onChange({ text: ev.target.value }, "Text")} />)}{F("Höjd (mm på papper)", <Num v={e.h} step={0.5} onChange={(n) => onChange({ h: n }, "Texthöjd")} />)}{F("Vridning °", <Num v={e.rot ?? 0} step={15} onChange={(n) => onChange({ rot: n }, "Vridning")} />)}</>}{e.type === "text" && <>
        {F("Hänger på", <select value={e.ref?.id ?? ""} onChange={(ev) => onChange({ ref: ev.target.value ? { id: ev.target.value, field: e.ref?.field ?? "name" } : null }, "Text hänger på")}><option value="">{tr("– fri text –")}</option>{doc.entities.filter((x) => x.id !== e.id && x.type !== "text" && x.type !== "underlay").map((x) => <option key={x.id} value={x.id}>{qLabel(x.type)} {x.name ?? x.id}</option>)}</select>)}
        {e.ref && F("Visar", <select value={e.ref.field} onChange={(ev) => onChange({ ref: { ...e.ref, field: ev.target.value as TagField } }, "Text visar")}>{(["name", "number", "area", "length", "system", "dn", "level", "id"] as TagField[]).map((f) => <option key={f} value={f}>{{ name: "namn", number: "nummer", area: "area", length: "längd", system: "system", dn: "DN", level: "nivå", id: "id" }[f]}</option>)}</select>)}
      </>}</>;
      break;
    case "dim":
      specific = <>{F("Avstånd", <Num v={e.off} onChange={(n) => onChange({ off: n }, "Måttavstånd")} />)}{F("Mått", <span className="muted">{e.p.length >= 2 ? fmtMm(Math.hypot(e.p[1][0] - e.p[0][0], e.p[1][1] - e.p[0][1])) : ""}</span>)}</>;
      break;
    case "leader":
      specific = F("Text", <input value={e.text} onChange={(ev) => onChange({ text: ev.target.value }, "Text")} />);
      break;
    case "site":
      specific = F("Slag", <select value={e.kind} onChange={(ev) => onChange({ kind: ev.target.value }, "Slag")}>{["site_boundary", "property_boundary", "road", "path", "footprint", "spot", "other"].map((k) => <option key={k} value={k}>{k}</option>)}</select>);
      break;
    case "underlay":
      specific = <>
        {F("Skala", <span className="muted">{e.scale_state === "VERIFIED" ? "verifierad (läst handling)" : e.scale_state === "CALIBRATED" ? "uppmätt" : "saknas"}</span>)}
        {F("mm per pixel", <Num v={e.mm_per_px ?? null} step={0.01} onChange={(n) => onChange({ mm_per_px: n, scale_state: "CALIBRATED" }, "Underlagets skala")} />)}
        {F("Genomskinlighet", <Num v={Math.round((e.opacity ?? 0.6) * 100)} step={5} min={0} onChange={(n) => onChange({ opacity: Math.max(0, Math.min(1, n / 100)) }, "Underlag")} />)}
        {F("Vridning", <Num v={e.rot ?? 0} step={1} onChange={(n) => onChange({ rot: n }, "Underlag")} />)}
        {F("Kalibrera", <button className="secondary small" onClick={onCalibrate}>{tr("Två punkter")}</button>)}
        {e.source?.filename && F("Källa", <span className="muted small">{e.source.filename}{e.source.page != null ? ` s. ${e.source.page + 1}` : ""}</span>)}
      </>;
      break;
    case "mesh":
      specific = <>
        {F("Fil", <span className="muted small">{e.filename ?? e.asset} ({e.format})</span>)}
        {F("mm per enhet", <Num v={e.scale} step={1} onChange={(n) => onChange({ scale: n }, "Referensens skala")} />)}
        {F("Höjd (z)", <Num v={e.p[0][2]} onChange={(n) => onChange({ p: [[e.p[0][0], e.p[0][1], n]] }, "Referensens höjd")} />)}
        {F("Vridning", <Num v={e.rot ?? 0} step={1} onChange={(n) => onChange({ rot: n }, "Referens")} />)}
        {e.bounds && F("Låda", <span className="muted small">{((e.bounds.max[0] - e.bounds.min[0]) * e.scale / 1000).toFixed(2)} × {((e.bounds.max[2] - e.bounds.min[2]) * e.scale / 1000).toFixed(2)} × {((e.bounds.max[1] - e.bounds.min[1]) * e.scale / 1000).toFixed(2)} m</span>)}
      </>;
      break;
    default: break;
  }
  const isMep = e.type === "pipe" || e.type === "duct" || e.type === "cable_tray" || e.type === "conduit" || e.type === "equipment";
  const conns = isMep ? connections(doc).filter((c) => c.from === e.id || c.to === e.id) : [];
  const other = (c: { from: string; to: string }) => { const id = c.from === e.id ? c.to : c.from; const t = doc.entities.find((x) => x.id === id); return t ? `${t.name || qLabel(t.type)} (${t.id})` : id; };
  return (
    <div className="bcad-list">
      <div className="bcad-kind">{qLabel(e.type)} <span className="muted small">{e.id}</span></div>
      {specific}
      {isMep && F("Ansluter till", <span className="muted small">{conns.length ? conns.map((c) => `${other(c)}${c.via === "tee" ? " (T)" : c.via === "connector" ? " (anslutning)" : ""}`).join(", ") : "inget - änden sitter inte i något"}</span>)}
      {common}
      <p className="muted small">Ursprung: {e.provenance} · version {e.version}{e.updated_at ? ` · ${new Date(e.updated_at).toLocaleString(locale())}` : ""}</p>
    </div>
  );
}

function ToolDefaultsPanel({ tool, defaults, setDefaults, materials }: { tool: ToolId; defaults: ToolDefaults; setDefaults: (f: (d: ToolDefaults) => ToolDefaults) => void; materials: CadDocument["materials"] }) {
  const F = (label: string, node: any) => <div className="bcad-field"><label>{label}</label>{node}</div>;
  const set = (k: keyof ToolDefaults, patch: any) => setDefaults((d) => ({ ...d, [k]: { ...(d[k] as any), ...patch } }));
  const MatSel = (k: keyof ToolDefaults, v: string) => <select value={v} onChange={(ev) => set(k, { material: ev.target.value })}>{materials.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}</select>;
  const head = <p className="muted small">Inget valt. Det här är vad nästa {TOOLS.find((t) => t.id === tool)?.label.toLowerCase() ?? "objekt"} får.</p>;
  switch (tool) {
    case "vagg": case "glasfasad": return <div className="bcad-list">{head}{F("Tjocklek", <Num v={defaults.wall.thickness} onChange={(n) => set("wall", { thickness: n })} />)}{F("Höjd (tom = till nivån ovanför)", <Num v={defaults.wall.height} step={100} onChange={(n) => set("wall", { height: n || null })} />)}{F("Material", MatSel("wall", defaults.wall.material))}{F("Justering", <select value={defaults.wall.alignment} onChange={(ev) => set("wall", { alignment: ev.target.value })}><option value="centre">Centrum</option><option value="left">{tr("Vänster")}</option><option value="right">{tr("Höger")}</option></select>)}</div>;
    case "dorr": return <div className="bcad-list">{head}{F("Bredd", <Num v={defaults.door.width} onChange={(n) => set("door", { width: n })} />)}{F("Höjd", <Num v={defaults.door.height} onChange={(n) => set("door", { height: n })} />)}{F("Slag", <select value={defaults.door.swing} onChange={(ev) => set("door", { swing: ev.target.value })}><option value="left">{tr("Vänster")}</option><option value="right">{tr("Höger")}</option><option value="double">Par</option><option value="sliding">Skjut</option></select>)}</div>;
    case "fonster": return <div className="bcad-list">{head}{F("Bredd", <Num v={defaults.window.width} onChange={(n) => set("window", { width: n })} />)}{F("Höjd", <Num v={defaults.window.height} onChange={(n) => set("window", { height: n })} />)}{F("Bröstning", <Num v={defaults.window.sill} onChange={(n) => set("window", { sill: n })} />)}</div>;
    case "oppning": return <div className="bcad-list">{head}{F("Bredd", <Num v={defaults.opening.width} onChange={(n) => set("opening", { width: n })} />)}{F("Höjd", <Num v={defaults.opening.height} onChange={(n) => set("opening", { height: n })} />)}{F("Underkant", <Num v={defaults.opening.sill} onChange={(n) => set("opening", { sill: n })} />)}</div>;
    case "bjalklag": case "platta": return <div className="bcad-list">{head}{F("Tjocklek", <Num v={defaults.floor.thickness} onChange={(n) => set("floor", { thickness: n })} />)}{F("Material", MatSel("floor", defaults.floor.material))}</div>;
    case "tak": return <div className="bcad-list">{head}{F("Typ", <select value={defaults.roof.kind} onChange={(ev) => set("roof", { kind: ev.target.value })}><option value="flat">Platt</option><option value="pitched">Sadel</option></select>)}{F("Lutning °", <Num v={defaults.roof.slope_deg} step={1} onChange={(n) => set("roof", { slope_deg: n })} />)}{F("Tjocklek", <Num v={defaults.roof.thickness} onChange={(n) => set("roof", { thickness: n })} />)}{F("Material", MatSel("roof", defaults.roof.material))}</div>;
    case "undertak": return <div className="bcad-list">{head}{F("Höjd över nivå", <Num v={defaults.ceiling.height_offset} step={100} onChange={(n) => set("ceiling", { height_offset: n })} />)}{F("Tjocklek", <Num v={defaults.ceiling.thickness} onChange={(n) => set("ceiling", { thickness: n })} />)}</div>;
    case "rum": return <div className="bcad-list">{head}{F("Namn", <input value={defaults.room.name} onChange={(ev) => set("room", { name: ev.target.value })} />)}</div>;
    case "trappa": return <div className="bcad-list">{head}{F("Bredd", <Num v={defaults.stair.width} onChange={(n) => set("stair", { width: n })} />)}{F("Antal steg", <Num v={defaults.stair.risers} step={1} onChange={(n) => set("stair", { risers: Math.max(2, Math.round(n)) })} />)}{F("Stegdjup", <Num v={defaults.stair.tread_d} onChange={(n) => set("stair", { tread_d: n })} />)}</div>;
    case "pelare": return <div className="bcad-list">{head}{F("Bredd", <Num v={(defaults.column.profile as any).w ?? 300} onChange={(n) => set("column", { profile: { kind: "rect", w: n, d: (defaults.column.profile as any).d ?? 300 } })} />)}{F("Djup", <Num v={(defaults.column.profile as any).d ?? 300} onChange={(n) => set("column", { profile: { kind: "rect", w: (defaults.column.profile as any).w ?? 300, d: n } })} />)}{F("Material", MatSel("column", defaults.column.material))}</div>;
    case "balk": return <div className="bcad-list">{head}{F("Bredd", <Num v={(defaults.beam.profile as any).w ?? 300} onChange={(n) => set("beam", { profile: { kind: "rect", w: n, d: (defaults.beam.profile as any).d ?? 500 } })} />)}{F("Höjd", <Num v={(defaults.beam.profile as any).d ?? 500} onChange={(n) => set("beam", { profile: { kind: "rect", w: (defaults.beam.profile as any).w ?? 300, d: n } })} />)}{F("Material", MatSel("beam", defaults.beam.material))}</div>;
    case "grund": return <div className="bcad-list">{head}{F("Typ", <select value={defaults.foundation.kind} onChange={(ev) => set("foundation", { kind: ev.target.value })}><option value="strip">Sula</option><option value="isolated">Punktplint</option><option value="slab">Platta</option></select>)}{F("Bredd", <Num v={defaults.foundation.w} onChange={(n) => set("foundation", { w: n })} />)}{F("Höjd", <Num v={defaults.foundation.h} onChange={(n) => set("foundation", { h: n })} />)}</div>;
    case "ror": return <div className="bcad-list">{head}{F("System", <input value={defaults.pipe.system} onChange={(ev) => set("pipe", { system: ev.target.value })} />)}{F("DN", <Num v={defaults.pipe.dn} step={1} onChange={(n) => set("pipe", { dn: n })} />)}{F("Höjd över nivå", <Num v={defaults.pipe.elevation} step={100} onChange={(n) => set("pipe", { elevation: n })} />)}{F("Material", MatSel("pipe", defaults.pipe.material))}</div>;
    case "kanal": return <div className="bcad-list">{head}{F("System", <input value={defaults.duct.system} onChange={(ev) => set("duct", { system: ev.target.value })} />)}{F("Form", <select value={defaults.duct.shape} onChange={(ev) => set("duct", { shape: ev.target.value })}><option value="rect">{tr("Rektangulär")}</option><option value="round">{tr("Cirkulär")}</option></select>)}{defaults.duct.shape === "rect" ? <>{F("Bredd", <Num v={defaults.duct.w} onChange={(n) => set("duct", { w: n })} />)}{F("Höjd", <Num v={defaults.duct.h} onChange={(n) => set("duct", { h: n })} />)}</> : F("Diameter", <Num v={defaults.duct.d} onChange={(n) => set("duct", { d: n })} />)}{F("Höjd över nivå", <Num v={defaults.duct.elevation} step={100} onChange={(n) => set("duct", { elevation: n })} />)}</div>;
    case "kabelstege": return <div className="bcad-list">{head}{F("Bredd", <Num v={defaults.cable_tray.w} onChange={(n) => set("cable_tray", { w: n })} />)}{F("Höjd", <Num v={defaults.cable_tray.h} onChange={(n) => set("cable_tray", { h: n })} />)}{F("Höjd över nivå", <Num v={defaults.cable_tray.elevation} step={100} onChange={(n) => set("cable_tray", { elevation: n })} />)}</div>;
    case "elror": return <div className="bcad-list">{head}{F("Diameter", <Num v={defaults.conduit.d} onChange={(n) => set("conduit", { d: n })} />)}{F("Höjd över nivå", <Num v={defaults.conduit.elevation} step={100} onChange={(n) => set("conduit", { elevation: n })} />)}</div>;
    case "utrustning": return <div className="bcad-list">{head}{F("Slag", <input value={defaults.equipment.kind} onChange={(ev) => set("equipment", { kind: ev.target.value })} placeholder={tr("pump, LA, WC…")} />)}{F("System", <input value={defaults.equipment.system} onChange={(ev) => set("equipment", { system: ev.target.value })} />)}{F("Bredd", <Num v={defaults.equipment.size[0]} onChange={(n) => set("equipment", { size: [n, defaults.equipment.size[1], defaults.equipment.size[2]] })} />)}{F("Djup", <Num v={defaults.equipment.size[1]} onChange={(n) => set("equipment", { size: [defaults.equipment.size[0], n, defaults.equipment.size[2]] })} />)}{F("Höjd", <Num v={defaults.equipment.size[2]} onChange={(n) => set("equipment", { size: [defaults.equipment.size[0], defaults.equipment.size[1], n] })} />)}</div>;
    case "apparat": return <div className="bcad-list">{head}{F("Slag", <select value={defaults.device.kind} onChange={(ev) => set("device", { kind: ev.target.value })}>{["light", "outlet", "switch", "panel", "air_terminal", "sprinkler_head", "sensor", "other"].map((k) => <option key={k} value={k}>{k}</option>)}</select>)}{F("Höjd", <Num v={defaults.device.elevation} step={100} onChange={(n) => set("device", { elevation: n })} />)}</div>;
    case "text": return <div className="bcad-list">{head}{F("Text", <input value={defaults.text.text} onChange={(ev) => set("text", { text: ev.target.value })} />)}{F("Höjd (mm på papper)", <Num v={defaults.text.h} step={0.5} onChange={(n) => set("text", { h: n })} />)}</div>;
    case "hanvisning": return <div className="bcad-list">{head}{F("Text", <input value={defaults.leader.text} onChange={(ev) => set("leader", { text: ev.target.value })} />)}</div>;
    case "natlinje": return <div className="bcad-list">{head}{F("Beteckning", <input value={defaults.grid.label} onChange={(ev) => set("grid", { label: ev.target.value })} />)}</div>;
    case "terrang": return <div className="bcad-list">{head}{F("Höjd (mm)", <Num v={defaults.terrain.z} step={100} onChange={(n) => set("terrain", { z: n })} />)}</div>;
    default: return <div className="bcad-list">{head}</div>;
  }
}

function SectionSvg({ shapes }: { shapes: SectionShape[] }) {
  if (!shapes.length) return <p className="muted small">{tr("Ingenting i snittet.")}</p>;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const s of shapes) for (const [x, y] of s.poly) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  const pad = 500; const w = x1 - x0 + 2 * pad, h = y1 - y0 + 2 * pad;
  const fill: Record<string, string> = { wall: "#3a3a3a", curtain_wall: "#9fd3e8", floor: "#8a8f98", roof: "#a5533a", column: "#7048e8", beam: "#7048e8", foundation: "#6b6f75", pipe: "#1f6feb", duct: "#0b7285", cable_tray: "#b58900", conduit: "#b58900", door: "#c8a165", window: "#9fd3e8", stair: "#cfc6b8", ceiling: "#e6dfc8", equipment: "#5c7080" };
  return (
    <svg viewBox={`${x0 - pad} ${-(y1 + pad)} ${w} ${h}`} style={{ width: "100%", background: "#fff", border: "1px solid var(--line)" }}>
      {shapes.map((s, i) => <polygon key={i} points={s.poly.map(([x, y]) => `${x},${-y}`).join(" ")} fill={fill[s.kind] || "#999"} stroke="#222" strokeWidth={w / 400} opacity={s.kind === "window" || s.kind === "curtain_wall" ? 0.6 : 0.95} />)}
      <line x1={x0 - pad} y1={0} x2={x1 + pad} y2={0} stroke="#e8590c" strokeWidth={w / 500} strokeDasharray={`${w / 60} ${w / 120}`} />
    </svg>
  );
}
