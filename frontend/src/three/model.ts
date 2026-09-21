/* Från ritningens läsning till en byggnad i tre dimensioner.
 *
 * Rena funktioner: läsningens svar in, en modell ut. Ingen three.js här, ingen React, ingen skärm - modellen är
 * data, och den som vill kontrollera vad 3D-vyn visar kan läsa den utan att öppna en canvas.
 *
 * Modellen gissar inte mer än ritningen bär. Rören vet vi allt om: läsningen har deras väg, deras dimension och
 * deras namn, och de blir rör med rätt grovlek på rätt ställe. Väggarna vet vi mindre om - de är arkitektens
 * bläck som läsningen valde bort - så de reses som enkla skivor där bläcket går, hellre tydligt förenklat än
 * påhittat i detalj. Det som inte går att avgöra byggs inte.
 */

import { identityColor } from "../palette";

export type Vec2 = [number, number];

export type ModelPipe = {
  id: string;
  designation: string;
  dn: number | null;
  system: string;
  path: Vec2[];          // i meter, i modellens plan
  radius: number;        // meter
  risers: number;
  color: string;
  meters: number;
  inWall?: boolean;      // biten som går genom en vägg: ritad, mätt, och räknad för sig i mängden
};

export type ModelWall = {
  id: string;
  a: Vec2;
  b: Vec2;
  thickness: number;     // meter
  height: number;        // meter
};

export type BuildingModel = {
  /** Modellens utsträckning i meter, med origo i mitten. */
  size: { width: number; depth: number };
  floorHeight: number;
  walls: ModelWall[];
  pipes: ModelPipe[];
  scaled: boolean;       // false när bladet saknar skala: då är måtten ritningens punkter
  stats: { walls: number; pipes: number; metres: number };
};

/** Ytterdiameter i meter för en nominell dimension; okänd dimension får ett tunt rör. */
export function pipeRadius(dn: number | null): number {
  const dy: Record<number, number> = {
    10: 12, 12: 15, 15: 18, 16: 18, 20: 22, 22: 22, 25: 28, 28: 28, 32: 35, 35: 35, 40: 42, 42: 42,
    50: 54, 54: 54, 63: 63, 65: 76.1, 75: 75, 80: 88.9, 90: 90, 100: 114.3, 110: 110, 125: 139.7,
    140: 140, 160: 160, 200: 219.1,
  };
  if (dn == null) return 0.012;
  return ((dy[dn] ?? dn) / 1000) / 2;
}

/** Två segment som ligger parallellt och nära är en väggs två sidor; avståndet är väggens tjocklek. */
function wallThickness(seg: { x0: number; y0: number; x1: number; y1: number },
                       others: { x0: number; y0: number; x1: number; y1: number }[], mpp: number): number {
  const ax = seg.x1 - seg.x0, ay = seg.y1 - seg.y0;
  const len = Math.hypot(ax, ay) || 1;
  const nx = -ay / len, ny = ax / len;
  const mx = (seg.x0 + seg.x1) / 2, my = (seg.y0 + seg.y1) / 2;
  let best = 0;
  for (const o of others) {
    const bx = o.x1 - o.x0, by = o.y1 - o.y0;
    const bl = Math.hypot(bx, by) || 1;
    const cos = Math.abs((ax * bx + ay * by) / (len * bl));
    if (cos < 0.985) continue;                       // inte parallell
    const d = Math.abs((o.x0 - mx) * nx + (o.y0 - my) * ny);
    const along = Math.abs((o.x0 - mx) * (ax / len) + (o.y0 - my) * (ay / len));
    if (d > 1.5 && d < 40 && along < len) {          // 1,5-40 punkter isär: en vägg, inte ett rum
      if (!best || d < best) best = d;
    }
  }
  return best ? Math.min(0.6, best * mpp) : 0.1;
}

type Seg = { x0: number; y0: number; x1: number; y1: number };

type Family = {
  segments?: number[][] | number[][][];
  kind?: string;
  layer?: string;
  on_a_pipe_like_layer?: boolean;
  family?: string;
};

type Result = {
  scale?: { meters_per_pdf_point?: number | null } | null;
  page?: { width_pt?: number; height_pt?: number } | null;
  pipes?: any[];
  quantities?: any[];
  declined_geometry?: { families?: Family[]; unconsidered?: Family[] } | null;
  hatched_geometry?: { x0: number; y0: number; x1: number; y1: number; identity?: string }[] | null;
};

/* Vilket bläck som är byggnad och vilket som är installation.
 *
 * Läsningen säger själv vad den vägde: en familj den såg som sammanhängande linjer på ett lager som inte
 * liknar rörens är arkitektens och konstruktörens streck - väggar, bjälklag, pelare. Korta lösa streck är
 * skraffering, streckade hjälplinjer och text, och de blir inga väggar. Ingen ritning nämns vid namn här:
 * urvalet går på läsningens egna omdömen, så ett annat blad behandlas likadant.
 */
function isBuildingInk(f: Family): boolean {
  if (f.on_a_pipe_like_layer) return false;
  if (f.kind === "sparse" || f.kind === "fragmented-dashed") return false;
  return true;
}

/** Familjernas segment, oavsett om de kommer platta ([x0,y0,x1,y1]) eller som par av punkter. */
function segmentsOf(f: Family): Seg[] {
  const out: Seg[] = [];
  for (const s of (f.segments ?? []) as any[]) {
    if (!Array.isArray(s)) continue;
    if (typeof s[0] === "number" && s.length >= 4) {
      out.push({ x0: s[0], y0: s[1], x1: s[2], y1: s[3] });
    } else if (Array.isArray(s[0]) && s.length >= 2) {
      const a = s[0] as number[], b = s[s.length - 1] as number[];
      out.push({ x0: a[0], y0: a[1], x1: b[0], y1: b[1] });
    }
  }
  return out;
}

/* Skraffering är ingen vägg.
 *
 * En vägg ritas som två linjer med ett mönster emellan, och mönstret består av många streck som alla lutar
 * likadant. Reses de blir huset ett staket. Familjen avslöjar sig på just det: går nästan allt bläck i samma
 * riktning är det ett fyllnadsmönster, medan riktiga väggar går åt två håll - längs huset och tvärs över det.
 * Provet är på familjen och inte på ett enskilt streck, för ett streck kan inte veta vad det är del av.
 */
const HATCH_SHARE = 0.85;
const HATCH_MIN = 15;

export function isHatchFill(segs: Seg[]): boolean {
  if (segs.length < HATCH_MIN) return false;
  const bins = new Array(12).fill(0);
  for (const s of segs) {
    let a = Math.atan2(s.y1 - s.y0, s.x1 - s.x0);
    if (a < 0) a += Math.PI;                        // riktning, inte håll: 10° och 190° är samma lutning
    bins[Math.min(11, Math.floor((a / Math.PI) * 12))] += 1;
  }
  return Math.max(...bins) / segs.length >= HATCH_SHARE;
}

/** Rörets sträckor: läsningen lägger dem under `geometry`, en lista polylinjer per fysiskt rör. */
function polylinesOf(p: any): number[][][] {
  const raw = p?.geometry ?? p?.points ?? [];
  if (!Array.isArray(raw) || raw.length === 0) return [];
  // en enda polylinje kan komma oinslagen: [[x, y], [x, y], ...]
  if (Array.isArray(raw[0]) && typeof (raw[0] as any)[0] === "number") return [raw as number[][]];
  return raw as number[][][];
}

/**
 * Bygg modellen ur läsningens svar.
 *
 * `wallLimit` håller väggarna på ett antal som ritas snabbt även på ett stort blad; de längsta tas först, för
 * det är de som bär byggnadens form.
 */
export function buildModel(result: Result, opts: { floorHeight?: number; wallLimit?: number } = {}): BuildingModel {
  const mpp = result?.scale?.meters_per_pdf_point ?? 0;
  const scaled = !!mpp && mpp > 0;
  const k = scaled ? mpp : 1;                       // utan skala är en punkt en enhet
  const floorHeight = opts.floorHeight ?? 2.7;
  const wallLimit = opts.wallLimit ?? 1400;

  // ---- planområdet: den del av bladet som är byggnad ---------------------------------------------------
  // Ett blad är inte bara en plan. Där finns namnruta, förklaringslista, orienteringsfigur, logotyp och en ram
  // runt alltihop, och rest till väggar blir de skivor som står och lutar utanför huset. Installationen visar
  // var planen ligger: rören är ritade i byggnaden och ingen annanstans, så deras utbredning med marginal är
  // det område modellen bygger. Saknas rör byggs hela bladet - då finns inget bättre besked.
  let pminX = Infinity, pminY = Infinity, pmaxX = -Infinity, pmaxY = -Infinity;
  const seePipe = (x: number, y: number) => {
    if (x < pminX) pminX = x; if (y < pminY) pminY = y;
    if (x > pmaxX) pmaxX = x; if (y > pmaxY) pmaxY = y;
  };
  for (const p of result.pipes ?? []) {
    for (const poly of polylinesOf(p)) for (const pt of poly) if (pt?.length >= 2) seePipe(pt[0], pt[1]);
  }
  for (const h of result.hatched_geometry ?? []) { seePipe(h.x0, h.y0); seePipe(h.x1, h.y1); }
  const hasPipes = Number.isFinite(pminX) && pmaxX > pminX;
  const mgx = hasPipes ? (pmaxX - pminX) * 0.2 : 0;
  const mgy = hasPipes ? (pmaxY - pminY) * 0.2 : 0;
  const inPlan = (x: number, y: number) =>
    !hasPipes || (x >= pminX - mgx && x <= pmaxX + mgx && y >= pminY - mgy && y <= pmaxY + mgy);

  // En vägg kortare än en halv meter är ingen vägg: det är skraffering, en måttpil, en dörrslagning eller en
  // bokstav ritad med streck. De byggs inte, för de säger ingenting om huset och skymmer det som gör det.
  const minWall = scaled ? 0.5 / k : 20;

  // ---- utsträckning: det som byggs, så modellen hamnar centrerad ---------------------------------------
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  const see = (x: number, y: number) => {
    if (x < minX) minX = x; if (y < minY) minY = y;
    if (x > maxX) maxX = x; if (y > maxY) maxY = y;
  };
  for (const p of result.pipes ?? []) {
    for (const poly of polylinesOf(p)) for (const pt of poly) if (pt?.length >= 2) see(pt[0], pt[1]);
  }
  for (const h of result.hatched_geometry ?? []) { see(h.x0, h.y0); see(h.x1, h.y1); }
  const rawWalls: Seg[] = [];
  const families = [...(result.declined_geometry?.families ?? []), ...(result.declined_geometry?.unconsidered ?? [])];
  for (const f of families) {
    if (!isBuildingInk(f)) continue;
    const long = segmentsOf(f).filter((s) => Math.hypot(s.x1 - s.x0, s.y1 - s.y0) >= minWall
                                             && inPlan((s.x0 + s.x1) / 2, (s.y0 + s.y1) / 2));
    if (isHatchFill(long)) continue;
    for (const s of long) {
      rawWalls.push(s);
      see(s.x0, s.y0); see(s.x1, s.y1);
    }
  }
  if (!Number.isFinite(minX)) { minX = 0; minY = 0; maxX = 100; maxY = 100; }
  const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
  const to = (x: number, y: number): Vec2 => [(x - cx) * k, (cy - y) * k];   // y vänds: pappret ner, världen upp

  // ---- väggar: de längsta först, med tjocklek ur parvisa linjer ---------------------------------------
  const byLength = rawWalls
    .map((s) => ({ s, len: Math.hypot(s.x1 - s.x0, s.y1 - s.y0) }))
    .sort((a, b) => b.len - a.len)
    .slice(0, wallLimit);
  const neighbours = byLength.map((r) => r.s);
  const walls: ModelWall[] = byLength.map((r, i) => ({
    id: `w${i}`,
    a: to(r.s.x0, r.s.y0),
    b: to(r.s.x1, r.s.y1),
    thickness: wallThickness(r.s, neighbours, k),
    height: floorHeight,
  }));

  // ---- rör: läsningens egna sträckor, i sin egen grovlek ----------------------------------------------
  const qty = new Map<string, any>();
  for (const q of result.quantities ?? []) qty.set(q.designation, q);
  const pipes: ModelPipe[] = [];
  const push = (id: string, des: string, dn: number | null, poly: number[][], inWall = false, key = "") => {
    if (!poly || poly.length < 2) return;
    const path = poly.filter((pt) => Array.isArray(pt) && pt.length >= 2).map((pt) => to(pt[0], pt[1]));
    if (path.length < 2) return;
    let metres = 0;
    for (let i = 1; i < path.length; i++) metres += Math.hypot(path[i][0] - path[i - 1][0], path[i][1] - path[i - 1][1]);
    if (metres <= 0) return;
    pipes.push({
      id, designation: des, dn, system: (des.match(/^[A-ZÅÄÖ]+\d*/) ?? [""])[0],
      path, radius: scaled ? pipeRadius(dn) : 0.6,
      // stackarna hör till beteckningen och inte till varje sträcka; de delas ut nedan, på den längsta
      risers: 0,
      color: identityColor(key || des), meters: metres, inWall,
    });
  };
  for (const p of result.pipes ?? []) {
    const des: string = p.designation ?? (typeof p.identity === "string" ? p.identity : p.identity?.display) ?? "";
    const dn: number | null = p.dn ?? (typeof p.identity === "object" ? p.identity?.dn : null) ?? null;
    const key = typeof p.identity === "string" && p.identity ? p.identity : des;
    let n = 0;
    for (const poly of polylinesOf(p)) push(`${p.physical_pipe_id ?? p.id ?? pipes.length}-${n++}`, des, dn, poly, false, key);
  }
  // Bitarna som går genom en vägg är ritade rör som mängden räknar för sig; utan dem har varje rör hål där
  // väggarna står, och byggnaden ser ut att sakna installation just där den behöver den.
  const idDes = new Map<string, { des: string; dn: number | null }>();
  for (const p of result.pipes ?? []) {
    const key = typeof p.identity === "string" ? p.identity : "";
    if (key && !idDes.has(key)) idDes.set(key, { des: p.designation ?? "", dn: p.dn ?? null });
  }
  let h = 0;
  for (const seg of result.hatched_geometry ?? []) {
    const who = idDes.get(seg.identity ?? "") ?? { des: seg.identity ?? "", dn: null };
    push(`hatch-${h++}`, who.des, who.dn, [[seg.x0, seg.y0], [seg.x1, seg.y1]], true, seg.identity ?? who.des);
  }
  // stackarna: en per beteckning, på den längsta sträckan den beteckningen har
  const longest = new Map<string, ModelPipe>();
  for (const p of pipes) {
    if (p.inWall) continue;
    const cur = longest.get(p.designation);
    if (!cur || p.meters > cur.meters) longest.set(p.designation, p);
  }
  for (const [des, p] of longest) p.risers = Number(qty.get(des)?.riser_count ?? 0);

  const width = (maxX - minX) * k, depth = (maxY - minY) * k;
  return {
    size: { width: width || 1, depth: depth || 1 },
    floorHeight,
    walls,
    pipes,
    scaled,
    stats: { walls: walls.length, pipes: pipes.length, metres: Math.round(pipes.reduce((acc, p) => acc + p.meters, 0)) },
  };
}
