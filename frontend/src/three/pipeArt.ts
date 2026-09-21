import * as THREE from "three";

/* Hur ett rör ser ut, och var det går.
 *
 * Två saker skiljer en modell som ser ut som ett rör från en som bara är ett färgat streck i rymden, och båda
 * är lika mycket noggrannhet som utseende:
 *
 *   * **Böjen.** Ett rör går rakt och böjer i hörnet; det slingrar sig inte. Den förra kurvan lades som en
 *     Catmull-Rom genom alla punkter, och en sådan lämnar den räta linjen redan innan hörnet - röret hamnade
 *     bredvid det streck ritningen dragit. Här är varje rak sträcka exakt rak ända in i böjen, och böjen är
 *     en riktig böj med en radie som en rörböj har. Då ligger modellen på ritningens geometri i stället för
 *     nära den.
 *   * **Materialet.** Koppar, stål, plast och isolering ser olika ut i verkligheten, och ögat läser skillnaden
 *     fortare än det läser en text. Mediet gissas ur systembokstäverna - det är en tolkning och inget bladet
 *     säger, så panelen skriver ut vilken klass som antagits. Färgen är alltid beteckningens egen; det är bara
 *     ytan som byter, så regeln att en beteckning har en färg står kvar.
 */

export type Medium = "koppar" | "isolerat" | "stål" | "plast" | "okänt";

/** Vad rörets systembokstäver säger om vad det är gjort av. En gissning, och den redovisas som en gissning. */
export function mediumOf(system: string): Medium {
  const s = (system || "").toUpperCase();
  if (/^V[VS]|^KB|^VP/.test(s)) return "isolerat";     // varmvatten, värme, köldbärare: isolerade
  if (/^KV/.test(s)) return "koppar";                  // kallvatten
  if (/^SP|^SK/.test(s)) return "stål";                // sprinkler
  if (/^S|^D|^BD|^LD|^TA/.test(s)) return "plast";     // spill, dag, avlopp
  return "okänt";
}

export const MEDIUM_TEXT: Record<Medium, string> = {
  koppar: "koppar",
  isolerat: "isolerat rör",
  stål: "stål",
  plast: "plast",
  okänt: "okänt material",
};

/** Isoleringens tjocklek på ett rör av den här grovleken. Tunna rör får tunn isolering, grova får tjockare. */
export function jacketThickness(radius: number): number {
  return Math.min(0.05, Math.max(0.018, radius * 0.9));
}

/* Ett DN16-rör är åtta millimeter i radie. På ett trettio meter brett hus är det ett hårstrå som försvinner,
 * så det som är för tunt för att se ritas grövre. Det gamla sättet var ett golv - allt under gränsen blev
 * exakt lika grovt, och DN20 såg ut som DN110. Här trycks skalan ihop i stället för att klippas: ordningen
 * mellan grovlekarna står kvar hela vägen ned, och inget rör blir grövre än gränsen. */
export function readableRadius(real: number, floor: number): number {
  if (!(real > 0)) return floor * 0.55;
  if (real >= floor) return real;
  return floor * (0.55 + 0.45 * Math.sqrt(real / floor));
}

/** Två punkter som ligger på varandra är inte en sträcka. */
function dedupe(points: THREE.Vector3[]): THREE.Vector3[] {
  const out: THREE.Vector3[] = [];
  for (const p of points) {
    if (!out.length || out[out.length - 1].distanceTo(p) > 1e-6) out.push(p.clone());
  }
  return out;
}

/**
 * Rörets väg: raka sträckor med riktiga böjar i hörnen.
 *
 * Böjen läggs som en kvadratisk bézier mellan de två tangentpunkterna med hörnet som styrpunkt. En sådan är
 * tangent till båda raksträckorna i sina ändar, vilket är just det en rörböj är, och den kan aldrig gå utanför
 * hörnet. Böjradien klipps mot halva den kortaste angränsande sträckan, så två hörn nära varandra aldrig äter
 * upp sträckan mellan sig.
 */
export function pipeCurve(points: THREE.Vector3[], bend: number):
  { curve: THREE.CurvePath<THREE.Vector3>; bends: number } {
  const path = new THREE.CurvePath<THREE.Vector3>();
  const p = dedupe(points);
  if (p.length < 2) return { curve: path, bends: 0 };
  const last = p[p.length - 1];
  let from = p[0].clone();
  let bends = 0;
  for (let i = 1; i < p.length - 1; i++) {
    const c = p[i];
    const va = new THREE.Vector3().subVectors(p[i - 1], c);
    const vb = new THREE.Vector3().subVectors(p[i + 1], c);
    const la = va.length(), lb = vb.length();
    if (la < 1e-6 || lb < 1e-6) continue;
    const cos = va.dot(vb) / (la * lb);
    if (cos < -0.9995) continue;    // rakt fram: inget hörn att böja
    if (cos > 0.9995) continue;     // rakt tillbaka: en böj som inte går att lägga
    const d = Math.min(bend, la / 2, lb / 2);
    const a = c.clone().addScaledVector(va.divideScalar(la), d);
    const b = c.clone().addScaledVector(vb.divideScalar(lb), d);
    if (from.distanceTo(a) > 1e-7) path.add(new THREE.LineCurve3(from, a));
    path.add(new THREE.QuadraticBezierCurve3(a, c.clone(), b));
    from = b;
    bends++;
  }
  if (from.distanceTo(last) > 1e-7) path.add(new THREE.LineCurve3(from, last.clone()));
  if (!path.curves.length) path.add(new THREE.LineCurve3(p[0].clone(), last.clone()));
  return { curve: path, bends };
}

/** Rörets yta. Färgen är beteckningens; mediet bestämmer bara hur ytan tar ljuset. */
export function pipeMaterial(color: string, medium: Medium, inWall = false): THREE.MeshPhysicalMaterial {
  if (inWall) {
    // biten som går genom en vägg är inte blank - den är ingjuten, och ska läsas som en annan sorts sträcka
    return new THREE.MeshPhysicalMaterial({ color, metalness: 0.0, roughness: 0.95 });
  }
  switch (medium) {
    // En helt metallisk yta har ingen egen diffus färg - allt den visar är det den speglar - och en sådan
    // koppar blev nästan vit mot en ljus omgivning. Beteckningens färg är det som säger vilket rör man ser,
    // så metallen får vara nästan metall: blank och speglande, men med färgen kvar.
    case "koppar": return new THREE.MeshPhysicalMaterial({ color, metalness: 0.72, roughness: 0.22 });
    case "stål": return new THREE.MeshPhysicalMaterial({ color, metalness: 0.68, roughness: 0.4 });
    case "plast": return new THREE.MeshPhysicalMaterial({
      color, metalness: 0.0, roughness: 0.5, clearcoat: 0.5, clearcoatRoughness: 0.3,
    });
    case "isolerat": return new THREE.MeshPhysicalMaterial({ color, metalness: 0.7, roughness: 0.3 });
    default: return new THREE.MeshPhysicalMaterial({ color, metalness: 0.45, roughness: 0.4 });
  }
}

/** Isoleringens mantel: matt och ljus, med systemets färg kvar som en svag ton. */
export function jacketMaterial(color: string): THREE.MeshPhysicalMaterial {
  const c = new THREE.Color(color).lerp(new THREE.Color("#efe9df"), 0.8);
  return new THREE.MeshPhysicalMaterial({
    color: c, metalness: 0.0, roughness: 0.9,
    sheen: 0.5, sheenColor: new THREE.Color("#ffffff"), sheenRoughness: 0.8,
  });
}

/** Kopplingen i böjen: en kort hylsa som är något grövre än röret. Det är den man ser på ett riktigt rör. */
export function couplingMaterial(color: string, medium: Medium): THREE.MeshPhysicalMaterial {
  const c = new THREE.Color(color).lerp(new THREE.Color("#0b0d10"), 0.22);
  return medium === "plast"
    ? new THREE.MeshPhysicalMaterial({ color: c, metalness: 0.0, roughness: 0.42, clearcoat: 0.4 })
    : new THREE.MeshPhysicalMaterial({ color: c, metalness: 1.0, roughness: 0.3 });
}

/**
 * Var i höjdled ett system ligger.
 *
 * Bladet säger ingenting om höjd - det är en plan. Lägger man då alla rör i samma plan lägger sig korsande
 * rör i varandra och bilden blir en enda matta. Systemen läggs därför i band, ett band per system, i
 * bokstavsordning så att samma ritning alltid ger samma bild. Det är en läsbarhetsordning och ingen mätning,
 * och panelen säger det rakt ut.
 */
export function bandOf(system: string, systems: string[], floorHeight: number): number {
  const order = [...new Set(systems)].sort();
  const i = Math.max(0, order.indexOf(system));
  const n = Math.max(1, order.length);
  const lo = floorHeight * 0.62, hi = floorHeight * 0.88;
  return n === 1 ? floorHeight * 0.82 : lo + ((hi - lo) * i) / (n - 1);
}
