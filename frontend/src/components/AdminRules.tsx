import { useEffect, useMemo, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { api } from "../api";
import LearnFigure from "./LearnFigures";

/* Reglerna läsningen följer, öppna för den som driver tjänsten.
 *
 * En mängd som inte går att ifrågasätta är inget belägg. Varje gräns i motorn har ett skäl, och skälet står i
 * koden där gränsen används - vilket hjälper den som läser koden och ingen annan. Här står de i ritningens
 * språk: vad regeln avgör, vad den står på, vad den stod på från början, och en levande figur som visar vad den
 * handlar om.
 *
 * En flyttad regel gäller för tjänsten - varje ritning som läses härnäst - så den flyttas av administratören,
 * med en anteckning om varför och en skärmbild av fallet, så att nästa person kan se vad som fick någon att
 * ändra den i stället för att hitta en siffra som inte stämmer med koden.
 */

type Rule = {
  id: string; group: string; title: string; why: string; unit: string;
  default: number | boolean; value: number | boolean; lo: number | null; hi: number | null;
  figure: string | null; tunable: boolean; fixed_why: string;
  changed?: boolean; note?: string | null; shot?: string | null; changed_at?: string | null;
};

const nice = (v: number | boolean) =>
  typeof v === "boolean" ? (v ? "på" : "av") : String(Math.round(v * 1000) / 1000).replace(".", ",");

function RuleRow({ r, onSave }: { r: Rule; onSave: (id: string, body: any) => Promise<void> }) {
  const [draft, setDraft] = useState(String(r.value).replace(".", ","));
  const [note, setNote] = useState(r.note ?? "");
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const file = useRef<HTMLInputElement>(null);
  const bool = typeof r.default === "boolean";
  useEffect(() => { setDraft(String(r.value).replace(".", ",")); setNote(r.note ?? ""); }, [r.value, r.note]);

  const save = async (body: any) => {
    setBusy(true); setErr("");
    try { await onSave(r.id, body); } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  // a screenshot of the case that made someone move the rule, kept beside it as the reason in picture form
  const shoot = async (f: File) => {
    if (f.size > 3_500_000) { setErr("bilden är större än 3,5 MB"); return; }
    const data = await new Promise<string>((ok, no) => {
      const r2 = new FileReader(); r2.onload = () => ok(String(r2.result)); r2.onerror = no; r2.readAsDataURL(f);
    });
    await save({ value: bool ? r.value : Number(draft.replace(",", ".")), note, shot: data });
  };

  return (
    <div className={`rulerow${r.changed ? " moved" : ""}${r.tunable ? "" : " fixed"}`}>
      <div className="rl-main">
        <button type="button" className="rl-head" onClick={() => setOpen(!open)}>
          <span className="nm">{r.title}</span>
          <span className="val" title={r.unit === "pt" ? "punkter på pappret — 1 pt = 1/72 tum"
            : r.unit === "textrader" ? "mätt i etikettens egen texthöjd" : r.unit}>
            {nice(r.value)}{r.unit ? <i> {r.unit}</i> : null}</span>
          {r.changed && <span className="badge warn small">flyttad</span>}
          {!r.tunable && <span className="badge small">fast</span>}
        </button>
        <p className="why">{r.why}</p>
        {open && (
          <div className="rl-body">
            {r.figure && <div className="rl-fig"><LearnFigure id={r.figure} /></div>}
            <div className="rl-edit">
              {r.tunable ? (
                <>
                  <label>
                    Värde
                    {bool ? (
                      <select value={r.value ? "1" : "0"} disabled={busy}
                        onChange={(e) => save({ value: e.target.value === "1", note })}>
                        <option value="0">av</option><option value="1">{tr("på")}</option>
                      </select>
                    ) : (
                      <input value={draft} disabled={busy} style={{ width: 96 }}
                        onChange={(e) => setDraft(e.target.value)} />
                    )}
                  </label>
                  <span className="muted">
                    från början {nice(r.default)}
                    {r.lo != null && r.hi != null && <> · går mellan {nice(r.lo)} och {nice(r.hi)}</>}
                  </span>
                  <label className="grow">
                    Varför flyttad
                    <input value={note} placeholder={tr("t.ex. det här kontoret drar linjerna en aning kort")}
                      onChange={(e) => setNote(e.target.value)} />
                  </label>
                  <div className="row">
                    {!bool && (
                      <button type="button" disabled={busy}
                        onClick={() => save({ value: Number(draft.replace(",", ".")), note })}>Spara</button>
                    )}
                    <input type="file" accept="image/*" ref={file} hidden
                      onChange={(e) => { const f = e.target.files?.[0]; if (f) shoot(f); }} />
                    <button type="button" className="secondary small" disabled={busy}
                      onClick={() => file.current?.click()}>
                      {r.shot ? "Byt skärmbild" : "Lägg till skärmbild"}
                    </button>
                    {r.changed && (
                      <button type="button" className="ghost small" disabled={busy}
                        onClick={() => save({ reset: true })}>{tr("Återställ")}</button>
                    )}
                  </div>
                  {r.shot && <img className="rl-shot" src={r.shot} alt={tr("Fallet som fick regeln att flyttas")} />}
                </>
              ) : (
                <p className="lf-note">{r.fixed_why}</p>
              )}
              {err && <p className="error">{err}</p>}
              <p className="muted rl-id"><code>{r.id}</code></p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function RulesCatalogue() {
  const [cat, setCat] = useState<any>(null);
  const [err, setErr] = useState("");
  const [q, setQ] = useState("");
  const [only, setOnly] = useState<"alla" | "flyttade" | "flyttbara">("alla");
  const load = () => api.rules().then(setCat).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);
  const save = async (id: string, body: any) => { await api.setRule(id, body); await load(); };

  const groups = useMemo(() => {
    if (!cat) return [];
    const t = q.trim().toLowerCase();
    return cat.groups
      .map((g: any) => ({ ...g, rules: g.rules.filter((r: Rule) =>
        (!t || `${r.title} ${r.why} ${r.id}`.toLowerCase().includes(t))
        && (only === "alla" || (only === "flyttade" ? r.changed : r.tunable))) }))
      .filter((g: any) => g.rules.length);
  }, [cat, q, only]);

  return (
    <>
      {err && <p className="error">{err}</p>}
      <div className="adm-toolbar">
        <input value={q} placeholder={tr("Sök regel…")} onChange={(e) => setQ(e.target.value)} />
        <div className="seg">
          {(["alla", "flyttade", "flyttbara"] as const).map((k) => (
            <button key={k} className={only === k ? "on" : ""} onClick={() => setOnly(k)}>
              {k === "alla" ? "Alla" : k === "flyttade" ? "Flyttade" : "Går att flytta"}
            </button>
          ))}
        </div>
        <span className="muted small">
          {cat ? <>{cat.n_rules} regler · {cat.n_tunable} går att flytta · <b>{cat.n_changed} flyttade</b></> : "Laddar…"}
        </span>
      </div>
      {groups.map((g: any) => (
        <section key={g.group} className="card">
          <h3 style={{ marginTop: 0 }}>{g.group}</h3>
          <div className="rules">
            {g.rules.map((r: Rule) => <RuleRow key={r.id} r={r} onSave={save} />)}
          </div>
        </section>
      ))}
      {cat && !groups.length && <p className="muted">{tr("Ingen regel matchar.")}</p>}
    </>
  );
}
