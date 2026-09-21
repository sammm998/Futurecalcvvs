import { useEffect } from "react";

/* Skrollen med tröghet, och det som hänger på den.
 *
 * En sida som rör sig exakt som hjulet känns som ett dokument; en som kommer ikapp känns som en yta. Det är
 * hela skillnaden mellan en hemsida och en plats, och det är den effekt den sortens sidor bygger på.
 *
 * Gjort på sidans egen skroll, inte genom att flytta ett omslag med transform. Ett förskjutet omslag bryter
 * `position: sticky`, och hela startsidan står på fastnålade scener - de skulle sluta fastna. Här flyttas
 * fönstret självt, en bildruta i taget, mot det läge hjulet har bett om.
 *
 * Tre saker lämnas i fred: pekskärmar (de har egen tröghet, och att ta den ifrån dem gör sidan sämre),
 * tangentbord och ankarlänkar (de ska hoppa som de brukar), och den som bett om mindre rörelse.
 */

const EASE = 0.098;        // hur snabbt sidan kommer ikapp: lägre är tyngre
const STOP = 0.4;          // närmare än så är framme
const WHEEL_SCALE = 1.0;

export function prefersStill(): boolean {
  return typeof window !== "undefined"
    && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

function coarsePointer(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches === true;
}

/** Sätter tröghet på hela sidans skroll så länge komponenten lever. */
export function useSmoothScroll(enabled = true) {
  useEffect(() => {
    if (!enabled || prefersStill() || coarsePointer()) return;

    let target = window.scrollY;
    let current = window.scrollY;
    let frame = 0;
    let running = false;
    // Medan vi själva skrollar kommer scroll-händelser som är vårt eget verk. Bara det som inte är vårt får
    // flytta målet, annars slåss sidan med sig själv när något annat skrollar den.
    let ours = false;

    const maxY = () => document.documentElement.scrollHeight - window.innerHeight;

    const tick = () => {
      frame = 0;
      const d = target - current;
      if (Math.abs(d) < STOP) {
        current = target;
        ours = true; window.scrollTo(0, Math.round(current)); ours = false;
        running = false;
        return;
      }
      current += d * EASE;
      ours = true; window.scrollTo(0, Math.round(current)); ours = false;
      frame = requestAnimationFrame(tick);
    };

    const start = () => { if (!running) { running = true; frame = requestAnimationFrame(tick); } };

    const onWheel = (e: WheelEvent) => {
      if (e.ctrlKey) return;                                   // nypzoom hör till webbläsaren
      // Något som skrollar för egen maskin - en kodruta, en lista, en modal - får göra det själv.
      let n = e.target as HTMLElement | null;
      while (n && n !== document.body) {
        const s = getComputedStyle(n);
        if (/(auto|scroll)/.test(s.overflowY) && n.scrollHeight > n.clientHeight + 2) return;
        n = n.parentElement;
      }
      e.preventDefault();
      target = Math.max(0, Math.min(maxY(), target + e.deltaY * WHEEL_SCALE));
      start();
    };

    // Allt annat som flyttar sidan - tangentbord, ankare, sökfältet - är sanningen, inte vårt mål.
    const onScroll = () => { if (!ours && !running) { target = window.scrollY; current = window.scrollY; } };
    const onResize = () => { target = Math.max(0, Math.min(maxY(), target)); };

    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("wheel", onWheel);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(frame);
    };
  }, [enabled]);
}

/* ---------------------------------------------------------------------------------------------------
 * Parallax: det som ligger bakom rör sig långsammare än det som ligger framför.
 * ------------------------------------------------------------------------------------------------ */

/**
 * Ger varje element med `data-par` en förskjutning i takt med skrollen. Talet är hur många bildpunkter
 * elementet halkar efter över en hel skärmhöjd - negativt betyder att det går före.
 */
export function useParallax(scope?: React.RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (prefersStill()) return;
    const root = scope?.current ?? document;
    const nodes = Array.from(root.querySelectorAll<HTMLElement>("[data-par]"));
    if (!nodes.length) return;
    let frame = 0;
    const read = () => {
      frame = 0;
      const vh = window.innerHeight;
      for (const el of nodes) {
        const r = el.getBoundingClientRect();
        if (r.bottom < -vh || r.top > vh * 2) continue;        // långt utanför bild: rör inte
        const mid = r.top + r.height / 2;
        const off = (mid - vh / 2) / vh;                        // 0 i mitten av skärmen
        const amt = Number(el.dataset.par || 0);
        el.style.transform = `translate3d(0, ${(off * amt).toFixed(2)}px, 0)`;
      }
    };
    const on = () => { if (!frame) frame = requestAnimationFrame(read); };
    read();
    window.addEventListener("scroll", on, { passive: true });
    window.addEventListener("resize", on);
    return () => {
      window.removeEventListener("scroll", on);
      window.removeEventListener("resize", on);
      cancelAnimationFrame(frame);
      for (const el of nodes) el.style.transform = "";
    };
  }, [scope]);
}
