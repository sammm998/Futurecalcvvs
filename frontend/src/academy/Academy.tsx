import { useEffect, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useNavigate, useParams } from "react-router-dom";
import Exercise from "./Exercise";
import TrainingDrawing from "./TrainingDrawing";
import { ac, type Block, type ExerciseOut, type PlanData } from "./api";
import "./academy.css";

/* FutureCalc Academy.
 *
 * Tre vyer: var man är, vad en utbildning innehåller, och lektionen man läser just nu.
 *
 * Designen hör till FutureCalc men är dämpad. En marknadssida ska imponera; en lektion ska gå att läsa i
 * fyrtio minuter utan att något rör sig i kanten av ögat. Rörelsen som finns här är den som säger något:
 * en progressring som fylls, ett resultat som räknas upp, en modul som låses upp.
 */

function Shell({ children, crumb }: { children: React.ReactNode; crumb?: React.ReactNode }) {
  return (
    <div className="acx">
      <header className="acx-top">
        <Link className="acx-brand" to="/academy">
          <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="M2 13.5h5.2V6h5.6v7.5H18" stroke="currentColor" strokeWidth="1.7" strokeLinecap="square" />
            <circle cx="7.2" cy="13.5" r="1.7" fill="currentColor" />
          </svg>
          FutureCalc <span>Academy</span>
        </Link>
        <nav className="acx-crumb">{crumb}</nav>
        <Link className="fc-btn sm" to="/projekt">{tr("Till verktyget")}</Link>
      </header>
      {children}
    </div>
  );
}

function Ring({ v, size = 54 }: { v: number; size?: number }) {
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  return (
    <svg width={size} height={size} className="acx-ring" role="img" aria-label={`${Math.round(v * 100)} procent klart`}>
      <circle cx={size / 2} cy={size / 2} r={r} className="bg" />
      <circle cx={size / 2} cy={size / 2} r={r} className="fg"
        strokeDasharray={c} strokeDashoffset={c * (1 - v)} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="53%" dominantBaseline="middle" textAnchor="middle">{Math.round(v * 100)}</text>
    </svg>
  );
}

/* ---------------------------------------------------------------- var man är */

export function AcademyHome() {
  const [me, setMe] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { ac.me().then(setMe).catch((e) => setErr(String(e.message || e))); }, []);

  if (err) return <Shell><p className="acx-err">{err}</p></Shell>;
  if (!me) return <Shell><p className="acx-load">{tr("Hämtar ditt läge…")}</p></Shell>;

  const niva = me.niva;
  return (
    <Shell>
      <section className="acx-hero">
        <div>
          <p className="fc-label">{tr("FutureCalc Academy")}</p>
          <h1 className="fc-display fc-display-md">
            {me.fortsatt ? "Fortsätt där du slutade" : "Börja lära dig mängda"}
          </h1>
          {me.fortsatt ? (
            <p className="acx-lead">
              {me.fortsatt.kurs_titel} — nästa lektion är <b>{me.fortsatt.titel}</b>.
            </p>
          ) : (
            <p className="acx-lead">{(me.kurser || []).length} utbildningar i VVS-kalkyl, mängdning, ventilation,
              entreprenadjuridik och ritningsläsning. Börja med grunderna.</p>
          )}
          {me.fortsatt && (
            <Link className="fc-btn solid" to={`/academy/lektion/${me.fortsatt.lektion}`}>
              Fortsätt utbildningen <span aria-hidden="true">→</span>
            </Link>
          )}
        </div>
        <aside className="acx-level">
          <p className="fc-label">{tr("Din nivå")}</p>
          <p className="acx-level-n">{niva.namn}</p>
          <p className="acx-xp"><b>{me.xp}</b> XP</p>
          {niva.nasta && (
            <>
              <div className="acx-bar"><i style={{ width: `${Math.min(100, ((me.xp - niva.fran) / (niva.nasta_vid - niva.fran)) * 100)}%` }} /></div>
              <p className="fc-label">{niva.kvar} XP till {niva.nasta}</p>
            </>
          )}
        </aside>
      </section>

      <section className="acx-stats">
        <div><b>{me.ovningar.gjorda}</b><span className="fc-label">{tr("Övningar gjorda")}</span></div>
        <div><b>{me.ovningar.godkanda}</b><span className="fc-label">{tr("Godkända")}</span></div>
        <div><b>{Math.round(me.ovningar.snitt * 100)} %</b><span className="fc-label">Snittresultat</span></div>
        <div><b>{me.certifikat.length}</b><span className="fc-label">Certifikat</span></div>
      </section>

      <section className="acx-sec">
        <h2 className="fc-display fc-display-md">Utbildningar</h2>
        <div className="acx-courses">
          {me.kurser.map((k: any) => (
            <Link key={k.slug} className={`acx-card ${k.state}`} to={`/academy/${k.slug}`}>
              <Ring v={k.andel} />
              <div>
                <p className="fc-label">{k.level} · {k.hours} h</p>
                <h3>{k.title}</h3>
                <p>{k.blurb}</p>
                <p className="fc-label">{k.klara} av {k.av} lektioner
                  {k.state === "klar" ? " · klar" : k.state === "pagaende" ? " · pågående" : ""}</p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {!!me.certifikat.length && (
        <section className="acx-sec">
          <h2 className="fc-display fc-display-md">{tr("Dina certifikat")}</h2>
          <div className="acx-certs">
            {me.certifikat.map((c: any) => (
              <Link key={c.code} className="acx-cert" to={`/certifikat/${c.code}`}>
                <p className="fc-label">{tr("FutureCalc Certified")}</p>
                <b>{c.title}</b>
                <p className="fc-label">{c.code} · {c.score} % · {c.issued.slice(0, 10)}</p>
              </Link>
            ))}
          </div>
        </section>
      )}

      {!!me.aktivitet.length && (
        <section className="acx-sec">
          <h2 className="fc-display fc-display-md">{tr("Senaste aktivitet")}</h2>
          <ul className="acx-act">
            {me.aktivitet.map((a: any, i: number) => (
              <li key={i}><span>{a.why}</span><b>+{a.points} XP</b>
                <span className="fc-label">{a.when.slice(0, 10)}</span></li>
            ))}
          </ul>
        </section>
      )}
    </Shell>
  );
}

/* ---------------------------------------------------------------- en utbildning */

export function AcademyCourse() {
  const { kurs } = useParams();
  const [c, setC] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => { ac.course(kurs!).then(setC).catch((e) => setErr(String(e.message || e))); }, [kurs]);

  if (err) return <Shell><p className="acx-err">{err}</p></Shell>;
  if (!c) return <Shell><p className="acx-load">{tr("Hämtar utbildningen…")}</p></Shell>;

  return (
    <Shell crumb={<Link to="/academy">Academy</Link>}>
      <section className="acx-hero">
        <div>
          <p className="fc-label">{c.level} · {c.hours} timmar</p>
          <h1 className="fc-display fc-display-md">{c.title}</h1>
          <p className="acx-lead">{c.blurb}</p>
        </div>
      </section>

      <ol className="acx-mods">
        {c.moduler.map((m: any, i: number) => (
          <li key={m.slug} className={m.open ? "" : "locked"}>
            <div className="acx-mod-h">
              <span className="acx-mod-n fc-label">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3>{m.title}{!m.open && <span className="acx-lock" title={tr("Låst")}> {tr("· låst")}</span>}</h3>
                <p>{m.blurb}</p>
                <p className="fc-label">
                  {m.lektioner.length} lektioner
                  {m.ovningar ? ` · ${m.ovningar} övningar` : ""}
                  {m.quiz ? ` · quiz` : ""}
                  {" · "}{m.xp} XP
                  {!m.open && ` · kräver ${m.requires}`}
                </p>
              </div>
            </div>
            {m.open && (
              <ul className="acx-lessons">
                {m.lektioner.map((l: any) => (
                  <li key={l.id}>
                    <Link to={`/academy/lektion/${l.id}`}>
                      <span className={`acx-dot ${l.state}`} aria-hidden="true" />
                      <span className="acx-l-t">{l.title}</span>
                      <span className="fc-label">{l.minutes} min</span>
                      <span className="fc-label acx-l-s">
                        {l.state === "klar" ? "Klar" : l.state === "pagaende" ? "Påbörjad" : "Inte påbörjad"}
                      </span>
                    </Link>
                  </li>
                ))}
                {!!m.quiz && (
                  <li><Link to={`/academy/${c.slug}/${m.slug}/quiz`} className="acx-quizlink">
                    <span className="acx-dot" aria-hidden="true" />
                    <span className="acx-l-t">Quiz — {m.quiz} frågor i banken</span>
                    <span className="fc-label">{tr("upp till 50 XP")}</span>
                  </Link></li>
                )}
              </ul>
            )}
          </li>
        ))}
      </ol>

      {c.tenta && (
        <section className="acx-exam-cta">
          <div>
            <p className="fc-label">Sluttenta</p>
            <h2 className="fc-display fc-display-md">{c.tenta.title}</h2>
            <p className="acx-lead">
              Fem delar: teori, ritningsläsning, mängdning, kalkyl och kalkylkontroll. Godkänt kräver
              {" "}{c.tenta.pass_pct} % totalt och minst 60 % i varje del. Godkänd tenta ger ett verifierbart
              FutureCalc-certifikat.
            </p>
          </div>
          <Link className="fc-btn solid" to={`/academy/tenta/${c.tenta.slug}`}>{tr("Skriv sluttentan")} <span aria-hidden="true">→</span></Link>
        </section>
      )}
    </Shell>
  );
}

/* ---------------------------------------------------------------- en lektion */

export function AcademyLesson() {
  const { id } = useParams();
  const nav = useNavigate();
  const [l, setL] = useState<any>(null);
  const [err, setErr] = useState("");
  const [done, setDone] = useState(false);
  const [xp, setXp] = useState(0);

  useEffect(() => {
    setL(null); setDone(false); setXp(0);
    ac.lesson(id!).then((d) => { setL(d); setDone(d.state === "klar"); })
      .catch((e) => setErr(String(e.message || e)));
    window.scrollTo(0, 0);
  }, [id]);

  if (err) return <Shell><p className="acx-err">{err}</p></Shell>;
  if (!l) return <Shell><p className="acx-load">{tr("Hämtar lektionen…")}</p></Shell>;

  const markDone = async () => {
    const r = await ac.lessonDone(l.id);
    setDone(true);
    setXp(r.xp);
  };

  return (
    <Shell crumb={
      <>
        <Link to="/academy">Academy</Link>
        <span aria-hidden="true">/</span>
        <Link to={`/academy/${l.kurs.slug}`}>{l.kurs.title}</Link>
        <span aria-hidden="true">/</span>
        <span>{l.modul.title}</span>
      </>
    }>
      <article className="acx-lesson">
        <header>
          <p className="fc-label">{l.modul.title} · {l.minutes} min · {l.xp} XP</p>
          <h1 className="fc-display fc-display-md">{l.title}</h1>
        </header>

        <div className="acx-blocks">
          {(l.blocks as Block[]).map((b, i) => <BlockView key={i} b={b} />)}
        </div>

        {!!l.ovningar.length && (
          <section className="acx-ex">
            <h2 className="fc-display fc-display-md">{tr("Öva")}</h2>
            {l.ovningar.map((e: ExerciseOut) => (
              <Exercise key={e.slug} ex={e} onDone={(r) => setXp((x) => x + r.xp)} />
            ))}
          </section>
        )}

        <footer className="acx-lfoot">
          <div>
            {done ? (
              <p className="acx-done"><span aria-hidden="true">✓</span> Lektionen är klar{xp > 0 && ` · +${xp} XP`}</p>
            ) : (
              <button className="fc-btn solid" onClick={markDone}>{tr("Markera som läst")}</button>
            )}
          </div>
          <div className="acx-lnav">
            {l.forra && <button className="fc-btn sm" onClick={() => nav(`/academy/lektion/${l.forra}`)}>{tr("← Föregående")}</button>}
            {l.nasta
              ? <button className="fc-btn sm" onClick={() => nav(`/academy/lektion/${l.nasta}`)}>{tr("Nästa lektion →")}</button>
              : <Link className="fc-btn sm" to={`/academy/${l.kurs.slug}`}>{tr("Tillbaka till utbildningen")}</Link>}
          </div>
        </footer>
      </article>
    </Shell>
  );
}

function BlockView({ b }: { b: Block }) {
  switch (b.k) {
    case "h": return <h2 className="acx-h">{b.t}</h2>;
    case "p": return <p>{b.t}</p>;
    case "ul": return <ul className="acx-ul">{b.t.map((x) => <li key={x}>{x}</li>)}</ul>;
    case "terms":
      return (
        <dl className="acx-terms">
          {b.t.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      );
    case "note": return <aside className="acx-note"><span className="fc-label">{tr("Att veta")}</span><p>{b.t}</p></aside>;
    case "warn": return <aside className="acx-warn"><span className="fc-label">Varning</span><p>{b.t}</p></aside>;
    case "formula":
      return (
        <figure className="acx-formula">
          <code>{b.t}</code>
          <figcaption>{b.why}</figcaption>
        </figure>
      );
    case "drawing": return <PlanBlock slug={b.plan} caption={b.caption} />;
    default: return null;
  }
}

/** En ritning i löptext. Bladen hämtas ur övningarnas data, så samma blad används på båda ställena. */
function PlanBlock({ slug, caption }: { slug: string; caption: string }) {
  const [plan, setPlan] = useState<PlanData | null>(null);
  useEffect(() => {
    let alive = true;
    ac.plan(slug)
      .then((p) => { if (alive && p) setPlan(p); })
      .catch(() => { /* ritningen är illustration; utan den står texten kvar */ });
    return () => { alive = false; };
  }, [slug]);
  if (!plan) return <figure className="acx-plan acx-plan-none"><figcaption>{caption}</figcaption></figure>;
  return (
    <figure className="acx-plan">
      <TrainingDrawing plan={plan} mode="las" height={360} />
      <figcaption>{caption}</figcaption>
    </figure>
  );
}
