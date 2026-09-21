import { useEffect, useRef, useState } from "react";

/* Kapitelraden: var i berättelsen man är, längst ned, hela tiden.
 *
 * En lång sida är en bok utan innehållsförteckning. Raden här nere gör den till en bok med en: varje kapitel
 * har sin egen linje som fylls medan man läser det, och den man är i är den enda som lyser. Man ser tre saker
 * på en gång utan att fråga - hur många kapitel som finns, vilket man är i, och hur långt in i det man kommit.
 *
 * Den är också vägen dit: klicka på ett kapitel och sidan går dit. Det är skillnaden mellan en mätare och ett
 * reglage, och den skillnaden är vad som gör en sida levande i stället för bara animerad.
 *
 * Måtten läses en gång per bildruta och bara när något rört sig, och de läses av en observatör i stället för
 * av en skrollyssnare som mäter varje element varje gång.
 */

export type Chapter = { href: string; label: string };

export default function ChapterBar({ chapters }: { chapters: Chapter[] }) {
  const [at, setAt] = useState(0);          // vilket kapitel som gäller
  const [p, setP] = useState(0);            // hur långt in i det, 0..1
  const [on, setOn] = useState(false);      // visas först när man lämnat hjälten
  const frame = useRef(0);

  useEffect(() => {
    const read = () => {
      frame.current = 0;
      const vh = window.innerHeight;
      const mark = vh * 0.42;               // läshöjden: en bit ovanför mitten, där ögat står
      let cur = -1;
      let frac = 0;
      for (let i = 0; i < chapters.length; i++) {
        const el = document.querySelector(chapters[i].href);
        if (!el) continue;
        const r = (el as HTMLElement).getBoundingClientRect();
        if (r.top <= mark) {
          cur = i;
          const nextEl = chapters[i + 1] ? document.querySelector(chapters[i + 1].href) : null;
          const end = nextEl ? (nextEl as HTMLElement).getBoundingClientRect().top : r.bottom;
          const span = end - r.top;
          frac = span > 0 ? Math.min(1, Math.max(0, (mark - r.top) / span)) : 1;
        }
      }
      // Sist på sidan står foten med sina egna länkar, och den låg rakt under romarsiffrorna. Kapitelraden
      // har gjort sitt när sista kapitlet är passerat, så den stiger undan i stället för att lägga sig över
      // det sista man ska kunna läsa.
      const foot = document.querySelector(".lp-foot");
      const footIn = !!foot && (foot as HTMLElement).getBoundingClientRect().top < vh - 40;
      setOn(cur >= 0 && !footIn);
      if (cur >= 0) { setAt(cur); setP(frac); }
      // Raderna byter röst med rummet de ligger över - kapitelraden längst ned, och huvudet högst upp. Mätt på
      // avsnittens egna lägen och inte med elementFromPoint: raderna ligger själva överst vid sina punkter, så
      // träffprovet svarade "raden" och aldrig "papper". Huvudet har en egen punkt: det ligger i toppen av
      // rutan och rummet där är sällan samma som rummet nere vid foten.
      const probe = vh - 52;
      let paper = false;
      let headPaper = false;
      for (const el of document.querySelectorAll(".lp-light")) {
        const r = (el as HTMLElement).getBoundingClientRect();
        if (r.top <= probe && r.bottom >= probe) paper = true;
        if (r.top <= 34 && r.bottom >= 34) headPaper = true;
      }
      const root = document.querySelector(".lp");
      root?.classList.toggle("on-paper", paper);
      root?.classList.toggle("head-paper", headPaper);
    };
    const kick = () => { if (!frame.current) frame.current = requestAnimationFrame(read); };
    read();
    window.addEventListener("scroll", kick, { passive: true });
    window.addEventListener("resize", kick);
    return () => {
      window.removeEventListener("scroll", kick);
      window.removeEventListener("resize", kick);
      cancelAnimationFrame(frame.current);
    };
  }, [chapters]);

  const go = (href: string) => {
    const el = document.querySelector(href);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <nav className={`ch${on ? " in" : ""}`} aria-label="Kapitel">
      {chapters.map((c, i) => (
        <button key={c.href} className={`ch-i${i === at ? " now" : ""}${i < at ? " past" : ""}`}
          onClick={() => go(c.href)} aria-current={i === at ? "true" : undefined}>
          <span className="ch-n">{roman(i + 1)}</span>
          <span className="ch-l">{c.label}</span>
          <span className="ch-bar">
            <i style={{ transform: `scaleX(${i < at ? 1 : i === at ? p : 0})` }} />
          </span>
        </button>
      ))}
    </nav>
  );
}

/* Kapitel numreras med romerska siffror, som i en bok. Listan är kort och blir inte längre av sig själv. */
function roman(n: number): string {
  const t = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"];
  return t[n - 1] || String(n);
}
