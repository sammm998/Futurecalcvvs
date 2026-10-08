import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { num, t as tr, trf } from "../i18n";

/* ABT 06: rummen i projektet, lästa ur A-planernas rumsetiketter.
 *
 * Varje rad är RÄKNAD - läsningen räknade den på bladet, den mätte inget - och visar var den lästes. En sida som
 * upprepar en annan räknas inte två gånger, och det står vid sidan; den som kalkylerar bestämmer vilka sidor som
 * är projektets. Arean är den som står skriven i etiketten. */

type Page = { drawing_id: string; filename: string; page: number; rooms: number; apartments: number; area_m2: number;
  counted: boolean; same_as: { filename: string; page: number } | null };

const KIND: Record<string, string> = { rum: "Rum", lagenhet: "Lägenhet" };

export function AbtPanel({ project }: { project: any }) {
  const [tab, setTab] = useState("rum");
  return (
    <section className="card" style={{ marginTop: 18 }} aria-label="ABT 06">
      <h3 style={{ marginTop: 0 }}>{tr("ABT 06 – totalentreprenad")}</h3>
      <div className="tabs">
        <button className={tab === "rum" ? "active" : ""} onClick={() => setTab("rum")}>{tr("Rum och ytor")}</button>
        <button className={tab === "enheter" ? "active" : ""} onClick={() => setTab("enheter")}>{tr("Enheter")}</button>
        {["Symboler", "Nyckeltal", "Schablon", "Krav"].map((t) => (
          <button key={t} disabled title={tr("Kommer i nästa del av ABT 06.")}>{tr(t)} · {tr("kommer")}</button>
        ))}
      </div>
      {tab === "rum" && <AbtRooms project={project} />}
      {tab === "enheter" && <AbtUnits project={project} />}
    </section>
  );
}

export default function AbtRooms({ project }: { project: any }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState("");
  const [offer, setOffer] = useState<any>(null);
  const [filter, setFilter] = useState("");
  const load = () => api.projectRooms(project.id).then(setData).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [project.id]);

  const ask = async (d: any) => {
    setErr(""); setBusy(d.id);
    try { setOffer({ drawing: d, ...(await api.roomsPrice(d.id)) }); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  const read = async () => {
    if (!offer) return;
    setErr(""); setBusy(offer.drawing.id);
    try { await api.readRooms(offer.drawing.id); setOffer(null); await load(); }
    catch (e: any) { setErr(e.message); } finally { setBusy(""); }
  };
  const choose = async (p: Page, counted: boolean) => {
    try { setData(await api.chooseRoomPage(project.id, { drawing_id: p.drawing_id, page: p.page, counted })); }
    catch (e: any) { setErr(e.message); }
  };
  const csv = async () => {
    const b = await api.fetchBlob(`/api/projects/${project.id}/rooms.csv`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b);
    a.download = `${(project.name || "projekt").replace(/[^\wåäöÅÄÖ-]+/g, "_")}-rum.csv`; a.click();
  };
  const rows = useMemo(() => (data?.rooms ?? []).filter((r: any) => r.kind !== "summa" && (!filter ||
    `${r.number ?? ""} ${r.name ?? ""} ${r.apartment?.text ?? ""}`.toLowerCase().includes(filter.toLowerCase()))), [data, filter]);
  const read_ = new Set((data?.pages ?? []).map((p: Page) => p.drawing_id));
  const t = data?.register?.totals;

  return (
    <div style={{ marginTop: 12 }}>
      <p className="muted small">{tr("Rummen läses ur A-planernas rumsetiketter: nummer, namn eller lägenhetstyp och arean som står skriven. Raderna är RÄKNADE – inget är mätt. En sida som upprepar en annan räknas en gång; du väljer vilka sidor som räknas.")}</p>
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("Ritning")}</th><th>{tr("Sidor")}</th><th></th></tr></thead>
          <tbody>
            {project.drawings.map((d: any) => (
              <tr key={d.id}>
                <td>{d.filename}</td>
                <td className="num">{d.n_pages}</td>
                <td>
                  <button className="secondary small" disabled={!!busy} onClick={() => ask(d)}>
                    {busy === d.id ? tr("Läser…") : read_.has(d.id) ? tr("Läs rummen igen") : tr("Läs rum")}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {offer && (
        <div className="callout" role="dialog" style={{ marginTop: 10 }}>
          {offer.pages_with_rooms.length === 0 ? <p>{tr("Ritningen har inga rumsetiketter att läsa. Det kostar ingenting.")}</p> : (
            <p>
              {trf("{0} sidor har rumsetiketter ({1} etiketter).", offer.pages_with_rooms.length, offer.labels)}{" "}
              {offer.exempt ? tr("Läsningen kostar inga credits här.") : offer.already_paid ? tr("Ritningen är redan betald – att läsa den igen kostar ingenting.")
                : trf("Läsningen kostar {0} credits – bladpriset för sidorna med rum.", num(offer.credits, 1))}
            </p>
          )}
          <div className="row" style={{ gap: 8 }}>
            {offer.pages_with_rooms.length > 0 && <button onClick={read} disabled={!!busy}>{tr("Läs rummen")}</button>}
            <button className="secondary" onClick={() => setOffer(null)}>{tr("Avbryt")}</button>
          </div>
        </div>
      )}
      {err && <p className="error" role="alert">{err}</p>}

      {t && (data.pages?.length ?? 0) > 0 && <>
        <div className="kpi" style={{ marginTop: 14 }}>
          <div className="card"><div className="v">{t.rooms}</div><div className="l">{tr("Rum")}</div></div>
          <div className="card"><div className="v">{num(t.area_m2, 1)}</div><div className="l">{tr("Rumsarea, m²")}</div></div>
          <div className="card"><div className="v">{t.apartments}</div><div className="l">{tr("Lägenheter")}</div></div>
          <div className="card"><div className="v">{num(t.apartment_area_m2, 1)}</div><div className="l">{tr("Lägenhetsarea, m²")}</div></div>
        </div>
        {data.register.apartments.length > 0 && (
          <div className="tablewrap" style={{ marginTop: 12 }}>
            <table className="qty">
              <thead><tr><th>{tr("Lägenhetstyp")}</th><th className="num">{tr("Antal")}</th><th className="num">{tr("Area, m²")}</th><th>{tr("Källtyp")}</th></tr></thead>
              <tbody>{data.register.apartments.map((a: any) => (
                <tr key={a.type}><td>{a.type}</td><td className="num">{a.count}</td><td className="num">{num(a.area_m2, 1)}</td><td><span className="badge">RÄKNAD</span></td></tr>
              ))}</tbody>
            </table>
          </div>
        )}
        <h4>{tr("Sidor")}</h4>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>{tr("Ritning")}</th><th className="num">{tr("Sida")}</th><th className="num">{tr("Rum")}</th><th className="num">{tr("Lägenheter")}</th><th className="num">{tr("Area, m²")}</th><th>{tr("Räknas")}</th><th></th></tr></thead>
            <tbody>{data.pages.map((p: Page) => (
              <tr key={`${p.drawing_id}-${p.page}`}>
                <td>{p.filename}</td><td className="num">{p.page + 1}</td><td className="num">{p.rooms}</td>
                <td className="num">{p.apartments}</td><td className="num">{num(p.area_m2, 1)}</td>
                <td><input type="checkbox" checked={p.counted} onChange={(e) => choose(p, e.target.checked)}
                  aria-label={trf("Räkna rummen på {0} sida {1}", p.filename, p.page + 1)} /></td>
                <td className="muted small">{p.same_as ? trf("Samma plan som {0} sida {1}", p.same_as.filename, p.same_as.page + 1) : ""}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="row" style={{ marginTop: 14, gap: 8 }}>
          <input placeholder={tr("Sök rum, nummer eller typ")} value={filter} onChange={(e) => setFilter(e.target.value)} />
          <button className="secondary small" onClick={csv}>{tr("Exportera rummen (CSV)")}</button>
        </div>
        <div className="tablewrap" style={{ marginTop: 8, maxHeight: 420, overflow: "auto" }}>
          <table className="qty">
            <thead><tr><th>{tr("Källtyp")}</th><th>{tr("Slag")}</th><th>{tr("Nummer")}</th><th>{tr("Namn eller typ")}</th><th className="num">{tr("Area, m²")}</th><th>{tr("Var")}</th></tr></thead>
            <tbody>{rows.slice(0, 500).map((r: any) => (
              <tr key={r.id} className={r.counted ? "" : "muted"} title={r.lines?.join(" / ")}>
                <td><span className="badge">{r.source_type}</span></td>
                <td>{tr(KIND[r.kind] ?? r.kind)}</td>
                <td>{r.number ?? "–"}</td>
                <td>{r.apartment?.text ?? r.name ?? "–"}</td>
                <td className="num">{num(r.area_m2, 1)}</td>
                <td className="muted small">{r.filename} · {tr("sida")} {r.page + 1}{r.counted ? "" : ` · ${tr("räknas inte")}`}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        {rows.length > 500 && <p className="muted small">{trf("Visar 500 av {0} rader – exporten har alla.", rows.length)}</p>}
      </>}
    </div>
  );
}

/* Enheterna: koderna arkitekten skriver vid inredningen - TM, DM, TS - räknade på sidorna som räknas. Varje enhet
 * är en räknemarkering på lagret "ABT enheter" i mängdningsverktyget, där den kan granskas, flyttas eller avvisas.
 * En kod heter det du säger, det bladets förklaring säger eller det referensdatan säger - annars okänd. */
const SOURCE: Record<string, string> = { "angiven": "angiven av dig", "bladets förklaring": "bladets förklaring",
  "referensdata": "referensdata", "okänd": "okänd" };

export function AbtUnits({ project }: { project: any }) {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  const [names, setNames] = useState<Record<string, string>>({});
  const load = () => api.projectUnits(project.id).then(setData).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [project.id]);
  const save = async (code: string) => {
    try { setData(await api.nameUnit(project.id, code, names[code] ?? "")); setNames({ ...names, [code]: undefined as any }); }
    catch (e: any) { setErr(e.message); }
  };
  const csv = async () => {
    const b = await api.fetchBlob(`/api/projects/${project.id}/units.csv`);
    const a = document.createElement("a"); a.href = URL.createObjectURL(b);
    a.download = `${(project.name || "projekt").replace(/[^\wåäöÅÄÖ-]+/g, "_")}-enheter.csv`; a.click();
  };
  const rows = data?.units ?? [];
  return (
    <div style={{ marginTop: 12 }}>
      <p className="muted small">{tr("Enheterna räknas ur koderna arkitekten skriver vid inredningen – TM, DM, TS – på samma sidor som rummen. De läses när rummen läses. Varje enhet är en räknemarkering på lagret ”ABT enheter” i Mängda, där du kan granska, flytta eller avvisa den. En kod som varken bladets förklaring eller referensdatan förklarar namnger du själv.")}</p>
      {err && <p className="error" role="alert">{err}</p>}
      {data && rows.length === 0 && <p className="muted">{tr("Inga enheter än. Läs rummen i fliken Rum och ytor – enheterna läses samtidigt.")}</p>}
      {rows.length > 0 && <>
        <div className="kpi">
          <div className="card"><div className="v">{data.totals.units}</div><div className="l">{tr("Enheter")}</div></div>
          <div className="card"><div className="v">{data.totals.codes}</div><div className="l">{tr("Koder")}</div></div>
          <div className="card"><div className="v">{data.totals.named}</div><div className="l">{tr("Med namn")}</div></div>
        </div>
        <div className="row" style={{ margin: "12px 0", gap: 8 }}>
          <button className="secondary small" onClick={csv}>{tr("Exportera enheterna (CSV)")}</button>
          {project.drawings[0] && <a className="small" href={`/mangda/${project.drawings[0].id}`}>{tr("Granska markeringarna i Mängda →")}</a>}
        </div>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>{tr("Källtyp")}</th><th>{tr("Kod")}</th><th>{tr("Namn")}</th><th>{tr("Namnet enligt")}</th><th className="num">{tr("Antal")}</th><th>{tr("Sidor")}</th><th></th></tr></thead>
            <tbody>{rows.map((r: any) => (
              <tr key={r.code}>
                <td><span className="badge">{r.source_type}</span></td>
                <td><b>{r.code}</b></td>
                <td>
                  <input value={names[r.code] ?? r.name ?? ""} placeholder={tr("Namnge koden")} style={{ minWidth: 160 }}
                    onChange={(e) => setNames({ ...names, [r.code]: e.target.value })} />
                </td>
                <td className="muted small">{tr(SOURCE[r.name_source] ?? r.name_source)}{r.legend ? ` · ${r.legend.filename} ${tr("sida")} ${r.legend.page + 1}` : ""}</td>
                <td className="num">{r.count}{r.not_counted ? <span className="muted small"> (+{r.not_counted})</span> : null}</td>
                <td className="muted small">{r.pages.length}</td>
                <td>{names[r.code] !== undefined && <button className="small" onClick={() => save(r.code)}>{tr("Spara")}</button>}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className="muted small">{tr("(+N) är enheter på sidor som inte räknas – samma plan en gång till.")}</p>
      </>}
    </div>
  );
}
