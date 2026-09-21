/* Ritningens eget bläck, läst ur PDF:en så att mängdningen kan fånga mot det.
 *
 * Bluebeams "snap to content" är inte en bekvämlighet. En sträcka mängdad på frihand följer inte röret utan
 * går bredvid det, och felet syns inte i något tal - det ser precis lika rakt ut. Fångar markören ritningens
 * egen linje mäts röret och inte handens darr, och en yta som ska sluta i ett hörn slutar i hörnet.
 *
 * Strecken läses ur sidans egen operatorlista, samma ström som ritar bilden. Det är den enda källan som finns
 * för varje PDF: en ritning som aldrig analyserats har ingen läsning att fråga, men den har sitt bläck.
 */
import type { Entity, Pt } from "./model";

type Mat = [number, number, number, number, number, number];

const mul = (a: Mat, b: Mat): Mat => [
  a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
  a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
  a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5],
];
const app = (m: Mat, x: number, y: number): Pt => [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]];

/** Hur mycket bläck som läses innan det får räcka: en A0-ritning har hundratusentals streck, och fångst
 *  behöver inte alla - den behöver de som ligger där pekaren är. Taket håller sidan svarande. */
const MAX_SEGS = 60000;

/**
 * Sidans streck i sidans egna punkter (samma koordinater som markeringar sparas i).
 *
 * Kurvor delas i korta räta bitar: en fångst mot en böjd vägg ska landa på väggen, inte på kordan.
 */
export async function pageInk(page: any): Promise<[Pt, Pt][]> {
  const ops = await page.getOperatorList();
  const { OPS } = await import("pdfjs-dist");
  const view = page.getViewport({ scale: 1, rotation: page.rotate });
  const base = view.transform as Mat;
  let ctm: Mat = [1, 0, 0, 1, 0, 0];
  const stack: Mat[] = [];
  const out: [Pt, Pt][] = [];
  let cur: Pt[] = [];
  let start: Pt | null = null;

  const flush = () => {
    for (let i = 1; i < cur.length; i++) out.push([cur[i - 1], cur[i]]);
    cur = [];
  };
  const P = (x: number, y: number): Pt => {
    const u = app(ctm, x, y);
    return app(base, u[0], u[1]);
  };

  for (let i = 0; i < ops.fnArray.length && out.length < MAX_SEGS; i++) {
    const fn = ops.fnArray[i];
    const args = ops.argsArray[i];
    if (fn === OPS.save) { stack.push(ctm); continue; }
    if (fn === OPS.restore) { ctm = stack.pop() ?? ctm; continue; }
    if (fn === OPS.transform) { ctm = mul(ctm, args as Mat); continue; }
    if (fn === OPS.constructPath) {
      // [operatorer, tal] - talen ligger i en enda ström och läses i den takt varje operator vill ha dem
      const [sub, nums] = args as [number[], number[]];
      let k = 0;
      for (const o of sub) {
        if (o === OPS.moveTo) { flush(); start = P(nums[k], nums[k + 1]); cur = [start]; k += 2; }
        else if (o === OPS.lineTo) { cur.push(P(nums[k], nums[k + 1])); k += 2; }
        else if (o === OPS.curveTo) {
          const p0 = cur[cur.length - 1] ?? P(nums[k], nums[k + 1]);
          const c1 = P(nums[k], nums[k + 1]), c2 = P(nums[k + 2], nums[k + 3]), p1 = P(nums[k + 4], nums[k + 5]);
          for (let t = 1; t <= 6; t++) {
            const u = t / 6, v = 1 - u;
            cur.push([v * v * v * p0[0] + 3 * v * v * u * c1[0] + 3 * v * u * u * c2[0] + u * u * u * p1[0],
                      v * v * v * p0[1] + 3 * v * v * u * c1[1] + 3 * v * u * u * c2[1] + u * u * u * p1[1]]);
          }
          k += 6;
        } else if (o === OPS.curveTo2 || o === OPS.curveTo3) {
          cur.push(P(nums[k + 2], nums[k + 3])); k += 4;
        } else if (o === OPS.closePath) { if (start) cur.push(start); }
        else if (o === OPS.rectangle) {
          const [x, y, w, h] = [nums[k], nums[k + 1], nums[k + 2], nums[k + 3]];
          flush();
          const r = [P(x, y), P(x + w, y), P(x + w, y + h), P(x, y + h)];
          out.push([r[0], r[1]], [r[1], r[2]], [r[2], r[3]], [r[3], r[0]]);
          k += 4;
        }
      }
      flush();
      continue;
    }
  }
  flush();
  // nollstreck bär ingen riktning och ger ingen fångst
  return out.filter(([a, b]) => Math.abs(a[0] - b[0]) > 0.01 || Math.abs(a[1] - b[1]) > 0.01);
}

/** Strecken som ritobjekt, så att samma fångstkod som i CAD kan användas på dem. */
export function inkEntities(segs: [Pt, Pt][]): Entity[] {
  return segs.map((s, i) => ({ id: `ink${i}`, type: "line" as const, layer: "ink", p: [s[0], s[1]] }));
}

/**
 * Ett rutnät över bläcket, så att fångst kostar lika lite på ett blad med tvåhundratusen streck som på ett
 * med tio. Utan det söks hela sidan igenom vid varje musrörelse, och handen känner det.
 */
export class InkIndex {
  private cell: number;
  private grid = new Map<string, number[]>();
  readonly segs: [Pt, Pt][];

  constructor(segs: [Pt, Pt][], cell = 40) {
    this.segs = segs;
    this.cell = cell;
    segs.forEach((s, i) => {
      const x0 = Math.min(s[0][0], s[1][0]), x1 = Math.max(s[0][0], s[1][0]);
      const y0 = Math.min(s[0][1], s[1][1]), y1 = Math.max(s[0][1], s[1][1]);
      // ett långt streck ligger i många rutor; det ska hittas från var och en av dem
      for (let x = Math.floor(x0 / cell); x <= Math.floor(x1 / cell); x++)
        for (let y = Math.floor(y0 / cell); y <= Math.floor(y1 / cell); y++) {
          const k = `${x}:${y}`;
          const a = this.grid.get(k);
          if (a) a.push(i); else this.grid.set(k, [i]);
        }
    });
  }

  near(p: Pt, r: number): [Pt, Pt][] {
    const out: [Pt, Pt][] = [];
    const seen = new Set<number>();
    for (let x = Math.floor((p[0] - r) / this.cell); x <= Math.floor((p[0] + r) / this.cell); x++)
      for (let y = Math.floor((p[1] - r) / this.cell); y <= Math.floor((p[1] + r) / this.cell); y++)
        for (const i of this.grid.get(`${x}:${y}`) ?? []) {
          if (seen.has(i)) continue;
          seen.add(i); out.push(this.segs[i]);
        }
    return out;
  }
}
