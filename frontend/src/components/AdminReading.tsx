import { Fragment, useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

/* Läsningens halva av administrationen: vad som lästs, vad kunderna rättat, och vad rättelserna lärt.
 *
 * Den tredje av de tre är den som lätt blir en lögn. "Systemet lär sig" är en mening man kan säga om nästan
 * vad som helst, så sidan säger i stället exakt vad en rättelse får göra och exakt vad den inte får göra, och
 * visar hur många av rättelserna som blivit en lärdom som någonsin kan tala igen. En rättelse utan situation
 * är ett påstående om sin egen ritning, och det står det.
 */

const pct = (v: number | null | undefined) => (v == null ? "–" : `${(v * 100).toFixed(0)} %`);
const m = (v: number | null | undefined) =>
  v == null ? "–" : `${v.toLocaleString(locale(), { maximumFractionDigits: 1 })} m`;
const when = (s: string | null) => (s ? new Date(s).toLocaleString(locale(), { dateStyle: "short", timeStyle: "short" }) : "–");

export function Readings() {
  const [d, setD] = useState<any>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(0);
  const [err, setErr] = useState("");
  const LIMIT = 50;
  useEffect(() => {
    const t = setTimeout(() => {
      api.adm(`readings?limit=${LIMIT}&offset=${page * LIMIT}&status=${status}&q=${encodeURIComponent(q)}`)
        .then(setD).catch((e) => setErr(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [q, status, page]);
  useEffect(() => { setPage(0); }, [q, status]);

  return (
    <>
      <div className="card">
        <div className="matbar">
          <input className="grow" value={q} placeholder={tr("Sök ritning, projekt eller e-post…")}
            onChange={(e) => setQ(e.target.value)} />
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{tr("alla lägen")}</option>
            <option value="DONE">klara</option>
            <option value="FAILED">misslyckade</option>
            <option value="RUNNING">{tr("pågående")}</option>
          </select>
        </div>
        {err && <p className="error">{err}</p>}
        <p className="muted" style={{ margin: 0 }}>{d ? `${d.total} läsningar` : "Laddar…"}</p>
      </div>
      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr>
              <th>{tr("När")}</th><th>Ritning</th><th>Konto</th><th>{tr("Läge")}</th><th className="num">Tid</th>
              <th className="num">Namn</th><th className="num">{tr("Täckning")}</th><th className="num">{tr("Mätt")}</th>
              <th className="num">{tr("Onämnt")}</th><th>{tr("Påskrift")}</th>
            </tr></thead>
            <tbody>
              {(d?.rows ?? []).map((r: any) => (
                <tr key={r.job_id} className={r.status === "FAILED" ? "bad" : ""}>
                  <td className="muted">{when(r.created_at)}</td>
                  <td><a href={`/jobs/${r.job_id}`}>{r.drawing}</a>
                    <div className="muted small">{r.project}</div></td>
                  <td className="muted">{r.user}</td>
                  <td>{r.status === "DONE" ? <span className="badge ok small">klar</span>
                    : r.status === "FAILED" ? <span className="badge warn small" title={r.error}>fel</span>
                      : <span className="badge small">{r.stage}</span>}</td>
                  <td className="num muted">{r.seconds ? `${r.seconds} s` : "–"}</td>
                  <td className="num">{r.names_with_metres ?? "–"}/{r.names ?? "–"}</td>
                  <td className="num"><b className={(r.coverage ?? 1) < 0.6 ? "warntext" : ""}>{pct(r.coverage)}</b></td>
                  <td className="num">{m(r.confirmed_m)}</td>
                  <td className="num muted">{m(r.unowned_m)}</td>
                  <td className="muted small">
                    {r.markup_set_aside ? `${r.markup_set_aside.n} st · ${m(r.markup_set_aside.ink_m)}` : "–"}
                  </td>
                </tr>
              ))}
              {d && !d.rows.length && <tr><td colSpan={10} className="empty">{tr("Inga läsningar matchar.")}</td></tr>}
            </tbody>
          </table>
        </div>
        {d && d.total > LIMIT && (
          <div className="row" style={{ marginTop: 12, alignItems: "center" }}>
            <button className="secondary small" disabled={page === 0} onClick={() => setPage(page - 1)}>{tr("← Föregående")}</button>
            <span className="muted">sida {page + 1} av {Math.ceil(d.total / LIMIT)}</span>
            <button className="secondary small" disabled={(page + 1) * LIMIT >= d.total} onClick={() => setPage(page + 1)}>{tr("Nästa →")}</button>
          </div>
        )}
      </div>
    </>
  );
}

export function Corrections() {
  const [d, setD] = useState<any>(null);
  const [kind, setKind] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.adm(`corrections?kind=${kind}`).then(setD).catch((e) => setErr(e.message));
  }, [kind]);

  return (
    <>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          Varje rättelse en kund gjort. Kolumnen <b>{tr("lär")}</b> säger om rättelsen någonsin kan tala igen: den
          kräver att situationen sparades, och situationen är fingeravtrycket motorn jämför mot på nästa blad.
          En rättelse utan situation är ett påstående om sin egen ritning och inget mer.
        </p>
        <div className="matbar">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">{tr("alla slag")}</option>
            <option value="extend">{tr("förläng")}</option><option value="draw">rita</option>
            <option value="erase">sudda</option><option value="retag">{tr("byt beteckning")}</option>
            <option value="quantity">{tr("mängd")}</option>
          </select>
          <span className="muted">{d ? `${d.total} rättelser` : "Laddar…"}</span>
        </div>
        {err && <p className="error">{err}</p>}
      </div>
      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>{tr("När")}</th><th>Slag</th><th>Beteckning</th><th>Ritning</th><th>Av</th>
              <th>{tr("Lär")}</th><th>Anteckning</th></tr></thead>
            <tbody>
              {(d?.rows ?? []).map((r: any) => (
                /* nyckeln på fragmentet, inte på den inre raden: annars är listan namnlös för React */
                <Fragment key={r.id}>
                  <tr className={r.undone ? "muted" : ""}
                    onClick={() => setOpen(open === r.id ? null : r.id)} style={{ cursor: "pointer" }}>
                    <td className="muted">{when(r.created_at)}</td>
                    <td>{r.kind}{r.undone && <span className="badge small" style={{ marginLeft: 6 }}>{tr("ångrad")}</span>}</td>
                    <td className="lf-mono">{r.designation ?? "–"}</td>
                    <td><a href={`/drawings/${r.drawing_id}`}>{r.drawing}</a></td>
                    <td className="muted">{r.user}</td>
                    <td>{r.teaches ? <span className="badge ok small">ja</span>
                      : <span className="badge small" title={tr("ingen situation sparad")}>nej</span>}</td>
                    <td className="muted">{r.note ?? ""}</td>
                  </tr>
                  {open === r.id && (
                    <tr><td colSpan={7}>
                      <div className="adm-sit">
                        <b>{tr("Situationen rättelsen gjordes i")}</b>
                        <p className="muted">
                          En lärdom talar bara vid exakt träff på alla delar. Två blad som bara liknar varandra
                          är två olika ritningar.
                        </p>
                        <table className="qty"><tbody>
                          {Object.entries(r.situation).map(([k, v]: any) => (
                            <tr key={k}><td className="muted">{k}</td><td className="lf-mono">{JSON.stringify(v)}</td></tr>
                          ))}
                          {!Object.keys(r.situation).length && (
                            <tr><td className="empty">{tr("Ingen situation sparad - rättelsen gjordes innan den delen fanns.")}</td></tr>
                          )}
                        </tbody></table>
                      </div>
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {d && !d.rows.length && <tr><td colSpan={7} className="empty">{tr("Ingen har rättat något ännu.")}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

export function Learning() {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.adm("learning").then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <p className="error">{err}</p>;
  if (!d) return <p className="muted">{tr("Laddar…")}</p>;
  const c = d.corrections, l = d.lessons;
  const reach = c.total ? c.with_situation / c.total : 0;

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Vad rättelserna har lärt systemet")}</h3>
        <p className="muted">
          Det här är den ärliga versionen av att systemet blir smartare. En rättelse får göra <b>{tr("exakt en sak")}</b> på
          ett senare blad: avgöra ett fall som motorn själv redan märkt som tvetydigt, till förmån för det svar
          en människa gav i samma situation. Den blir aldrig en sannolikhet, aldrig en modell som gissar, och
          aldrig något som går emot ritningen - därför att en gissning som ser ut som en läsning är värre än
          ingen läsning alls.
        </p>
        <div className="adm-stats">
          <div className="adm-stat"><div className="k">{tr("Rättelser")}</div><div className="v">{c.total}</div>
            <div className="s">{tr("som inte ångrats")}</div></div>
          <div className={`adm-stat${reach < 0.5 ? " bad" : " good"}`}>
            <div className="k">{tr("Kan tala igen")}</div><div className="v">{c.with_situation}</div>
            <div className="s">{c.without_situation} saknar situation</div></div>
          <div className="adm-stat"><div className="k">{tr("Lärdomar")}</div><div className="v">{l.total}</div>
            <div className="s">{tr("en per situation")}</div></div>
          <div className={`adm-stat${l.strong ? " good" : ""}`}>
            <div className="k">{tr("Starka lärdomar")}</div><div className="v">{l.strong}</div>
            <div className="s">{tr("samma svar två gånger eller fler")}</div></div>
        </div>
      </div>

      <div className="adm-two" style={{ marginTop: 14 }}>
        <section className="card">
          <h3 style={{ marginTop: 0 }}>{tr("Vad en lärdom aldrig får göra")}</h3>
          <ul className="adm-limits">{d.limits.map((t: string) => <li key={t}>{t}</li>)}</ul>
        </section>
        <section className="card">
          <h3 style={{ marginTop: 0 }}>{tr("Vad en situation består av")}</h3>
          <p className="muted">{tr("Alla sex läses av ritningen. Alla sex måste stämma.")}</p>
          <ul className="adm-limits">{d.keys.map((k: string) => <li key={k}><code>{k}</code></li>)}</ul>
        </section>
      </div>

      <section className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <h3>{tr("Lärdomarna")}</h3>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>Svar</th><th className="num">{tr("Gånger")}</th><th className="num">Personer</th><th>Situation</th></tr></thead>
            <tbody>
              {l.rows.map((r: any, i: number) => (
                <tr key={i}>
                  <td className="lf-mono">{r.answer ?? r.choice ?? "–"}</td>
                  <td className="num"><b>{r.times ?? 1}</b></td>
                  <td className="num muted">{r.people ?? "–"}</td>
                  <td className="muted small lf-mono">
                    {Object.entries(r.situation ?? {}).map(([k, v]: any) => `${k}=${v}`).join(" · ").slice(0, 160)}
                  </td>
                </tr>
              ))}
              {!l.rows.length && <tr><td colSpan={4} className="empty">
                Inga lärdomar ännu. De uppstår när någon rättar ett tvetydigt fall.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}

export function RulesMoved() {
  const [d, setD] = useState<any>(null);
  const [shot, setShot] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { api.adm("rules").then(setD).catch((e) => setErr(e.message)); }, []);
  if (err) return <p className="error">{err}</p>;

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Regler kunderna flyttat")}</h3>
        <p className="muted">
          En regel som flera konton flyttat åt <b>samma</b> håll är ingen inställning. Det är ett grundvärde som
          är fel, och den raden är märkt. En regel en enda kund flyttat är förmodligen deras kontors sätt att
          rita, och ska stå kvar som deras.
        </p>
      </div>
      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>Regel</th><th className="num">{tr("Flyttad av")}</th><th className="num">{tr("Från")}</th>
              <th className="num">Till</th><th>{tr("Skäl")}</th></tr></thead>
            <tbody>
              {(d?.rows ?? []).map((r: any) => (
                <tr key={r.rule_id} className={r.same_direction ? "bad" : ""}>
                  <td className="lf-mono">{r.rule_id}
                    {r.same_direction && <span className="badge warn small" style={{ marginLeft: 6 }}>
                      alla åt samma håll</span>}</td>
                  <td className="num"><b>{r.n}</b></td>
                  <td className="num">{r.min}</td>
                  <td className="num">{r.max}</td>
                  <td>
                    {r.movers.map((mv: any) => (
                      <div key={mv.user_id} className="muted small">
                        {mv.user}: {mv.value} {mv.note ? `— ${mv.note}` : ""}
                        {mv.has_shot && (
                          <button className="ghost small" style={{ marginLeft: 6 }}
                            onClick={() => api.adm(`rules/${encodeURIComponent(r.rule_id)}/shot/${mv.user_id}`).then(setShot)}>
                            bild
                          </button>
                        )}
                      </div>
                    ))}
                  </td>
                </tr>
              ))}
              {d && !d.rows.length && <tr><td colSpan={5} className="empty">{tr("Ingen har flyttat någon regel.")}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
      {shot && (
        <div className="adm-shot" onClick={() => setShot(null)}>
          <div className="inner" onClick={(e) => e.stopPropagation()}>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <b className="lf-mono">{shot.rule_id}</b>
              <button className="ghost small" onClick={() => setShot(null)}>{tr("Stäng")}</button>
            </div>
            {shot.note && <p className="muted">{shot.note}</p>}
            <img src={shot.shot} alt={tr("Fallet som fick regeln att flyttas")} />
          </div>
        </div>
      )}
    </>
  );
}
