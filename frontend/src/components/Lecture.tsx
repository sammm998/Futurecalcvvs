import { useEffect, useMemo, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useNavigate } from "react-router-dom";
import { MODULES, markDone, readProgress, type Block, type Lesson, type Module, type Quiz } from "../learn";
import LearnFigure from "./LearnFigures";
import LearnExercise, { EXERCISE_IDS } from "./LearnExercises";

/* En föreläsning är en sida, inte en ruta ovanpå något annat.
 *
 * Akademin låg i en guide som lade sig över det man höll på med. Det är rätt mitt i en läsning - då är
 * lektionen något man gör medan man väntar, och läsningen ska finnas kvar bakom. Men när man går in i
 * akademin för att läsa är lektionen det man gör, och då ska den ha en egen sida: en egen adress att spara
 * och dela, en tillbakaknapp som fungerar, plats åt hela texten och åt figuren, och nästa steg längst ned.
 *
 * Det här är den sidan. Den vet ingenting om ramen runt omkring, så samma föreläsning kan visas både publikt
 * och inloggat - bara adressen och vad som händer efteråt skiljer.
 */

export type LessonAt = { module: Module; mi: number; lesson: Lesson; li: number };

/** Slå upp en kurs och en föreläsning ur adressen. Okänd adress ger null, och den som ropar visar då 404. */
export function findLesson(moduleId?: string, lessonId?: string): LessonAt | null {
  const mi = MODULES.findIndex((m) => m.id === moduleId);
  if (mi < 0) return null;
  const module = MODULES[mi];
  if (!lessonId) return null;
  const li = module.lessons.findIndex((l) => l.id === lessonId);
  if (li < 0) return null;
  return { module, mi, lesson: module.lessons[li], li };
}

export function findModule(moduleId?: string): { module: Module; mi: number } | null {
  const mi = MODULES.findIndex((m) => m.id === moduleId);
  return mi < 0 ? null : { module: MODULES[mi], mi };
}

/** Alla föreläsningar i ordning, så "nästa" kan gå vidare till nästa kurs. */
export const FLAT: { m: Module; mi: number; l: Lesson; li: number }[] =
  MODULES.flatMap((m, mi) => m.lessons.map((l, li) => ({ m, mi, l, li })));

export function lessonHref(base: string, moduleId: string, lessonId: string) {
  return `${base}/${moduleId}/${lessonId}`;
}

/* ---------- texten ---------- */

function Body({ body }: { body: Block[] }) {
  return (
    <>
      {body.map((b, i) => {
        if (b.k === "p") return <p key={i}>{b.t}</p>;
        if (b.k === "note") return <aside key={i} className="ac-note">{b.t}</aside>;
        if (b.k === "ul") return <ul key={i} className="ac-ul">{b.t.map((x, j) => <li key={j}>{x}</li>)}</ul>;
        if (b.k === "terms") {
          return (
            <dl key={i} className="ac-terms">
              {b.t.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
            </dl>
          );
        }
        if (b.k === "fig") {
          return (
            <figure key={i} className="ac-fig">
              <LearnFigure id={b.id} />
              <figcaption>{b.caption}</figcaption>
            </figure>
          );
        }
        return null;
      })}
    </>
  );
}

function QuizCard({ q, onPass }: { q: Quiz; onPass: (tries: number) => void }) {
  const [pick, setPick] = useState<number | null>(null);
  const [tries, setTries] = useState(0);
  const right = pick !== null && pick === q.answer;
  return (
    <section className="ac-quiz">
      <p className="lp-mono">{tr("Kontrollfråga")}</p>
      <h3>{q.q}</h3>
      <div className="ac-opts">
        {q.options.map((o, i) => {
          const chosen = pick === i;
          const cls = ["ac-opt", chosen ? (i === q.answer ? "right" : "wrong") : "",
            pick !== null && i === q.answer ? "is-answer" : ""].filter(Boolean).join(" ");
          return (
            <button key={o} className={cls} disabled={right}
              onClick={() => {
                setPick(i);
                const t = tries + 1;
                setTries(t);
                if (i === q.answer) onPass(t);
              }}>
              <span className="mark" aria-hidden="true">{String.fromCharCode(65 + i)}</span>
              <span>{o}</span>
            </button>
          );
        })}
      </div>
      {pick !== null && (
        <p className={`ac-why${right ? " ok" : ""}`}>
          {right ? "Rätt. " : "Inte riktigt. "}{q.why}
        </p>
      )}
    </section>
  );
}

/* ---------- själva sidan ---------- */

export default function Lecture({ at, base, locked }: { at: LessonAt; base: string; locked?: boolean }) {
  const nav = useNavigate();
  const { module, mi, lesson, li } = at;
  const [prog, setProg] = useState<Record<string, boolean>>(() => readProgress());
  const [passed, setPassed] = useState(false);
  useEffect(() => { setPassed(false); window.scrollTo(0, 0); }, [lesson.id]);

  const flatIdx = useMemo(() => FLAT.findIndex((f) => f.l.id === lesson.id), [lesson.id]);
  const prev = flatIdx > 0 ? FLAT[flatIdx - 1] : null;
  const next = flatIdx >= 0 && flatIdx < FLAT.length - 1 ? FLAT[flatIdx + 1] : null;
  const done = !!prog[lesson.id];
  const drill = EXERCISE_IDS.includes(lesson.id as any) ? lesson.id : null;

  const finish = (result?: { right?: boolean; tries?: number }) => {
    if (locked) return;
    setProg(markDone(lesson.id, result));
  };

  return (
    <article className="ac-lecture">
      <nav className="ac-crumbs" aria-label={tr("Var du är")}>
        <Link to={base}>Akademin</Link>
        <span aria-hidden="true">/</span>
        <Link to={`${base}/${module.id}`}>{module.title}</Link>
        <span aria-hidden="true">/</span>
        <span className="here">{lesson.title}</span>
      </nav>

      <header className="ac-lechead">
        <p className="lp-mono">
          Kurs {String(mi + 1).padStart(2, "0")} · Föreläsning {li + 1} av {module.lessons.length} · {lesson.minutes} min
        </p>
        <h1>{lesson.title}</h1>
        {!!lesson.short?.length && <p className="ac-lede">{lesson.short[0]}</p>}
      </header>

      <div className="ac-lecbody">
        <div className="ac-read">
          <Body body={lesson.body} />
          {lesson.quiz && <QuizCard q={lesson.quiz} onPass={(tries) => { setPassed(true); finish({ right: true, tries }); }} />}
          {drill && (
            <section className="ac-drill">
              <p className="lp-mono">{tr("Öva själv")}</p>
              <LearnExercise id={drill as any} />
            </section>
          )}
        </div>

        {lesson.fig && (
          <aside className="ac-side">
            <div className="ac-sidefig">
              <LearnFigure id={lesson.fig} />
              {!!lesson.short?.length && (
                <ul className="ac-shorts">{lesson.short.map((t) => <li key={t}>{t}</li>)}</ul>
              )}
            </div>
          </aside>
        )}
      </div>

      <footer className="ac-lecfoot">
        <div className="ac-done">
          {done || passed ? (
            <span className="ac-badge on"><b>✓</b> Klart</span>
          ) : (
            <button className="lp-btn primary" onClick={() => finish()} disabled={locked}>
              Markera som läst
            </button>
          )}
          {locked && <span className="pub-note">{tr("Logga in för att spara var du är.")}</span>}
        </div>
        <div className="ac-steps">
          {prev
            ? <Link className="ac-step prev" to={lessonHref(base, prev.m.id, prev.l.id)}>
                <span className="lp-mono">{tr("Föregående")}</span><b>{prev.l.title}</b>
              </Link>
            : <span />}
          {next
            ? <Link className="ac-step next" to={lessonHref(base, next.m.id, next.l.id)}
                onClick={() => { if (!done && !passed) finish(); }}>
                <span className="lp-mono">{next.m.id === module.id ? "Nästa" : `Nästa kurs · ${next.m.title}`}</span>
                <b>{next.l.title}</b>
              </Link>
            : <button className="ac-step next" onClick={() => { finish(); nav(base); }}>
                <span className="lp-mono">{tr("Sista föreläsningen")}</span><b>{tr("Tillbaka till akademin")}</b>
              </button>}
        </div>
      </footer>
    </article>
  );
}
