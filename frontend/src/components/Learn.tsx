import { useEffect, useMemo, useState } from "react";
import { t as tr, num } from "../i18n";
import { MODULES, readProgress, syncProgress, type Module } from "../learn";
import { api } from "../api";
import LearnWizard from "./LearnWizard";
import LearnExercise, { EXERCISE_IDS } from "./LearnExercises";

/* VVS-akademin.
 *
 * En läsning tar en stund, och den stunden är en av få gånger någon sitter still framför verktyget. Det här är
 * vad de kan göra under tiden - och eftersom det som lärs ut är precis det verktyget arbetar med, blir en person
 * som gått igenom det bättre på att läsa vad verktyget svarar. Var lektion är märkt som gjord i webbläsaren, så
 * nästa ritning kan fortsätta där den förra slutade.
 */

/* ---------- the figures the lessons point at ---------- */

/* ---------- the exercise: a small sheet to take off ---------- */

type Run = { id: string; d: string; answer: string | null; m: number };

const RUNS: Run[] = [
  { id: "a", d: "M100 250 H260 V160 H420", answer: "KV1-X31-16", m: 12.4 },
  { id: "b", d: "M100 288 H230 V330 H370", answer: "VV1-X31-16", m: 10.6 },
  { id: "c", d: "M450 92 H540 V240", answer: "S3-P2-110", m: 13.6 },
  { id: "d", d: "M400 330 H540", answer: null, m: 6.0 },
];
const CODES = ["KV1-X31-16", "VV1-X31-16", "S3-P2-110", "ingen beteckning"];
const HUE: Record<string, string> = {
  "KV1-X31-16": "#2563eb", "VV1-X31-16": "#c2410c", "S3-P2-110": "#15803d", "ingen beteckning": "#9b9b9b",
};

/** One of the sheet's own labels, with the line it draws to the run it names. */
function Label({ x, y, t, to }: { x: number; y: number; t: string; to: [number, number] }) {
  return (
    <g>
      <path d={`M${x + 112} ${y + 12} L${to[0]} ${to[1]}`} stroke="#c026d3" strokeWidth="1.3" fill="none" />
      <circle cx={to[0]} cy={to[1]} r="4.6" fill="#fff" stroke="#c026d3" strokeWidth="2" />
      <rect x={x} y={y} width="112" height="24" rx="4" fill="#fff" stroke="var(--line-2)" />
      <text x={x + 9} y={y + 16} className="lf-mono" fontSize="11.5" fill="var(--ink)">{t}</text>
    </g>
  );
}

export function Exercise() {
  const [picked, setPicked] = useState<string | null>(null);
  const [given, setGiven] = useState<Record<string, string>>({});
  const [checked, setChecked] = useState(false);
  const right = RUNS.filter((r) => given[r.id] === (r.answer ?? "ingen beteckning")).length;

  return (
    <div className="lf-ex">
      <div className="lf-ex-sheet">
        <svg viewBox="0 0 620 400" role="img" aria-label={tr("Övningsblad med fyra sträckor")}>
          <rect x="6" y="6" width="608" height="388" rx="6" fill="#fff" stroke="var(--line-2)" />
          <g stroke="#e0e0e0" strokeWidth="1.6" fill="none">
            <path d="M60 50 H560 V360 H60 Z M300 50 V360 M60 210 H300 M420 50 V210 M420 210 H560" />
          </g>
          <g className="lf-mono" fontSize="10" fill="var(--faint)">
            <text x="62" y="38">ÖVNINGSBLAD · SKALA 1:50</text>
            <text x="470" y="38">{tr("4 STRÄCKOR")}</text>
          </g>
          {RUNS.map((r) => {
            const g = given[r.id];
            const ok = checked && g === (r.answer ?? "ingen beteckning");
            const bad = checked && g && !ok;
            const on = picked === r.id;
            return (
              <g key={r.id} onClick={() => setPicked(r.id)} style={{ cursor: "pointer" }}>
                {(on || ok) && (
                  <path d={r.d} fill="none" strokeWidth="14" strokeLinecap="round" strokeLinejoin="round"
                    stroke={ok ? HUE[g] : "#0d0d0d"} strokeOpacity={ok ? 0.15 : 0.1} />
                )}
                <path d={r.d} fill="none" stroke="transparent" strokeWidth="22" />
                <path d={r.d} fill="none" strokeWidth={on ? 6 : 5} strokeLinecap="round" strokeLinejoin="round"
                  strokeDasharray="15 6"
                  stroke={bad ? "#a32020" : g ? HUE[g] : on ? "#0d0d0d" : "#b0b0b0"} />
              </g>
            );
          })}
          <Label x={72} y={104} t="KV1-X31-16" to={[260, 160]} />
          <Label x={72} y={196} t="VV1-X31-16" to={[230, 300]} />
          <Label x={330} y={62} t="S3-P2-110" to={[450, 92]} />
          <text x="400" y="316" className="lf-mono" fontSize="10.5" fill="var(--faint)">
            ingen etikett pekar hit
          </text>
        </svg>
      </div>
      <div className="lf-ex-side">
        <h4>{picked ? `Sträcka ${picked.toUpperCase()}` : "Välj en sträcka"}</h4>
        <p className="muted">
          {picked
            ? "Vilken beteckning namnger den? Följ hänvisningslinjen, inte närheten."
            : "Klicka på ett av de streckade rören i bladet."}
        </p>
        <div className="lf-ex-codes">
          {CODES.map((c) => (
            <button key={c} type="button" className={`secondary small${picked && given[picked] === c ? " on" : ""}`}
              disabled={!picked}
              onClick={() => picked && (setGiven({ ...given, [picked]: c }), setChecked(false))}>
              <i style={{ background: HUE[c] }} /> {c}
            </button>
          ))}
        </div>
        <div className="row" style={{ marginTop: 14 }}>
          <button type="button" onClick={() => setChecked(true)} disabled={Object.keys(given).length < RUNS.length}>
            Rätta
          </button>
          <button type="button" className="ghost small"
            onClick={() => { setGiven({}); setChecked(false); setPicked(null); }}>{tr("Börja om")}</button>
        </div>
        {checked && (
          <>
            <div className={`badge ${right === RUNS.length ? "ok" : "warn"}`} style={{ marginTop: 14 }}>
              {right} av {RUNS.length} rätt
            </div>
            <ul className="lf-ex-facit">
              {RUNS.map((r) => (
                <li key={r.id}>
                  <b>{r.id.toUpperCase()}</b> {r.answer ?? "ingen beteckning"}
                  <span className="muted"> · {r.answer ? `${num(r.m, 1)} m` : "mängdas inte"}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

/* Kurs för kurs.
 *
 * Kapitlen är kurser, och de tas i ordning: den kurs man är på står öppen, de bakom är klara, de framför är
 * låsta tills den pågående är gjord. Ordningen är innehållets egen - man kan inte läsa en beteckning innan man
 * vet vad ett system är - men en lås som inte går att öppna är en fälla, så varje låst kurs går att öppna ändå
 * med ett klick som säger att man hoppar.
 */
export function Awards() {
  const [rows, setRows] = useState<any[] | null>(null);
  useEffect(() => { api.awards().then((r) => setRows(r.awards)).catch(() => setRows([])); }, []);
  if (!rows || !rows.length) return null;
  const taken = rows.filter((a) => a.taken_at).length;
  return (
    <section className="lf-awards">
      <div className="row" style={{ justifyContent: "space-between" }}>
        <h3 style={{ margin: 0 }}>{tr("Utmärkelser")}</h3>
        <span className="muted small">{taken} av {rows.length}</span>
      </div>
      <div className="lf-award-grid">
        {rows.map((a) => (
          <div key={a.key} className={`lf-award${a.taken_at ? " on" : ""}`} title={a.why}>
            <span className="medal" aria-hidden="true">{a.taken_at ? "★" : "☆"}</span>
            <b>{a.title}</b>
            <span className="muted small">{a.why}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export default function Learn({ compact }: { compact?: boolean }) {
  const [prog, setProg] = useState<Record<string, boolean>>(() => readProgress());
  const [open, setOpen] = useState<string | null>(null);
  const [skipTo, setSkipTo] = useState<string | null>(null);        // en låst kurs någon valde att öppna ändå
  const [view, setView] = useState<"kurser" | "ova" | "utmarkelser">("kurser");
  const [picked, setPicked] = useState<string | null>(null);        // kursen man tittar på, om inte den pågående
  // Det lokala ritas direkt; kontots svar vinner så snart det kommer. Den som byter dator ska hitta sina steg
  // där de var, inte börja om.
  useEffect(() => { syncProgress().then(setProg); }, []);
  const flat = useMemo(() => MODULES.flatMap((m) => m.lessons.map((l) => ({ m, l }))), []);
  const done = flat.filter(({ l }) => prog[l.id]).length;
  const next = flat.find(({ l }) => !prog[l.id]) ?? flat[0];
  const minutesLeft = flat.filter(({ l }) => !prog[l.id]).reduce((a, { l }) => a + l.minutes, 0);
  // den pågående kursen: det första kapitlet som inte är klart
  const moduleDone = (m: Module) => m.lessons.every((l) => prog[l.id]);
  const currentIdx = Math.max(0, MODULES.findIndex((m) => !moduleDone(m)));
  const allDone = MODULES.every(moduleDone);
  const shownIdx = picked ? Math.max(0, MODULES.findIndex((m) => m.id === picked)) : currentIdx;
  const shown = MODULES[shownIdx];
  const shownLocked = shownIdx > currentIdx && skipTo !== shown.id;
  const shownDone = shown.lessons.filter((l) => prog[l.id]).length;

  /* Hjälten: var man är, vad som är kvar och en enda knapp som fortsätter där man slutade. */
  const hero = (
    <div className="lf-hero">
      <div>
        <div className="lf-kicker">VVS-akademin</div>
        <h2>{tr("Lär dig läsa och mängda en rörritning")}</h2>
        <p className="muted">
          {flat.length} steg i {MODULES.length} kurser, ett i taget, vart och ett med en levande figur som visar
          vad det handlar om — och övningar där du svarar själv och ser facit. Stegen sparas på ditt konto, så du
          fortsätter där du slutade även från en annan dator.
        </p>
        <div className="row" style={{ marginTop: 16 }}>
          <button onClick={() => setOpen(next.l.id)}>
            {done === 0 ? "Starta guiden" : done === flat.length ? "Gå igenom igen" : "Fortsätt guiden"}
          </button>
          {done > 0 && done < flat.length && <span className="muted">Härnäst: {next.l.title}</span>}
        </div>
      </div>
      <div className="lf-ring" style={{ ["--p" as any]: `${Math.round((done / flat.length) * 100)}%` }}>
        <span>{done}<i>/{flat.length}</i></span>
      </div>
    </div>
  );

  if (compact) {
    // I väntan på en läsning: hjälten och kurserna som kort, ingenting som kräver en till sida att navigera i.
    return (
      <div className="learn compact">
        {hero}
        <div className="lf-mods">
          {MODULES.map((m: Module, mi) => (
            <section key={m.id} className={`lf-mod${moduleDone(m) ? " full" : ""}`}>
              <div className="lf-mod-no">{String(mi + 1).padStart(2, "0")}</div>
              <h3>{m.title}</h3>
              <p className="muted">{m.blurb}</p>
              <ol className="lf-less">
                {m.lessons.map((l) => (
                  <li key={l.id} className={prog[l.id] ? "done" : ""}>
                    <button className="ghost" onClick={() => setOpen(l.id)}>
                      <span className="tick" aria-hidden="true" />
                      <span className="nm">{l.title}</span>
                      <span className="mi">{l.minutes} min</span>
                    </button>
                  </li>
                ))}
              </ol>
            </section>
          ))}
        </div>
        <LearnWizard open={open !== null} start={open ?? undefined}
          onClose={() => { setOpen(null); setProg(readProgress()); }} />
      </div>
    );
  }

  return (
    <div className="learn">
      {hero}

      {/* Tre saker att göra, och bara en åt gången: gå kursen, öva, se vad man samlat. */}
      <nav className="lf-nav">
        <button className={view === "kurser" ? "on" : ""} onClick={() => setView("kurser")}>
          Kurser <span className="n">{done}/{flat.length}</span>
        </button>
        <button className={view === "ova" ? "on" : ""} onClick={() => setView("ova")}>
          Öva <span className="n">{EXERCISE_IDS.length}</span>
        </button>
        <button className={view === "utmarkelser" ? "on" : ""} onClick={() => setView("utmarkelser")}>
          Utmärkelser
        </button>
        <span className="spacer" />
        <span className="muted small">
          {allDone ? "Alla kurser klara" : `${minutesLeft} min kvar`}
        </span>
      </nav>

      {view === "kurser" && (
        <div className="lf-split">
          {/* Kurslistan som en gång, i innehållets egen ordning: klara bakom, pågående mitt i, låsta framför. */}
          <aside className="lf-rail">
            {MODULES.map((m: Module, mi) => {
              const d = m.lessons.filter((l) => prog[l.id]).length;
              const locked = mi > currentIdx && skipTo !== m.id;
              const cls = [
                "lf-railitem",
                shownIdx === mi ? "on" : "",
                d === m.lessons.length ? "full" : "",
                mi === currentIdx && !allDone ? "now" : "",
                locked ? "locked" : "",
              ].filter(Boolean).join(" ");
              return (
                <button key={m.id} className={cls} onClick={() => setPicked(m.id)}>
                  <span className="no">{String(mi + 1).padStart(2, "0")}</span>
                  <span className="nm">
                    {m.title}
                    <i>{d} av {m.lessons.length} steg{locked ? " · låst" : ""}</i>
                  </span>
                  <span className="bar" aria-hidden="true"><i style={{ width: `${(d / m.lessons.length) * 100}%` }} /></span>
                </button>
              );
            })}
          </aside>

          <section className="lf-course">
            <div className={`lf-current${allDone ? " done" : ""}`}>
              <div className="k">
                Kurs {shownIdx + 1} av {MODULES.length}
                {shownIdx === currentIdx && !allDone ? " · pågående" : shownDone === shown.lessons.length ? " · klar" : ""}
              </div>
              <h3>{shown.title}</h3>
              <p className="muted">{shown.blurb}</p>
              <div className="row">
                <button disabled={shownLocked}
                  onClick={() => setOpen((shown.lessons.find((l) => !prog[l.id]) ?? shown.lessons[0]).id)}>
                  {shownDone === 0 ? "Börja kursen" : shownDone === shown.lessons.length ? "Gå igenom igen" : "Fortsätt kursen"}
                </button>
                <span className="muted small">
                  {shownDone} av {shown.lessons.length} steg klara
                  {shownIdx + 1 < MODULES.length && ` · nästa kurs: ${MODULES[shownIdx + 1].title}`}
                </span>
              </div>
            </div>

            {shownLocked ? (
              <div className="lf-lock">
                <span className="muted small">
                  Låst tills kurs {currentIdx + 1} är klar. Ordningen är innehållets egen — man läser inte en
                  beteckning innan man vet vad ett system är — men ett lås som inte går att öppna är en fälla.
                </span>
                <button className="ghost small" onClick={() => setSkipTo(shown.id)}>{tr("Öppna ändå")}</button>
              </div>
            ) : (
              <ol className="lf-less lf-steps">
                {shown.lessons.map((l, li) => (
                  <li key={l.id} className={prog[l.id] ? "done" : ""}>
                    <button className="ghost" onClick={() => setOpen(l.id)}>
                      <span className="tick" aria-hidden="true" />
                      <span className="no">{li + 1}</span>
                      <span className="nm">{l.title}</span>
                      <span className="mi">{l.minutes} min</span>
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      )}

      {view === "ova" && (
        <section className="lf-drills">
          <p className="muted">
            Att läsa om en regel och att tillämpa den är två olika saker, och det är den andra som fastnar.
            Ingen av övningarna går att klara genom att gissa på det som ligger närmast — det är hela poängen
            med dem.
          </p>
          {EXERCISE_IDS.map((id) => <LearnExercise key={id} id={id} />)}
        </section>
      )}

      {view === "utmarkelser" && <Awards />}

      <LearnWizard open={open !== null} start={open ?? undefined}
        onClose={() => { setOpen(null); setProg(readProgress()); }} />
    </div>
  );
}
