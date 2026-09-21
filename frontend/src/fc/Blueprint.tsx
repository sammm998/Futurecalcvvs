import { t as tr } from "../i18n";
/* Ritningen som webbplatsen är byggd av.
 *
 * Det som gör att en sida om VVS-kalkyl ser ut som VVS-kalkyl är inte en bild på ett rör. Det är bladets egen
 * grammatik: väggar i tunn linje, rör i sitt systems färg, hänvisningslinjer med etikett i änden, måttlinjer
 * med pil åt båda håll, en skalstock. Allt här är ritat i samma koordinater som en plan i skala 1:50, så att
 * måtten som skrivs ut faktiskt stämmer med längden på strecken.
 *
 * Figuren är dekor på de publika sidorna - den mäter ingenting och har inget facit. Academys övningsblad är
 * en annan sak och bor för sig, med sitt svar på servern.
 */

export const PLAN_W = 1200;
export const PLAN_H = 760;

/** Rörens färger. Samma betydelse som i verktyget: en beteckning, en färg. */
export const SYS = {
  KV: "#4ea8ff",
  VV: "#ff6b6b",
  VVC: "#ffa23a",
  S: "#6ee7a5",
  VS: "#b48cff",
};

/* Planen som punkter, en gång.
 *
 * Både bladet och byggnaden ritas ur samma tal. Det är inte en förenkling utan hela poängen: det som visas i
 * 3D är samma geometri som ligger i 2D, och en ändring i den ena kan därför inte glida isär från den andra.
 * Punkterna är bladets koordinater; 3D-scenen skalar om dem till meter. */
export type Pt = [number, number];

export const WALL_PTS: Pt[][] = [
  [[120, 120], [1080, 120], [1080, 640], [120, 640], [120, 120]],
  [[470, 140], [470, 430]], [[470, 510], [470, 620]],
  [[740, 140], [740, 300]], [[740, 380], [740, 620]],
  [[140, 430], [470, 430]],
];

const d = (pts: Pt[]) => "M" + pts.map(([x, y]) => `${x} ${y}`).join(" L");

/* Väggarna. En yttervägg i dubbel linje, innerväggar i enkel, och tre rum som hänger ihop. */
const WALLS = [
  ...WALL_PTS.map(d),
  "M140 140 H1060 V620 H140 Z",
];

/** Måttlinje med pilar i båda ändar och text i mitten. */
function Dim({ x1, y1, x2, y2, t }: { x1: number; y1: number; x2: number; y2: number; t: string }) {
  const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
  const vert = Math.abs(x2 - x1) < 1;
  return (
    <g className="bp-dim">
      <line x1={x1} y1={y1} x2={x2} y2={y2} />
      <line x1={x1 - (vert ? 5 : 0)} y1={y1 - (vert ? 0 : 5)} x2={x1 + (vert ? 5 : 0)} y2={y1 + (vert ? 0 : 5)} />
      <line x1={x2 - (vert ? 5 : 0)} y1={y2 - (vert ? 0 : 5)} x2={x2 + (vert ? 5 : 0)} y2={y2 + (vert ? 0 : 5)} />
      <text x={mx} y={my - (vert ? 0 : 6)} dx={vert ? 8 : 0} textAnchor={vert ? "start" : "middle"}>{t}</text>
    </g>
  );
}

/** En beteckning i änden av sin hänvisningslinje, precis som på ett blad. */
export function Leader(
  { x, y, tx, ty, label, color, id }:
  { x: number; y: number; tx: number; ty: number; label: string; color: string; id?: string },
) {
  return (
    <g className="bp-leader" id={id}>
      <circle cx={x} cy={y} r={3.4} fill={color} />
      <path d={`M${x} ${y} L${tx} ${ty}`} stroke={color} strokeWidth={1} fill="none" opacity={0.7} />
      <rect x={tx - 4} y={ty - 15} width={label.length * 7.6 + 16} height={21} rx={4}
        fill="rgba(8,8,8,0.82)" stroke={color} strokeOpacity={0.45} strokeWidth={0.8} />
      <text x={tx + 5} y={ty} className="bp-leader-t" fill={color}>{label}</text>
    </g>
  );
}

/* Rörstråken. Varje stråk har id så att en scen kan rita det, tända det eller mäta det. */
export const RUN_PTS: { id: string; sys: keyof typeof SYS; dn: number; label: string; pts: Pt[] }[] = [
  { id: "kv-1", sys: "KV", dn: 25, label: "KV1-X31-25", pts: [[170, 580], [400, 580], [400, 300], [660, 300], [660, 210]] },
  { id: "vv-1", sys: "VV", dn: 20, label: "VV1-X31-20", pts: [[188, 580], [418, 580], [418, 318], [660, 318], [660, 232]] },
  { id: "vvc-1", sys: "VVC", dn: 15, label: "VVC1-X31-15", pts: [[206, 580], [436, 580], [436, 336], [660, 336], [660, 254]] },
  { id: "s-1", sys: "S", dn: 110, label: "S1-P5-110", pts: [[300, 640], [300, 470], [830, 470], [830, 300], [1010, 300]] },
  { id: "vs-1", sys: "VS", dn: 32, label: "VS1-S13-32", pts: [[900, 620], [900, 360], [540, 360], [540, 180]] },
];

/** Metrarna räknas ur punkterna, inte ur ett tal någon skrivit. Skalan är bladets: 1:50 på 1200 enheter. */
const M_PER_UNIT = 0.0265;
const len = (pts: Pt[]) =>
  pts.slice(1).reduce((a, p, i) => a + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0) * M_PER_UNIT;

export const RUNS = RUN_PTS.map((r) => ({ ...r, d: d(r.pts), m: Math.round(len(r.pts) * 100) / 100 }));
export const PLAN_SCALE = M_PER_UNIT;

export default function Blueprint(
  { className = "", labels = true, dims = true }: { className?: string; labels?: boolean; dims?: boolean },
) {
  return (
    <svg className={`bp ${className}`.trim()} viewBox={`0 0 ${PLAN_W} ${PLAN_H}`} role="img"
      aria-label={tr("Planritning med tappvatten, spillvatten och värme")}>
      <g className="bp-wall">{WALLS.map((d, i) => <path key={i} d={d} />)}</g>

      {/* fasta installationer: wc, tvättställ, golvbrunn, radiatorer */}
      <g className="bp-fix">
        <rect x={200} y={480} width={54} height={38} rx={6} />
        <circle cx={330} cy={498} r={20} />
        <circle cx={300} cy={610} r={11} />
        <path d="M296 606 L304 614 M304 606 L296 614" />
        <rect x={860} y={560} width={86} height={16} rx={3} />
        <rect x={860} y={200} width={86} height={16} rx={3} />
        <rect x={520} y={160} width={16} height={74} rx={3} />
      </g>

      <g className="bp-runs">
        {RUNS.map((r) => (
          <path key={r.id} id={`run-${r.id}`} d={r.d} stroke={SYS[r.sys]} className={`bp-run bp-${r.sys}`} />
        ))}
      </g>

      {labels && (
        <g>
          <Leader x={400} y={430} tx={330} ty={392} label="KV1-X31-25" color={SYS.KV} id="lbl-kv" />
          <Leader x={660} y={260} tx={700} ty={244} label="VV1-X31-20" color={SYS.VV} id="lbl-vv" />
          <Leader x={830} y={400} tx={874} ty={392} label="S1-P5-110" color={SYS.S} id="lbl-s" />
          <Leader x={540} y={280} tx={580} ty={296} label="VS1-S13-32" color={SYS.VS} id="lbl-vs" />
        </g>
      )}

      {dims && (
        <g>
          <Dim x1={140} y1={680} x2={470} y2={680} t="4 250" />
          <Dim x1={470} y1={680} x2={1060} y2={680} t="7 600" />
          <Dim x1={1100} y1={140} x2={1100} y2={620} t="6 200" />
        </g>
      )}

      {/* skalstocken: det som gör en ritning mätbar */}
      <g className="bp-scale" transform="translate(140, 714)">
        <rect x={0} y={0} width={40} height={6} /><rect x={80} y={0} width={40} height={6} />
        <rect x={0} y={0} width={160} height={6} fill="none" stroke="currentColor" strokeWidth={0.8} />
        <text x={0} y={20}>0</text><text x={150} y={20}>4 m</text>
        <text x={186} y={6}>SKALA 1:50</text>
      </g>
    </svg>
  );
}
