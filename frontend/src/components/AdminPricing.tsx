import { useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

/* Priser och credits: vad ett blad kostar kunden, vad det kostar tjänsten, och marginalen däremellan.
 *
 * Prislistan står i credits och paketen i kronor - de flyttas här och ingen annanstans, och den som flyttar
 * dem ser i samma stund vad marginalen blir per format och paket. Kostnadsmodellen är uppmätt på korpusen
 * (results/*-kostnad/KOSTNAD.md) och kan justeras när serverpriset eller modellpriset ändras. Ingenting på den
 * här sidan når läsningen: ett pris kan aldrig flytta en meter. */

const num = (v: number | null | undefined, d = 2) =>
  v == null ? "–" : v.toLocaleString(locale(), { maximumFractionDigits: d });
const DATE = new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

function Num({ value, onChange, step = 0.5 }: { value: number; onChange: (v: number) => void; step?: number }) {
  return <input type="number" step={step} min={0} value={value} onChange={(e) => onChange(Number(e.target.value))} />;
}

export function Pricing() {
  const [d, setD] = useState<any>(null);
  const [prices, setPrices] = useState<any>(null);
  const [costs, setCosts] = useState<any>(null);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => api.adm("pricing").then((r) => { setD(r); setPrices(r.prices); setCosts(r.costs); });
  useEffect(() => { load().catch((e) => setMsg(e.message)); }, []);
  if (!d || !prices || !costs) return <p className="muted">{msg || "Laddar…"}</p>;
  const save = async () => {
    setMsg("");
    try { const r = await api.admPut("pricing", { prices, costs, note }); setD(r); setPrices(r.prices); setCosts(r.costs); setMsg("Sparat. Kunderna ser den nya listan nu."); }
    catch (e: any) { setMsg(e.message); }
  };
  const reset = () => { setPrices(d.defaults.prices); setCosts(d.defaults.costs); };
  const setSheet = (k: string, v: number) => setPrices({ ...prices, sheet: { ...prices.sheet, [k]: v } });
  const setPk = (i: number, k: string, v: any) => setPrices({ ...prices, packages: prices.packages.map((p: any, j: number) => j === i ? { ...p, [k]: v } : p) });
  return (
    <div>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Vad ett blad kostar kunden")}</h3>
        <p className="muted small">{tr("Credits per sida efter format, plus ett bläcktillägg för blad med många banor. Priset visas för kunden innan läsningen körs.")}</p>
        <div className="tablewrap">
          <table className="qty pricegrid">
            <thead><tr><th>{tr("A3 och mindre")}</th><th>A2</th><th>A1</th><th>A0</th><th>{tr("Större än A0")}</th><th>Bläcksteg (banor)</th><th>{tr("Per steg")}</th><th>Tak</th><th>{tr("Andra blick")}</th><th>Provcredits</th></tr></thead>
            <tbody>
              <tr>
                {["A3", "A2", "A1", "A0", "A0+"].map((k) => <td key={k}><Num value={prices.sheet[k]} onChange={(v) => setSheet(k, v)} /></td>)}
                <td><Num value={prices.ink_step_paths} step={1000} onChange={(v) => setPrices({ ...prices, ink_step_paths: v })} /></td>
                <td><Num value={prices.ink_step_credits} onChange={(v) => setPrices({ ...prices, ink_step_credits: v })} /></td>
                <td><Num value={prices.ink_cap_credits} onChange={(v) => setPrices({ ...prices, ink_cap_credits: v })} /></td>
                <td><Num value={prices.vision_page} onChange={(v) => setPrices({ ...prices, vision_page: v })} /></td>
                <td><Num value={prices.trial_credits} step={1} onChange={(v) => setPrices({ ...prices, trial_credits: v })} /></td>
              </tr>
            </tbody>
          </table>
        </div>
        <label className="row" style={{ gap: 8, marginTop: 10 }}>
          <input type="checkbox" checked={!!prices.refund_when_unmeasured} onChange={(e) => setPrices({ ...prices, refund_when_unmeasured: e.target.checked })} />
          En läsning som inte kunde ge en enda meter betalas tillbaka av sig själv
        </label>

        <h3>Paketen</h3>
        <div className="tablewrap">
          <table className="qty pricegrid">
            <thead><tr><th>Id</th><th>Namn</th><th>Credits</th><th>{tr("Kr exkl. moms")}</th><th>{tr("Kr per credit")}</th><th>Beskrivning</th><th></th></tr></thead>
            <tbody>
              {prices.packages.map((p: any, i: number) => (
                <tr key={i}>
                  <td><input value={p.id} style={{ width: 90 }} onChange={(e) => setPk(i, "id", e.target.value)} /></td>
                  <td><input value={p.name} style={{ width: 120 }} onChange={(e) => setPk(i, "name", e.target.value)} /></td>
                  <td><Num value={p.credits} step={5} onChange={(v) => setPk(i, "credits", v)} /></td>
                  <td><Num value={p.kr} step={10} onChange={(v) => setPk(i, "kr", v)} /></td>
                  <td>{num(p.credits ? p.kr / p.credits : null)}</td>
                  <td><input value={p.lead || ""} style={{ width: 320 }} onChange={(e) => setPk(i, "lead", e.target.value)} /></td>
                  <td><button className="ghost small" onClick={() => setPrices({ ...prices, packages: prices.packages.filter((_: any, j: number) => j !== i) })}>{tr("Ta bort")}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button className="secondary small" onClick={() => setPrices({ ...prices, packages: [...prices.packages, { id: "nytt", name: "Nytt paket", credits: 50, kr: 490, lead: "" }] })}>{tr("Lägg till paket")}</button>

        <h3>{tr("Vad ett blad kostar tjänsten")}</h3>
        <p className="muted small">Uppmätt på korpusen; se KOSTNAD.md. Flytta talen när servern eller modellen byter pris.</p>
        <div className="tablewrap">
          <table className="qty pricegrid">
            <thead><tr><th>{tr("Kr per kärntimme")}</th><th>{tr("CPU-s per 1000 banor")}</th><th>{tr("CPU-s fast per sida")}</th><th>{tr("Kr per modellfråga")}</th><th>{tr("Frågor per 1000 banor")}</th><th>{tr("Kr lagring per blad")}</th><th>{tr("Betalavgift %")}</th><th>{tr("Kr per synfråga")}</th></tr></thead>
            <tbody>
              <tr>
                {[["cpu_kr_per_hour", 0.05], ["cpu_s_per_1000_paths", 0.1], ["cpu_s_base", 0.5], ["llm_kr_per_question", 0.01], ["llm_questions_per_1000_paths", 0.05], ["storage_kr_per_sheet", 0.01], ["payment_fee_pct", 0.1], ["vision_kr_per_page", 0.05]].map(([k, st]) => (
                  <td key={k as string}><Num value={costs[k as string]} step={st as number} onChange={(v) => setCosts({ ...costs, [k as string]: v })} /></td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>

        <div className="row" style={{ marginTop: 14, gap: 10, alignItems: "center" }}>
          <input placeholder={tr("Varför ändras listan?")} value={note} onChange={(e) => setNote(e.target.value)} style={{ flex: 1 }} />
          <button onClick={save}>{tr("Spara prislistan")}</button>
          <button className="ghost" onClick={reset}>{tr("Utgångsläget")}</button>
        </div>
        {msg && <p className={/Sparat/.test(msg) ? "ok" : "error"} style={{ marginTop: 10 }}>{msg}</p>}
      </div>

      <div className="card" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}>{tr("Marginal per typblad")}</h3>
        <p className="muted small">Intäkten räknas med varje pakets kronor per credit; kostnaden ur modellen ovan. Ett typblad per format med ett vanligt antal banor.</p>
        <div className="tablewrap">
          <table className="qty">
            <thead>
              <tr><th>Format</th><th>Banor</th><th>Pris (credits)</th><th>Kostnad (kr)</th>
                {d.margin[0]?.per_package.map((p: any) => <th key={p.id}>Marginal · {p.id} ({num(p.kr_per_credit)} kr/credit)</th>)}
              </tr>
            </thead>
            <tbody>
              {d.margin.map((r: any) => (
                <tr key={r.size_class}>
                  <td>{r.size_class}</td><td>{r.paths.toLocaleString(locale())}</td><td>{num(r.credits)}</td><td>{num(r.cost_kr, 3)}</td>
                  {r.per_package.map((p: any) => <td key={p.id}>{num(p.margin_kr)} kr · {num(p.margin_pct, 1)} %</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Ledger />
    </div>
  );
}

function Ledger() {
  const [d, setD] = useState<any>(null);
  const [owner, setOwner] = useState("");
  const [credits, setCredits] = useState(10);
  const [note, setNote] = useState("");
  const [msg, setMsg] = useState("");
  const load = () => api.adm("credits").then(setD).catch((e) => setMsg(e.message));
  useEffect(() => { load(); }, []);
  if (!d) return null;
  const grant = async () => {
    setMsg("");
    try { await api.admPost("credits/grant", { owner, credits, note }); setOwner(""); setNote(""); setMsg("Tilldelat."); load(); }
    catch (e: any) { setMsg(e.message); }
  };
  const setStatus = async (id: string, status: string) => {
    try { await api.admPut(`credits/purchases/${id}`, { status }); load(); } catch (e: any) { setMsg(e.message); }
  };
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>Reskontran</h3>
      <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
        <div className="stat"><div className="k">{tr("Sålt")}</div><div className="v">{num(d.totals.sold_kr, 0)} <span className="unit">kr</span></div></div>
        <div className="stat"><div className="k">{tr("Använt i läsningar")}</div><div className="v">{num(d.totals.credits_used)} <span className="unit">credits</span></div></div>
        <div className="stat"><div className="k">{tr("Återbetalt")}</div><div className="v">{num(d.totals.credits_refunded)} <span className="unit">credits</span></div></div>
      </div>

      <h4>{tr("Tilldela credits")}</h4>
      <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        <input placeholder="e-post, account:<id> eller user:<id>" value={owner} onChange={(e) => setOwner(e.target.value)} style={{ width: 300 }} />
        <input type="number" value={credits} onChange={(e) => setCredits(Number(e.target.value))} style={{ width: 90 }} />
        <input placeholder={tr("Skäl")} value={note} onChange={(e) => setNote(e.target.value)} style={{ width: 240 }} />
        <button className="secondary small" onClick={grant} disabled={!owner}>Tilldela</button>
      </div>
      {msg && <p className={/Tilldelat/.test(msg) ? "ok" : "error"}>{msg}</p>}

      <h4>Saldon</h4>
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("Ägare")}</th><th>Nyckel</th><th>Saldo</th></tr></thead>
          <tbody>
            {d.owners.map((o: any) => <tr key={o.owner}><td>{o.name}</td><td className="muted">{o.owner}</td><td>{num(o.balance)}</td></tr>)}
            {d.owners.length === 0 && <tr><td colSpan={3} className="empty">{tr("Inga konton har credits än.")}</td></tr>}
          </tbody>
        </table>
      </div>

      <h4>{tr("Köp att fakturera")}</h4>
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("När")}</th><th>Vad</th><th>Credits</th><th>Kr</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {d.purchases.map((p: any) => (
              <tr key={p.id}>
                <td>{DATE.format(new Date(p.created_at))}</td><td>{p.note}</td><td>{num(p.credits)}</td><td>{num(p.kr, 0)}</td>
                <td><span className={`badge ${p.status === "betald" ? "ok" : p.status === "makulerad" ? "bad" : "warn"}`}>{p.status}</span></td>
                <td>
                  {p.status !== "betald" && p.status !== "makulerad" && <button className="ghost small" onClick={() => setStatus(p.id, "betald")}>{tr("Markera betald")}</button>}
                  {p.status !== "makulerad" && <button className="ghost small" onClick={() => setStatus(p.id, "makulerad")}>Makulera</button>}
                </td>
              </tr>
            ))}
            {d.purchases.length === 0 && <tr><td colSpan={6} className="empty">{tr("Inga köp än.")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Messages() {
  const [rows, setRows] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const load = () => api.adm("contact").then((r) => setRows(r.rows)).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const set = async (id: string, status: string) => { try { await api.admPut(`contact/${id}`, { status }); load(); } catch (e: any) { setErr(e.message); } };
  return (
    <div className="card">
      <h3 style={{ marginTop: 0 }}>{tr("Meddelanden från kontaktsidan")}</h3>
      {err && <p className="error">{err}</p>}
      <div className="tablewrap">
        <table className="qty">
          <thead><tr><th>{tr("När")}</th><th>Vem</th><th>{tr("Ämne")}</th><th>Meddelande</th><th>Status</th><th></th></tr></thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td>{DATE.format(new Date(m.created_at))}</td>
                <td>{m.name}<br /><a href={`mailto:${m.email}`}>{m.email}</a>{m.company && <><br /><span className="muted">{m.company}</span></>}</td>
                <td>{m.subject}</td>
                <td style={{ whiteSpace: "pre-wrap", maxWidth: 420 }}>{m.body}</td>
                <td><span className={`badge ${m.status === "ny" ? "warn" : m.status === "besvarad" ? "ok" : ""}`}>{m.status}</span></td>
                <td>
                  {m.status !== "besvarad" && <button className="ghost small" onClick={() => set(m.id, "besvarad")}>Besvarad</button>}
                  {m.status !== "stangd" && <button className="ghost small" onClick={() => set(m.id, "stangd")}>{tr("Stäng")}</button>}
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={6} className="empty">{tr("Inga meddelanden än.")}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
