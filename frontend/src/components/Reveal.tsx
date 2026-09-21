import { useEffect, useRef, useState } from "react";
import { prefersStill } from "./lp-smooth";

/* Rubriken stiger upp bakom sin egen kant, ord för ord.
 *
 * Effekten är en mask: varje rad ligger i en ruta som klipper, och orden börjar under kanten och stiger upp i
 * den. Ögat läser det som att texten sätter sig på plats i stället för att tonas in, och det är den rörelsen
 * den sortens sidor är byggda av.
 *
 * Måsten:
 *   - Raderna är rader, inte ord med radbrytning. Därför mäts var raderna faktiskt bröts i webbläsaren, efter
 *     att typsnittet laddat, och orden grupperas per baslinje. En mask per ord ser ut som en lösning men
 *     klipper fel så fort ett ord hänger ned (g, j, p) eller bär en ring (Å).
 *   - Texten ska gå att markera och läsas upp: orden är riktiga ord i riktig ordning, ingenting ritas om.
 *   - Den som bett om mindre rörelse får texten stillastående och läsbar direkt.
 */

type Props = { text: string; className?: string; as?: any; delay?: number; stagger?: number };

export default function RevealLines({ text, className, as: Tag = "h2", delay = 0, stagger = 70 }: Props) {
  const host = useRef<HTMLElement | null>(null);
  const [lines, setLines] = useState<string[] | null>(null);
  const [on, setOn] = useState(false);

  // Var bröt webbläsaren raderna? Frågas av den riktiga texten, inte gissas.
  useEffect(() => {
    const el = host.current;
    if (!el || prefersStill()) return;
    let dead = false;
    const measure = () => {
      if (dead || !el) return;
      const probe = document.createElement("span");
      probe.style.cssText = "position:absolute;visibility:hidden;white-space:normal;";
      probe.style.width = `${el.clientWidth}px`;
      probe.style.font = getComputedStyle(el).font;
      probe.style.letterSpacing = getComputedStyle(el).letterSpacing;
      probe.style.lineHeight = getComputedStyle(el).lineHeight;
      probe.innerHTML = text.split(" ").map((w) => `<i style="font-style:inherit">${w}</i>`).join(" ");
      el.appendChild(probe);
      const rows: string[] = [];
      let top: number | null = null;
      for (const w of Array.from(probe.querySelectorAll("i"))) {
        const t = Math.round(w.getBoundingClientRect().top);
        if (top === null || Math.abs(t - top) > 3) { rows.push(w.textContent || ""); top = t; }
        else rows[rows.length - 1] += " " + (w.textContent || "");
      }
      el.removeChild(probe);
      if (!dead) setLines(rows.length ? rows : [text]);
    };
    const fonts = (document as any).fonts;
    if (fonts?.ready) fonts.ready.then(measure); else measure();
    window.addEventListener("resize", measure);
    return () => { dead = true; window.removeEventListener("resize", measure); };
  }, [text]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    if (prefersStill() || !("IntersectionObserver" in window)) { setOn(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setOn(true); io.disconnect(); } },
      { rootMargin: "-10% 0px -10% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [lines]);

  // Innan raderna är mätta står texten som den är: sidan ska aldrig vara tom medan den väntar.
  if (!lines) return <Tag className={className} ref={host as any}>{text}</Tag>;

  return (
    <Tag className={`${className || ""} rv${on ? " in" : ""}`} ref={host as any} aria-label={text}>
      {lines.map((l, i) => (
        <span className="rv-line" key={i} aria-hidden="true">
          <span className="rv-in" style={{ transitionDelay: `${delay + i * stagger}ms` }}>{l}</span>
        </span>
      ))}
    </Tag>
  );
}
