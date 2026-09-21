import { useEffect, useRef, useState } from "react";
import AnalysisGateAnimation from "./AnalysisGateAnimation";

/* Resultatet avslöjas när det finns.
 *
 * Komponenten känner bara till motorns status: `idle`, `processing`, `completed`, `failed`. Den bestämmer inget
 * om läsningen och läsningen bestämmer inget om den. Portarna öppnas en enda gång, när status blir `completed`
 * och innehållet är monterat, och aldrig vid ett fel - ett misslyckande ska mötas av ett besked, inte av en
 * föreställning.
 */
export type EngineStatus = "idle" | "processing" | "completed" | "failed";

export default function AnalysisCompletionReveal({ status, children, label }: {
  status: EngineStatus;
  children: React.ReactNode;
  label?: string;
}) {
  const played = useRef(false);
  const [open, setOpen] = useState(false);
  // Resultatet ligger bakom portarna och syns när de börjar gå isär. Har de redan spelat, eller kommer sidan
  // hit på annat sätt än genom en avslutad läsning, ligger det framme direkt.
  const [revealed, setRevealed] = useState(status !== "completed");

  useEffect(() => {
    if (status !== "completed" || played.current) return;
    played.current = true;
    // ett andetag så att innehållet hunnit monteras bakom portarna innan de går isär
    const t = requestAnimationFrame(() => setOpen(true));
    return () => cancelAnimationFrame(t);
  }, [status]);

  if (status === "failed" || status === "idle" || status === "processing") return <>{children}</>;
  return (
    <div className="reveal-wrap">
      <div className={`reveal-body${revealed ? " shown" : ""}`}>{children}</div>
      <AnalysisGateAnimation open={open} label={label} onOpening={() => setRevealed(true)} />
    </div>
  );
}
