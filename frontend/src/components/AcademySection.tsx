import { Link } from "react-router-dom";
import { t as tr } from "../i18n";
import { MODULES } from "../learn";
import { useInView } from "./lp-motion";
import { tiltStyle, useTilt } from "./tilt";

/* The academy, on the front page, because it is part of what the product is and not a waiting-room toy.
 *
 * The six modules stand as a deck seen at an angle: the one you would start with nearest, the rest stepping
 * back behind it. Reading a drawing is a skill; the thing that reads drawings ought to teach it.
 */

const ICONS: Record<string, string> = {
  system: "M3 15h4l2-7 3 12 2.5-9 1.5 4h5",
  beteckning: "M3 6h18M3 12h11M3 18h7",
  bladet: "M4 3h11l5 5v13H4z M15 3v5h5",
  rita: "M4 20 L14 5 l4 3 -10 15 -4 1z",
  mangda: "M4 19V5h16v14z M8 5v14 M4 12h16",
  ovning: "M12 3 3 7l9 4 9-4z M6 10v5c0 1.7 2.7 3 6 3s6-1.3 6-3v-5",
};

export default function AcademySection() {
  const { ref, seen } = useInView<HTMLDivElement>();
  const { tilt, handlers } = useTilt(3);
  const lessons = MODULES.reduce((n, m) => n + m.lessons.length, 0);
  const minutes = MODULES.reduce((n, m) => n + m.lessons.reduce((k, l) => k + l.minutes, 0), 0);

  return (
    <section className="lp-sec lp-wrap" id="akademin">
      <div className="lp-sec-head">
        <div className="lp-kicker">VVS-akademin</div>
        <h2>{tr("Lär dig läsa ritningen medan den läses")}</h2>
        <p>
          En läsning tar ett par minuter. Under tiden kan du gå ett delmoment: systemen, beteckningen, bladet,
          hur en ritning ritas och hur en mängd tas fram — och till sist mängda ett övningsblad själv och få
          rättat. Delmomenten sparas, så nästa ritning fortsätter där den förra slutade.
        </p>
      </div>
      <div className={`lp-acad${seen ? " in" : ""}`} ref={ref}>
        <div className="lp-acad-deck" {...handlers} style={tiltStyle(tilt, 12)}>
          {/* six cards leaning back from the one you would start with: every title readable, the whole course
              visible as one thing. The card under the pointer comes forward and says what it is about. */}
          {MODULES.map((m, i) => (
            <article key={m.id} className="lp-acad-card"
              style={{
                top: `${i * 66}px`,
                transform: `scale(${1 - i * 0.018}) rotateX(${i * 0.9}deg)`,
                zIndex: MODULES.length - i,
                animationDelay: `${0.07 * i}s`,
              }}>
              <span className="ic">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <path d={ICONS[m.id]} stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"
                    strokeLinejoin="round" />
                </svg>
              </span>
              <h3>{m.title}</h3>
              <span className="n">{m.lessons.length} delmoment</span>
              <span className="no">{String(i + 1).padStart(2, "0")}</span>
              <p>{m.blurb}</p>
            </article>
          ))}
        </div>
        <div className="lp-acad-say">
          <ul className="lp-beats">
            <li className="on"><span className="no">01</span><span><b>{tr("Sex moduler")}</b><em>{lessons} delmoment, {minutes} minuter totalt</em></span></li>
            <li className="on"><span className="no">02</span><span><b>{tr("Kontrollfrågor")}</b><em>{tr("varje moment slutar med en fråga och ett svar som förklarar varför")}</em></span></li>
            <li className="on"><span className="no">03</span><span><b>{tr("Ett övningsblad")}</b><em>{tr("para ihop beteckning och sträcka, och få rättat direkt")}</em></span></li>
            <li className="on"><span className="no">04</span><span><b>{tr("Sparas där du är")}</b><em>{tr("fortsätt nästa gång en ritning läses")}</em></span></li>
          </ul>
          <Link className="lp-btn primary lg" to="/lar">{tr("Öppna akademin")}</Link>
        </div>
      </div>
    </section>
  );
}
