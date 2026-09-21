import { useEffect, useRef, useState } from "react";

/* Portarna som öppnar sig när läsningen är klar.
 *
 * Två paneler möts på mitten, en ljuslinje går genom fogen, och de glider isär och lämnar resultatet bakom sig.
 * De öppnas när motorn faktiskt säger att den är klar och resultatet är laddat - aldrig på en timer, för en
 * animation som låtsas att något är färdigt är en lögn om arbetet.
 *
 * `open` styr; komponenten monterar bort sig själv när den spelat färdigt, så den kostar ingenting sedan.
 * Slutet läses av panelens egen animationend och inte av en klocka som gissar hur länge den håller på; en
 * klocka finns bara som skyddsnät, för en port som fastnar stängd får aldrig bli ett resultat ingen ser.
 */
export default function AnalysisGateAnimation({ open, onOpening, onDone, label = "Analys klar" }: {
  open: boolean;
  onOpening?: () => void;
  onDone?: () => void;
  label?: string;
}) {
  const [state, setState] = useState<"stangd" | "oppnar" | "borta">("stangd");
  const started = useRef(false);
  const done = useRef(false);
  const cb = useRef({ onOpening, onDone });
  cb.current = { onOpening, onDone };

  const finish = () => {
    if (done.current) return;
    done.current = true;
    setState("borta");
    cb.current.onDone?.();
  };

  useEffect(() => {
    if (!open || started.current) return;
    started.current = true;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    setState("oppnar");
    // innehållet får synas i samma stund som porten börjar gå isär: panelerna är täckande, så ingenting
    // avslöjas för tidigt - och en port som skulle fastna lämnar ändå aldrig sidan tom
    cb.current.onOpening?.();
    // skyddsnätet ligger efter animationens längd; normalfallet avslutas av animationend nedan
    const t = setTimeout(finish, reduced ? 260 : 1500);
    return () => clearTimeout(t);
  }, [open]);

  if (state === "borta") return null;
  return (
    <div className={`gate ${state}`} aria-hidden="true">
      <div className="gate-panel left" onAnimationEnd={finish} />
      <div className="gate-panel right" />
      <div className="gate-seam" />
      <div className="gate-label">{label}</div>
    </div>
  );
}
