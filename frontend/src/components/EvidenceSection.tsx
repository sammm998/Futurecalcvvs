import { useInView } from "./lp-motion";
import { t as tr } from "../i18n";
import { tiltStyle, useTilt } from "./tilt";

/* What the reading leaves behind, drawn rather than listed.
 *
 * Six claims about evidence had six copies of the same tick as their illustration, which says nothing about any
 * of them. Each card draws the thing it is claiming instead: the chain from a label to a metre, the scale bar
 * being checked against the printed scale, the sheet coming back coloured, two readings disagreeing. The section
 * is about being able to look at the evidence, so it had better be worth looking at.
 */

function Card({ span, title, body, figure, tall, wide }: {
  span: number; title: string; body: string; figure: React.ReactNode; tall?: boolean; wide?: boolean;
}) {
  const { tilt, handlers } = useTilt(wide ? 1.6 : 3);
  return (
    <article className={`lp-ev${tall ? " tall" : ""}${wide ? " wide" : ""}`}
      style={{ gridColumn: `span ${span}`, ...tiltStyle(tilt, wide ? 6 : 10) }} {...handlers}>
      <div className="lp-ev-fig">{figure}</div>
      <div className="lp-ev-say">
        <h3>{title}</h3>
        <p>{body}</p>
      </div>
    </article>
  );
}

/** The chain itself: a label, the line it draws, the stroke that line lands on, and the metre that comes out. */
function Chain({ on }: { on: boolean }) {
  const d = (s: number) => ({ animationDelay: `${s}s`, animationPlayState: on ? "running" : "paused" as const });
  return (
    <svg viewBox="0 0 460 168" role="img" aria-label={tr("Från etikett till meter, steg för steg")} className="lp-chain">
      {/* the label the sheet writes */}
      <g className="lp-ci" style={d(0)}>
        <rect x="14" y="24" width="118" height="26" rx="4" className="lp-ev-box" />
        <text x="26" y="42" className="lp-ev-mono">KV1-X31-16</text>
        <line x1="26" y1="47" x2="120" y2="47" className="lp-ev-rule" />
      </g>
      {/* the leader it draws from that label */}
      <path d="M132 44 C 176 44, 186 78, 214 86" className="lp-ev-leader lp-cd" style={d(0.45)} pathLength={1} />
      {/* the geometry the leader lands on */}
      <g className="lp-ci" style={d(0.9)}>
        <circle cx="214" cy="87" r="5.5" className="lp-ev-hit" />
      </g>
      <g className="lp-cd" style={d(1.0)}>
        <path d="M150 87 H344" className="lp-ev-run on" pathLength={1} />
      </g>
      {/* and the metre that comes out of it */}
      <g className="lp-ci" style={d(1.6)}>
        <rect x="352" y="70" width="96" height="34" rx="8" className="lp-ev-sum" />
        <text x="366" y="92" className="lp-ev-num">17,10 m</text>
      </g>
      <g className="lp-ci" style={d(1.8)} textAnchor="middle">
        <text x="73" y="150" className="lp-ev-cap">etikett</text>
        <text x="172" y="150" className="lp-ev-cap">ledarlinje</text>
        <text x="266" y="150" className="lp-ev-cap">kontaktpunkt</text>
        <text x="400" y="150" className="lp-ev-cap">{tr("mängd")}</text>
      </g>
    </svg>
  );
}

/** The printed scale and the bar on the paper, checked against each other. */
function ScaleFig() {
  return (
    <svg viewBox="0 0 230 100" aria-hidden="true">
      <text x="8" y="24" className="lp-ev-mono sm">SKALA 1:50</text>
      <g className="lp-ev-bar">
        <path d="M8 52 H152" />
        {[0, 24, 48, 72, 96, 120, 144].map((x) => <path key={x} d={`M${8 + x} 45 V59`} />)}
      </g>
      <rect x="8" y="52" width="48" height="7" className="lp-ev-barfill" />
      <text x="8" y="80" className="lp-ev-cap">0</text>
      <text x="126" y="80" className="lp-ev-cap">6 m</text>
      <g className="lp-ev-ok">
        <circle cx="200" cy="52" r="14" />
        <path d="M193.5 52 l5 5 L208 46" />
      </g>
    </svg>
  );
}

/** The sheet coming back with each run in its identity's colour, and what nothing named left grey. */
function MarkedFig() {
  return (
    <svg viewBox="0 0 240 124" aria-hidden="true">
      <rect x="6" y="6" width="228" height="112" rx="4" className="lp-ev-sheet" />
      <path d="M30 32 H136 V70 H206" className="lp-ev-mrun a" />
      <path d="M30 56 H108 V96" className="lp-ev-mrun b" />
      <path d="M108 32 H206" className="lp-ev-mrun c" />
      <path d="M44 96 H188" className="lp-ev-mrun grey" />
      <text x="30" y="112" className="lp-ev-cap">grått = onämnt, mäts inte</text>
    </svg>
  );
}

/** Two ways to the same run, and what happens where they disagree. */
function AgreeFig() {
  return (
    <svg viewBox="0 0 240 108" aria-hidden="true">
      <rect x="8" y="10" width="72" height="20" rx="4" className="lp-ev-box" />
      <text x="16" y="25" className="lp-ev-mono sm">S3-R8-75</text>
      <path d="M80 21 C 120 21, 132 48, 158 54" className="lp-ev-leader" />
      <path d="M42 34 C 42 78, 100 88, 156 62" className="lp-ev-leader alt" />
      <circle cx="160" cy="57" r="5.5" className="lp-ev-hit" />
      <path d="M160 57 H230" className="lp-ev-run on" />
      <text x="8" y="98" className="lp-ev-cap">{tr("två vägar · samma svar")}</text>
    </svg>
  );
}

/** What was left over, each with the reason the drawing gave. */
function ListFig() {
  return (
    <svg viewBox="0 0 240 108" aria-hidden="true">
      {[["VV1-X7-20", "ingen linje", 0], ["S1-P2-110", "flera anspråk", 1], ["KV2-X31", "når ej fram", 2]]
        .map(([a, b, i]) => (
          <g key={a as string} transform={`translate(0 ${(i as number) * 30})`}>
            <path d="M8 22 H232" className="lp-ev-rule" />
            <text x="8" y="17" className="lp-ev-mono sm">{a}</text>
            <rect x="132" y="4" width="100" height="16" rx="8" className="lp-ev-chip" />
            <text x="142" y="15.5" className="lp-ev-cap chip">{b}</text>
          </g>
        ))}
    </svg>
  );
}

/** The takeoff on its way out, in the shapes a calculation already reads. */
function ExportFig() {
  return (
    <svg viewBox="0 0 420 92" aria-hidden="true">
      {[["BETECKNING", "DN", "M"], ["KV1-X31-16", "16", "17,10"], ["S3-R8-110", "110", "58,40"],
        ["VV1-X31-16", "16", "33,92"]].map((r, i) => (
        <g key={r[0]} transform={`translate(0 ${i * 22})`}>
          <path d="M0 18 H300" className="lp-ev-rule" />
          <text x="4" y="13" className={`lp-ev-mono sm${i ? "" : " head"}`}>{r[0]}</text>
          <text x="176" y="13" className={`lp-ev-mono sm${i ? "" : " head"}`}>{r[1]}</text>
          <text x="240" y="13" className={`lp-ev-mono sm${i ? "" : " head"}`}>{r[2]}</text>
        </g>
      ))}
      {["XLSX", "CSV", "JSON", "PDF"].map((f, i) => (
        <g key={f} transform={`translate(330 ${i * 22})`}>
          <rect x="0" y="0" width="62" height="17" rx="8" className="lp-ev-chip" />
          <text x="12" y="12" className="lp-ev-cap chip">{f}</text>
        </g>
      ))}
    </svg>
  );
}

export default function EvidenceSection() {
  const { ref, seen } = useInView<HTMLDivElement>();
  return (
    <section className="lp-sec lp-wrap" id="belagg">
      <div className="lp-sec-head">
        <div className="lp-kicker">{tr("Beläggen")}</div>
        <h2>{tr("Varje meter går att spåra tillbaka")}</h2>
        <p>{tr("Klicka på en rad i mängden och se exakt vilken etikett, vilken ledarlinje och vilka streck som gav den.")}</p>
      </div>
      <div className="lp-bento" ref={ref}>
        <Card span={4} tall title={tr("Bevis per rad")}
          body="Etikett, ledarlinje, kontaktpunkt och varje streck som räknades — med sidkoordinater."
          figure={<Chain on={seen} />} />
        <Card span={2} tall title={tr("Skalan verifierad")}
          body="Utskriven skala kontrolleras mot skalstocken på pappret innan en enda meter räknas."
          figure={<ScaleFig />} />
        <Card span={2} title={tr("Markerad PDF")}
          body="Samma ritning tillbaka med varje rör färgat efter identitet och det onämnda i grått."
          figure={<MarkedFig />} />
        <Card span={2} title={tr("Flera läsningar")}
          body="Sidan läses om längs vägar med andra bevis. Där de säger emot varandra lämnar röret mängden."
          figure={<AgreeFig />} />
        <Card span={2} title="Granskningslista"
          body="Rör ingen väg namngav och etiketter ingen väg placerade, var och en med sitt skäl."
          figure={<ListFig />} />
        <Card span={6} wide title={tr("Excel och CSV")}
          body="Mängden ut i det format kalkylen redan använder, med beläggen kvar i filen."
          figure={<ExportFig />} />
      </div>
    </section>
  );
}
