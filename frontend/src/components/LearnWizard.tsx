import { useCallback, useEffect, useMemo, useState } from "react";
import { t as tr } from "../i18n";
import { MODULES, markDone, readProgress, type Block, type Lesson, type Quiz } from "../learn";
import LearnFigure from "./LearnFigures";
import LearnExercise from "./LearnExercises";
import { Exercise } from "./Learn";

/* Akademin som en guide ovanpå det man höll på med.
 *
 * Att trycka på "Lär mig om VVS" mitt i en läsning ska inte ta bort läsningen. Det här lägger sig över den:
 * ett steg i taget, en levande figur som visar vad steget handlar om, två rader som säger det, och en
 * kontrollfråga innan man går vidare. Läsningen fortsätter bakom, och att stänga kostar ingenting.
 */

type Step = { lesson: Lesson; module: string; moduleId: string; i: number; n: number };

/** The lesson in full, for the reader who wants the whole thing rather than the two lines of the step. */
function More({ body }: { body: Block[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="wz-more">
      <button className="ghost small" onClick={() => setOpen(!open)}>
        {open ? "Dölj hela avsnittet" : "Läs hela avsnittet"}
      </button>
      {open && (
        <div className="wz-more-body">
          {body.map((b, i) => {
            if (b.k === "p") return <p key={i}>{b.t}</p>;
            if (b.k === "note") return <p key={i} className="lf-note">{b.t}</p>;
            if (b.k === "ul") return <ul key={i} className="lf-ul">{b.t.map((x, j) => <li key={j}>{x}</li>)}</ul>;
            if (b.k === "terms") {
              return (
                <dl key={i} className="lf-terms">
                  {b.t.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
                </dl>
              );
            }
            return null;
          })}
        </div>
      )}
    </div>
  );
}

function QuizStep({ q, onPass }: { q: Quiz; onPass: (tries: number) => void }) {
  const [pick, setPick] = useState<number | null>(null);
  // Antalet försök räknas här och skickas med. En utmärkelse som heter "utan fel" måste veta om det gick fel,
  // och den som gissar sig fram till rätt svar har inte gjort samma sak som den som kunde det.
  const [tries, setTries] = useState(0);
  return (
    <div className="wz-quiz">
      <div className="wz-quiz-q">{q.q}</div>
      <div className="wz-quiz-opts">
        {q.options.map((o, i) => (
          <button key={i} type="button"
            className={`secondary${pick === null ? "" : i === q.answer ? " right" : pick === i ? " wrong" : ""}`}
            onClick={() => { setPick(i); const n = tries + 1; setTries(n); if (i === q.answer) onPass(n); }}>
            <span className="k">{String.fromCharCode(65 + i)}</span>{o}
          </button>
        ))}
      </div>
      {pick !== null && (
        <p className={`wz-why${pick === q.answer ? " ok" : ""}`}>
          <b>{pick === q.answer ? "Rätt." : "Inte riktigt."}</b> {q.why}
        </p>
      )}
    </div>
  );
}

export default function LearnWizard({ open, onClose, start }: {
  open: boolean; onClose: () => void; start?: string;
}) {
  const steps: Step[] = useMemo(() => {
    const out: Step[] = [];
    for (const m of MODULES) for (const l of m.lessons) out.push({ lesson: l, module: m.title, moduleId: m.id, i: 0, n: 0 });
    return out.map((s, i) => ({ ...s, i, n: out.length }));
  }, []);
  const [at, setAt] = useState(0);
  const [prog, setProg] = useState<Record<string, boolean>>(() => readProgress());

  // opening picks up where the last drawing left off, so a wizard is a course and not a loop
  useEffect(() => {
    if (!open) return;
    const p = readProgress();
    setProg(p);
    // where to open: the step asked for, else the first one not yet done, else the first - and never an index
    // that is not a step. findIndex returns -1 when every step is done, and a wizard opened on step minus one
    // has nothing to render at all.
    const named = start ? steps.findIndex((s) => s.lesson.id === start) : -1;
    const undone = steps.findIndex((s) => !p[s.lesson.id]);
    const want = named >= 0 ? named : undone >= 0 ? undone : 0;
    setAt(Math.max(0, Math.min(want, steps.length - 1)));
  }, [open, start, steps]);

  const go = useCallback((d: number) => setAt((v) => Math.max(0, Math.min(steps.length - 1, v + d))), [steps.length]);

  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", k);
    document.body.classList.add("wz-open");
    return () => { window.removeEventListener("keydown", k); document.body.classList.remove("wz-open"); };
  }, [open, onClose, go]);

  if (!open) return null;
  const s = steps[Math.max(0, Math.min(at, steps.length - 1))];
  if (!s) return null;
  const l = s.lesson;
  const done = steps.filter((x) => prog[x.lesson.id]).length;
  const finish = (tries = 1) => setProg(markDone(l.id, { right: true, tries }));
  const chapters = MODULES.map((m) => {
    const own = steps.filter((x) => x.moduleId === m.id);
    return {
      id: m.id, title: m.title, steps: own,
      done: own.filter((x) => prog[x.lesson.id]).length,
      has: (i: number) => own.some((x) => x.i === i),
    };
  });

  return (
    <div className="wz" role="dialog" aria-modal="true" aria-label="VVS-akademin">
      <div className="wz-scrim" onClick={onClose} />
      <div className="wz-panel">
        <header className="wz-head">
          <div>
            <div className="wz-kicker">{s.module} · steg {at + 1} av {s.n}</div>
            <h2>{l.title}</h2>
          </div>
          <div className="wz-headr">
            <span className="wz-count">{done}/{s.n} klara</span>
            <button className="ghost small" onClick={onClose} aria-label={tr("Stäng")}>✕</button>
          </div>
        </header>

        {/* The rail used to be one dot per step: fourteen identical squares said nothing about where in the
            course you were. It is now the chapters, each showing its own steps, so a reader can see what is left
            of the chapter they are in and jump straight into another one. */}
        <nav className="wz-rail" aria-label="Kapitel">
          {chapters.map((c) => (
            <div key={c.id} className={`wz-ch${c.has(at) ? " on" : ""}${c.done === c.steps.length ? " full" : ""}`}>
              <button type="button" className="wz-ch-t" onClick={() => setAt(c.steps[0].i)}>
                <span className="nm">{c.title}</span>
                <span className="ct">{c.done}/{c.steps.length}</span>
              </button>
              <div className="wz-ch-dots">
                {c.steps.map((x) => (
                  <button key={x.lesson.id} type="button"
                    className={`wz-dot${x.i === at ? " on" : ""}${prog[x.lesson.id] ? " done" : ""}`}
                    title={x.lesson.title} aria-label={x.lesson.title} onClick={() => setAt(x.i)} />
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="wz-body">
          <div className={`wz-fig${(l.fig || "").startsWith("ex:") || l.fig === "exercise" ? " wide" : ""}`}>
            {l.fig === "exercise" ? <Exercise />
              : (l.fig || "").startsWith("ex:") ? <LearnExercise id={(l.fig || "").slice(3)} />
                : <LearnFigure id={l.fig || ""} />}
          </div>
          <div className="wz-say">
            {(l.short ?? []).map((t, i) => <p key={i}>{t}</p>)}
            <More body={l.body} />
            {l.quiz && <QuizStep q={l.quiz} onPass={finish} />}
            {!l.quiz && (
              <button className={prog[l.id] ? "secondary small" : "small"} onClick={() => finish()}>
                {prog[l.id] ? "Markerad som klar" : "Jag har läst det här"}
              </button>
            )}
          </div>
        </div>

        <footer className="wz-foot">
          <button className="secondary" onClick={() => go(-1)} disabled={at === 0}>{tr("← Tillbaka")}</button>
          <div className="wz-prog"><div style={{ width: `${((at + 1) / s.n) * 100}%` }} /></div>
          {at < s.n - 1
            ? <button onClick={() => { finish(); go(1); }}>{tr("Nästa →")}</button>
            : <button onClick={() => { finish(); onClose(); }}>Klart</button>}
        </footer>
      </div>
    </div>
  );
}
