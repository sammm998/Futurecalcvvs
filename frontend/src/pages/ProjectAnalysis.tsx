import { Fragment, useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import ProjectAgentChat from "../components/ProjectAgentChat";

/* Projektet läst som en handling.
 *
 * En enkel analys läser en ritning och svarar med meter. Den här läser alla blad och svarar med vad handlingen
 * består av: vilka hus, vilka discipliner, vilka versioner, vad som hör ihop och vad som inte gick att avgöra.
 *
 * Regeln som styr hela sidan: ett före och ett efter får aldrig hittas på. Två handlingar från samma dag med
 * samma status är inte ett revisionspar utan två discipliner i samma skede, och det står så - för en påhittad
 * diff ser exakt ut som en riktig och varje rad i den är fel.
 */

type Field = { value: any; source: string; where: string; confidence: number };
type Doc = {
  drawing_id: string; filename: string; key: string; n_pages: number;
  number: Field; discipline: Field; building: Field; floor: Field; part: Field;
  title: Field; kind: Field; status: Field; revision: Field; revision_date: Field;
  document_date: Field; project: Field; scale: Field;
};

/* Vad en människa får rätta, och vad det heter på svenska. Rollen står inte med: den är inget bladet bär,
   den är vad bladet gör i just det här projektet, och den frågan hör hemma i ändringsregistret. */
const FIXABLE: [string, string][] = [
  ["building", "Hus"], ["discipline", "Disciplin"], ["number", "Ritningsnummer"],
  ["floor", "Plan"], ["part", "Del"],
];

const val = (f?: Field) => (f && f.value != null ? String(f.value) : "–");
const conf = (f?: Field) => (f && f.confidence ? Math.round(f.confidence * 100) : 0);

function Sure({ f }: { f?: Field }) {
  /* Ett värde utan sin säkerhet är ett påstående ingen kan pröva. Under sjuttio procent är det en läsning
     någon bör titta på, och då syns det. */
  const c = conf(f);
  if (!f || f.value == null) return <span className="muted">–</span>;
  return (
    <span title={`${f.where}: ${f.source}`} className={c < 70 ? "pa-weak" : ""}>
      {String(f.value)}{c > 0 && c < 70 && <i className="pa-c"> {c} %</i>}
    </span>
  );
}

export function ModeChooser({ projectId, onPicked }: { projectId: string; onPicked: (m: string) => void }) {
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const pick = async (mode: string) => {
    setBusy(mode); setErr("");
    try { await api.setMode(projectId, mode); onPicked(mode); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  return (
    <>
      <div className="head"><div>
        <h1>{tr("Välj analys")}</h1>
        <p className="lead">Vad ska läsas: en ritning, eller hela handlingen?</p>
      </div></div>
      {err && <p className="error">{err}</p>}
      <div className="pa-choice">
        <div className="card">
          <h3>{tr("Enkel analys")}</h3>
          <p>{tr("Analysera en eller flera ritningar direkt.")}</p>
          <p className="muted">
            Bra för mängdning, röranalys, frågor och kontroll av en handling. Varje ritning läses för sig och
            svarar med meter, stigare och beteckningar.
          </p>
          <button disabled={!!busy} onClick={() => pick("simple")}>
            {busy === "simple" ? "Väljer…" : "Välj enkel analys"}
          </button>
        </div>
        <div className="card">
          <h3>Projektanalys</h3>
          <p>{tr("Analysera hela projektet som en sammanhängande handling.")}</p>
          <p className="muted">
            Läser varje blads namnruta, bygger handlingsförteckningen, håller husen isär och parar ihop
            versioner — men bara där handlingarna själva säger vilken som kom först.
          </p>
          <button disabled={!!busy} onClick={() => pick("project")}>
            {busy === "project" ? "Väljer…" : "Välj projektanalys"}
          </button>
        </div>
      </div>
    </>
  );
}

/* Att rätta vad läsningen kom fram till om ett blad.
 *
 * Läsningen har rätt oftare än mappstrukturen - en mapp som heter "Hus B" visade sig innehålla hus C:s
 * ritningar, och det var läsningen som hade rätt. Men den har inte alltid rätt, och när den har fel ska det gå
 * att säga så utan att någon behöver ladda om något. Rättelsen ligger kvar när analysen körs om; det är hela
 * poängen med den, och det är också därför den kräver en omläsning: parningen och husindelningen bygger på de
 * här fälten, och en rättelse som inte fick räkna om dem vore bara en etikett.
 */
function Fix({ projectId, doc, fixed, onSaved }:
  { projectId: string; doc: Doc; fixed: Record<string, string>; onSaved: () => void }) {
  const [f, setF] = useState(FIXABLE[0][0]);
  const [v, setV] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const now = (doc as any)[f] as Field | undefined;
  const save = async () => {
    if (!v.trim()) { setErr("Skriv vad det ska vara i stället."); return; }
    setBusy(true); setErr("");
    try { await api.setOverride(projectId, { drawing_id: doc.drawing_id, field: f, value: v.trim(), note }); setV(""); setNote(""); onSaved(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="pa-fix">
      <div className="row">
        <select value={f} onChange={(e) => { setF(e.target.value); setV(""); }}>
          {FIXABLE.map(([k, label]) => <option key={k} value={k}>{label}</option>)}
        </select>
        <span className="muted small">
          läsningen säger <b>{val(now)}</b>{now?.where ? ` ur ${now.where}` : ""}
          {fixed[f] ? ` · redan rättat till ${fixed[f]}` : ""}
        </span>
      </div>
      <div className="row">
        <input value={v} placeholder={tr("ska vara…")} onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") save(); }} />
        <input value={note} placeholder={tr("varför (valfritt)")} onChange={(e) => setNote(e.target.value)} />
        <button className="small" disabled={busy} onClick={save}>{busy ? "Sparar…" : "Rätta"}</button>
      </div>
      {err && <p className="error small" style={{ margin: 0 }}>{err}</p>}
    </div>
  );
}

function Tree({ tree, projectId, fixes, onFixed }:
  { tree: any; projectId: string; fixes: Record<string, Record<string, string>>; onFixed: () => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [fixing, setFixing] = useState<string>("");
  return (
    <div className="pa-tree">
      {Object.entries(tree).map(([building, discs]: any) => (
        <section key={building} className="card">
          <h3 style={{ marginTop: 0 }}>{building === "Okänt hus" ? "Hus okänt" : `Hus ${building}`}</h3>
          {Object.entries(discs).map(([disc, rows]: any) => {
            const k = `${building}/${disc}`;
            const shown = open[k] ? rows : rows.slice(0, 6);
            return (
              <div key={k} className="pa-disc">
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <b>{disc}</b><span className="muted">{rows.length} blad</span>
                </div>
                <div className="tablewrap">
                  <table className="qty">
                    <thead><tr><th>Nummer</th><th>Namn</th><th>Sort</th><th>Plan</th><th>Del</th>
                      <th>Status</th><th>Rev</th><th>Datum</th><th></th></tr></thead>
                    <tbody>
                      {shown.map((d: Doc) => {
                        const mine = fixes[d.drawing_id] ?? {};
                        return (
                        <Fragment key={d.drawing_id ?? d.filename}>
                        <tr className={Object.keys(mine).length ? "pa-fixed" : ""}>
                          <td className="lf-mono"><Sure f={d.number} /></td>
                          <td>{val(d.title) === "–" ? <span className="muted">{d.filename}</span> : d.title.value}</td>
                          <td className="muted">{val(d.kind)}</td>
                          <td className="muted">{val(d.floor)}</td>
                          <td className="muted">{val(d.part)}</td>
                          <td>{d.status?.value ? <span className="badge small">{d.status.value}</span> : <span className="muted">–</span>}</td>
                          <td className="muted">{val(d.revision)}</td>
                          <td className="muted">{val(d.document_date)}</td>
                          <td className="row" style={{ gap: 6 }}>
                            {d.drawing_id && <Link className="ghost small" to={`/drawings/${d.drawing_id}`}>{tr("Öppna")}</Link>}
                            {d.drawing_id && (
                              <button className="ghost small"
                                onClick={() => setFixing(fixing === d.drawing_id ? "" : d.drawing_id)}>
                                {fixing === d.drawing_id ? "Stäng" : "Rätta"}
                              </button>
                            )}
                          </td>
                        </tr>
                        {fixing === d.drawing_id && (
                          <tr><td colSpan={9}>
                            <Fix projectId={projectId} doc={d} fixed={mine} onSaved={onFixed} />
                          </td></tr>
                        )}
                        </Fragment>
                      ); })}
                    </tbody>
                  </table>
                </div>
                {rows.length > 6 && (
                  <button className="ghost small" onClick={() => setOpen({ ...open, [k]: !open[k] })}>
                    {open[k] ? "Visa färre" : `Visa alla ${rows.length}`}
                  </button>
                )}
              </div>
            );
          })}
        </section>
      ))}
    </div>
  );
}

/* Ändringslistan för ett par.
 *
 * Den står mellan två LÄSNINGAR och inte mellan två ritningar, och det är skillnaden som avgör hur den får
 * läsas. Att en beteckning bara finns på ena bladet är starkt. Att dess meter skiljer sig är svagt: två
 * läsningar av samma oförändrade rör rör sig något. Och saknas läsningen på någon av sidorna finns ingen lista
 * alls - att fylla i den saknade sidan med noll skulle göra hela den lästa sidan till en ändring.
 */
function Changes({ projectId, pairKey }: { projectId: string; pairKey: string }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.changes(projectId, pairKey).then(setD).catch((e) => setErr(e.message)); }, [projectId, pairKey]);
  if (err) return <p className="error">{err}</p>;
  if (!d) return <p className="muted">{tr("Jämför…")}</p>;
  const c = d.changes;
  if (c.state !== "JÄMFÖRD") {
    return (
      <div className="pa-unread">
        <b>{tr("Går inte att jämföra ännu.")}</b>
        <p className="muted" style={{ margin: "6px 0 0" }}>{c.why}</p>
        <p className="muted small" style={{ margin: "6px 0 0" }}>
          Saknas: {c.missing.map((m: string) => (m === "before" ? "före-bladet" : "efter-bladet")).join(" och ")}.
        </p>
      </div>
    );
  }
  const t = c.totals;
  const moved = c.rows.filter((r: any) => r.what !== "OFÖRÄNDRAD");
  return (
    <div className="pa-changes">
      <div className="row" style={{ gap: 8 }}>
        <span className="badge ok small">{t.added} tillkomna</span>
        <span className="badge bad small">{t.removed} borttagna</span>
        <span className="badge warn small">{t.changed} ändrade</span>
        <span className="badge small">{t.unchanged} oförändrade</span>
        <span className="muted small">{t.before_m} m → {t.after_m} m</span>
      </div>
      {moved.length ? (
        <div className="tablewrap" style={{ marginTop: 10 }}>
          <table className="qty">
            <thead><tr><th>Beteckning</th><th>Vad</th><th className="num">{tr("Före")}</th><th className="num">Efter</th>
              <th className="num">Skillnad</th><th>Styrka</th><th>{tr("Skäl")}</th></tr></thead>
            <tbody>
              {moved.map((r: any) => (
                <tr key={r.designation}>
                  <td className="lf-mono"><b>{r.designation}</b></td>
                  <td><span className={`badge small${r.what === "TILLKOMMEN" ? " ok" : r.what === "BORTTAGEN" ? " bad" : " warn"}`}>{r.what}</span></td>
                  <td className="num">{r.before_m == null ? "–" : `${r.before_m} m`}</td>
                  <td className="num">{r.after_m == null ? "–" : `${r.after_m} m`}</td>
                  <td className="num">{r.delta_m == null ? "–" : `${r.delta_m > 0 ? "+" : ""}${r.delta_m} m`}</td>
                  <td className={r.strength === "stark" ? "" : "muted"}>{r.strength}</td>
                  <td className="muted small">{r.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="muted" style={{ marginBottom: 0 }}>{tr("Ingenting skiljer de två läsningarna åt.")}</p>}
      <p className="muted small" style={{ margin: "10px 0 0" }}>{c.caveat}</p>
    </div>
  );
}

function Versions({ report, projectId }: { report: any; projectId: string }) {
  const pairs = report.pairs ?? [];
  const unclear = report.unclear ?? [];
  const [open, setOpen] = useState<string>("");
  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Före och efter")}</h3>
        <p className="muted">
          Ett par påstås bara när handlingarna själva bär ordningen: en revisionsbeteckning, ett revisionsdatum,
          ett handlingsdatum eller ett skede som skiljer dem åt. Ett tal i filnamnet är ingen revision, och två
          handlingar från samma dag med samma status är inte ett par.
        </p>
      </div>

      {pairs.length > 0 ? pairs.map((p: any, i: number) => (
        <section key={i} className="card" style={{ marginTop: 14 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b className="lf-mono">{p.key}</b>
            <span className={p.confidence >= 0.8 ? "badge ok small" : "badge warn small"}>
              {Math.round(p.confidence * 100)} % säker matchning
            </span>
          </div>
          <div className="pa-pair">
            {[["Före", p.before], ["Efter", p.after]].map(([label, d]: any) => (
              <div key={label} className="side">
                <div className="k">{label}</div>
                <div className="lf-mono">{val(d.number)}</div>
                <div className="muted small">{val(d.title)}</div>
                <div className="muted small">{val(d.status)} · rev {val(d.revision)} · {val(d.document_date)}</div>
                {d.drawing_id && <Link className="ghost small" to={`/drawings/${d.drawing_id}`}>{tr("Öppna")}</Link>}
              </div>
            ))}
          </div>
          <p className="muted">Skäl: {p.why.join(" · ")}</p>
          <button className="ghost small" onClick={() => setOpen(open === p.key ? "" : p.key)}>
            {open === p.key ? "Dölj ändringarna" : "Vad ändrades?"}
          </button>
          {open === p.key && <Changes projectId={projectId} pairKey={p.key} />}
        </section>
      )) : (
        <div className="card" style={{ marginTop: 14 }}>
          <p className="empty">{tr("Inga säkra revisionspar hittades.")}</p>
        </div>
      )}

      {unclear.length > 0 && (
        <section className="card" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>{tr("Det som inte gick att ordna")}</h3>
          {unclear.map((u: any, i: number) => (
            <div key={i} className="pa-unclear">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <b className="lf-mono">{u.key}</b>
                <span className="badge small">{u.reading}</span>
              </div>
              <p className="muted">{u.why}</p>
              <div className="muted small">
                {u.docs.map((d: any) => d.filename).join(" · ")}
              </div>
            </div>
          ))}
        </section>
      )}
    </>
  );
}

function Quantities({ q }: { q: any }) {
  const buildings = Object.keys(q ?? {});
  if (!buildings.length) {
    return <div className="card"><p className="empty">
      Inga mängder ännu. Kör en analys på bladen, så summeras de här per hus.</p></div>;
  }
  return (
    <>
      <div className="card">
        <p className="muted" style={{ margin: 0 }}>
          Summerat per hus, aldrig över projektet. Hus A och hus B har var sin beteckningslista, och en
          beteckning som bara finns i ett av husen ska stå under det huset och ingen annanstans.
        </p>
      </div>
      {buildings.map((b) => (
        <section key={b} className="card" style={{ marginTop: 14, paddingTop: 6 }}>
          <h3>{b === "Okänt hus" ? "Hus okänt" : `Hus ${b}`}</h3>
          <div className="tablewrap">
            <table className="qty">
              <thead><tr><th>Beteckning</th><th className="num">DN</th><th className="num">Horisontellt</th>
                <th className="num">Stigare</th><th className="num">Etiketter</th><th>Blad</th></tr></thead>
              <tbody>
                {q[b].map((r: any) => (
                  <tr key={r.designation}>
                    <td className="lf-mono"><b>{r.designation}</b></td>
                    <td className="num">{r.dn ?? "–"}</td>
                    <td className="num">{r.horizontal_m.toLocaleString(locale(), { maximumFractionDigits: 2 })} m</td>
                    <td className="num">{r.risers || "–"}</td>
                    <td className="num muted">{r.labels}</td>
                    <td className="muted small">{r.sheets.length} st</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </>
  );
}

export default function ProjectAnalysisPage() {
  const { id } = useParams();
  const [mode, setMode] = useState<any>(null);
  const [run, setRun] = useState<any>(null);
  const [tab, setTab] = useState<"oversikt" | "handlingar" | "versioner" | "mangder" | "agent">("oversikt");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  // vad någon rättat om bladen, och om det gjorts en rättelse sedan den läsning som står på skärmen
  const [fixes, setFixes] = useState<Record<string, Record<string, string>>>({});
  const [stale, setStale] = useState(false);

  // Varje start av en läsning måste starta om avfrågningen. Den satt tidigare bara på sidladdningen, så efter
  // "Läs handlingen" frågade ingen servern igen: läsningen var klar på en tiondels sekund och sidan stod kvar
  // på "I kö" för alltid. Rökprovet i webbläsaren fann det.
  const [poll, setPoll] = useState(0);
  const loadMode = () => api.mode(id!).then(setMode).catch((e) => setErr(e.message));
  const loadFixes = () => api.overrides(id!)
    .then((r) => {
      const by: Record<string, Record<string, string>> = {};
      for (const o of r.rows) (by[o.drawing_id] ??= {})[o.field] = o.value;
      setFixes(by);
    })
    .catch(() => { /* rättelser är inte livsviktiga för att visa handlingen */ });
  useEffect(() => { loadMode(); loadFixes(); }, [id]);
  useEffect(() => {
    if (mode?.effective !== "project") return;
    let stop = false;
    const tick = () => api.projectAnalysis(id!)
      .then((r) => {
        if (stop) return;
        setRun(r.status === "NONE" ? null : r);            // ingen körd ännu är inget att visa, och inget fel
        if (r.status === "RUNNING" || r.status === "QUEUED") setTimeout(tick, 1200);
      })
      .catch((e) => setErr(e.message));
    tick();
    return () => { stop = true; };
  }, [id, mode?.effective, poll]);

  const start = async () => {
    setBusy(true); setErr("");
    try {
      await api.startProjectAnalysis(id!);
      setRun({ status: "QUEUED", stage: "I kö", progress: 0 });
      setStale(false); loadMode();
      setPoll((n) => n + 1);                                 // och fråga servern tills den är klar
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  const fixed = () => { setStale(true); loadFixes(); };

  const rep = run?.report;
  const t = rep?.totals;

  if (!mode) return <main><p className="muted">{tr("Laddar…")}</p></main>;
  if (!mode.chosen) {
    return <main>
      <p className="crumb"><Link to={`/projects/${id}`}>Projektet</Link> {tr("· Analys")}</p>
      <ModeChooser projectId={id!} onPicked={() => loadMode()} />
    </main>;
  }
  if (mode.effective === "simple") {
    return <main>
      <p className="crumb"><Link to={`/projects/${id}`}>Projektet</Link> {tr("· Analys")}</p>
      <div className="head"><div>
        <h1>{tr("Enkel analys")}</h1>
        <p className="lead">{tr("Projektet läses en ritning i taget. Öppna en ritning och kör analysen på den.")}</p>
      </div></div>
      <div className="card">
        <p className="muted">
          {mode.drawings} handlingar, {mode.readings} läsningar körda.
        </p>
        <div className="row">
          <Link to={`/projects/${id}`}><button>{tr("Till ritningarna")}</button></Link>
          <button className="secondary" onClick={async () => { await api.setMode(id!, "project"); loadMode(); }}>
            Byt till projektanalys
          </button>
        </div>
      </div>
    </main>;
  }

  return (
    <main>
      <p className="crumb"><Link to={`/projects/${id}`}>Projektet</Link> {tr("· Projektanalys")}</p>
      <div className="head">
        <div>
          <h1>Projektanalys</h1>
          <p className="lead">
            Hela handlingen läst som en modell: vad varje blad är, vad som hör ihop, och vad som inte gick att
            avgöra.
          </p>
        </div>
        <div className="row">
          <button disabled={busy || run?.status === "RUNNING"} onClick={start}>
            {run ? "Läs om" : "Läs handlingen"}
          </button>
        </div>
      </div>
      {err && <p className="error">{err}</p>}

      {stale && run?.status === "DONE" && (
        <div className="card pa-stale">
          <p style={{ margin: 0 }}>
            <b>{tr("Rättelsen är sparad, men modellen på skärmen är läst innan den.")}</b> Husindelningen och parningen
            bygger på de fälten, så de räknas om först när handlingen läses om.
          </p>
          <button className="small" onClick={start} disabled={busy}>{tr("Läs om handlingen")}</button>
        </div>
      )}

      {run && run.status !== "DONE" && (
        <div className="card">
          {run.status === "FAILED"
            ? <pre className="error">{run.error}</pre>
            : <>
              <p className="muted" style={{ marginTop: 0 }}>{run.stage}</p>
              <div className="bar"><span style={{ width: `${Math.round((run.progress || 0) * 100)}%` }} /></div>
            </>}
        </div>
      )}

      {rep && (
        <>
          <div className="adm-stats" style={{ marginTop: 14 }}>
            <div className="adm-stat"><div className="k">Handlingar</div><div className="v">{t.documents}</div></div>
            <div className="adm-stat"><div className="k">Byggnader</div><div className="v">{t.buildings}</div></div>
            <div className="adm-stat"><div className="k">Discipliner</div><div className="v">{t.disciplines}</div></div>
            <div className="adm-stat"><div className="k">Versionspar</div><div className="v">{t.pairs}</div></div>
            <div className={`adm-stat${t.unclear ? " bad" : ""}`}>
              <div className="k">Oklara</div><div className="v">{t.unclear}</div>
              <div className="s">{tr("gick inte att ordna")}</div></div>
            <div className={`adm-stat${rep.unreadable.length ? " bad" : ""}`}>
              <div className="k">{tr("Olästa")}</div><div className="v">{rep.unreadable.length}</div></div>
          </div>

          <div className="tabs" style={{ marginTop: 18 }}>
            {([["oversikt", "Översikt"], ["handlingar", "Handlingar"], ["versioner", "Före / efter"],
               ["mangder", "Mängder"], ["agent", "Agent"]] as const).map(([k, label]) => (
              <button key={k} className={tab === k ? "active" : ""} onClick={() => setTab(k as any)}>{label}</button>
            ))}
          </div>

          <div style={{ marginTop: 14 }}>
            {tab === "oversikt" && (
              <>
                <div className="card">
                  <h3 style={{ marginTop: 0 }}>{tr("Vad handlingen består av")}</h3>
                  <p className="muted">
                    Läst ur bladens egna namnrutor. Ett filnamn används bara när bladet inte bär något nummer,
                    och då syns det på säkerheten.
                  </p>
                  <table className="qty"><tbody>
                    <tr><td>Byggnader</td><td>{rep.buildings.join(", ") || "–"}</td></tr>
                    <tr><td>Discipliner</td><td>{rep.disciplines.join(", ") || "–"}</td></tr>
                    <tr><td>Dubbletter</td><td>{Object.keys(rep.duplicates).length
                      ? Object.entries(rep.duplicates).map(([k, v]: any) => `${k} (${v.length})`).join(", ")
                      : <span className="muted">inga</span>}</td></tr>
                  </tbody></table>
                </div>
                {rep.unreadable.length > 0 && (
                  <div className="card" style={{ marginTop: 14 }}>
                    <h3 style={{ marginTop: 0 }}>{tr("Gick inte att läsa")}</h3>
                    <p className="muted">{rep.unreadable.join(" · ")}</p>
                  </div>
                )}
              </>
            )}
            {tab === "handlingar" && <Tree tree={rep.tree} projectId={id!} fixes={fixes} onFixed={fixed} />}
            {tab === "versioner" && <Versions report={rep} projectId={id!} />}
            {tab === "mangder" && <Quantities q={rep.quantities} />}
            {tab === "agent" && <ProjectAgentChat projectId={id!} />}
          </div>
        </>
      )}

      {!run && (
        <div className="card">
          <p className="muted">
            {mode.drawings} handlingar väntar. Läsningen tar sekunder per blad — den läser namnrutorna, inte
            geometrin.
          </p>
        </div>
      )}
    </main>
  );
}
