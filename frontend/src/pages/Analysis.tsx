import { extension, withPipeExtensions } from "../live/gestures";
import type { DrawingAction } from "../live/LiveDrawingAgent";
import SourceAssignment from "../components/SourceAssignment";
import { Suspense, lazy, useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import AnalysisCompletionReveal from "../components/AnalysisCompletionReveal";
import DrawingTo3DTransition from "../components/DrawingTo3DTransition";
import PdfViewer, { Drawn, EditKind, InkVerdict, Layer, ViewerHandle } from "../components/PdfViewer";
import QuantityTable, { withFloorHeight } from "../components/QuantityTable";
import AnalysisFilm from "../components/AnalysisFilm";
import LearnWizard from "../components/LearnWizard";
import Boundary from "../components/Boundary";
import DrawingQuality from "../components/DrawingQuality";
import AnalysisQuality from "../components/AnalysisQuality";
import DrawingDeclarations from "../components/DrawingDeclarations";
import ReferenceComparison from "../components/ReferenceComparison";
import Markups, { type MarkDraft, type MarkTool } from "../components/Markups";
import Corrections, { Draft } from "../components/Corrections";
import LegendView from "../components/LegendView";
import Reasoning from "../components/Reasoning";
import { frontierColor, frontierText } from "../frontier";
import AgentChat from "../components/AgentChat";
import { StatusBadge, stageText } from "../components/Status";

// three.js är tungt och behövs först när någon vill se ritningen i 3D: hämtas då, inte vid sidladdning.
const LiveDrawingAgent = lazy(() => import("../live/LiveDrawingAgent"));
const Drawing3DView = lazy(() => import("../components/Drawing3DView"));


// why a label never got a line to follow, said the way a person reads a drawing

const LAYER_LABELS: Record<Layer, string> = { pipes: "Mätta rör", ambiguous: "Tvetydigt", claimed: "Påpekad men onämnd", unowned: "Oidentifierat", declined: "Bortvald geometri", designations: "Beteckningar", legend: "Förklaringslistan", leaders: "CAD-leaders", anchors: "Anslutningar", inWall: "I vägg (räknas ej)", frontiers: "Var rören slutar" };
const LAYER_HINTS: Record<Layer, string> = {
  pipes: "Sträckor som fått en identitet och en längd, en färg per beteckning",
  ambiguous: "Ritad linje som kunde tillhöra mer än en beteckning — mäts inte",
  claimed: "Ritad linje som en beteckning faktiskt pekar på, men som läsningen inte kunde ge till en enda identitet. Den mäts inte — men den finns på ritningen, så den göms inte heller. Håll pekaren över den för att se vilka beteckningar som gör anspråk.",
  unowned: "Ritad linje i en accepterad rörfamilj som ingen beteckning nådde. Avstängt från början: det är ett fynd att titta på, inte ett fel i mätningen.",
  declined: "Ritad linje läsningen tittade på och inte tog som rör, med skälet",
  designations: "Alla lästa beteckningar på bladet",
  legend: "Varje beteckning färgad efter vad handlingens förklaringslista säger att koden är: grönt rörsystem, orange komponent, grått material — och magenta streckat för en kod som inte står i listan alls. Listans egen ruta markeras där den står på bladet.",
  leaders: "Hänvisningslinjerna som ritningen drar från etikett till rör",
  anchors: "Där en beteckning faktiskt möter sitt rör",
  frontiers: "Varje kant på varje mätt rör, med skälet: grönt där röret slutar på rätt ställe (annan dimension, annat system, stigare, komponent, bladets kant), rött där läsningen sannolikt tappar meter (samma penna fortsätter utan namn, ett gap som inte överbryggades, byte av penna), orange där något lämnats öppet (tvetydig korsning). Det valda röret visar alltid sina kanter. Inget rör slutar tyst.",
  inWall: "Rör i vägg ritas alltid i det ej räknades färg — längden ligger utanför den horisontella mängden. Etiketter, hänvisningslinjer och anslutningar över en skrafferad yta ritas blekt; det här lagret lyfter fram dem. Ingenting läsningen hittade göms.",
};

export default function AnalysisPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [liveAgent, setLiveAgent] = useState(false);
  const lastLiveCorrection = useRef<string | null>(null);
  const live3d = useRef<{ motion: (dx: number, dy: number, factor: number) => void; fit: () => void; snapshot: () => string } | null>(null);
  const [job, setJob] = useState<any>(null);
  const [result, setResult] = useState<any>(null);
  const [pdf, setPdf] = useState<ArrayBuffer | null>(null);
  const [err, setErr] = useState("");

  const [actionErr, setActionErr] = useState("");
  const [learn, setLearn] = useState(false);
  const [tab, setTab] = useState<"mangder" | "agent" | "oversikt" | "artefakter" | "rattelser" | "markera">("mangder");
  // egna markeringar: verktyget som är laddat, det som ritas just nu, och det som redan sparats på sidan
  const [markTool, setMarkTool] = useState<MarkTool>(null);
  const [markDraft, setMarkDraft] = useState<MarkDraft>(null);
  const [markups, setMarkups] = useState<any[]>([]);
  // what the agent means by "this": the runs the reader has clicked, and the box they dragged
  const [agentIds, setAgentIds] = useState<string[]>([]);
  // The three things a reader comes here for, and they are not the same thing: what the drawing says its codes
  // mean, the sheet with the reading drawn on it, and how the reading got there. Each had to be dug out of the
  // side panel before; each is a view of its own now.
  const [view, setView] = useState<"forklaring" | "analys" | "resonemang">("analys");
  const [selIdent, setSelIdent] = useState<string | null>(null);
  const [selPipe, setSelPipe] = useState<any>(null);
  // Frågan som ska ligga i agentens ruta när man går dit från ett utpekat rör.
  const [agentAsk, setAgentAsk] = useState("");
  const [why, setWhy] = useState<any>(null);
  const [page, setPage] = useState(0);
  const liveContext = useRef({ id, page }); liveContext.current = { id, page };
  useEffect(() => { lastLiveCorrection.current = null; }, [id]);
  // The quantity table has more columns than any fixed panel width fits, so the split is the reader's to set:
  // wide drawing while tracing a run, wide table while reading the takeoff. The choice is remembered.
  const [corrections, setCorrections] = useState<any[]>([]);
  const [drawKind, setDrawKind] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState<boolean>(() => {
    try { return localStorage.getItem("vvs.panelOpen") !== "0"; } catch { return true; }
  });
  const setOpen = (v: boolean) => {
    setPanelOpen(v);
    try { localStorage.setItem("vvs.panelOpen", v ? "1" : "0"); } catch { /* private window */ }
  };
  const [draft, setDraft] = useState<Draft>(null);
  const [show3d, setShow3d] = useState(false);
  /* Skalan någon skriver in för ett blad vars egen stämpel inte räckte. Den startar en ny läsning - mängden
     räknas om från början under den skalan - i stället för att skala om en tabell efteråt, så att varje tal på
     skärmen fortsätter komma ur en och samma läsning. */
  const [ratio, setRatio] = useState("");
  const [rescaling, setRescaling] = useState(false);
  const [drawing, setDrawing] = useState<any>(null);
  const [rising, setRising] = useState(false);
  const [panel, setPanel] = useState<number>(() => {
    const v = Number((() => { try { return localStorage.getItem("vvs.panel"); } catch { return null; } })());
    return v >= 360 && v <= 1400 ? v : 480;
  });
  const dragging = useRef(false);
  const [nPages, setNPages] = useState(1);
  const [sheetBusy, setSheetBusy] = useState(false);
  const [floorHeight, setFloorHeight] = useState<string>(() => { try { return localStorage.getItem("vvs.floorHeight") ?? ""; } catch { return ""; } });
  const [includeHatched, setIncludeHatched] = useState<boolean>(() => { try { return localStorage.getItem("vvs.includeHatched") === "1"; } catch { return false; } });
  // Förklarade kopplingsledningar räknas med som förval: det är ritningens eget besked om dem. Valet finns för
  // den förteckning som prissätter dem per apparat eller mäter dem på ett annat blad.
  const [includeDeclared, setIncludeDeclared] = useState<boolean>(() => { try { return localStorage.getItem("vvs.includeDeclared") !== "0"; } catch { return true; } });
  const [riserSource, setRiserSource] = useState<string>(() => { try { return localStorage.getItem("vvs.riserSource") ?? "labels"; } catch { return "labels"; } });
  // the service's assumptions are the starting point; what this browser set for itself stays in front of them
  useEffect(() => {
    api.settings().then((s) => {
      try {
        if (localStorage.getItem("vvs.floorHeight") == null && s.floor_height_m != null) setFloorHeight(String(s.floor_height_m).replace(".", ","));
        if (localStorage.getItem("vvs.riserSource") == null && s.riser_source) setRiserSource(s.riser_source);
        if (localStorage.getItem("vvs.includeHatched") == null && s.include_hatched) setIncludeHatched(true);
        if (localStorage.getItem("vvs.includeDeclared") == null && s.include_declared === false) setIncludeDeclared(false);
      } catch { /* privat läge: tjänstens antaganden gäller rakt av */
        if (s.floor_height_m != null) setFloorHeight(String(s.floor_height_m).replace(".", ","));
        if (s.riser_source) setRiserSource(s.riser_source);
        setIncludeHatched(!!s.include_hatched);
        setIncludeDeclared(s.include_declared !== false);
      }
    }).catch(() => { /* utan svar gäller webbläsarens egna */ });
  }, []);
  // the export has to be given the same choices the table is showing, or the file states a different quantity
  const exportQuery = [
    floorHeight.trim() && !Number.isNaN(Number(floorHeight.replace(",", "."))) ? `floor_height=${Number(floorHeight.replace(",", "."))}` : "",
    includeHatched ? "include_hatched=true" : "",
    includeDeclared ? "" : "include_declared=false",
    `riser_source=${riserSource}`,
  ].filter(Boolean).join("&");
  const fh = floorHeight.trim() ? Number(floorHeight.replace(",", ".")) : NaN;
  const floorH = Number.isFinite(fh) && fh > 0 ? fh : null;
  // a row of the whole-document rollup counts its stacks from the same source the table and the export use
  const docRisers = (r: any) => Number((riserSource === "labels" ? r.riser_count_from_labels : r.riser_count) ?? 0);
  // The question a reader opens this page with is "did it get the pipes?", and that is a question about the
  // drawing with the reading on top of it - not about leaders, label boxes and attachment marks, which cover the
  // sheet so thickly that the runs underneath cannot be seen at all. They are diagnostics, and they start off.
  // The sheet opens showing what was measured. Ink the reading accepted as pipe but no label reached is a real
  // finding and has its own switch - shown first it reads as a fault, and a grey tangle over a good reading is
  // the fastest way to make a correct answer look wrong.
  const [layers, setLayers] = useState<Record<Layer, boolean>>({ pipes: true, ambiguous: true, claimed: true, unowned: false, declined: false, designations: false, legend: false, leaders: false, anchors: false, inWall: false, frontiers: false });
  // which bortvald family the reader is pointing at, so the sheet can show that ink and not all of it at once
  const selDeclined: string | null = null;
  const [layersOpen, setLayersOpen] = useState(false);
  // what the reading made of the ink the reader last pointed at - "varför är det röret inte markerat?"
  const [ink, setInk] = useState<InkVerdict | null>(null);
  const [artifacts, setArtifacts] = useState<any[]>([]);
  const viewer = useRef<ViewerHandle>(null);

  useEffect(() => {
    let t: any; let loaded = false; let active = true;
    setJob(null); setResult(null); setPdf(null); setErr(""); setActionErr(""); setPage(0);
    setSelPipe(null); setSelIdent(null); setWhy(null); setDrawing(null);
    setCorrections([]); setArtifacts([]); setMarkups([]);
    const poll = async () => {
      try {
        const j = await api.job(id!); if (!active) return; setJob(j);
        if (j.status === "COMPLETED") {
          if (!loaded) {
            const [r, b, arts, dr, corr] = await Promise.all([
              api.result(id!), api.fetchBlob(api.fileUrl(j.drawing_id)).then(b => b.arrayBuffer()),
              api.artifacts(id!), api.drawing(j.drawing_id).catch(() => null),
              api.corrections(j.drawing_id).catch(() => []),
            ]);
            if (!active) return;
            loaded = true; setResult(r); setPage(r.page?.page ?? r.pages?.[0] ?? 0);
            setPdf(b); setArtifacts(arts); setDrawing(dr); setCorrections(corr);
          }
        } else if (j.status !== "FAILED") t = setTimeout(poll, 1500);
      } catch (e: any) { if (active) setErr(e.message); }
    };
    poll();
    return () => { active = false; clearTimeout(t); };
  }, [id]);

  /* Bladet byts: läsningen av det bladet hämtas.
   *
   * Rören, etiketterna, hänvisningslinjerna och det avvisade bläcket är fakta om ett blad, och en handling kan
   * vara tjugosex blad i en fil. Förr låg bara det första bladets läsning i svaret, så en handling där blad ett
   * är en försättssida visade ingenting alls fast fyrahundra meter var uppmätta bakom den. Nu hämtas bladet man
   * står på, och den utpekning som väntade på det görs när det kommit fram. */
  const wantBox = useRef<{ page: number; bbox: number[] } | null>(null);
  useEffect(() => {
    if (!result || !job || job.status !== "COMPLETED") return;
    if ((result.page?.page ?? 0) === page) return;
    let levande = true;
    setSheetBusy(true);
    api.result(id!, page)
      .then((r) => { if (levande) setResult(r); })
      .catch((e: any) => { if (levande) setErr(e.message); })
      .finally(() => { if (levande) setSheetBusy(false); });
    return () => { levande = false; };
  }, [page, job?.status, id, job, result]);

  // den utpekning som väntade på sitt blad görs när bladets läsning kommit fram
  useEffect(() => {
    const w = wantBox.current;
    if (!w || !result || (result.page?.page ?? 0) !== w.page) return;
    wantBox.current = null;
    viewer.current?.zoomTo(w.bbox);
  }, [result]);

  /** A run's extent on the sheet, from the geometry it carries. The pipe record has never had a box of its
      own, so every "go to this run" in the application was quietly doing nothing at all. */
  const boxOf = (p: any): number[] | null => {
    const xs: number[] = [], ys: number[] = [];
    for (const line of (p?.geometry ?? [])) for (const [x, y] of line) { xs.push(x); ys.push(y); }
    return xs.length ? [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)] : null;
  };

  /** The whole of one identity on one page, so picking a row shows the run rather than a corner of it. */
  const spanOf = (rows: any[]): number[] | null => {
    const bs = rows.map(boxOf).filter(Boolean) as number[][];
    if (!bs.length) return null;
    return [Math.min(...bs.map((b: number[]) => b[0])), Math.min(...bs.map((b: number[]) => b[1])),
            Math.max(...bs.map((b: number[]) => b[2])), Math.max(...bs.map((b: number[]) => b[3]))];
  };

  /** Go to a run the reader picked: onto its page if it is on another one, then to the run itself. */
  const goTo = (bbox: number[] | null, onPage: number) => {
    if (!bbox) return;
    if (onPage !== page) {
      // bladets egen läsning hämtas först; utpekningen görs när den kommit fram, inte efter en gissad väntan
      wantBox.current = { page: onPage, bbox };
      setPage(onPage);
    } else {
      viewer.current?.zoomTo(bbox);
    }
  };

  /* Ett klick pekar ut, ett klick till släpper taget.
   *
   * Att klicka på ett rör zoomar in på det och färgar resten av bladet ned. Utan en väg tillbaka satt man kvar
   * i det: enda sättet ut var att leta rätt på knappen "Sida". Nu är samma klick vägen ut - trycker man på det
   * rör man redan står på släpps markeringen och bladet läggs tillbaka som det låg innan. */
  const onPipeClick = async (p: any) => {
    if (selPipe && selPipe.physical_pipe_id === p.physical_pipe_id) {
      setSelPipe(null); setSelIdent(null); setWhy(null);
      viewer.current?.fitPage();
      return;
    }
    setSelPipe(p); setSelIdent(p.identity);
    // while correcting, the click picks the run to correct: staying on the takeoff tab would hide the tools
    if (tab !== "rattelser") setTab("mangder");
    goTo(boxOf(p), p.page ?? 0);
    try { setWhy(await api.why(id!, p.physical_pipe_id)); } catch { setWhy(null); }
  };

  /** Picking a designation goes to everything it owns, on the page that holds most of it. */
  const onIdentityPick = (key: string | null) => {
    // samma sak för beteckningen: trycker man på den man redan står på läggs bladet tillbaka som det låg
    if (key && key === selIdent && !selPipe) {
      setSelIdent(null); setWhy(null);
      viewer.current?.fitPage();
      return;
    }
    setSelIdent(key); setSelPipe(null); setWhy(null);
    if (!key || !result) return;
    const mine = result.pipes.filter((p: any) => p.identity === key);
    if (!mine.length) return;
    const counts = new Map<number, number>();
    for (const p of mine) counts.set(p.page ?? 0, (counts.get(p.page ?? 0) ?? 0) + 1);
    const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0][0];
    goTo(spanOf(mine.filter((p: any) => (p.page ?? 0) === best)), best);
  };
  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!dragging.current) return;
      e.preventDefault();
      setPanel(Math.min(Math.max(window.innerWidth - e.clientX, 300), Math.max(window.innerWidth - 420, 300)));
    };
    const up = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.classList.remove("resizing");
      try { localStorage.setItem("vvs.panel", String(panel)); } catch { /* private window */ }
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
  }, [panel]);

  const dl = async (path: string, name: string) => { const b = await api.fetchBlob(path); const a = document.createElement("a"); a.href = URL.createObjectURL(b); a.download = name; a.click(); };

  if (err) return <main><p className="error">{err}</p></main>;
  if (!job) return <main>{tr("Laddar…")}</main>;
  if (job.status !== "COMPLETED") {
    /* The reading takes a minute or two, and it is one of the few times somebody sits still in front of the
       tool. So the wait is offered as something else - but as a guide laid over the reading, not instead of it:
       the film keeps running behind the panel, and closing it costs nothing. */
    return (
      <main>
        <p className="crumb"><Link to={`/drawings/${job.drawing_id}`}>Ritning</Link> {tr("/ Analys")}</p>
        <div className="head">
          <div>
            <h1>{tr("Läser ritningen")}</h1>
            <p className="lead">{stageText(job.stage) || job.stage}</p>
          </div>
          <div className="row">
            <button onClick={() => setLearn(true)}>{tr("Lär mig om VVS")}</button>
            <StatusBadge job={job} />
          </div>
        </div>
        <div className="rule" style={{ marginBottom: 26 }} />
        {job.status === "FAILED"
          ? <pre className="error">{job.error}</pre>
          : <AnalysisFilm jobId={id!} stage={job.stage} progress={job.progress} />}
        <LearnWizard open={learn} onClose={() => setLearn(false)} />
      </main>
    );
  }
  if (!result) return <main>{tr("Laddar resultat…")}</main>;
  const c = result.coverage;
  const displayedPage = result.page?.page ?? page;
  const pipesOnPage = result.pipes.filter((p: any) => p.page === displayedPage);
  /* How much of what the drawing names ended up with a metre.
   *
   * The warning used to divide verified attachments by every designation on the sheet, and most of those are
   * not runs at all - legend rows, component tags, drawing numbers in the title block. A sheet the reading got
   * all the way through could still show "133 of 190" and read as half-failed. This counts only the names the
   * sheet's own list says are pipes, against the ones the takeoff carries metres for. */
  const nm = c.named_vs_measured ?? {};
  const namedShare: number | null = typeof nm.share === "number" ? nm.share : null;
  const covWarn = namedShare !== null && namedShare < 0.6;
  /* Utan fastställd skala finns inga meter. Då är "0 av 12 fick meter" och "0 m ritat rör" sant om siffrorna
   * och falskt om bladet: rören ÄR lästa, de går bara inte att räkna om till meter förrän någon säger vad
   * bladet är ritat i. Den skillnaden ska stå i klartext, inte gömmas bakom nollor. */
  const noScale = nm.scale_settled === false || nm.drawn_m == null;
  /* Someone else's marks on the sheet. A drawing that arrives with a takeoff already drawn on it in coloured
   * polylines carries somebody's answer on top of the drawing, and the reading takes that ink off before it
   * reads - otherwise it would measure an opinion of the drawing and hand it back as the drawing. That is worth
   * saying out loud: whoever uploaded the file may not know the marks are in it, and may want them counted. */
  const markup = nm.markup_set_aside ?? null;
  const setDoc = result.document ?? null;
  const nSheets = setDoc?.totals?.sheets ?? 1;
  const viewtabs = (
    <div className="viewtabs">
      <button className={view === "forklaring" ? "active" : ""} onClick={() => setView("forklaring")}>
        Förklaringslista{result.legend?.entries?.length ? ` (${result.legend.entries.length})` : ""}
      </button>
      <button className={view === "analys" ? "active" : ""} onClick={() => setView("analys")}>Analys</button>
      <button className={view === "resonemang" ? "active" : ""} onClick={() => setView("resonemang")}>{tr("Agenternas resonemang")}</button>
      <span className="spacer" />
      <StatusBadge job={job} />
    </div>
  );
  if (view === "forklaring") {
    return (
      <div className="workspace">
        {viewtabs}
        <LegendView legend={result.legend ?? { entries: [] }} designations={result.designations}
          quantities={result.quantities} />
      </div>
    );
  }
  if (view === "resonemang") {
    return (
      <div className="workspace">
        {viewtabs}
        <Reasoning jobId={id!} result={result} onZoom={(b) => { setView("analys"); setTimeout(() => viewer.current?.zoomTo(b), 60); }} />
      </div>
    );
  }
  return (
    <AnalysisCompletionReveal status={job.status === "COMPLETED" ? "completed" : job.status === "FAILED" ? "failed" : "processing"}
      label={`Analys klar · ${result.quantities.length} beteckningar`}>
    <div className={`workspace${rising ? " rising" : ""}`}>
    {liveAgent && <Suspense fallback={<div className="live-agent">Laddar samtalsagent…</div>}>
      <LiveDrawingAgent key={id} jobId={id!} onClose={() => setLiveAgent(false)}
        onMotion={m => {
          if (show3d) live3d.current?.motion(m.dx, m.dy, m.factor);
          else { viewer.current?.panBy(m.dx, m.dy); if (m.factor !== 1) viewer.current?.zoomBy(m.factor); }
        }}
        execute={async (args: DrawingAction) => {
          const a = args?.action;
          if (show3d && ['zoom', 'pan', 'fit', 'snapshot'].includes(a) && !live3d.current) throw new Error('3D-vyn laddas fortfarande. Försök igen strax.');
          const finite = (v: unknown, min: number, max: number) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
          if (a === 'context') return { page, view: show3d ? '3D' : '2D', selected: selPipe,
            quantities: result.quantities, corrections: corrections.filter(c => !c.undone),
            pipes: result.pipes.map((p: any) => ({ pipe_id: p.physical_pipe_id, designation: p.designation, page: p.page })),
            caution: 'Automatisk analys, inte verifierat facit. Korrigeringar är separata från originalgeometrin.' };
          if (a === 'snapshot') return { image: show3d ? live3d.current?.snapshot() : viewer.current?.snapshot(), page, view: show3d ? '3D' : '2D' };
          if (a === 'view3d') { setShow3d(true); setRising(true); return { ok: true, view: '3D' }; }
          if (a === 'view2d') { setShow3d(false); setRising(false); setView('analys'); return { ok: true, view: '2D' }; }
          if (a === 'fit') { if (show3d) live3d.current?.fit(); else viewer.current?.fitPage(); return { ok: true }; }
          if (a === 'zoom' && finite(args.factor, 0.25, 4)) {
            if (show3d) live3d.current?.motion(0, 0, args.factor!); else viewer.current?.zoomBy(args.factor!);
            return { ok: true };
          }
          if (a === 'pan' && finite(args.dx ?? 0, -2000, 2000) && finite(args.dy ?? 0, -2000, 2000)) {
            if (show3d) live3d.current?.motion(args.dx ?? 0, args.dy ?? 0, 1); else viewer.current?.panBy(args.dx ?? 0, args.dy ?? 0);
            return { ok: true };
          }
          if (a === 'select') {
            const p = result.pipes.find((p: any) => p.physical_pipe_id === args.pipe_id && (p.page ?? 0) === page);
            if (!p) throw new Error('Röret finns inte på aktuellt blad.');
            setSelPipe(p); setSelIdent(p.identity); const box = boxOf(p); if (box) viewer.current?.zoomTo(box); return { ok: true, selected: p.physical_pipe_id };
          }
          if (a === 'extend') {
            if (!args.pipe_id || args.pipe_id !== selPipe?.physical_pipe_id) throw new Error('Läs aktuellt urval först och ange dess pipe_id.');
            const extensions = corrections
              .filter(c => !c.undone && c.kind === 'extend' && c.payload?.pipe_id === selPipe.physical_pipe_id && c.page === page)
              .map(c => c.payload.points);
            const extended = { ...selPipe, extensions, geometry: [...(selPipe.geometry ?? []), ...extensions] };
            const payload = { ...extension(extended, page, args.meters!, args.direction!, result.scale?.meters_per_pdf_point), pipe_id: selPipe.physical_pipe_id };
            const saved = await api.addCorrection(job.drawing_id, { kind: 'extend', designation: selPipe.designation ?? selPipe.identity,
              page, payload, note: 'Förlängning via samtalsagent', job_id: id });
            lastLiveCorrection.current = saved.id;
            if (liveContext.current.id !== id || liveContext.current.page !== page) return { ok: true, correction_id: saved.id, meters: payload.meters, page };
            setCorrections(await api.corrections(job.drawing_id)); setResult(await api.result(id!, page));
            setShow3d(false); setRising(false); setView('analys'); setTab('rattelser'); setOpen(true);
            return { ok: true, correction_id: saved.id, meters: payload.meters, original_unchanged: true, undo_available: true };
          }
          if (a === 'undo') {
            if (!lastLiveCorrection.current) throw new Error('Det finns ingen agentförlängning att ångra i detta samtal.');
            await api.undoCorrection(job.drawing_id, lastLiveCorrection.current); lastLiveCorrection.current = null;
            setCorrections(await api.corrections(job.drawing_id)); setResult(await api.result(id!, page)); return { ok: true };
          }
          throw new Error('Kommandot eller dess värden stöds inte.');
        }} />
    </Suspense>}
    {show3d && (
      <DrawingTo3DTransition onDone={() => setRising(false)}>
        <Suspense fallback={<div className="d3-wrap"><div className="d3-loading"><span /></div></div>}>
          <Drawing3DView controlRef={live3d} result={withPipeExtensions(result, corrections)} title={drawing?.filename?.replace(/\.pdf$/i, "") ?? undefined}
            onClose={() => { setShow3d(false); setRising(false); }} />
        </Suspense>
      </DrawingTo3DTransition>
    )}
    {viewtabs}
    <div className={`analysis${panelOpen ? "" : " closed"}`}
      style={{ gridTemplateColumns: `minmax(0, 1fr) 6px ${panel}px` }}>
      <div className="left">
        {!panelOpen && (
          <button className="secondary small reopen" onClick={() => setOpen(true)}>{tr("Visa mängder")}</button>
        )}
        {/* One line of controls, because every line here is a line the drawing does not get. The eight layer
            switches used to wrap onto a second row and push the sheet down the page; they live behind one
            control now, which says how many are on. */}
        <div className="toolbar">
          <Link to={`/drawings/${job.drawing_id}`} className="back">{tr("← Ritning")}</Link>
          <span className="seg zoomseg">
            <button onClick={() => viewer.current?.zoomOut()} title={tr("Zooma ut")}>−</button>
            <button onClick={() => viewer.current?.zoomIn()} title={tr("Zooma in")}>+</button>
            <button onClick={() => viewer.current?.fitPage()} title={tr("Hela sidan")}>Sida</button>
            <button onClick={() => viewer.current?.fitWidth()} title={tr("Full bredd")}>Bredd</button>
          </span>
          <button className="secondary small" onClick={() => viewer.current?.fullscreen()}>{tr("Helskärm")}</button>
          <button className="small d3-open" title={tr("Res ritningen till en byggnad")}
            onClick={() => { setRising(true); setShow3d(true); }}>{tr("Visa i 3D")}</button>
          <button className="secondary small" onClick={() => setLiveAgent(true)}>Samtalsagent</button>
          {sheetBusy && <span className="muted small">{tr("Läser bladet…")}</span>}
          {nPages > 1 && <select value={page} disabled={sheetBusy} onChange={(e) => {
            // the selected run belongs to the page it was found on; carrying it across would put its ends,
            // and any correction dragged from them, on geometry that is not it
            setPage(Number(e.target.value)); setSelPipe(null); setWhy(null);
          }}>{(result.pages ?? [page]).map((i: number) => <option key={i} value={i}>Sida {i + 1}</option>)}</select>}
          {result.skipped_pages?.length > 0 && <span className="badge warn" title={result.skipped_pages.map((p: any) => `${p.page + 1}: ${p.mode}`).join(", ")}>
            {tr("Blad utan analys")}: {result.skipped_pages.map((p: any) => p.page + 1).join(", ")}
          </span>}
          <span className="spacer" />
          <div className="layerpop">
            <button className={`secondary small${layersOpen ? " on" : ""}`} onClick={() => setLayersOpen(!layersOpen)}>
              Lager · {(Object.keys(LAYER_LABELS) as Layer[]).filter((l) => layers[l]).length}
            </button>
            {layersOpen && (
              <div className="pop" onMouseLeave={() => setLayersOpen(false)}>
                {(Object.keys(LAYER_LABELS) as Layer[]).map((l) => (
                  <label key={l} title={LAYER_HINTS[l]}>
                    <input type="checkbox" checked={layers[l]} onChange={(e) => setLayers({ ...layers, [l]: e.target.checked })} />
                    <span>{LAYER_LABELS[l]}</span>
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>
        <Boundary what="ritningsvyn"><PdfViewer ref={viewer} data={pdf} page={displayedPage} pipes={pipesOnPage} ambiguous={result.ambiguous_geometry} unowned={result.unowned_geometry} claimed={result.claimed_geometry ?? []}
          designations={result.designations} legend={result.legend ?? null} leaders={result.leaders} anchors={result.anchors} hatched={result.hatched_geometry ?? []} selectedIdentity={selIdent}
          declined={[...(result.declined_geometry?.families ?? []), ...(result.declined_geometry?.unconsidered ?? [])]} selectedDeclined={selDeclined}
          selectedPipe={selPipe?.physical_pipe_id ?? null} layers={layers} onPipeClick={onPipeClick} onPageCount={setNPages}
          ink={ink} onInkClick={setInk}
          editKind={(tab === "markera"
            ? (markTool ? "draw" : null)
            : (drawKind === "extend" || drawKind === "draw" || drawKind === "erase" ? drawKind : null)) as EditKind}
          markups={markups}
          editPipe={selPipe} meterPerPt={result.scale?.meters_per_pdf_point ?? null}
          onDrawn={(d: Drawn) => tab === "markera"
            ? setMarkDraft({ points: d.points, meters: d.meters })
            : setDraft({ points: d.points, meters: d.meters, hits: d.hits })}
          corrections={corrections.filter((c: any) => !c.undone && c.page === page)} /></Boundary>
      </div>
      <div className="splitter" role="separator" aria-orientation="vertical" aria-label={tr("Dra för att ändra bredd")}
        onMouseDown={() => { dragging.current = true; document.body.classList.add("resizing"); }}
        onDoubleClick={() => setPanel(380)} />
      {/* the chat is a conversation, so it fills its column and scrolls inside itself; every other tab is a
          document and scrolls the column */}
      <div className={`right${tab === "agent" ? " agentmode" : ""}`}>
        <div className="panelbar">
          <button className="ghost small" onClick={() => setPanel(Math.max(300, panel - 120))}
            title="Smalare">−</button>
          <button className="ghost small" onClick={() => setPanel(Math.min(Math.max(window.innerWidth - 420, 300), panel + 120))}
            title="Bredare">+</button>
          <button className="ghost small" onClick={() => setPanel(380)} title={tr("Återställ bredden")}>{tr("Återställ")}</button>
          <span className="spacer" />
          <button className="ghost small" onClick={() => setOpen(false)} title={tr("Stäng fältet")}>{tr("Stäng ✕")}</button>
        </div>
        <div className="tabs">
          <button className={tab === "mangder" ? "active" : ""} onClick={() => setTab("mangder")}>{tr("Mängder")}</button>
          <button className={tab === "agent" ? "active" : ""} onClick={() => setTab("agent")}>Agent</button>
          <button className={tab === "rattelser" ? "active" : ""} onClick={() => setTab("rattelser")}>
            Rätta{corrections.filter((c: any) => !c.undone).length ? ` (${corrections.filter((c: any) => !c.undone).length})` : ""}
          </button>
          <button className={tab === "markera" ? "active" : ""} onClick={() => setTab("markera")}>Markera</button>
          <button className={tab === "oversikt" ? "active" : ""} onClick={() => setTab("oversikt")}>{tr("Översikt")}</button>
          <button className={tab === "artefakter" ? "active" : ""} onClick={() => setTab("artefakter")}>Export</button>
          <Link className="tabs-cta" to={`/jobs/${id}/kalkyl`} title={tr("Kalkylera mängderna: material, normtid, pris och anbud")}>{tr("Kalkylera →")}</Link>
        </div>
        {tab === "mangder" && (
          <div className="card">
            <SourceAssignment report={result.source_assignment} />
            <div className="row" style={{ marginBottom: 18 }}>
              <button className="secondary small" disabled={rescaling} onClick={async () => {
                setRescaling(true); setActionErr("");
                try { const j = await api.analyze(job.drawing_id, undefined, page, "combined", "auto"); navigate(`/jobs/${j.id}`); }
                catch (e: any) { setActionErr(e.message); } finally { setRescaling(false); }
              }}>{tr("Analysera ritningen")}</button>
            </div>
            <AnalysisQuality quality={result.quality} />
            {actionErr && <p className="error" role="alert">{actionErr}</p>}
            {job?.motor?.foraldrad && (
              <p className="badge warn">
                {tr("Motorns programkod har ändrats sedan den här analysen gjordes. Resultatet räknas inte om automatiskt. Läs om bladet för att använda den aktuella motorn.")}
                <button className="small" style={{ marginLeft: 10 }} disabled={rescaling}
                  onClick={async () => {
                    setRescaling(true); setActionErr("");
                    try {
                      const nj = await api.analyze(job.drawing_id, undefined, page, "combined", "auto");
                      navigate(`/jobs/${nj.id}`);
                    } catch (e: any) { setActionErr(e.message); } finally { setRescaling(false); }
                  }}>{rescaling ? "Läser om…" : "Läs om"}</button>
              </p>
            )}
            {markup && (
              <p className={`badge${markup.removed ? "" : " warn"}`}>
                {markup.removed
                  ? `Bladet innehåller ${markup.n} PDF-annoteringar från ${Object.keys(markup.authors ?? {}).join(", ") || "okänd källa"}`
                    + `${markup.ink_m ? ` med ${markup.ink_m} m markerade linjer` : ""}. Annoteringarna ingår inte i mängden. `
                    + "Ritningens ursprungliga text och geometri analyseras separat."
                  : `Bladet bär ${markup.n} markeringar som inte gick att lyfta av: ${markup.why}.`}
              </p>
            )}
            {noScale ? (
              <>
                <p className="badge bad">
                  {`Bladets skala är inte fastställd${nm.scale_reason ? ` (${nm.scale_reason})` : ""}, så ingen sträcka `
                    + "kan ges i meter. Läsningen hittade rören - de ligger ritade på bladet - men ett mått kräver "
                    + "att någon vet vad bladet är ritat i. Skriv in skalan här, så läses bladet om under den."}
                </p>
                <div className="row" style={{ gap: 8, alignItems: "center", margin: "10px 0 4px" }}>
                  <label className="small muted" htmlFor="skala">Skala 1:</label>
                  <input id="skala" className="small" style={{ width: 90 }} inputMode="numeric" value={ratio}
                    placeholder="50" onChange={(e) => setRatio(e.target.value.replace(/[^0-9]/g, ""))} />
                  <button className="small" disabled={!ratio || rescaling}
                    onClick={async () => {
                      setRescaling(true); setActionErr("");
                      try {
                        const nj = await api.analyze(job.drawing_id, Number(ratio), page);
                        navigate(`/jobs/${nj.id}`);
                      } catch (e: any) { setActionErr(e.message); } finally { setRescaling(false); }
                    }}>{rescaling ? "Läser om…" : "Läs om med den skalan"}</button>
                  <span className="muted small">
                    Metrarna heter då angiven skala, inte bekräftad: de vilar på ditt besked, inte på bladets.
                  </span>
                </div>
              </>
            ) : covWarn && (
              <p className="badge warn">
                {`${nm.pipe_names_with_metres} av ${nm.pipe_names} rörbeteckningar som ritningen skriver ut fick meter `
                  + `(${Math.round((namedShare ?? 0) * 100)} %). Av ${nm.drawn_m} m möjlig rörgeometri bar `
                  + `${nm.confirmed_m} m en identitet och ${nm.unowned_m} m ingen alls. Det som ingen `
                  + "beteckning namngav ligger grått på ritningen."}
              </p>
            )}
            {c.unowned_outside_hatch_m != null && <p className="muted small">
              {tr("Oidentifierad rörgeometri utanför skrafferade områden")}: {c.unowned_outside_hatch_m} m.
              {" "}{tr("Oidentifierad rörgeometri inom skrafferade områden")}: {c.unowned_in_hatch_m} m.
              {" "}{tr("Skrafferad geometri undantas enligt källreglerna. Detta verifierar inte hela ritningens träffsäkerhet.")}
            </p>}
            {nSheets > 1 && (
              <details className="settings" open>
                <summary>
                  Hela handlingen <span className="muted">· {nSheets} blad · {setDoc.totals.confirmed_horizontal_m} m
                    horisontellt · {setDoc.rows.reduce((t: number, r: any) => t + docRisers(r), 0)} stigare
                    · {setDoc.totals.designations} beteckningar</span>
                </summary>
                <div className="body">
                  <p className="muted">
                    Tabellen nedan är det här bladet. Handlingen som helhet står här: samma beteckning summerad
                    över de blad den står på.
                  </p>
                  <div className="tablewrap">
                    <table className="legendtable">
                      <thead>
                        <tr><th>Beteckning</th><th>DN</th><th className="num">Horisontellt</th>
                          <th className="num">Stigare</th><th className="num">Vertikalt</th>
                          <th className="num">{tr("Rör")}</th><th>Blad</th></tr>
                      </thead>
                      <tbody>
                        {setDoc.rows.map((r: any) => (
                          <tr key={`${r.designation}/${r.dn}`}>
                            <td><b>{r.designation}</b></td>
                            <td>{r.dn ?? <span className="muted">–</span>}</td>
                            <td className="num">{r.confirmed_horizontal_m.toFixed(2)}</td>
                            {/* the stacks the sheets state, and the metres they become once a floor height is given */}
                            <td className="num">{docRisers(r) || <span className="muted">–</span>}</td>
                            <td className="num">{(() => {
                              const v = r.confirmed_vertical_m + (floorH ? docRisers(r) * floorH : 0);
                              return v ? v.toFixed(2) : <span className="muted">–</span>;
                            })()}</td>
                            <td className="num">{r.physical_pipe_count}</td>
                            <td className="muted">{r.sheets.map((n: number) => n + 1).join(", ")}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {setDoc.sheets_without_a_settled_scale?.length > 0 && (
                    <p className="badge warn">
                      {`${setDoc.sheets_without_a_settled_scale.length} blad har ingen fastställd skala och bär `
                        + "därför inga meter i summan: blad "
                        + setDoc.sheets_without_a_settled_scale.map((x: any) => x.page + 1).join(", ")}
                    </p>
                  )}
                </div>
              </details>
            )}
            {/* Two settings and a paragraph explaining them used to stand between the reader and the numbers they
                came for. They are still one click away, and the summary line says what they are set to. */}
            <details className="settings">
              <summary>
                Antaganden <span className="muted">· våningshöjd {floorHeight ? `${floorHeight} m` : "ej satt"} · stigare ur
                  {riserSource === "labels" ? " etiketter" : " ritade symboler"}</span>
              </summary>
              <div className="body">
                <label>Våningshöjd för stigare (m)
                  <input style={{ width: 84 }} value={floorHeight} placeholder={tr("t.ex. 2,8")}
                    onChange={(e) => { setFloorHeight(e.target.value); try { localStorage.setItem("vvs.floorHeight", e.target.value); } catch { /* private window: the setting just does not persist */ } }} /></label>
                <label>Stigare räknas från
                  <select value={riserSource} onChange={(e) => { setRiserSource(e.target.value); try { localStorage.setItem("vvs.riserSource", e.target.value); } catch { /* private window: the setting just does not persist */ } }}>
                    <option value="labels">{tr("etiketter med dimension på raden under")}</option>
                    <option value="symbols">{tr("ritade stigarsymboler")}</option>
                  </select></label>
                <p className="muted">Vertikalt = antal stigare × våningshöjd; ritningen anger ingen höjd. Rör i
                  skrafferade ytor mäts alltid men räknas in bara om du kryssar i rutan nedan.</p>
              </div>
            </details>
            <QuantityTable rows={result.quantities} selected={selIdent} onSelect={onIdentityPick} floorHeight={floorH}
              pipes={result.pipes} meterPerPt={result.scale?.meters_per_pdf_point ?? null} onPipeClick={onPipeClick}
              includeHatched={includeHatched} onIncludeHatched={(v) => { setIncludeHatched(v); try { localStorage.setItem("vvs.includeHatched", v ? "1" : "0"); } catch { /* private window: the setting just does not persist */ } }}
              includeDeclared={includeDeclared} onIncludeDeclared={(v) => { setIncludeDeclared(v); try { localStorage.setItem("vvs.includeDeclared", v ? "1" : "0"); } catch { /* privat läge: valet gäller bara den här sessionen */ } }}
              riserSource={riserSource} />
            {why && (
              <div style={{ marginTop: 12 }}>
                <h4>Varför? {why.pipe.designation} DN{why.pipe.dn ?? "?"} · {typeof why.pipe.horizontal_m === "number" ? `${why.pipe.horizontal_m.toFixed(2)} m` : "ingen skala"}</h4>
                <p className="muted">Rör-id {why.pipe.physical_pipe_id} · {why.pipe.raw_pt.toFixed(1)} pt + {why.pipe.bridged_gap_pt.toFixed(1)} pt överbryggade mikrogap · {why.pipe.source_path_ids.length} PDF-objekt</p>
                {/* Vägen från det utpekade röret till agenten. Frågan skrivs färdig med rörets eget namn och
                    id, och läggs i rutan - inte i samtalet - så att den går att läsa och ändra innan den
                    ställs. Agenten ser samma rör som markerats på bladet. */}
                <div className="row agentask">
                  <span className="muted small">Fråga agenten:</span>
                  {[["Vad är det här?", `Vad är ${why.pipe.designation} DN${why.pipe.dn ?? "?"} (rör ${why.pipe.physical_pipe_id}) för något, och var går det?`],
                    ["Varför slutar det här?", `Varför slutar ${why.pipe.designation} (rör ${why.pipe.physical_pipe_id}) där det gör? Visa fronterna.`],
                    ["Följ nätet", `Följ nätet från rör ${why.pipe.physical_pipe_id} och visa vad det sitter ihop med.`],
                    ["Förläng den", `Förläng rör ${why.pipe.physical_pipe_id} (${why.pipe.designation}) ut i det som fortsätter förbi änden, om ritningen tillåter det. Säg vad som ligger bortom änden och hur många meter det blir.`]]
                    .map(([label, q]) => (
                      <button key={label} className="ghost small"
                              onClick={() => { setAgentAsk(q); setTab("agent"); }}>{label}</button>
                    ))}
                </div>
                {(why.pipe.frontiers ?? []).length > 0 && (
                  <div className="frontiers">
                    <h5>{tr("Var röret slutar")}</h5>
                    <ul>
                      {why.pipe.frontiers.map((f: any, i: number) => (
                        <li key={i}>
                          <span className="dot" style={{ background: frontierColor(f.reason) }} />
                          <button className="link" onClick={() => viewer.current?.zoomTo([f.x - 30, f.y - 30, f.x + 30, f.y + 30])}>
                            ({f.x.toFixed(0)}, {f.y.toFixed(0)})
                          </button>{" "}
                          {frontierText(f)}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {why.evidence_chain.map((e: any, i: number) => (
                  <div key={i} className="issue" onClick={() => e.designation && viewer.current?.zoomTo(e.designation.bbox)}>
                    <b>{e.designation?.text}</b> DN {e.dn ?? "?"} ({e.designation?.source}) → leader {e.leader?.family} ({e.leader?.n_segments} segment) → {e.attachment.state} ({e.attachment.reason})
                  </div>
                ))}
                <p className="muted">Skala: {why.scale.state} {why.scale.meters_per_pdf_point ? `${why.scale.meters_per_pdf_point.toFixed(6)} m/pt` : ""}</p>
              </div>
            )}
          </div>
        )}
        {tab === "agent" && (
          <AgentChat jobId={id!} page={page} ask={agentAsk}
            selection={{ pipeIds: selPipe ? [selPipe.physical_pipe_id] : agentIds, bbox: null }}
            onHighlight={(ids) => {
              setAgentIds(ids);
              const first = result.pipes.find((p: any) => p.physical_pipe_id === ids[0]);
              if (first) { setSelIdent(first.identity); goTo(boxOf(first), first.page ?? 0); }
            }}
            onChanged={async () => {
              setCorrections(await api.corrections(job.drawing_id));
              setResult(await api.result(id!, page));
            }} />
        )}
        {tab === "rattelser" && (
          <Corrections drawingId={job.drawing_id} jobId={id!} page={page} quantities={result.quantities}
            corrections={corrections} draft={draft} kind={drawKind} pipe={selPipe} proposals={result.proposals ?? []}
            onKindChange={setDrawKind} onDraftClear={() => setDraft(null)}
            onChanged={async () => {
              setCorrections(await api.corrections(job.drawing_id));
              setResult(await api.result(id!, page));
            }} />
        )}
        {tab === "markera" && (
          <Markups drawingId={job.drawing_id} page={page} tool={markTool} draft={markDraft}
            meterPerPt={result.scale?.meters_per_pdf_point ?? null}
            onToolChange={setMarkTool} onDraftClear={() => setMarkDraft(null)} onChanged={setMarkups} />
        )}
        {tab === "oversikt" && (() => {
          // The overview used to read the engine's raw totals while the table beside it read the same numbers
          // under the takeoff's own assumptions. A sheet full of stacks then said "0,0 m vertikalt" on one tab
          // and counted its risers on the next. One reading, one set of assumptions, both tabs.
          // Handlingen, inte bladet man råkar stå på. Översikten är det tal någon prissätter, och en handling på
          // tjugosex blad prissätts inte efter sitt försättsblad.
          const calcRows = nSheets > 1 && setDoc?.rows?.length ? setDoc.rows : (result.quantities || []);
          const calc = withFloorHeight(calcRows, floorH, includeHatched, riserSource, includeDeclared);
          const sum = (k: string) => calc.reduce((t: number, r: any) => t + (Number(r[k]) || 0), 0);
          const risers = calc.reduce((t: number, r: any) => t + (r.risers_calc || 0), 0);
          return (
          <div className="card">
            <SourceAssignment report={result.source_assignment} />
            <div className="row" style={{ marginBottom: 18 }}>
              <button className="secondary small" disabled={rescaling} onClick={async () => {
                setRescaling(true); setActionErr("");
                try { const j = await api.analyze(job.drawing_id, undefined, page, "combined", "auto"); navigate(`/jobs/${j.id}`); }
                catch (e: any) { setActionErr(e.message); } finally { setRescaling(false); }
              }}>{tr("Analysera ritningen")}</button>
            </div>
            <AnalysisQuality quality={result.quality} />
            <DrawingQuality style={result.drawing_style} visibility={result.pdf_visibility} />
            <DrawingDeclarations declarations={result.declarations} />
            <ReferenceComparison report={result.reference_comparison} page={page} />
            <div className="kpi">
              <div className="card"><div className="v">{c.designations}</div><div className="l">Vektorbeteckningar</div></div>
              <div className="card"><div className="v">{c.with_dn}</div><div className="l">DN</div></div>
              <div className="card"><div className="v">{c.leaders}</div><div className="l">CAD-leaders</div></div>
              <div className="card"><div className="v">{c.verified_attachments}</div><div className="l">{tr("Verifierade röranslutningar")}</div></div>
              <div className="card"><div className="v">{c.physical_pipes}</div><div className="l">PhysicalPipes</div></div>
              <div className="card"><div className="v">{sum("horizontal_calc").toFixed(1)} m</div><div className="l">Horisontellt</div></div>
              {/* Vertical metres are risers times a floor height nobody has stated yet. Until someone does, the
                  honest figure is the count - "0,0 m" reads as "the drawing has no stacks", which is a lie. */}
              {floorH
                ? <div className="card"><div className="v">{sum("vertical_calc").toFixed(1)} m</div><div className="l">Vertikalt · {risers} st × {String(floorH).replace(".", ",")} m</div></div>
                : <div className="card"><div className="v">{risers} st</div><div className="l">{tr("Stigare · ange våningshöjd för meter")}</div></div>}
              <div className="card"><div className="v">{sum("total_calc").toFixed(1)} m</div><div className="l">Totalt</div></div>
              <div className="card"><div className="v">{result.totals.ambiguous_m.toFixed(1)} m</div><div className="l">Tvetydigt</div></div>
              <div className="card"><div className="v">{c.claimed_m ?? "?"} m</div><div className="l">{tr("Påpekad men onämnd")}</div></div>
              <div className="card"><div className="v">{c.unowned_m ?? "?"} m</div><div className="l">{tr("Oidentifierad geometri")}</div></div>
              <div className="card"><div className="v">{c.unsupported_families}</div><div className="l">{tr("Unsupported styles")}</div></div>
              <div className="card"><div className="v">{c.ambiguous_attachments + c.no_attachments}</div><div className="l">{tr("Ej anslutna beteckningar")}</div></div>
              {(() => {
                // length the drawing puts inside walls: drawn, measured, and outside the horizontal quantity by
                // design. Stated rather than hidden, because a number that is left out silently is a number a
                // reader will one day find and not be able to place.
                const inWall = (result.quantities || []).reduce((t: number, r: any) => t + (r.in_hatched_area_m || 0), 0);
                return inWall > 0.005
                  ? <div className="card"><div className="v">{inWall.toFixed(1)} m</div><div className="l">I vägg (utanför mängden)</div></div>
                  : null;
              })()}
              {(() => {
                const tags = (result.designations || []).filter((d: any) => d.names_a_pipe === false).length;
                return tags > 0
                  ? <div className="card"><div className="v">{tags}</div><div className="l">Komponentbeteckningar</div></div>
                  : null;
              })()}
            </div>
            <p style={{ marginTop: 12 }}>Indata: <b>ren vektor</b> ({result.input?.classification?.n_paths ?? "?"} vektorobjekt, {result.input?.classification?.n_chars ?? 0} söktecken) · Skala: <b>{result.scale.state}</b> ({result.scale.reason}) · Reconciliation: <b>{c.reconciliation}</b> · Determinism: <b>{c.determinism ?? "ej körd"}</b> · Contamination: <b>{c.contamination}</b> · Andraläsare: <b>{c.second_reader?.consulted ? `tillfrågad (${c.second_reader.asked} fall, ${c.second_reader.settled} avgjorda)` : "ej tillfrågad"}</b> · Motor: <b>{result.build?.engine ?? "?"}</b> (bygge <code>{result.build?.build ?? "okänt"}</code>)</p>
            <p className="muted">Vågrätt och lodrätt läses ur hur beteckningen är skriven: står dimensionen på
              raden under beteckningen är det en stigare, och den räknas som antal; står allt på en rad är det en
              sträcka i planet, och den mäts i meter. Etiketterna med dimension på raden under ger {calc.reduce((t: number, r: any) => t + (r.riser_count_from_labels ?? 0), 0)} stigare,
              de ritade stigarsymbolerna {calc.reduce((t: number, r: any) => t + (r.riser_count ?? 0), 0)}. Här räknas
              de ur <b>{riserSource === "labels" ? "etiketterna" : "symbolerna"}</b>; källan byts under Antaganden.</p>
            <p className="muted">Sida {result.page.width_pt}×{result.page.height_pt} pt ({result.page.format}) · analys {result.performance.total_seconds} s · {result.performance.counts.raw_vector_objects} vektorobjekt · {result.performance.counts.glyphs} glyfer i {result.performance.counts.glyph_families} familjer</p>
          </div>
          );
        })()}
        {tab === "artefakter" && (
          <div className="card">
            <h4>Export</h4>
            <div className="row">
              <button onClick={() => dl(api.exportUrl(id!, "pdf"), "markerad.pdf")}>{tr("Markerad PDF")}</button>
              <button onClick={() => dl(api.exportUrl(id!, "xlsx") + (exportQuery ? `?${exportQuery}` : ""), "mangder.xlsx")}>Excel</button>
              <button onClick={() => dl(api.exportUrl(id!, "csv") + (exportQuery ? `?${exportQuery}` : ""), "mangder.csv")}>CSV</button>
              <button onClick={() => dl(api.exportUrl(id!, "json"), "quantities.json")}>JSON</button>
              <button onClick={() => dl(api.exportUrl(id!, "report"), "analysrapport.md")}>Analysrapport</button>
            </div>
            <h4>Artefakter</h4>
            <table><tbody>{artifacts.map((a) => <tr key={a.name}><td><a href="#" onClick={(e) => { e.preventDefault(); dl(api.artifactUrl(id!, a.name), a.name); }}>{a.name}</a></td><td className="num muted">{(a.size / 1024).toFixed(0)} kB</td></tr>)}</tbody></table>
          </div>
        )}
      </div>
    </div>
    </div>
    </AnalysisCompletionReveal>
  );
}
