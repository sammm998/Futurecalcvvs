import { useMemo, useState } from "react";

import { t as tr, num } from "../i18n";
/* Övningarna.
 *
 * Att läsa om en regel och att tillämpa den är två olika saker, och det är den andra som fastnar. Var övning är
 * ett litet blad med ett facit: man svarar, får rätt eller fel, och får veta varför. Ingen av dem går att klara
 * genom att gissa på det som ligger närmast - det är hela poängen med dem.
 */

function Verdict({ right, of, again }: { right: number; of: number; again: () => void }) {
  return (
    <div className="lx-verdict">
      <div className={`badge ${right === of ? "ok" : "warn"}`}>{right} av {of} rätt</div>
      <button type="button" className="ghost small" onClick={again}>{tr("Börja om")}</button>
    </div>
  );
}

/* ---------- 1. sträcka eller stigare ---------- */

type Card = { id: string; code: string; dim: string | null; riser: boolean; why: string };

const CARDS: Card[] = [
  { id: "c1", code: "S2-P5-110", dim: null, riser: false, why: "Allt står på en rad — en sträcka i planet, som mäts i meter." },
  { id: "c2", code: "S2-P5", dim: "110", riser: true, why: "Dimensionen står på raden under: en stigare i den punkten, som räknas som antal." },
  { id: "c3", code: "VS21-S13-15-F50", dim: null, riser: false, why: "En rad, med isolerklassen sist. Fortfarande en sträcka i planet." },
  { id: "c4", code: "KV1-X31", dim: "16", riser: true, why: "Dimensionen på raden under. Stigare." },
  { id: "c5", code: "2xKV1-X31", dim: "16", riser: false, why: "Två rader — men antalsprefixet säger att det är två rör som går tillsammans i planet, inte en stam." },
  { id: "c6", code: "S1-P2-75", dim: null, riser: false, why: "En rad. Sträcka." },
];

function RowsExercise() {
  const [given, setGiven] = useState<Record<string, boolean>>({});
  const [checked, setChecked] = useState(false);
  const right = CARDS.filter((c) => given[c.id] === c.riser).length;
  const all = Object.keys(given).length === CARDS.length;
  return (
    <div className="lx">
      <div className="lx-head">
        <h4>Sträcka eller stigare?</h4>
        <p className="muted">Står dimensionen på raden under beteckningen är det en stigare. Står allt på en rad
          är det en sträcka i planet. Ett antalsprefix är undantaget.</p>
      </div>
      <div className="lx-cards">
        {CARDS.map((c) => {
          const g = given[c.id];
          const ok = checked && g === c.riser;
          const bad = checked && g !== undefined && !ok;
          return (
            <div key={c.id} className={`lx-card${ok ? " ok" : ""}${bad ? " bad" : ""}`}>
              <div className="lx-label">
                <span className="lf-mono">{c.code}</span>
                {c.dim && <><span className="rule" /><span className="lf-mono dim">{c.dim}</span></>}
              </div>
              <div className="lx-choose">
                <button type="button" className={`secondary small${g === false ? " on" : ""}`}
                  onClick={() => { setGiven({ ...given, [c.id]: false }); setChecked(false); }}>{tr("Sträcka")}</button>
                <button type="button" className={`secondary small${g === true ? " on" : ""}`}
                  onClick={() => { setGiven({ ...given, [c.id]: true }); setChecked(false); }}>Stigare</button>
              </div>
              {checked && <p className={`lx-why${ok ? " ok" : ""}`}>{c.why}</p>}
            </div>
          );
        })}
      </div>
      <div className="row">
        <button type="button" disabled={!all} onClick={() => setChecked(true)}>{tr("Rätta")}</button>
        {checked && <Verdict right={right} of={CARDS.length} again={() => { setGiven({}); setChecked(false); }} />}
      </div>
    </div>
  );
}

/* ---------- 2. följ hänvisningslinjen, inte närheten ---------- */

/** Three parallel runs, one label. The leader lands on the middle one; the nearest to the label is the top one. */
const BUNDLE = [
  { id: "p1", y: 150, code: "VV1-X31-16", hue: "#c2410c" },
  { id: "p2", y: 182, code: "KV1-X31-16", hue: "#2563eb" },
  { id: "p3", y: 214, code: "VVC1-X31-12", hue: "#b45309" },
];

function LeaderExercise() {
  const [pick, setPick] = useState<string | null>(null);
  const answer = "p2";
  const done = pick !== null;
  return (
    <div className="lx">
      <div className="lx-head">
        <h4>Vilket rör namnger etiketten?</h4>
        <p className="muted">Tre rör går i bunt. En etikett med en hänvisningslinje pekar på ett av dem.
          Klicka på det rör linjen faktiskt slutar på.</p>
      </div>
      <div className="lx-sheet">
        <svg viewBox="0 0 620 300" role="img" aria-label={tr("Tre parallella rör och en etikett med hänvisningslinje")}>
          <rect x="6" y="6" width="608" height="288" rx="6" fill="#fff" stroke="var(--line-2)" />
          <g stroke="#e6e6e6" strokeWidth="1.6" fill="none"><path d="M40 40 H580 V270 H40 Z M330 40 V270" /></g>
          {BUNDLE.map((p) => {
            const on = pick === p.id;
            const ok = done && p.id === answer;
            const bad = done && on && p.id !== answer;
            return (
              <g key={p.id} onClick={() => !done && setPick(p.id)} style={{ cursor: done ? "default" : "pointer" }}>
                <path d={`M70 ${p.y} H560`} stroke="transparent" strokeWidth="24" fill="none" />
                {(on || ok) && <path d={`M70 ${p.y} H560`} stroke={ok ? "#15803d" : "#a32020"} strokeOpacity="0.16"
                  strokeWidth="16" strokeLinecap="round" fill="none" />}
                <path d={`M70 ${p.y} H560`} stroke={bad ? "#a32020" : p.hue} strokeWidth="4.6"
                  strokeDasharray="14 7" strokeLinecap="round" fill="none" />
                {done && <text x="566" y={p.y + 4} className="lf-mono" fontSize="10.5" fill="var(--faint)">{p.code}</text>}
              </g>
            );
          })}
          <rect x="120" y="62" width="132" height="26" rx="4" fill="#fff" stroke="var(--line-2)" />
          <text x="130" y="80" className="lf-mono" fontSize="11.5" fill="var(--ink)">KV1-X31-16</text>
          <path d="M252 76 L300 182" stroke="#c026d3" strokeWidth="1.6" fill="none" />
          <circle cx="300" cy="182" r="5" fill="#fff" stroke="#c026d3" strokeWidth="2.2" />
          <text x="70" y="264" className="lf-mono" fontSize="10.5" fill="var(--faint)">
            NÄRMAST ETIKETTEN ÄR INTE SAMMA SAK SOM UTPEKAD
          </text>
        </svg>
      </div>
      {done && (
        <p className={`lx-why${pick === answer ? " ok" : ""}`}>
          {pick === answer
            ? "Rätt. Linjen slutar på det mittersta röret, och det är det enda som avgör saken."
            : "Nej. Det rör du valde ligger närmare etiketten, men hänvisningslinjen slutar på det mittersta. Närhet är inget bevis — i en bunt hör grannröret till ett annat system."}
          {" "}<button type="button" className="ghost small" onClick={() => setPick(null)}>{tr("Försök igen")}</button>
        </p>
      )}
    </div>
  );
}

/* ---------- 3. läs av skalan ---------- */

const SCALE_Q = [
  { id: "s1", mm: 62, m: 3.1 },
  { id: "s2", mm: 140, m: 7.0 },
  { id: "s3", mm: 34, m: 1.7 },
];
const OPTS = [1.7, 3.1, 5.0, 7.0, 12.4];

function ScaleExercise() {
  const [given, setGiven] = useState<Record<string, number>>({});
  const [checked, setChecked] = useState(false);
  const right = SCALE_Q.filter((q) => given[q.id] === q.m).length;
  const all = useMemo(() => Object.keys(given).length === SCALE_Q.length, [given]);
  return (
    <div className="lx">
      <div className="lx-head">
        <h4>{tr("Läs av sträckan")}</h4>
        <p className="muted">Bladet är i skala 1:50. Skalstocken under visar hur långt fem meter är på pappret.
          Hur lång är var sträcka i verkligheten?</p>
      </div>
      <div className="lx-sheet">
        <svg viewBox="0 0 400 292" role="img" aria-label={tr("Tre sträckor och en skalstock")}>
          <rect x="6" y="6" width="388" height="280" rx="6" fill="#fff" stroke="var(--line-2)" />
          {SCALE_Q.map((q, i) => (
            <g key={q.id} transform={`translate(60 ${58 + i * 56})`}>
              <text x="0" y="-8" className="lf-mono" fontSize="10.5" fill="var(--faint)">{q.id.toUpperCase()}</text>
              <path d={`M0 0 H${q.mm}`} stroke="#2563eb" strokeWidth="4.6" strokeDasharray="14 7"
                strokeLinecap="round" fill="none" />
              <path d={`M0 -9 V9 M${q.mm} -9 V9`} stroke="var(--line-2)" strokeWidth="1.2" />
              {checked && (
                <text x={q.mm + 14} y="4" className="lf-mono" fontSize="11"
                  fill={given[q.id] === q.m ? "var(--ok)" : "var(--warn)"}>
                  {num(q.m, 1)} m
                </text>
              )}
            </g>
          ))}
          <g transform="translate(48 240)">
            <text x="0" y="-12" className="lf-mono" fontSize="10.5" fill="var(--faint)">{tr("SKALSTOCK · 5 M")}</text>
            <rect x="0" y="0" width="50" height="10" fill="#0d0d0d" />
            <rect x="50" y="0" width="50" height="10" fill="#fff" stroke="#0d0d0d" />
            <text x="106" y="9" className="lf-mono" fontSize="10.5" fill="var(--faint)">0 — 5 m</text>
          </g>
        </svg>
      </div>
      <div className="lx-rows">
        {SCALE_Q.map((q) => (
          <div key={q.id} className="lx-row">
            <span className="lf-mono">{q.id.toUpperCase()}</span>
            <div className="lx-opts">
              {OPTS.map((o) => (
                <button key={o} type="button"
                  className={`secondary small${given[q.id] === o ? " on" : ""}${checked && o === q.m ? " right" : ""}`}
                  onClick={() => { setGiven({ ...given, [q.id]: o }); setChecked(false); }}>
                  {num(o, 1)} m
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div className="row">
        <button type="button" disabled={!all} onClick={() => setChecked(true)}>{tr("Rätta")}</button>
        {checked && <Verdict right={right} of={SCALE_Q.length} again={() => { setGiven({}); setChecked(false); }} />}
      </div>
      {checked && (
        <p className="lx-why">
          Skalstocken är alltid det säkraste beskedet om hur stort bladet är: den krymper med pappret, vilket den
          utskrivna skalan inte gör. Ett blad som skrivits ut i A3 från A1 säger fortfarande 1:50 i stämpeln, och
          den siffran är då fel.
        </p>
      )}
    </div>
  );
}

const EX: Record<string, () => JSX.Element> = {
  rader: RowsExercise, ledare: LeaderExercise, skala: ScaleExercise,
};

export default function LearnExercise({ id }: { id: string }) {
  const E = EX[id];
  return E ? <E /> : null;
}

export const EXERCISE_IDS = Object.keys(EX);
