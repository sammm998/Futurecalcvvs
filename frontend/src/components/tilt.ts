import { useCallback, useEffect, useRef, useState } from "react";

/* Depth, driven by where the reader actually is.
 *
 * A plane that leans towards the pointer reads as a thing on a table rather than a rectangle in a document, and
 * that is worth having on a landing page and on a list of drawings. It is worth nothing on a surface someone is
 * measuring against - a sheet that tilts under the cursor is a sheet you cannot trace a run on - so none of this
 * is applied to the drawing itself.
 *
 * Everything here is one pointer listener per element, read on the frame, and every one of them goes flat on the
 * system's reduced-motion setting.
 */

function reduced(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

export type Tilt = { rx: number; ry: number; px: number; py: number; over: boolean };

const FLAT: Tilt = { rx: 0, ry: 0, px: 0.5, py: 0.5, over: false };

/**
 * How far a plane should lean, from where the pointer is over it. `deg` is the lean at the very edge.
 *
 * Returns handlers to spread onto the element and the numbers to build a transform from, rather than a finished
 * style: what leans, how much, and what else moves with it differs everywhere this is used.
 */
export function useTilt(deg = 6) {
  const [t, setT] = useState<Tilt>(FLAT);
  const frame = useRef(0);
  const off = reduced();

  const onPointerMove = useCallback((e: React.PointerEvent<HTMLElement>) => {
    if (off) return;
    const el = e.currentTarget;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / Math.max(1, r.width);
    const py = (e.clientY - r.top) / Math.max(1, r.height);
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      setT({ rx: (0.5 - py) * 2 * deg, ry: (px - 0.5) * 2 * deg, px, py, over: true });
    });
  }, [deg, off]);

  const onPointerLeave = useCallback(() => {
    cancelAnimationFrame(frame.current);
    frame.current = 0;
    setT(FLAT);
  }, []);

  useEffect(() => () => cancelAnimationFrame(frame.current), []);
  return { tilt: off ? FLAT : t, handlers: { onPointerMove, onPointerLeave } };
}

/** The transform a leaning plane wears, and the light that falls on it, as CSS custom properties. */
export function tiltStyle(t: Tilt, lift = 10): React.CSSProperties {
  return {
    transform: `rotateX(${t.rx}deg) rotateY(${t.ry}deg) translateZ(${t.over ? lift : 0}px)`,
    ["--gx" as string]: `${(t.px * 100).toFixed(1)}%`,
    ["--gy" as string]: `${(t.py * 100).toFixed(1)}%`,
    ["--glare" as string]: t.over ? "1" : "0",
  };
}

/**
 * Where the pointer is on the page, -1 to 1 on each axis, for scenes that lean as a whole rather than per card.
 * One listener for the document, so a hero with five planes in it costs one.
 */
export function usePointerParallax() {
  const [p, setP] = useState({ x: 0, y: 0 });
  useEffect(() => {
    if (reduced()) return;
    let frame = 0;
    const on = (e: PointerEvent) => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        setP({ x: (e.clientX / window.innerWidth - 0.5) * 2, y: (e.clientY / window.innerHeight - 0.5) * 2 });
      });
    };
    window.addEventListener("pointermove", on, { passive: true });
    return () => { window.removeEventListener("pointermove", on); cancelAnimationFrame(frame); };
  }, []);
  return p;
}

/**
 * Marks each child of a list the moment it arrives, so a list of drawings assembles itself in depth instead of
 * being there already. Returns the ref to put on the container; the children carry the class.
 */
export function useStaggerIn<T extends HTMLElement>(count: number) {
  const ref = useRef<T | null>(null);
  const [n, setN] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (reduced() || !("IntersectionObserver" in window)) { setN(count); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setN(count); io.disconnect(); } },
      { rootMargin: "-5% 0px -5% 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, [count]);
  return { ref, shown: n > 0 };
}
