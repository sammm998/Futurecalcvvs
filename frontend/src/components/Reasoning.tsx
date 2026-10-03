import { useEffect, useState } from "react";
import { t as tr } from "../i18n";
import { api } from "../api";
import { tiltStyle, useTilt } from "./tilt";
import { AGENTS, AGENT_SV, frameSays } from "../agents";

/* How the reading got to its answer, from the first pass over the PDF to the last verdict.
 *
 * Every stage says what it found and hands that on to the next; the numbers are the ones the reading actually
 * worked from, not a retelling. After them the review agents speak: they never touch the measurement, they only
 * say whether they believe it, so a disagreement stays visible instead of being averaged away.
 */

type Frame = { stage: string; at: number; [k: string]: any };

const SEV: Record<string, string> = { ERROR: "bad", WARN: "warn", INFO: "ok" };

const BESLUT: Record<string, { text: string; cls: string }> = {
  GENOMFOR: { text: "genomförs", cls: "warn" },
  LAMNA: { text: "lämnas", cls: "ok" },
  RITNINGEN_SAGER_INTE: { text: "ritningen säger det inte", cls: "ok" },
};

/* A reviewer's card, leaning the way the reader is looking. The lean is the only thing that moves: what the
   card says is a finding, and a finding that slides about is harder to read, not easier. */
function AgentCard({ children }: { children: React.ReactNode }) {
  const { tilt, handlers } = useTilt(3.5);
  return (
    <div className="tiltwrap">
      <div className="agentcard tilt" {...handlers} style={tiltStyle(tilt, 6)}>{children}</div>
    </div>
  );
}

const ORDER = ["GENOMFOR", "RITNINGEN_SAGER_INTE", "LAMNA"];
const MEANS: Record<string, string> = {
  GENOMFOR: "Ritningen erbjuder svaret och det förs in i mängden.",
  RITNINGEN_SAGER_INTE: "Ritningen ger inget som avgör fallet. Mängden rörs inte; kontrollera på bladet.",
  LAMNA: "Noterat men ingenting att ändra: kontakten är förklarad och linjen ägd.",
};

/* The judge's verdicts, said once per reason instead of once per label.
 *
 * A sheet gives the same reason for twenty labels - "etiketten namnger flera system som ritningen drar som en
 * enda linje" - and printed twenty times it buried the two cases that mattered. Here each reason is one card
 * and the labels it covers are chips under it: a click on one goes to it on the sheet. The tiles at the top
 * count what was decided and filter the list. */
function Verdicts({ dom, onZoom }: { dom: any; onZoom?: (b: number[]) => void }) {
  const all: any[] = dom.utslag ?? [];
  const [only, setOnly] = useState<string | null>(null);
  const counts = new Map<string, number>();
  for (const v of all) counts.set(v.beslut, (counts.get(v.beslut) ?? 0) + 1);
  const groups = new Map<string, { beslut: string; skäl: string; items: any[] }>();
  for (const v of all) {
    if (only && v.beslut !== only) continue;
    const key = `${v.beslut}|${v.skäl}`;
    (groups.get(key) ?? groups.set(key, { beslut: v.beslut, skäl: v.skäl, items: [] }).get(key)!).items.push(v);
  }
  const rank = (b: string) => { const i = ORDER.indexOf(b); return i < 0 ? ORDER.length : i; };
  const list = [...groups.values()].sort((x, y) => rank(x.beslut) - rank(y.beslut) || y.items.length - x.items.length);
  return (
    <section className="verdictsec">
      <h3>{tr("Domarens utslag")}</h3>
      <p className="muted">{dom.regel}</p>
      {all.length === 0 && <p className="muted">{tr("Ingenting återstod att avgöra på det här bladet.")}</p>}
      {all.length > 0 && (
        <div className="vsummary">
          {ORDER.filter((b) => counts.get(b)).map((b) => (
            <button key={b} className={`vtile ${BESLUT[b]?.cls ?? "ok"}${only === b ? " on" : ""}`}
              onClick={() => setOnly(only === b ? null : b)} aria-pressed={only === b}>
              <span className="vcount">{counts.get(b)}</span>
              <span className="vname">{BESLUT[b]?.text ?? b}</span>
              <span className="vmeans">{MEANS[b]}</span>
            </button>
          ))}
        </div>
      )}
      <div className="vgroups">
        {list.map((g) => (
          <article key={`${g.beslut}|${g.skäl}`} className={`vgroup ${BESLUT[g.beslut]?.cls ?? "ok"}`}>
            <header>
              <span className={`badge ${BESLUT[g.beslut]?.cls ?? "ok"}`}>{BESLUT[g.beslut]?.text ?? g.beslut}</span>
              <span className="vn">{g.items.length} {g.items.length === 1 ? "fall" : "fall"}</span>
            </header>
            <p className="vwhy">{g.skäl}</p>
            <div className="vchips">
              {g.items.map((v, i) => {
                const more = [
                  v.kandidater?.length ? `Ritningens kandidater: ${v.kandidater.join(", ")}` : "",
                  v.delar_linje_med?.length ? `Delar linjen med: ${v.delar_linje_med.join(", ")}` : "",
                  v.kostar_m === 0 ? "Kostar mängden 0 m" : "",
                ].filter(Boolean).join("\n");
                return (
                  <button key={i} className={`vchip${v.bbox ? " go" : ""}`} disabled={!v.bbox}
                    title={more || undefined} onClick={() => v.bbox && onZoom?.(v.bbox)}>
                    {v.gäller || "—"}
                    {v.delar_linje_med?.length ? <small> + {v.delar_linje_med.length}</small> : null}
                  </button>
                );
              })}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export default function Reasoning({ jobId, result, onZoom }: { jobId: string; result: any; onZoom?: (b: number[]) => void }) {
  const [frames, setFrames] = useState<Frame[]>([]);
  const [dom, setDom] = useState<any>(null);
  useEffect(() => {
    let live = true;
    api.judge(jobId).then((d: any) => { if (live) setDom(d); }).catch(() => { /* the verdict is a view */ });
    return () => { live = false; };
  }, [jobId]);
  useEffect(() => {
    let live = true;
    api.film(jobId).then((f: any) => { if (live && Array.isArray(f.frames)) setFrames(f.frames); }).catch(() => { /* the account is a view */ });
    return () => { live = false; };
  }, [jobId]);
  const byStage: Record<string, Frame> = {};
  for (const f of frames) byStage[f.stage] = f;
  const findings = result?.review?.findings ?? [];
  const byAgent = new Map<string, any[]>();
  for (const f of findings) {
    const k = f.agent;
    if (!byAgent.has(k)) byAgent.set(k, []);
    byAgent.get(k)!.push(f);
  }
  const sr = result?.coverage?.second_reader;
  const ranReview: string[] = result?.review?.agents ?? [];

  return (
    <div className="sheetview">
      <div className="card reasoning">
        <h3>{tr("Vilka läsare som användes")}</h3>
        <p className="muted">
          En läsning som tyst använde en modell, eller tyst klarade sig utan en, är ingen läsning någon kan
          kontrollera. Här står vad som faktiskt kördes på det här jobbet.
        </p>
        <div className="roster">
          {AGENTS.map((a) => (
            <div key={a.stage} className={`rosteritem${byStage[a.stage] ? " on" : ""}`}>
              <span className="rname">{a.who}</span>
              <span className="rwhat">{tr("i motorn, ur ritningens vektorer")}</span>
              <span className={`badge ${byStage[a.stage] ? "ok" : "warn"}`}>{byStage[a.stage] ? "kördes" : "inget att visa"}</span>
            </div>
          ))}
          {ranReview.map((name) => {
            const key = name.replace(/\(.*\)$/, "").replace(/_agent$/, "");
            const state = /\((.*)\)$/.exec(name)?.[1];
            return (
              <div key={name} className="rosteritem on">
                <span className="rname">{AGENT_SV[key] ?? key}</span>
                <span className="rwhat">
                  granskare, ändrar aldrig mätningen{state && state !== "ok" ? ` · ${state === "unavailable" ? "kunde inte laddas i den här installationen" : state === "failed" ? "försökte men kom inte igenom" : state}` : ""}
                </span>
                <span className={`badge ${state && state !== "ok" ? "warn" : "ok"}`}>
                  {state && state !== "ok" ? "kördes inte" : "kördes"}
                </span>
              </div>
            );
          })}
          <div className={`rosteritem${sr?.consulted ? " on" : ""}`}>
            <span className="rname">Andraläsaren{sr?.model ? ` · ${sr.model}` : ""}</span>
            <span className="rwhat">
              {sr?.consulted
                ? `tillfrågad i ${sr.asked ?? "?"} fall, avgjorde ${sr.settled ?? 0}, avstod ${sr.refused ?? 0}`
                : sr?.enabled
                  ? "tillgänglig men behövdes inte på det här bladet"
                  : `av: ${sr?.why ?? "ingen modell konfigurerad"}`}
            </span>
            <span className={`badge ${sr?.consulted ? "warn" : "ok"}`}>
              {sr?.consulted ? "användes" : sr?.enabled ? "tillgänglig" : "ej tillgänglig"}
            </span>
          </div>
          <div className="rosteritem">
            <span className="rname">Synläsaren{sr?.model ? ` · ${sr.model}` : ""}</span>
            <span className="rwhat">
              tittar på sidan som bild och namnger rutor att granska; flyttar aldrig en meter. Körs på begäran
              från fliken Analys, aldrig som en del av mätningen.
            </span>
            <span className="badge ok">{tr("på begäran")}</span>
          </div>
        </div>

        {dom && <Verdicts dom={dom} onZoom={onZoom} />}

        <h3>{tr("Så kom läsningen fram till svaret")}</h3>
        <p className="muted">
          Varje steg lämnar sitt fynd vidare till nästa. Granskarna längst ned rör aldrig mätningen — de säger
          bara om de tror på den, så att en oenighet syns istället för att jämnas ut.
        </p>

        <ol className="steps">
          {AGENTS.map((s, i) => {
            const f = byStage[s.stage];
            const lines = frameSays(s.stage, f, result);
            const done = !!f || s.stage === "MEASURING";
            return (
              <li key={s.stage} className={done ? "done" : "pending"}>
                <div className="stepno">{i + 1}</div>
                <div className="stepbody">
                  <div className="stepwho">{s.who}</div>
                  <h4>{s.title}</h4>
                  <p className="asks">”{s.asks}”</p>
                  {lines.length
                    ? lines.map((l, j) => <p key={j} className="says">{l}</p>)
                    : <p className="says muted">{tr("Steget lämnade inget att visa på det här bladet.")}</p>}
                  {i < AGENTS.length - 1 && <div className="handoff">lämnar vidare till {AGENTS[i + 1].who}</div>}
                </div>
              </li>
            );
          })}
        </ol>

        <h3>Granskarna</h3>
        {byAgent.size === 0 && <p className="muted">{tr("Ingen granskning finns sparad för det här jobbet.")}</p>}
        {[...byAgent.entries()].map(([agent, fs]) => (
          <AgentCard key={agent}>
            <div className="agenthead">
              <b>{AGENT_SV[agent] ?? agent}</b>
              <span className={`badge ${SEV[fs[0].severity] ?? "ok"}`}>
                {fs.some((f: any) => f.severity === "ERROR") ? "invänder" : fs.some((f: any) => f.severity === "WARN") ? "reserverar sig" : "noterar"}
              </span>
            </div>
            {fs.map((f: any, i: number) => (
              <p key={i} className="says">{f.message}</p>
            ))}
          </AgentCard>
        ))}

        <AgentCard>
          <div className="agenthead">
            <b>{tr("Andraläsaren")}</b>
            <span className={`badge ${sr?.consulted ? "warn" : "ok"}`}>{sr?.consulted ? "tillfrågad" : "ej tillfrågad"}</span>
          </div>
          <p className="says">
            {sr?.consulted
              ? `Tillfrågad i ${sr.calls ?? "?"} fall som läsningen själv inte kunde avgöra. Varje svar prövades mot ritningens egna kandidater innan det fick flytta en meter.`
              : "Läsningen behövde ingen andra mening på det här bladet: varje identitet vilar på en beteckning, en ritad hänvisningslinje och den graf geometrin bildar."}
          </p>
        </AgentCard>
      </div>
    </div>
  );
}
