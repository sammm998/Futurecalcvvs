import { useEffect, useState } from "react";

/* Övergången från plan till byggnad.
 *
 * Ritningen ligger kvar medan den lyser till och zoomar en aning; först därefter tar 3D-vyn över. Det är den
 * korta stunden som gör att modellen känns rest ur planen i stället för att sidan bytts ut. Den som slagit på
 * reducerad rörelse hoppar över resan och får modellen direkt.
 */
export default function DrawingTo3DTransition({ children, onDone }: { children: React.ReactNode; onDone: () => void }) {
  const [phase, setPhase] = useState<"lyft" | "klar">("lyft");
  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    const t = setTimeout(() => { setPhase("klar"); onDone(); }, reduced ? 0 : 620);
    return () => clearTimeout(t);
  }, [onDone]);
  return <div className={`d3-transition ${phase}`}>{children}</div>;
}
