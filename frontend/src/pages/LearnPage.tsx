import { useState } from "react";
import { t as tr } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { MODULES } from "../learn";
import Lecture, { findLesson, findModule, FLAT } from "../components/Lecture";
import { CourseGrid, CourseView, ResumeCard, useProgress } from "../components/Academy";
import LearnExercise, { EXERCISE_IDS } from "../components/LearnExercises";
import { Awards } from "../components/Learn";

/* Akademin inloggad, i hela fönstret.
 *
 * Analysen är ett arbetsbord: paneler, tabeller, en ritning att peta på. Att läsa sig till något är en annan
 * sysselsättning och tål inte samma form - den vill ha ro, en spalt att följa och ingenting i ögonvrån. Så
 * akademin tar hela fönstret och har sitt eget huvud.
 *
 * Och en föreläsning är en sida. Den låg förut i en ruta ovanpå det man höll på med, vilket är rätt mitt i en
 * läsning - där är den något man gör medan man väntar - men fel när man gått hit för att läsa. Nu har varje
 * kurs och varje föreläsning en egen adress: en att spara, en att dela, en tillbakaknapp som fungerar.
 */

const BASE = "/lar";

function Shell({ children, sub }: { children: any; sub?: any }) {
  return (
    <div className="academy">
      <div className="academy-sky" aria-hidden="true" />
      <header className="academy-bar">
        <Link to={BASE} className="org">VVS-akademin</Link>
        {sub}
      </header>
      <div className="academy-scroll">
        <div className="academy-col">{children}</div>
      </div>
    </div>
  );
}

/* ---------- akademins förstasida ---------- */

export default function LearnPage() {
  const prog = useProgress(true);
  const [view, setView] = useState<"kurser" | "ova" | "utmarkelser">("kurser");
  const done = FLAT.filter((f) => prog[f.l.id]).length;
  return (
    <Shell sub={<span className="muted small">{done} av {FLAT.length} föreläsningar klara</span>}>
      <ResumeCard base={BASE} prog={prog} />

      <nav className="ac-tabs" aria-label="Akademin">
        <button className={view === "kurser" ? "on" : ""} onClick={() => setView("kurser")}>
          Kurser <span className="n">{MODULES.length}</span>
        </button>
        <button className={view === "ova" ? "on" : ""} onClick={() => setView("ova")}>
          Öva <span className="n">{EXERCISE_IDS.length}</span>
        </button>
        <button className={view === "utmarkelser" ? "on" : ""} onClick={() => setView("utmarkelser")}>
          Utmärkelser
        </button>
      </nav>

      {view === "kurser" && <CourseGrid base={BASE} prog={prog} />}

      {view === "ova" && (
        <section className="ac-drills">
          <p className="ac-lede">
            Att läsa om en regel och att tillämpa den är två olika saker, och det är den andra som fastnar.
            Ingen av övningarna går att klara genom att gissa på det som ligger närmast — det är hela poängen
            med dem.
          </p>
          {EXERCISE_IDS.map((id) => <LearnExercise key={id} id={id} />)}
        </section>
      )}

      {view === "utmarkelser" && <Awards />}
    </Shell>
  );
}

/* ---------- en kurs ---------- */

export function LearnCoursePage() {
  const { modul } = useParams();
  const prog = useProgress(true);
  const found = findModule(modul);
  if (!found) return <Missing />;
  return (
    <Shell><CourseView m={found.module} mi={found.mi} base={BASE} prog={prog} /></Shell>
  );
}

/* ---------- en föreläsning ---------- */

export function LearnLessonPage() {
  const { modul, lektion } = useParams();
  const at = findLesson(modul, lektion);
  if (!at) return <Missing />;
  return <Shell><Lecture at={at} base={BASE} /></Shell>;
}

function Missing() {
  return (
    <Shell>
      <div className="ac-missing">
        <h1>{tr("Den sidan finns inte i akademin")}</h1>
        <p className="ac-lede">{tr("Adressen pekar på en kurs eller en föreläsning som inte finns. Kurserna står kvar där de var.")}</p>
        <Link className="lp-btn primary lg" to={BASE}>{tr("Till kurserna")}</Link>
      </div>
    </Shell>
  );
}
