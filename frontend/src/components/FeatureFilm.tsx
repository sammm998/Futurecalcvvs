import { useEffect, useRef, useState } from "react";
import FeatureArt from "./FeatureArt";
import type { Step } from "../features";

/* Guiden som en film i stället för en punktlista.
 *
 * Stegen är desamma som står skrivna under - det här är samma innehåll fast spelat: figuren för steget syns,
 * texten byts, och stapeln högst upp visar var i förloppet man är. Den startar när den kommer in i bilden och
 * stannar när den lämnar den, så en sida längre ned aldrig spelar för sig själv.
 *
 * Man kan gripa in: klicka på ett steg och filmen hoppar dit och pausar, som en spellista. Den som har bett om
 * mindre rörelse får stillbilden och stegen, ingen automatik.
 */

const DUR = 4200;

function prefersStill() {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

export default function FeatureFilm({ steps, accent, title }:
  { steps: Step[]; accent: string; title: string }) {
  const [i, setI] = useState(0);
  const [playing, setPlaying] = useState(!prefersStill());
  const [seen, setSeen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  // spelar bara när den syns
  useEffect(() => {
    const el = box.current;
    if (!el || typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => setSeen(e.isIntersecting), { threshold: 0.35 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!playing || !seen) return;
    const t = setTimeout(() => setI((n) => (n + 1) % steps.length), DUR);
    return () => clearTimeout(t);
  }, [playing, seen, i, steps.length]);

  const s = steps[i];
  const running = playing && seen;

  return (
    <div className="ft-film" ref={box} style={{ ["--ac" as any]: accent }}>
      <div className="ff-bar" role="tablist" aria-label={`Steg i ${title}`}>
        {steps.map((st, k) => (
          <button key={st.n} role="tab" aria-selected={k === i} aria-label={`Steg ${st.n}: ${st.h}`}
            className={`ff-seg${k === i ? " now" : ""}${k < i ? " past" : ""}`}
            onClick={() => { setI(k); setPlaying(false); }}>
            <i style={k === i && running ? { animationDuration: `${DUR}ms` } : undefined}
              className={k === i && running ? "run" : ""} />
          </button>
        ))}
      </div>

      <div className="ff-stage">
        {steps.map((st, k) => (
          <figure key={st.n} className={`ff-frame${k === i ? " on" : ""}`} aria-hidden={k !== i}>
            <FeatureArt id={st.art} accent={accent} />
          </figure>
        ))}
        <button className="ff-play" onClick={() => setPlaying((p) => !p)}
          aria-label={playing ? "Pausa filmen" : "Spela filmen"}>
          {playing
            ? <svg width="15" height="15" viewBox="0 0 15 15" aria-hidden="true"><rect x="3" y="2" width="3.4" height="11" rx="1" fill="currentColor" /><rect x="8.6" y="2" width="3.4" height="11" rx="1" fill="currentColor" /></svg>
            : <svg width="15" height="15" viewBox="0 0 15 15" aria-hidden="true"><path d="M4 2.5 12.5 7.5 4 12.5 Z" fill="currentColor" /></svg>}
          <span>{playing ? "Pausa" : "Spela"}</span>
        </button>
      </div>

      <div className="ff-say" key={s.n}>
        <span className="ff-no" style={{ color: accent }}>{s.n}<i>/{String(steps.length).padStart(2, "0")}</i></span>
        <div>
          <h3>{s.h}</h3>
          <p>{s.p}</p>
        </div>
      </div>
    </div>
  );
}
