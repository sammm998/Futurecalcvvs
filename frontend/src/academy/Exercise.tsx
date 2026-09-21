import { useState } from "react";
import { t as tr, locale } from "../i18n";
import TrainingDrawing, { Symbol, type Run } from "./TrainingDrawing";
import { ac, type AttemptOut, type ExerciseOut, type PlanData } from "./api";

/* Övningen.
 *
 * En komponent per sort, och en ram runt dem alla som sköter det som är gemensamt: instruktionen, knappen
 * som rättar, ledtråden, återkopplingen och lösningen när den får visas.
 *
 * Rättningen sker alltid på servern. Den här filen vet inte vad som är rätt och kan därför inte råka visa det.
 */

type Props = { ex: ExerciseOut; onDone?: (r: AttemptOut) => void; exam?: boolean; onExam?: (given: unknown) => void };

export default function Exercise({ ex, onDone, exam = false, onExam }: Props) {
  const [given, setGiven] = useState<any>(() => empty(ex.kind));
  const [out, setOut] = useState<AttemptOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [showHint, setShowHint] = useState(false);

  const set = (v: any) => {
    setGiven(v);
    setOut(null);
    if (exam) onExam?.(v);
  };

  const check = async () => {
    setBusy(true);
    setErr("");
    try {
      const r = await ac.attempt(ex.slug, given);
      setOut(r);
      onDone?.(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Rättningen misslyckades");
    } finally {
      setBusy(false);
    }
  };

  const used = out?.forsok ?? ex.attempts;
  const left = ex.max_attempts ? ex.max_attempts - used : null;

  return (
    <section className={`ex${out?.passed ? " ok" : out ? " no" : ""}`}>
      <header className="ex-head">
        <div>
          <p className="fc-label">
            Övning · {kindName(ex.kind)} · {"●".repeat(ex.difficulty)}{"○".repeat(3 - ex.difficulty)}
            {ex.tolerance_pct > 0 && ` · tolerans ±${String(ex.tolerance_pct).replace(".", ",")} %`}
          </p>
          <h3>{ex.title}</h3>
        </div>
        <span className="ex-pts fc-label">{ex.points} p</span>
      </header>
      <p className="ex-inst">{ex.instructions}</p>

      <div className="ex-body">
        <Body ex={ex} given={given} set={set} />
      </div>

      {!exam && (
        <div className="ex-foot">
          <button className="fc-btn solid" onClick={check} disabled={busy || !ready(ex.kind, given)}>
            {busy ? "Rättar…" : "Kontrollera"}
          </button>
          {!!ex.hints.length && !out?.passed && (
            <button className="fc-btn sm" onClick={() => setShowHint((s) => !s)}>
              {showHint ? "Dölj ledtråd" : "Visa ledtråd"}
            </button>
          )}
          {out && !out.passed && <button className="fc-btn sm" onClick={() => { setGiven(empty(ex.kind)); setOut(null); }}>{tr("Försök igen")}</button>}
          {left !== null && <span className="fc-label">{left} försök kvar</span>}
        </div>
      )}

      {showHint && !!ex.hints.length && (
        <p className="ex-hint"><b>Ledtråd:</b> {ex.hints[Math.min(used, ex.hints.length - 1)]}</p>
      )}
      {err && <p className="ex-err" role="alert">{err}</p>}
      {out && <Result out={out} />}
    </section>
  );
}

/* ---------------------------------------------------------------- resultatet */

function Result({ out }: { out: AttemptOut }) {
  const f = out.feedback || {};
  return (
    <div className={`ex-res ${out.passed ? "ok" : "no"}`} role="status">
      {/* Rätt och fel får aldrig bara vara en färg: ikon, ord och text säger samma sak. */}
      <p className="ex-res-top">
        <span className="ex-res-i" aria-hidden="true">{out.passed ? "✓" : "✕"}</span>
        <b>{out.passed ? "Godkänd" : "Inte godkänd än"}</b>
        <span className="fc-label">{Math.round(out.score * 100)} %</span>
        {out.xp > 0 && <span className="ex-xp">+{out.xp} XP</span>}
      </p>
      <p className="ex-res-t">{f.text}</p>

      {Array.isArray(f.steg) && (
        <table className="ex-steps"><tbody>
          {f.steg.map((s: any) => (
            <tr key={s.key} className={s.ok ? "ok" : "no"}>
              <td><span aria-hidden="true">{s.ok ? "✓" : "✕"}</span> {s.label}</td>
              <td className="num">{fmt(s.ditt)} {s.unit}</td>
              <td className="num">{s.ok ? "" : `rätt: ${fmt(s.ratt)} ${s.unit}`}</td>
            </tr>
          ))}
        </tbody></table>
      )}
      {Array.isArray(f.poster) && (
        <table className="ex-steps"><tbody>
          {f.poster.map((s: any) => (
            <tr key={s.key} className={s.ok ? "ok" : "no"}>
              <td><span aria-hidden="true">{s.ok ? "✓" : "✕"}</span> {s.key}</td>
              <td className="num">{fmt(s.ditt)}</td>
              <td className="num">{s.ok ? "" : `rätt: ${fmt(s.ratt)}`}</td>
            </tr>
          ))}
        </tbody></table>
      )}
      {f.din_mangd !== undefined && (
        <dl className="ex-nums">
          <div><dt>{tr("Din mängd")}</dt><dd>{fmt(f.din_mangd)} m</dd></div>
          <div><dt>{tr("Rätt mängd")}</dt><dd>{fmt(f.ratt_mangd)} m</dd></div>
          <div><dt>Avvikelse</dt><dd>{fmt(f.avvikelse_pct, 1)} %</dd></div>
        </dl>
      )}
      {out.ledtrad && <p className="ex-hint"><b>Ledtråd:</b> {out.ledtrad}</p>}
      {out.losning && <p className="ex-sol"><b>Lösning:</b> {out.losning}</p>}
    </div>
  );
}

const fmt = (v: unknown, d = 2) =>
  typeof v === "number" ? v.toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d }) : "—";

/* ---------------------------------------------------------------- sorterna */

function Body({ ex, given, set }: { ex: ExerciseOut; given: any; set: (v: any) => void }) {
  const plan = ex.data as unknown as PlanData;
  switch (ex.kind) {
    case "mangda":
      return (
        <TrainingDrawing plan={plan} mode="matt" runs={given.runs || []}
          onRuns={(runs: Run[]) => set({ runs })}
          highlight={{ sys: plan.highlight_sys, dn: plan.highlight_dn }} />
      );
    case "markera":
    case "hitta-fel":
    case "ritningsquiz":
      if (ex.kind === "hitta-fel") return <FindErrors ex={ex} given={given} set={set} />;
      return (
        <TrainingDrawing plan={plan} mode="val" picked={given.picked || []}
          onPicked={(picked) => set({ picked })} />
      );
    case "dimension":
      return (
        <>
          <TrainingDrawing plan={plan} mode="las" highlight={{ run: plan.focus }} height={320} />
          <Choice options={plan.options || []} value={given.index} onPick={(i) => set({ index: i })} />
        </>
      );
    case "symbol":
      return (
        <>
          <figure className="ex-fig">
            <svg viewBox="-30 -30 60 60" className="ex-fig-svg"><Symbol kind={ex.data.figure} /></svg>
          </figure>
          <Choice options={ex.data.options || []} value={given.index} onPick={(i) => set({ index: i })} />
        </>
      );
    case "matcha":
      return <Match ex={ex} given={given} set={set} />;
    case "bygg":
      return <Order ex={ex} given={given} set={set} />;
    case "kalkyl":
      return <Steps ex={ex} given={given} set={set} />;
    case "numerisk":
      return (
        <label className="ex-num">
          <span>{tr("Ditt svar")}</span>
          <input inputMode="decimal" value={given.value ?? ""} onChange={(e) => set({ value: e.target.value })} />
          <span className="fc-label">{ex.data.unit}</span>
        </label>
      );
    case "kategorisera":
      return <Buckets ex={ex} given={given} set={set} />;
    case "rum":
      return <Room ex={ex} given={given} set={set} plan={plan} />;
    default:
      return <p className="ex-inst">{tr("Den här övningstypen kan inte visas här.")}</p>;
  }
}

function Choice({ options, value, onPick }: { options: string[]; value?: number; onPick: (i: number) => void }) {
  return (
    <div className="ex-choice" role="radiogroup">
      {options.map((o, i) => (
        <button key={o} role="radio" aria-checked={value === i}
          className={`ex-opt${value === i ? " on" : ""}`} onClick={() => onPick(i)}>
          <span className="ex-opt-k">{String.fromCharCode(65 + i)}</span>{o}
        </button>
      ))}
    </div>
  );
}

function Steps({ ex, given, set }: { ex: ExerciseOut; given: any; set: (v: any) => void }) {
  const steps = ex.data.steps || [];
  return (
    <div className="ex-calc">
      <table className="ex-given"><tbody>
        {(ex.data.givna || []).map(([k, v]: [string, string]) => (
          <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>
        ))}
      </tbody></table>
      <div className="ex-steps-in">
        {steps.map((s: any) => (
          <label key={s.key}>
            <span>{s.label}</span>
            <input inputMode="decimal" value={given.steps?.[s.key] ?? ""}
              placeholder={s.hint}
              onChange={(e) => set({ steps: { ...(given.steps || {}), [s.key]: e.target.value } })} />
            <span className="fc-label">{s.unit}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

function Room({ ex, given, set, plan }: { ex: ExerciseOut; given: any; set: (v: any) => void; plan: PlanData }) {
  return (
    <>
      <TrainingDrawing plan={plan} mode="matt" runs={given.runs || []} onRuns={(runs) => set({ ...given, runs })} />
      <div className="ex-steps-in">
        {(ex.data.poster || []).map((p: any) => (
          <label key={p.key}>
            <span>{p.label}</span>
            <input inputMode="decimal" value={given.items?.[p.key] ?? ""}
              onChange={(e) => set({ ...given, items: { ...(given.items || {}), [p.key]: e.target.value } })} />
            <span className="fc-label">{p.unit}</span>
          </label>
        ))}
      </div>
    </>
  );
}

function Match({ ex, given, set }: { ex: ExerciseOut; given: any; set: (v: any) => void }) {
  const [held, setHeld] = useState<string | null>(null);
  const pairs: Record<string, string> = given.pairs || {};
  const taken = new Set(Object.values(pairs));
  return (
    <div className="ex-match">
      <div className="ex-match-l">
        {(ex.data.left || []).map((l: any) => (
          <button key={l.id} className={`ex-tile${held === l.id ? " held" : ""}${pairs[l.id] ? " done" : ""}`}
            onClick={() => setHeld(held === l.id ? null : l.id)} aria-pressed={held === l.id}>
            <svg viewBox="-30 -30 60 60"><Symbol kind={l.figure} /></svg>
            {pairs[l.id] && <span className="ex-tile-x" onClick={(e) => {
              e.stopPropagation();
              const p = { ...pairs }; delete p[l.id]; set({ pairs: p });
            }}>✕</span>}
          </button>
        ))}
      </div>
      <div className="ex-match-r">
        {(ex.data.right || []).map((r: any) => {
          const owner = Object.keys(pairs).find((k) => pairs[k] === r.id);
          return (
            <button key={r.id} className={`ex-slot${owner ? " done" : ""}`}
              disabled={!held && !owner}
              onClick={() => {
                if (!held) return;
                const p = { ...pairs };
                for (const k of Object.keys(p)) if (p[k] === r.id) delete p[k];
                p[held] = r.id;
                set({ pairs: p });
                setHeld(null);
              }}>
              {r.text}{taken.has(r.id) && <span aria-hidden="true"> ✓</span>}
            </button>
          );
        })}
      </div>
      <p className="td-hint">{tr("Klicka en symbol, klicka sedan dess namn. Klicka krysset för att lossa ett par.")}</p>
    </div>
  );
}

function Order({ ex, given, set }: { ex: ExerciseOut; given: any; set: (v: any) => void }) {
  const items = ex.data.items || [];
  const order: string[] = given.order?.length ? given.order : items.map((i: any) => i.id);
  const move = (i: number, d: number) => {
    const n = [...order];
    const j = i + d;
    if (j < 0 || j >= n.length) return;
    [n[i], n[j]] = [n[j], n[i]];
    set({ order: n });
  };
  const byId = Object.fromEntries(items.map((i: any) => [i.id, i.text]));
  return (
    <ol className="ex-order">
      {order.map((id, i) => (
        <li key={id}>
          <span className="ex-order-n">{i + 1}</span>
          <span className="ex-order-t">{byId[id]}</span>
          <span className="ex-order-b">
            <button onClick={() => move(i, -1)} disabled={i === 0} aria-label={`Flytta ${byId[id]} uppåt`}>↑</button>
            <button onClick={() => move(i, 1)} disabled={i === order.length - 1} aria-label={`Flytta ${byId[id]} nedåt`}>↓</button>
          </span>
        </li>
      ))}
    </ol>
  );
}

function Buckets({ ex, given, set }: { ex: ExerciseOut; given: any; set: (v: any) => void }) {
  const [held, setHeld] = useState<string | null>(null);
  const b: Record<string, string> = given.buckets || {};
  const items = ex.data.items || [];
  return (
    <div className="ex-buckets">
      <div className="ex-bucket-pool">
        {items.filter((i: any) => !b[i.id]).map((i: any) => (
          <button key={i.id} className={`ex-chip${held === i.id ? " held" : ""}`}
            onClick={() => setHeld(held === i.id ? null : i.id)} aria-pressed={held === i.id}>{i.text}</button>
        ))}
        {items.every((i: any) => b[i.id]) && <span className="td-hint">{tr("Alla utplacerade.")}</span>}
      </div>
      <div className="ex-bucket-row">
        {(ex.data.buckets || []).map((k: any) => (
          <div key={k.id} className="ex-bucket">
            <button className="ex-bucket-h" onClick={() => { if (held) { set({ buckets: { ...b, [held]: k.id } }); setHeld(null); } }}
              disabled={!held}>{k.text}</button>
            <ul>
              {items.filter((i: any) => b[i.id] === k.id).map((i: any) => (
                <li key={i.id}>
                  <button onClick={() => { const n = { ...b }; delete n[i.id]; set({ buckets: n }); }}>
                    {i.text} <span aria-hidden="true">✕</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function FindErrors({ ex, given, set }: { ex: ExerciseOut; given: any; set: (v: any) => void }) {
  const picked: string[] = given.picked || [];
  return (
    <table className="ex-rows">
      <thead><tr><th>Post</th><th className="num">{tr("Mängd")}</th><th className="num">Pris</th><th className="num">Tid</th><th /></tr></thead>
      <tbody>
        {(ex.data.rows || []).map((r: any) => {
          const on = picked.includes(r.id);
          return (
            <tr key={r.id} className={on ? "on" : ""}>
              <td>{r.text}</td><td className="num">{r.qty}</td><td className="num">{r.price}</td><td className="num">{r.time}</td>
              <td>
                <button className={`ex-flag${on ? " on" : ""}`} aria-pressed={on}
                  onClick={() => set({ picked: on ? picked.filter((p) => p !== r.id) : [...picked, r.id] })}>
                  {on ? "✓ Markerad" : "Markera fel"}
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

/* ---------------------------------------------------------------- hjälp */

function empty(kind: string): any {
  switch (kind) {
    case "mangda": return { runs: [] };
    case "rum": return { runs: [], items: {} };
    case "markera": case "hitta-fel": case "ritningsquiz": return { picked: [] };
    case "dimension": case "symbol": return {};
    case "matcha": return { pairs: {} };
    case "bygg": return { order: [] };
    case "kalkyl": return { steps: {} };
    case "numerisk": return {};
    case "kategorisera": return { buckets: {} };
    default: return {};
  }
}

function ready(kind: string, g: any): boolean {
  switch (kind) {
    case "mangda": return (g.runs || []).length > 0;
    case "rum": return Object.keys(g.items || {}).length > 0;
    case "markera": case "hitta-fel": case "ritningsquiz": return (g.picked || []).length > 0;
    case "dimension": case "symbol": return g.index !== undefined;
    case "matcha": return Object.keys(g.pairs || {}).length > 0;
    case "bygg": return true;
    case "kalkyl": return Object.keys(g.steps || {}).length > 0;
    case "numerisk": return !!String(g.value ?? "").trim();
    case "kategorisera": return Object.keys(g.buckets || {}).length > 0;
    default: return false;
  }
}

function kindName(k: string): string {
  return ({
    mangda: "Mängda", rum: "Mängda ett rum", markera: "Markera", "hitta-fel": "Hitta fel",
    ritningsquiz: "Ritningsquiz", dimension: "Dimension", symbol: "Symbol", matcha: "Matchning",
    bygg: "Bygg system", kalkyl: "Kalkyl", numerisk: "Räkna", kategorisera: "Sortera",
  } as Record<string, string>)[k] || k;
}

export { kindName };
