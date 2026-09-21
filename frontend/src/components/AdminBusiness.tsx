import { Fragment, useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { api } from "../api";

/* Företagets halva av administrationen: konton, partners, provision, kundvård, innehåll, prov och heatmaps.
 *
 * Ingenting här får avgöra hur en ritning läses. Det står i varje fil som rör den här sidan därför att det är
 * den enda regeln som verkligen måste hålla: den dagen en rabattsats kan flytta en meter går det inte längre
 * att svara på varför en mängd blev som den blev.
 */

const kr = (v: number | null | undefined) =>
  v == null ? "–" : `${v.toLocaleString(locale(), { maximumFractionDigits: 0 })} kr`;
const when = (s: string | null) => (s ? new Date(s).toLocaleDateString(locale()) : "–");

function Field({ label, children }: { label: string; children: any }) {
  return <label className="adm-field"><span>{label}</span>{children}</label>;
}

// ---------------------------------------------------------------------------------------------------- konton
const PLANS = ["prov", "grund", "kontor", "obegransad"];
const STATUSES = ["aktiv", "pausad", "uppsagd"];

export function Accounts() {
  const [d, setD] = useState<any>(null);
  const [partners, setPartners] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [edit, setEdit] = useState<any>(null);
  const [err, setErr] = useState("");
  const load = () => api.adm(`accounts?q=${encodeURIComponent(q)}`).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { const t = setTimeout(load, 200); return () => clearTimeout(t); }, [q]);
  useEffect(() => { api.adm("partners").then((r) => setPartners(r.rows)).catch(() => { /* valfritt */ }); }, []);

  const blank = { name: "", org_no: "", plan: "prov", discount_pct: 0, mrr_ore: 0, status: "aktiv", partner_id: null, note: "" };
  const save = async () => {
    const body = { ...edit, mrr_ore: Math.round(Number(edit.mrr_kr || 0) * 100) };
    delete body.mrr_kr; delete body.members; delete body.readings; delete body.partner; delete body.created_at;
    delete body.referral_code; delete body.id;
    try {
      if (edit.id) await api.admPut(`accounts/${edit.id}`, body); else await api.admPost("accounts", body);
      setEdit(null); load();
    } catch (e: any) { setErr(e.message); }
  };

  return (
    <>
      <div className="card">
        <div className="matbar">
          <input className="grow" value={q} placeholder={tr("Sök konto, orgnr eller e-post…")} onChange={(e) => setQ(e.target.value)} />
          <button onClick={() => setEdit({ ...blank, mrr_kr: 0 })}>{tr("Nytt konto")}</button>
        </div>
        {err && <p className="error">{err}</p>}
        <p className="muted" style={{ margin: 0 }}>
          Ett konto är en kund; en inloggning är en person. Ett företag med fyra rörläggare är ett konto och
          fyra inloggningar, och rabatten, fakturan och partnern hör till kontot.
        </p>
      </div>

      {edit && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>{edit.id ? `Ändra ${edit.name || "konto"}` : "Nytt konto"}</h3>
          <div className="adm-form">
            <Field label="Namn"><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Org.nr"><input value={edit.org_no} onChange={(e) => setEdit({ ...edit, org_no: e.target.value })} /></Field>
            <Field label="Plan">
              <select value={edit.plan} onChange={(e) => setEdit({ ...edit, plan: e.target.value })}>
                {PLANS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select></Field>
            <Field label={tr("Läge")}>
              <select value={edit.status} onChange={(e) => setEdit({ ...edit, status: e.target.value })}>
                {STATUSES.map((p) => <option key={p} value={p}>{p}</option>)}
              </select></Field>
            <Field label={tr("Rabatt %")}><input type="number" value={edit.discount_pct}
              onChange={(e) => setEdit({ ...edit, discount_pct: Number(e.target.value) })} /></Field>
            <Field label={tr("Månadsintäkt kr")}><input type="number" value={edit.mrr_kr ?? 0}
              onChange={(e) => setEdit({ ...edit, mrr_kr: Number(e.target.value) })} /></Field>
            <Field label="Partner">
              <select value={edit.partner_id ?? ""} onChange={(e) => setEdit({ ...edit, partner_id: e.target.value || null })}>
                <option value="">ingen</option>
                {partners.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.code})</option>)}
              </select></Field>
            <Field label="Anteckning"><input value={edit.note} onChange={(e) => setEdit({ ...edit, note: e.target.value })} /></Field>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={save}>Spara</button>
            <button className="secondary small" onClick={() => setEdit(null)}>Avbryt</button>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>Konto</th><th>Plan</th><th>{tr("Läge")}</th><th className="num">Rabatt</th>
              <th className="num">{tr("Intäkt/mån")}</th><th>Partner</th><th className="num">{tr("Läsningar")}</th>
              <th>Inloggningar</th><th></th></tr></thead>
            <tbody>
              {(d?.rows ?? []).map((r: any) => (
                <tr key={r.id} className={r.status !== "aktiv" ? "muted" : ""}>
                  <td><b>{r.name || "(namnlöst)"}</b><div className="muted small">{r.org_no}</div></td>
                  <td>{r.plan}</td>
                  <td>{r.status === "aktiv" ? <span className="badge ok small">aktiv</span>
                    : <span className="badge warn small">{r.status}</span>}</td>
                  <td className="num">{r.discount_pct ? `${r.discount_pct} %` : "–"}</td>
                  <td className="num">{kr(r.mrr_kr)}</td>
                  <td className="muted">{r.partner ?? "–"}</td>
                  <td className="num">{r.readings}</td>
                  <td className="muted small">{r.members.map((m: any) => m.email).join(", ") || "–"}</td>
                  <td><button className="ghost small"
                    onClick={() => setEdit({ ...r, mrr_kr: r.mrr_kr })}>{tr("Ändra")}</button></td>
                </tr>
              ))}
              {d && !d.rows.length && <tr><td colSpan={9} className="empty">{tr("Inga konton upplagda.")}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {d?.without_account?.length > 0 && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>{tr("Inloggningar utan konto")}</h3>
          <p className="muted">
            De har registrerat sig men hör inte till någon kund ännu. Antalet läsningar säger vilka som är värda
            ett samtal.
          </p>
          <div className="tablewrap">
            <table className="qty">
              <thead><tr><th>E-post</th><th>Roll</th><th className="num">{tr("Läsningar")}</th><th>Sedan</th><th></th></tr></thead>
              <tbody>
                {d.without_account.map((u: any) => (
                  <tr key={u.id}>
                    <td>{u.email}</td>
                    <td>
                      <select value={u.role} onChange={async (e) => {
                        await api.admPut(`users/${u.id}`, { role: e.target.value }); load();
                      }}>
                        <option value="member">medlem</option><option value="partner">partner</option>
                        <option value="admin">{tr("administratör")}</option>
                      </select>
                    </td>
                    <td className="num">{u.readings}</td>
                    <td className="muted">{when(u.created_at)}</td>
                    <td>
                      <select defaultValue="" onChange={async (e) => {
                        if (!e.target.value) return;
                        await api.admPut(`users/${u.id}`, { account_id: e.target.value }); load();
                      }}>
                        <option value="">{tr("koppla till konto…")}</option>
                        {(d.rows ?? []).map((a: any) => <option key={a.id} value={a.id}>{a.name || a.id}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

// -------------------------------------------------------------------------------------------------- partners
const KINDS = [["affiliate", "Affiliate"], ["ambassador", "Ambassadör"], ["aterforsaljare", "Återförsäljare"]];

export function Partners() {
  const [d, setD] = useState<any>(null);
  const [edit, setEdit] = useState<any>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [payouts, setPayouts] = useState<any>(null);
  const [err, setErr] = useState("");
  const load = () => {
    api.adm("partners").then(setD).catch((e) => setErr(e.message));
    api.adm("payouts").then(setPayouts).catch(() => { /* en partner ser sina egna */ });
  };
  useEffect(() => { load(); }, []);
  const blank = { name: "", email: "", kind: "affiliate", code: "", discount_pct: 10, commission_pct: 20, commission_months: 12, status: "aktiv", payout_ref: "", note: "" };

  // Skicka de fält servern vill ha, inte allt utom de vi råkar komma ihåg att stryka. En uträknad kolumn som
  // läggs till på serversidan ska inte kunna följa med tillbaka in i en spara-knapp.
  const FIELDS = ["name", "email", "kind", "code", "discount_pct", "commission_pct",
                  "commission_months", "status", "payout_ref", "note"];
  const save = async () => {
    const body: any = {};
    FIELDS.forEach((k) => { body[k] = edit[k]; });
    try {
      if (edit.id) await api.admPut(`partners/${edit.id}`, body); else await api.admPost("partners", body);
      setEdit(null); load();
    } catch (e: any) { setErr(e.message); }
  };

  /* Att göra en uträknad provision till en utbetalning.
   *
   * Beloppet skrivs aldrig här. Servern räknar det ur samma funktion som visar provisionen i tabellen, i ören
   * hela vägen - ett belopp som någon skrivit av från en skärm är ett belopp som inte går att härleda. Det
   * enda som frågas är vilken månad det gäller, och förslaget är den som gick. */
  const lastMonth = () => {
    const d = new Date();
    d.setDate(1); d.setMonth(d.getMonth() - 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  };
  const draft = async (p: any) => {
    const period = window.prompt(
      `Vilken månad gäller utbetalningen till ${p.name}?\n\nProvisionen just nu är ${kr(p.monthly_commission_kr)}.`,
      lastMonth());
    if (!period) return;
    setErr("");
    try { await api.admPost("payouts/draft", { partner_id: p.id, period }); load(); }
    catch (e: any) { setErr(e.message); }
  };

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Partners och ambassadörer")}</h3>
        <p className="muted">
          Två procenttal, aldrig ett. <b>Rabatten</b> är kundens skäl att komma; <b>provisionen</b> är partnerns
          skäl att värva. De betalas av olika sidor av samma affär och sätts därför var för sig. Provisionen
          löper det antal månader som står i raden - noll betyder så länge kunden är kvar.
        </p>
        {d?.is_admin && <button onClick={() => setEdit({ ...blank })}>{tr("Ny partner")}</button>}
        {err && <p className="error">{err}</p>}
      </div>

      {edit && (
        <div className="card" style={{ marginTop: 14 }}>
          <h3 style={{ marginTop: 0 }}>{edit.id ? `Ändra ${edit.name}` : "Ny partner"}</h3>
          <div className="adm-form">
            <Field label="Namn"><input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="E-post"><input value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
            <Field label="Slag">
              <select value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value })}>
                {KINDS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select></Field>
            <Field label={tr("Värvningskod")}><input value={edit.code} placeholder="ANNA10"
              onChange={(e) => setEdit({ ...edit, code: e.target.value.toUpperCase() })} /></Field>
            <Field label={tr("Rabatt till kund %")}><input type="number" value={edit.discount_pct}
              onChange={(e) => setEdit({ ...edit, discount_pct: Number(e.target.value) })} /></Field>
            <Field label={tr("Provision %")}><input type="number" value={edit.commission_pct}
              onChange={(e) => setEdit({ ...edit, commission_pct: Number(e.target.value) })} /></Field>
            <Field label={tr("Provision i månader")}><input type="number" value={edit.commission_months}
              onChange={(e) => setEdit({ ...edit, commission_months: Number(e.target.value) })} /></Field>
            <Field label={tr("Utbetalning till")}><input value={edit.payout_ref} placeholder="bankgiro"
              onChange={(e) => setEdit({ ...edit, payout_ref: e.target.value })} /></Field>
          </div>
          <div className="row" style={{ marginTop: 12 }}>
            <button onClick={save}>Spara</button>
            <button className="secondary small" onClick={() => setEdit(null)}>Avbryt</button>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>Partner</th><th>Kod</th><th>Slag</th><th className="num">Rabatt</th>
              <th className="num">Provision</th><th className="num">Kunder</th>
              <th className="num">{tr("Per månad")}</th><th className="num">Utbetalt</th><th></th></tr></thead>
            <tbody>
              {(d?.rows ?? []).map((p: any) => (
                /* nyckeln hör hemma på det yttersta elementet raden ger tillbaka - ligger den på den inre
                   <tr> ser React en lista av namnlösa fragment och kan blanda ihop raderna vid en omsortering */
                <Fragment key={p.id}>
                  <tr>
                    <td><b>{p.name}</b><div className="muted small">{p.email}</div></td>
                    <td className="lf-mono">{p.code}</td>
                    <td className="muted">{KINDS.find(([v]) => v === p.kind)?.[1] ?? p.kind}</td>
                    <td className="num">{p.discount_pct} %</td>
                    <td className="num">{p.commission_pct} %
                      <div className="muted small">{p.commission_months ? `${p.commission_months} mån` : "löpande"}</div></td>
                    <td className="num">{p.n_accounts}</td>
                    <td className="num"><b>{kr(p.monthly_commission_kr)}</b></td>
                    <td className="num muted">{kr(p.paid_total_kr)}</td>
                    <td>
                      <button className="ghost small" onClick={() => setOpen(open === p.id ? null : p.id)}>Kunder</button>
                      {d.is_admin && <button className="ghost small" onClick={() => setEdit({ ...p })}>{tr("Ändra")}</button>}
                      {d.is_admin && p.monthly_commission_kr > 0 && (
                        <button className="ghost small" onClick={() => draft(p)}>{tr("Betala ut")}</button>
                      )}
                    </td>
                  </tr>
                  {open === p.id && (
                    <tr><td colSpan={9}>
                      <table className="qty">
                        <thead><tr><th>Kund</th><th>Plan</th><th>{tr("Läge")}</th><th className="num">{tr("Intäkt")}</th>
                          <th className="num">{tr("Månader")}</th><th className="num">Provision</th></tr></thead>
                        <tbody>
                          {p.accounts.map((a: any) => (
                            <tr key={a.account_id} className={a.within_window ? "" : "muted"}>
                              <td>{a.name || a.account_id}</td><td>{a.plan}</td><td>{a.status}</td>
                              <td className="num">{kr(a.mrr_kr)}</td>
                              <td className="num">{a.months}{a.within_window ? "" : " (utanför)"}</td>
                              <td className="num">{kr(a.commission_kr)}</td>
                            </tr>
                          ))}
                          {!p.accounts.length && <tr><td colSpan={6} className="empty">{tr("Inga värvade kunder ännu.")}</td></tr>}
                        </tbody>
                      </table>
                    </td></tr>
                  )}
                </Fragment>
              ))}
              {d && !d.rows.length && <tr><td colSpan={9} className="empty">{tr("Inga partners upplagda.")}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {payouts && (
        <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
          <h3>Utbetalningar</h3>
          <div className="tablewrap">
            <table className="qty">
              <thead><tr><th>Period</th><th>Partner</th><th className="num">Belopp</th><th>{tr("Läge")}</th><th></th></tr></thead>
              <tbody>
                {payouts.rows.map((p: any) => (
                  <tr key={p.id}>
                    <td className="lf-mono">{p.period}</td><td>{p.partner}</td>
                    <td className="num">{kr(p.amount_kr)}</td>
                    <td>{p.status === "utbetald" ? <span className="badge ok small">utbetald {when(p.paid_at)}</span>
                      : <span className="badge small">{p.status}</span>}</td>
                    <td>{d?.is_admin && p.status === "oppen" && (
                      <button className="ghost small" onClick={async () => {
                        await api.admPut(`payouts/${p.id}?status=utbetald`); load();
                      }}>{tr("Markera utbetald")}</button>
                    )}</td>
                  </tr>
                ))}
                {!payouts.rows.length && <tr><td colSpan={5} className="empty">{tr("Inga utbetalningar registrerade.")}</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

// ------------------------------------------------------------------------------------------------------- CRM
export function Crm() {
  const [d, setD] = useState<any>(null);
  const [accounts, setAccounts] = useState<any[]>([]);
  const [openOnly, setOpenOnly] = useState(false);
  const [n, setN] = useState<any>({ account_id: "", kind: "anteckning", subject: "", body: "" });
  const [err, setErr] = useState("");
  const load = () => api.adm(`crm?open_only=${openOnly}`).then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [openOnly]);
  useEffect(() => { api.adm("accounts").then((r) => setAccounts(r.rows)).catch(() => { /* valfritt */ }); }, []);

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Kundvård")}</h3>
        <p className="muted">Vad som hänt med en kund: ett samtal, ett mejl, ett löfte, ett problem.</p>
        <div className="adm-form">
          <Field label="Konto">
            <select value={n.account_id} onChange={(e) => setN({ ...n, account_id: e.target.value })}>
              <option value="">{tr("välj…")}</option>
              {accounts.map((a) => <option key={a.id} value={a.id}>{a.name || a.id}</option>)}
            </select></Field>
          <Field label="Slag">
            <select value={n.kind} onChange={(e) => setN({ ...n, kind: e.target.value })}>
              {["anteckning", "samtal", "mejl", "mote", "arende"].map((k) => <option key={k} value={k}>{k}</option>)}
            </select></Field>
          <Field label="Rubrik"><input value={n.subject} onChange={(e) => setN({ ...n, subject: e.target.value })} /></Field>
        </div>
        <textarea style={{ marginTop: 10 }} rows={3} value={n.body} placeholder={tr("Vad hände?")}
          onChange={(e) => setN({ ...n, body: e.target.value })} />
        <div className="row" style={{ marginTop: 10 }}>
          <button disabled={!n.account_id} onClick={async () => {
            try { await api.admPost("crm", n); setN({ ...n, subject: "", body: "" }); load(); }
            catch (e: any) { setErr(e.message); }
          }}>Spara</button>
          <label className="check"><input type="checkbox" checked={openOnly}
            onChange={(e) => setOpenOnly(e.target.checked)} /> Bara öppna</label>
        </div>
        {err && <p className="error">{err}</p>}
      </div>
      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>{tr("När")}</th><th>Konto</th><th>Slag</th><th>Rubrik</th><th>Text</th><th></th></tr></thead>
            <tbody>
              {(d?.rows ?? []).map((r: any) => (
                <tr key={r.id} className={r.done ? "muted" : ""}>
                  <td className="muted">{when(r.created_at)}</td>
                  <td>{r.account}</td><td>{r.kind}</td><td><b>{r.subject}</b></td>
                  <td className="muted">{r.body}</td>
                  <td>{!r.done && <button className="ghost small"
                    onClick={async () => { await api.admPut(`crm/${r.id}?done=true`); load(); }}>Klar</button>}</td>
                </tr>
              ))}
              {d && !d.rows.length && <tr><td colSpan={6} className="empty">{tr("Inga anteckningar.")}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------------------------------------------- CMS
export function Content() {
  const [rows, setRows] = useState<any[]>([]);
  const [slug, setSlug] = useState("");
  const [doc, setDoc] = useState<any>(null);
  const [err, setErr] = useState("");
  const load = () => api.adm("content").then((r) => setRows(r.rows)).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const open = (s: string) => {
    setSlug(s);
    api.adm(`content/${s}`).then((c) => setDoc({ ...c, draft: c.draft ?? c.body })).catch(() => setDoc({ slug: s, title: "", body: "", draft: "", published: false }));
  };
  const put = async (publish: boolean) => {
    try {
      await api.admPut(`content/${doc.slug}?publish=${publish}`, { title: doc.title, body: doc.body, draft: doc.draft, published: doc.published });
      load(); open(doc.slug);
    } catch (e: any) { setErr(e.message); }
  };

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Innehåll")}</h3>
        <p className="muted">
          Att spara och att publicera är två handlingar och inte en. Ett utkast som publicerar sig självt är hur
          en halvskriven mening hamnar på förstasidan.
        </p>
        <div className="matbar">
          <input className="grow" value={slug} placeholder={tr("sidans namn, t.ex. landning-rubrik")}
            onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} />
          <button disabled={!slug} onClick={() => open(slug)}>{tr("Öppna")}</button>
        </div>
        {err && <p className="error">{err}</p>}
      </div>

      {doc && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="row" style={{ justifyContent: "space-between" }}>
            <b className="lf-mono">{doc.slug}</b>
            {doc.published ? <span className="badge ok small">publicerad</span> : <span className="badge small">opublicerad</span>}
          </div>
          <Field label="Rubrik"><input value={doc.title} onChange={(e) => setDoc({ ...doc, title: e.target.value })} /></Field>
          <textarea rows={10} style={{ marginTop: 10 }} value={doc.draft ?? ""}
            onChange={(e) => setDoc({ ...doc, draft: e.target.value })} />
          <div className="row" style={{ marginTop: 10 }}>
            <button className="secondary" onClick={() => put(false)}>{tr("Spara utkast")}</button>
            <button onClick={() => put(true)}>Publicera</button>
          </div>
          {doc.body && doc.draft !== doc.body && (
            <details className="settings" style={{ marginTop: 12 }}>
              <summary>{tr("Vad som ligger ute nu")}</summary>
              <div className="body"><pre className="lf-pre">{doc.body}</pre></div>
            </details>
          )}
        </div>
      )}

      <div className="card" style={{ marginTop: 14, paddingTop: 6 }}>
        <div className="tablewrap">
          <table className="qty">
            <thead><tr><th>Sida</th><th>Rubrik</th><th>{tr("Läge")}</th><th className="num">Tecken</th><th>{tr("Ändrad")}</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} onClick={() => open(r.slug)} style={{ cursor: "pointer" }}>
                  <td className="lf-mono">{r.slug}</td><td>{r.title}</td>
                  <td>{r.published ? <span className="badge ok small">publicerad</span> : <span className="badge small">utkast</span>}
                    {r.has_draft && <span className="badge warn small" style={{ marginLeft: 6 }}>{tr("osparat utkast")}</span>}</td>
                  <td className="num muted">{r.chars}</td><td className="muted">{when(r.updated_at)}</td>
                </tr>
              ))}
              {!rows.length && <tr><td colSpan={5} className="empty">{tr("Inget innehåll ännu.")}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

// -------------------------------------------------------------------------------------------------- A/B-prov
export function Experiments() {
  const [d, setD] = useState<any>(null);
  const [n, setN] = useState<any>(null);
  const [err, setErr] = useState("");
  const load = () => api.adm("experiments").then(setD).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const blank = { key: "", title: "", hypothesis: "", goal_event: "mal", variants: { a: "Nuvarande", b: "Nytt" }, split_b: 0.5, status: "utkast" };

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>A/B-prov</h3>
        <p className="muted">
          Ett prov redovisas aldrig som ett enda tal. Två andelar som skiljer sig men vars intervall överlappar
          är inget resultat - det är ett prov som behöver gå längre, och sidan säger det rakt ut i stället för
          att låta någon läsa en vinnare ur brus. Besökaren hamnar på samma sida av provet vid varje
          sidladdning, annars mäter provet ingenting.
        </p>
        <button onClick={() => setN({ ...blank })}>{tr("Nytt prov")}</button>
        {err && <p className="error">{err}</p>}
      </div>

      {n && (
        <div className="card" style={{ marginTop: 14 }}>
          <div className="adm-form">
            <Field label="Nyckel"><input value={n.key} placeholder="landning-rubrik"
              onChange={(e) => setN({ ...n, key: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-") })} /></Field>
            <Field label="Rubrik"><input value={n.title} onChange={(e) => setN({ ...n, title: e.target.value })} /></Field>
            <Field label={tr("Målhändelse")}>
              <select value={n.goal_event} onChange={(e) => setN({ ...n, goal_event: e.target.value })}>
                <option value="mal">{tr("mål")}</option><option value="klick">klick</option>
              </select></Field>
            <Field label={tr("Andel som ser B")}><input type="number" step="0.05" min="0" max="1" value={n.split_b}
              onChange={(e) => setN({ ...n, split_b: Number(e.target.value) })} /></Field>
          </div>
          <textarea rows={2} style={{ marginTop: 10 }} value={n.hypothesis} placeholder={tr("Vad tror du händer, och varför?")}
            onChange={(e) => setN({ ...n, hypothesis: e.target.value })} />
          <div className="row" style={{ marginTop: 10 }}>
            <button disabled={!n.key} onClick={async () => {
              try { await api.admPost("experiments", n); setN(null); load(); } catch (e: any) { setErr(e.message); }
            }}>Skapa</button>
            <button className="secondary small" onClick={() => setN(null)}>Avbryt</button>
          </div>
        </div>
      )}

      {(d?.rows ?? []).map((e: any) => (
        <div key={e.id} className="card" style={{ marginTop: 14 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <h3 style={{ margin: 0 }}>{e.title || e.key}</h3>
              <p className="muted" style={{ margin: "4px 0 0" }}>{e.hypothesis}</p>
            </div>
            <div className="row">
              <select value={e.status} onChange={async (ev) => {
                await api.admPut(`experiments/${e.key}?status=${ev.target.value}`); load();
              }}>
                <option value="utkast">utkast</option><option value="igang">{tr("igång")}</option>
                <option value="avslutad">avslutad</option>
              </select>
            </div>
          </div>
          <div className="adm-arms">
            {["a", "b"].map((v) => {
              const arm = e.arms[v];
              return (
                <div key={v} className={`arm${e.settled && arm.rate === Math.max(e.arms.a.rate ?? 0, e.arms.b.rate ?? 0) ? " win" : ""}`}>
                  <div className="k">{v.toUpperCase()} · {arm.label}</div>
                  <div className="v">{arm.rate == null ? "–" : `${(arm.rate * 100).toFixed(1)} %`}</div>
                  <div className="s">{arm.goal} av {arm.sessions} besökare</div>
                  <div className="ci">
                    <span style={{ left: `${arm.lo * 100}%`, right: `${100 - arm.hi * 100}%` }} />
                  </div>
                  <div className="s muted">{(arm.lo * 100).toFixed(1)}–{(arm.hi * 100).toFixed(1)} %</div>
                </div>
              );
            })}
          </div>
          <p className={e.settled ? "badge ok" : "badge"}>{e.reading}</p>
        </div>
      ))}
      {d && !d.rows.length && <div className="card" style={{ marginTop: 14 }}>
        <p className="empty">{tr("Inga prov upplagda.")}</p></div>}
    </>
  );
}

// --------------------------------------------------------------------------------------------------- heatmap
export function Heatmap() {
  const [paths, setPaths] = useState<any[]>([]);
  const [path, setPath] = useState("");
  const [d, setD] = useState<any>(null);
  const [days, setDays] = useState(30);
  const [err, setErr] = useState("");
  useEffect(() => { api.adm(`paths?days=${days}`).then((r) => { setPaths(r.rows); if (!path && r.rows.length) setPath(r.rows[0].path); }).catch((e) => setErr(e.message)); }, [days]);
  useEffect(() => { if (path) api.adm(`heatmap?path=${encodeURIComponent(path)}&days=${days}`).then(setD).catch((e) => setErr(e.message)); }, [path, days]);

  const cells = d?.cells ?? [];
  const peak = Math.max(1, d?.peak ?? 1);
  const W = 480, H = 640;

  return (
    <>
      <div className="card">
        <h3 style={{ marginTop: 0 }}>{tr("Var folk klickar")}</h3>
        <p className="muted">
          Punkterna sparas som andelar av fönstret och inte som bildpunkter, så bilden gäller alla
          skärmstorlekar på en gång. Det som sparas är rutan och inte punkten: en heatmap som går att spåra
          tillbaka till en enskild person är ingen heatmap, det är en logg över någons arbetsdag.
        </p>
        <div className="matbar">
          <select className="grow" value={path} onChange={(e) => setPath(e.target.value)}>
            {paths.map((p) => <option key={p.path} value={p.path}>{p.path} ({p.clicks})</option>)}
            {!paths.length && <option value="">{tr("inga klick registrerade")}</option>}
          </select>
          <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>{tr("7 dygn")}</option><option value={30}>{tr("30 dygn")}</option><option value={90}>{tr("90 dygn")}</option>
          </select>
        </div>
        {err && <p className="error">{err}</p>}
      </div>

      <div className="adm-two" style={{ marginTop: 14 }}>
        <section className="card">
          <p className="muted" style={{ marginTop: 0 }}>{d ? `${d.clicks} klick` : "–"}</p>
          <svg viewBox={`0 0 ${W} ${H}`} className="adm-heat" role="img" aria-label={`Heatmap för ${path}`}>
            <rect width={W} height={H} className="page" />
            {cells.map((c: any) => {
              const w = W / (d.cols || 1), h = H / (d.rows || 1);
              const t = c.n / peak;
              return <rect key={`${c.x}-${c.y}`} x={c.x * w} y={c.y * h} width={w} height={h}
                fill={`hsl(${(1 - t) * 210} 92% 55%)`} opacity={0.18 + 0.72 * t} />;
            })}
          </svg>
        </section>
        <section className="card">
          <h3 style={{ marginTop: 0 }}>{tr("Mest klickade")}</h3>
          <table className="qty"><tbody>
            {Object.entries(d?.targets ?? {}).map(([k, v]: any) => (
              <tr key={k}><td className="muted small">{k}</td><td className="num">{v}</td></tr>
            ))}
            {!Object.keys(d?.targets ?? {}).length && <tr><td className="empty">{tr("Inget registrerat.")}</td></tr>}
          </tbody></table>
        </section>
      </div>
    </>
  );
}
