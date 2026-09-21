import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { t as tr, num } from "../i18n";
import type { PlanData } from "./api";

/* Övningsritningen.
 *
 * Ett blad man kan zooma, panorera, mäta på och peka i. Samma verktyg som mängdaren använder i produkten,
 * fast i litet: klicka en startpunkt, klicka varje brytpunkt, avsluta stråket, och se längden växa medan du
 * går.
 *
 * Det som gör den användbar som övning och inte som pekövning är **fångsten**. Klicket dras till närmaste
 * punkt på ett ritat rör inom en liten radie. Då handlar uppgiften om att avgöra vilka rör som ska med -
 * vilket är vad en mängdare faktiskt gör - i stället för om att träffa en två punkter bred linje med musen.
 * Utan fångst mäter man sin egen handstadga.
 *
 * Tangentbordet kommer åt allt: symbolerna är knappar med ordning, mätpunkter kan läggas med Enter på en
 * fokuserad punkt, Backsteg ångrar och Escape avslutar stråket. En övning som kräver mus är en övning som
 * utestänger.
 */

export type Run = number[][];

type Props = {
  plan: PlanData;
  mode: "matt" | "val" | "las";
  runs?: Run[];
  onRuns?: (runs: Run[]) => void;
  picked?: string[];
  onPicked?: (ids: string[]) => void;
  /** vad som ska lysa: systemet eller dimensionen uppgiften handlar om */
  highlight?: { sys?: string; dn?: number; run?: string };
  height?: number;
};

const SYS_COLOR: Record<string, string> = {
  KV: "#4ea8ff", VV: "#ff6b6b", VVC: "#ffa23a", S: "#6ee7a5", D: "#7fd4ff", VS: "#b48cff",
};
const SNAP = 14;                      // fångstradie i ritningsenheter vid oskalad vy

/** Punkterna i ett path som bara använder M och L. Bladen ritas så, och en full parser vore överarbete. */
function pathPoints(d: string): number[][] {
  const out: number[][] = [];
  for (const m of d.matchAll(/([ML])\s*(-?[\d.]+)[ ,]+(-?[\d.]+)/g)) {
    out.push([parseFloat(m[2]), parseFloat(m[3])]);
  }
  return out;
}

function dist(a: number[], b: number[]) { return Math.hypot(a[0] - b[0], a[1] - b[1]); }

/** Närmaste punkt på en sträcka, och hur långt bort den ligger. */
function nearestOnSeg(p: number[], a: number[], b: number[]): { pt: number[]; d: number } {
  const vx = b[0] - a[0], vy = b[1] - a[1];
  const len2 = vx * vx + vy * vy;
  const t = len2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / len2)) : 0;
  const pt = [a[0] + vx * t, a[1] + vy * t];
  return { pt, d: dist(p, pt) };
}

export default function TrainingDrawing({
  plan, mode, runs = [], onRuns, picked = [], onPicked, highlight, height = 460,
}: Props) {
  const box = useRef<HTMLDivElement>(null);
  const [view, setView] = useState(() => ({ x: plan.view[0], y: plan.view[1], w: plan.view[2], h: plan.view[3] }));
  const [draft, setDraft] = useState<number[][]>([]);
  const [hover, setHover] = useState<number[] | null>(null);
  const drag = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null);

  useEffect(() => {
    setView({ x: plan.view[0], y: plan.view[1], w: plan.view[2], h: plan.view[3] });
    setDraft([]);
  }, [plan.plan, plan.view]);

  // Alla punkter det går att fånga mot: varje brytpunkt och varje sträcka på varje rör.
  const segs = useMemo(() => {
    const out: { a: number[]; b: number[] }[] = [];
    for (const r of plan.runs) {
      const pts = pathPoints(r.d);
      for (let i = 1; i < pts.length; i++) out.push({ a: pts[i - 1], b: pts[i] });
    }
    return out;
  }, [plan.runs]);

  const toPlan = useCallback((ev: { clientX: number; clientY: number }) => {
    const el = box.current;
    if (!el) return [0, 0];
    const r = el.getBoundingClientRect();
    // SVG:n brevlådar innehållet; samma räkning här som preserveAspectRatio gör där.
    const scale = Math.min(r.width / view.w, r.height / view.h);
    const ox = (r.width - view.w * scale) / 2;
    const oy = (r.height - view.h * scale) / 2;
    return [view.x + (ev.clientX - r.left - ox) / scale, view.y + (ev.clientY - r.top - oy) / scale];
  }, [view]);

  const snap = useCallback((p: number[]): number[] => {
    let best = { pt: p, d: Infinity };
    for (const s of segs) {
      const near = nearestOnSeg(p, s.a, s.b);
      if (near.d < best.d) best = near;
      for (const v of [s.a, s.b]) {
        const dv = dist(p, v);
        if (dv < best.d) best = { pt: v, d: dv };
      }
    }
    const radius = SNAP * (view.w / plan.view[2]);
    return best.d <= radius ? best.pt : p;
  }, [segs, view.w, plan.view]);

  const commit = useCallback((pts: number[][]) => {
    if (pts.length >= 2) onRuns?.([...runs, pts]);
    setDraft([]);
  }, [runs, onRuns]);

  const click = (e: React.MouseEvent) => {
    if (mode !== "matt" || drag.current) return;
    const p = snap(toPlan(e));
    setDraft((d) => [...d, p]);
  };

  const dblclick = () => { if (mode === "matt") commit(draft); };

  const move = (e: React.MouseEvent) => {
    if (drag.current) {
      const el = box.current!;
      const r = el.getBoundingClientRect();
      const scale = Math.min(r.width / view.w, r.height / view.h);
      setView((v) => ({ ...v, x: drag.current!.vx - (e.clientX - drag.current!.x) / scale,
                        y: drag.current!.vy - (e.clientY - drag.current!.y) / scale }));
      return;
    }
    if (mode === "matt") setHover(snap(toPlan(e)));
  };

  const down = (e: React.MouseEvent) => {
    if (e.button === 1 || e.button === 2 || e.shiftKey || mode === "las") {
      drag.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y };
    }
  };
  const up = () => { window.setTimeout(() => { drag.current = null; }, 0); };

  const wheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const p = toPlan(e);
    const k = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    setView((v) => {
      const w = Math.max(60, Math.min(plan.view[2] * 3, v.w * k));
      const h = w * (v.h / v.w);
      return { x: p[0] - (p[0] - v.x) * (w / v.w), y: p[1] - (p[1] - v.y) * (h / v.h), w, h };
    });
  };

  const key = (e: React.KeyboardEvent) => {
    if (mode !== "matt") return;
    if (e.key === "Backspace") { e.preventDefault(); setDraft((d) => d.slice(0, -1)); }
    if (e.key === "Escape") { e.preventDefault(); commit(draft); }
    if (e.key === "Enter" && hover) { e.preventDefault(); setDraft((d) => [...d, hover]); }
  };

  const lit = (r: PlanData["runs"][number]) =>
    !highlight ? true
      : (highlight.run ? r.id === highlight.run
        : (highlight.sys ? r.sys === highlight.sys : true) && (highlight.dn ? r.dn === highlight.dn : true));

  const live = useMemo(() => {
    const all = [...runs, draft];
    let m = 0;
    for (const r of all) for (let i = 1; i < r.length; i++) m += dist(r[i - 1], r[i]) * plan.m_per_unit;
    return m;
  }, [runs, draft, plan.m_per_unit]);

  const vb = `${view.x} ${view.y} ${view.w} ${view.h}`;
  const scaleTick = view.w / plan.view[2];

  return (
    <div className="td">
      <div
        ref={box}
        className={`td-box td-${mode}`}
        style={{ height }}
        onClick={click}
        onDoubleClick={dblclick}
        onMouseMove={move}
        onMouseDown={down}
        onMouseUp={up}
        onMouseLeave={() => setHover(null)}
        onWheel={wheel}
        onKeyDown={key}
        onContextMenu={(e) => e.preventDefault()}
        tabIndex={0}
        role="application"
        aria-label={`Övningsritning: ${plan.title}`}
      >
        <svg viewBox={vb} className="td-svg">
          <g className="td-rooms">
            {plan.rooms.map((r) => (
              <g key={r.name}>
                <rect x={r.x} y={r.y} width={r.w} height={r.h} />
                <text x={r.x + 10} y={r.y + 20}>{r.name}</text>
              </g>
            ))}
          </g>
          <g className="td-walls">
            {plan.walls.map((w, i) => (
              <polyline key={i} points={w.map((p) => p.join(",")).join(" ")} />
            ))}
          </g>
          <g className="td-runs">
            {plan.runs.map((r) => (
              <path key={r.id} d={r.d} stroke={SYS_COLOR[r.sys] || "#8aa"}
                className={`td-run${lit(r) ? " lit" : " dim"}`} />
            ))}
          </g>

          {/* symbolerna: klickbara i valläge, alltid läsbara */}
          <g className="td-syms">
            {plan.symbols.map((s, i) => (
              <g key={s.id} transform={`translate(${s.x} ${s.y}) rotate(${s.rot || 0})`}
                className={`td-sym${picked.includes(s.id) ? " on" : ""}${mode === "val" ? " pick" : ""}`}
                role={mode === "val" ? "checkbox" : undefined}
                aria-checked={mode === "val" ? picked.includes(s.id) : undefined}
                aria-label={s.name}
                tabIndex={mode === "val" ? 0 : -1}
                onKeyDown={(e) => {
                  if (mode !== "val" || (e.key !== "Enter" && e.key !== " ")) return;
                  e.preventDefault();
                  onPicked?.(picked.includes(s.id) ? picked.filter((x) => x !== s.id) : [...picked, s.id]);
                }}
                onClick={(e) => {
                  if (mode !== "val") return;
                  e.stopPropagation();
                  onPicked?.(picked.includes(s.id) ? picked.filter((x) => x !== s.id) : [...picked, s.id]);
                }}>
                <Symbol kind={s.kind} />
                <circle className="td-sym-hit" r={16} />
                {mode === "val" && <text className="td-sym-n" x={0} y={-20}>{i + 1}</text>}
              </g>
            ))}
          </g>

          {/* det som mätts, och det som mäts just nu */}
          <g className="td-meas">
            {runs.map((r, i) => (
              <polyline key={i} className="td-done" points={r.map((p) => p.join(",")).join(" ")} />
            ))}
            {draft.length > 0 && (
              <>
                <polyline className="td-draft"
                  points={[...draft, ...(hover ? [hover] : [])].map((p) => p.join(",")).join(" ")} />
                {draft.map((p, i) => <circle key={i} className="td-pt" cx={p[0]} cy={p[1]} r={4 * scaleTick} />)}
              </>
            )}
            {hover && mode === "matt" && (
              <circle className="td-snap" cx={hover[0]} cy={hover[1]} r={6 * scaleTick} />
            )}
          </g>
        </svg>
      </div>

      <div className="td-bar">
        <div className="td-bar-l">
          {mode === "matt" && (
            <>
              <span className="fc-label">{tr("Mätt")}</span>
              <b className="td-m">{num(live, 2)} m</b>
              <span className="td-hint">
                Klicka punkter · dubbelklick eller Esc avslutar stråket · Backsteg ångrar · Skift+dra panorerar
              </span>
            </>
          )}
          {mode === "val" && (
            <>
              <span className="fc-label">Markerat</span>
              <b className="td-m">{picked.length} st</b>
              <span className="td-hint">{tr("Klicka på symbolerna · Tabb och Enter fungerar också")}</span>
            </>
          )}
        </div>
        <div className="td-bar-r">
          {mode === "matt" && (
            <>
              <button className="fc-btn sm" onClick={() => setDraft((d) => d.slice(0, -1))} disabled={!draft.length}>
                Ångra punkt
              </button>
              <button className="fc-btn sm" onClick={() => onRuns?.(runs.slice(0, -1))} disabled={!runs.length}>
                Ångra stråk
              </button>
              <button className="fc-btn sm" onClick={() => { setDraft([]); onRuns?.([]); }}>{tr("Börja om")}</button>
            </>
          )}
          {mode === "val" && (
            <button className="fc-btn sm" onClick={() => onPicked?.([])} disabled={!picked.length}>Rensa</button>
          )}
          <button className="fc-btn sm"
            onClick={() => setView({ x: plan.view[0], y: plan.view[1], w: plan.view[2], h: plan.view[3] })}>
            Passa in
          </button>
        </div>
      </div>
    </div>
  );
}

/** VVS-symbolerna, ritade en gång och använda överallt: på bladet, i matchningen och i teckenförklaringen. */
export function Symbol({ kind }: { kind: string }) {
  switch (kind) {
    case "kulventil":
      return <g className="sym"><path d="M-9 -7 L0 0 L-9 7 Z M9 -7 L0 0 L9 7 Z" /><path d="M0 0 V-11 M-5 -11 H5" /></g>;
    case "backventil":
      return <g className="sym"><path d="M-9 -7 L0 0 L-9 7 Z" /><path d="M2 -8 V8" /></g>;
    case "injustering":
      return <g className="sym"><path d="M-9 -7 L0 0 L-9 7 Z M9 -7 L0 0 L9 7 Z" /><circle cx={0} cy={-10} r={4} /></g>;
    case "golvbrunn":
      return <g className="sym"><circle r={9} /><path d="M-6 -6 L6 6 M6 -6 L-6 6" /></g>;
    case "wc":
      return <g className="sym"><rect x={-11} y={-14} width={22} height={28} rx={9} /><path d="M-11 -4 H11" /></g>;
    case "tvattstall":
      return <g className="sym"><rect x={-14} y={-10} width={28} height={20} rx={8} /><circle cx={0} cy={0} r={2.5} /></g>;
    case "dusch":
      return <g className="sym"><path d="M-12 -10 H12" /><path d="M-8 -4 V6 M0 -4 V8 M8 -4 V6" /></g>;
    case "blandare":
      return <g className="sym"><path d="M0 8 V-4 A6 6 0 0 1 12 -4" /><circle cx={0} cy={9} r={3} /></g>;
    case "radiator":
      return <g className="sym"><rect x={-22} y={-7} width={44} height={14} rx={2} />
        <path d="M-14 -7 V7 M-6 -7 V7 M2 -7 V7 M10 -7 V7" /></g>;
    case "pump":
      return <g className="sym"><circle r={10} /><path d="M-4 -5 L6 0 L-4 5 Z" /></g>;
    case "expansionskarl":
      return <g className="sym"><rect x={-9} y={-12} width={18} height={24} rx={9} /><path d="M-9 0 H9" /></g>;
    default:
      return <g className="sym"><circle r={8} /></g>;
  }
}
