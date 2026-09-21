/* Byggmodellen: en gemensam objektmodell för hela byggnaden, i millimeter.
 *
 * Det som ritas i planen och det som syns i 3D är samma objekt. En vägg är inte fyra linjer utan en Wall med
 * tjocklek, höjd, material och nivåer; planen ritar dess fotavtryck, modellen dess volym, sektionen dess snitt,
 * mängden dess yta - alla ur samma fält. Därför finns här ingen "3D-kopia" av något: allt som visas är härlett,
 * och det enda som sparas är objekten själva.
 *
 * Tre saker gäller för varje objekt: det har en stabil identitet, det vet varifrån det kom (ritat, importerat,
 * hittat i en PDF, skapat av agenten och godkänt), och det bär sin nivå. Nivåerna är byggnadens egna - ingen
 * våningshöjd hittas på; den som skapar Level 1 säger var den ligger.
 *
 * Måtten är millimeter i byggets koordinater. Ingenting här beror på skärmen. */

export type Pt = [number, number];
export type Pt3 = [number, number, number];

export const MODEL_VERSION = 2;

export type Discipline = "ARK" | "KONSTR" | "VVS" | "VENT" | "EL" | "SPRINKLER" | "BRAND" | "MARK" | "UTRUSTNING" | "ALLMAN";
export const DISCIPLINES: { id: Discipline; label: string }[] = [
  { id: "ARK", label: "Arkitektur" }, { id: "KONSTR", label: "Konstruktion" }, { id: "VVS", label: "VVS" },
  { id: "VENT", label: "Ventilation" }, { id: "EL", label: "El" }, { id: "SPRINKLER", label: "Sprinkler" },
  { id: "BRAND", label: "Brand" }, { id: "MARK", label: "Mark" }, { id: "UTRUSTNING", label: "Utrustning" },
  { id: "ALLMAN", label: "Allmän CAD" },
];

export type Provenance = "USER_MODELLED" | "IMPORTED_IFC" | "IMPORTED_DXF" | "DETECTED_FROM_PDF" | "AGENT_CREATED_APPROVED" | "USER_CORRECTED";
export type Phase = "EXISTING" | "NEW" | "DEMOLISH";

export type Level = { id: string; name: string; elevation_mm: number };
export type GridLine = { id: string; label: string; p: [Pt, Pt] };
export type Layer = { id: string; name: string; color: string; visible: boolean; locked: boolean; width: number; discipline?: Discipline };
export type Material = { id: string; name: string; category: string; color: string; density_kg_m3?: number | null };

export type Profile =
  | { kind: "rect"; w: number; d: number }
  | { kind: "circle"; d: number }
  | { kind: "I" | "H" | "U" | "L" | "RHS" | "SHS"; w: number; d: number; t: number; name?: string };

/** Det varje objekt bär, vad det än är. */
export type Common = {
  id: string;
  layer: string;
  discipline: Discipline;
  level?: string;                  // nivån objektet hör till, där det har en
  phase: Phase;
  provenance: Provenance;
  version: number;                 // räknas upp för varje ändring - grunden för samtidighet senare
  updated_at?: string;
  user?: string;
  name?: string;
  material?: string;               // material-id
  props?: Record<string, string | number | boolean | null>;
};

// ---------------------------------------------------------------- allmän CAD

export type Line = Common & { type: "line"; p: [Pt, Pt] };
export type Polyline = Common & { type: "polyline"; p: Pt[]; closed?: boolean };
export type Rect = Common & { type: "rect"; p: [Pt, Pt] };
export type Circle = Common & { type: "circle"; p: [Pt]; r: number };
export type Arc = Common & { type: "arc"; p: [Pt]; r: number; a0: number; a1: number };
export type Ellipse = Common & { type: "ellipse"; p: [Pt]; rx: number; ry: number; rot?: number };
export type Spline = Common & { type: "spline"; p: Pt[]; closed?: boolean };          // Catmull-Rom genom punkterna
export type TagField = "name" | "number" | "area" | "length" | "system" | "dn" | "level" | "id";
/** En text kan hänga på ett objekt: då visar den objektets fält och följer det när det ändras. */
export type Text = Common & { type: "text"; p: [Pt]; text: string; h: number; rot?: number; ref?: { id: string; field: TagField } | null };
export type MText = Common & { type: "mtext"; p: [Pt]; text: string; h: number; w: number; rot?: number };
export type DimKind = "linear" | "aligned" | "angular" | "radius" | "diameter";
export type Dimension = Common & {
  type: "dim"; kind: DimKind; p: Pt[]; off: number;
  refs?: { id: string; grip?: number }[];   // objekt måttet hänger på: flyttas objektet följer måttet
};
export type Leader = Common & { type: "leader"; p: Pt[]; text: string; h?: number };
export type Hatch = Common & { type: "hatch"; p: Pt[]; pattern: string; spacing?: number; angle?: number };
export type BlockDef = { id: string; name: string; category: string; entities: Entity[]; origin: Pt; size_mm?: [number, number, number] };
export type BlockRef = Common & { type: "block"; def: string; p: [Pt]; rot?: number; scale?: number };

// ---------------------------------------------------------------- byggobjekt: arkitektur

export type Wall = Common & {
  type: "wall"; p: [Pt, Pt];         // centrumlinjen, från a till b
  thickness: number; base_level: string; top_level?: string | null; height?: number | null;
  base_offset?: number; top_offset?: number;
  wall_type?: string; alignment?: "centre" | "left" | "right";
  fire_rating?: string; sound_rating?: string; structural?: boolean;
  curve?: { bulge: number } | null;  // krökt vägg: bulge = 2·pilhöjd/korda, som i DXF
};
export type CurtainWall = Omit<Wall, "type"> & { type: "curtain_wall"; mullion_spacing?: number };
/** Något som sitter i en vägg: läget är en andel längs väggen, så att det följer med när väggen flyttas. */
export type Hosted = Common & { host: string; t: number; width: number; height: number; sill?: number };
export type Door = Hosted & { type: "door"; swing?: "left" | "right" | "double" | "sliding"; fire_rating?: string; door_type?: string };
export type Window = Hosted & { type: "window"; window_type?: string };
export type Opening = Hosted & { type: "opening"; host_kind?: "wall" | "slab" | "roof" | "ceiling"; boundary?: Pt[] };
export type Floor = Common & { type: "floor"; p: Pt[]; thickness: number; offset?: number; structural?: boolean; holes?: Pt[][] };
export type Roof = Common & {
  type: "roof"; p: Pt[]; kind: "flat" | "pitched"; thickness: number; offset?: number;
  slope_deg?: number; ridge?: [Pt, Pt] | null; overhang?: number;
};
export type Ceiling = Common & { type: "ceiling"; p: Pt[]; height_offset: number; thickness: number };
export type Room = Common & { type: "room"; p: Pt[]; number?: string; use?: string; height?: number | null; finish?: Record<string, string> };
export type Stair = Common & {
  type: "stair"; kind: "straight" | "L" | "U"; p: [Pt, Pt]; base_level: string; top_level: string;
  width: number; risers: number; riser_h?: number | null; tread_d: number; landing?: number;
};
export type Railing = Common & { type: "railing"; p: Pt[]; height: number; host?: string | null; spacing?: number; railing_type?: string };

// ---------------------------------------------------------------- byggobjekt: konstruktion

export type Column = Common & { type: "column"; p: [Pt]; profile: Profile; base_level: string; top_level?: string | null; height?: number | null; rot?: number; base_offset?: number; top_offset?: number; grid?: [string, string] | null };
export type Beam = Common & { type: "beam"; p: [Pt, Pt]; profile: Profile; elevation_offset?: number; rot?: number; supports?: string[] };
export type Foundation = Common & { type: "foundation"; kind: "isolated" | "strip" | "slab"; p: Pt[]; w?: number; d?: number; h: number; offset?: number };
export type Truss = Common & { type: "truss"; p: [Pt, Pt]; height: number; bays: number; profile: Profile };

// ---------------------------------------------------------------- MEP: en gemensam väg med disciplinens egna fält ovanpå

export type Connector = { id: string; name: string; kind: string; at: Pt3; dir?: Pt3 };
export type PathBase = Common & { path: Pt3[]; system: string; elevation?: number };
export type Pipe = PathBase & { type: "pipe"; dn: number; designation?: string; insulation?: number };
export type Duct = PathBase & { type: "duct"; shape: "rect" | "round"; w?: number; h?: number; d?: number };
export type CableTray = PathBase & { type: "cable_tray"; w: number; h: number };
export type Conduit = PathBase & { type: "conduit"; d: number };
export type Fitting = Common & { type: "fitting"; kind: "elbow" | "tee" | "reducer" | "valve" | "damper" | "transition" | "cap" | "other"; p: [Pt3]; host?: string | null; dn?: number; system?: string; rot?: number };
export type Equipment = Common & { type: "equipment"; kind: string; p: [Pt3]; size: Pt3; rot?: number; system?: string; connectors: Connector[] };
export type Device = Common & { type: "device"; kind: "light" | "outlet" | "switch" | "panel" | "air_terminal" | "sprinkler_head" | "sensor" | "other"; p: [Pt3]; rot?: number; system?: string; host?: string | null };

// ---------------------------------------------------------------- mark

export type Terrain = Common & { type: "terrain"; points: Pt3[] };

// ---------------------------------------------------------------- underlag och referenser: bilder att rita mot, aldrig modell

/** En PDF-sida eller bild bakom planen. Skalan är verifierad (ur en läst handling), uppmätt, eller saknas - och då är underlaget en bild man tittar på, inte något man fångar mått i. */
export type Underlay = Common & {
  type: "underlay"; p: [Pt]; asset: string; px: [number, number]; mm_per_px: number | null; rot?: number; opacity?: number;
  scale_state: "VERIFIED" | "CALIBRATED" | "UNCALIBRATED"; source?: Record<string, any> | null;
};
/** Ett 3D-nät från en fil (GLB/GLTF/OBJ/STL) som referens i modellen: placeras, skalas, syns - men mängdas inte. */
export type MeshRef = Common & { type: "mesh"; p: [Pt3]; asset: string; format: "glb" | "gltf" | "obj" | "stl"; scale: number; rot?: number; bounds?: { min: Pt3; max: Pt3 } | null; filename?: string };
export type SiteObject = Common & { type: "site"; kind: "site_boundary" | "property_boundary" | "road" | "path" | "footprint" | "spot" | "other"; p: Pt[]; z?: number | null; closed?: boolean };

export type Entity =
  | Line | Polyline | Rect | Circle | Arc | Ellipse | Spline | Text | MText | Dimension | Leader | Hatch | BlockRef
  | Wall | CurtainWall | Door | Window | Opening | Floor | Roof | Ceiling | Room | Stair | Railing
  | Column | Beam | Foundation | Truss
  | Pipe | Duct | CableTray | Conduit | Fitting | Equipment | Device
  | Terrain | SiteObject
  | Underlay | MeshRef;
export type EntityType = Entity["type"];

export const BUILDING_TYPES: EntityType[] = ["wall", "curtain_wall", "door", "window", "opening", "floor", "roof", "ceiling", "room", "stair", "railing",
  "column", "beam", "foundation", "truss", "pipe", "duct", "cable_tray", "conduit", "fitting", "equipment", "device", "terrain", "site"];
export const GENERIC_TYPES: EntityType[] = ["line", "polyline", "rect", "circle", "arc", "ellipse", "spline", "text", "mtext", "dim", "leader", "hatch", "block", "underlay", "mesh"];
export const MEP_PATH_TYPES: EntityType[] = ["pipe", "duct", "cable_tray", "conduit"];

// ---------------------------------------------------------------- vyer och blad

export type ViewKind = "plan" | "ceiling" | "3d" | "section" | "elevation" | "detail";
export type View = {
  id: string; kind: ViewKind; name: string;
  level?: string | null;                       // plan, undertak
  line?: [Pt, Pt] | null; depth?: number;      // sektion: snittlinjen och hur långt in man ser
  dir?: "N" | "S" | "E" | "W" | number | null; // fasad
  disciplines?: Discipline[] | null;           // null = alla
  hidden?: string[]; isolate?: string[] | null;
  scale_ratio?: number;
  camera?: { pos: Pt3; target: Pt3; ortho?: boolean } | null;
  transparency?: Partial<Record<Discipline, number>>;
  section_box?: { min: Pt3; max: Pt3 } | null;
  phase_filter?: Phase[] | null;
};
export type Viewport = { id: string; view: string; at: Pt; size: Pt; scale_ratio: number; title?: string };
export type Sheet = {
  id: string; name: string; paper: string; width_mm: number; height_mm: number;
  title: { number: string; name: string; project: string; revision: string; date: string; drawn_by?: string; scale?: string };
  viewports: Viewport[];
};

// ---------------------------------------------------------------- dokumentet

export type Constraint =
  | { kind: "grid"; entity: string; grip: number; grid: string }
  | { kind: "level_top"; entity: string; level: string }
  | { kind: "host"; entity: string; host: string }
  | { kind: "support"; entity: string; support: string };

export type CadDocument = {
  version: 2;
  units: "mm";
  project: { name: string; number?: string };
  site: { name?: string; origin?: { east: number; north: number; elevation: number; epsg?: string } | null };
  building: { name: string };
  levels: Level[];
  grids: GridLine[];
  layers: Layer[];
  materials: Material[];
  blocks: BlockDef[];
  entities: Entity[];
  views: View[];
  sheets: Sheet[];
  constraints: Constraint[];
  settings: { grid_mm: number; snap: boolean; ortho: number; discipline: Discipline; active_level: string; active_view: string };
  revision: number;
};

export const uid = () => Math.random().toString(36).slice(2, 10) + Math.random().toString(36).slice(2, 6);

export const DEFAULT_MATERIALS: Material[] = [
  { id: "m_concrete", name: "Betong C30/37", category: "Betong", color: "#b8bcc2", density_kg_m3: 2400 },
  { id: "m_steel", name: "Stål S355", category: "Stål", color: "#6b7280", density_kg_m3: 7850 },
  { id: "m_wood", name: "Trä C24", category: "Trä", color: "#c8a165", density_kg_m3: 420 },
  { id: "m_brick", name: "Tegel", category: "Murverk", color: "#a5533a", density_kg_m3: 1800 },
  { id: "m_gypsum", name: "Gips", category: "Skivor", color: "#e6e2d6", density_kg_m3: 800 },
  { id: "m_glass", name: "Glas", category: "Glas", color: "#9fd3e8", density_kg_m3: 2500 },
  { id: "m_insulation", name: "Mineralull", category: "Isolering", color: "#e9d98a", density_kg_m3: 30 },
  { id: "m_copper", name: "Koppar", category: "Metall", color: "#b87333", density_kg_m3: 8960 },
  { id: "m_plastic", name: "PP/PE", category: "Plast", color: "#7aa6c2", density_kg_m3: null },
];

export const DEFAULT_LAYERS: Layer[] = [
  { id: "l_ark", name: "Arkitektur", color: "#111111", visible: true, locked: false, width: 0.35, discipline: "ARK" },
  { id: "l_konstr", name: "Konstruktion", color: "#7048e8", visible: true, locked: false, width: 0.5, discipline: "KONSTR" },
  { id: "l_vvs", name: "VVS", color: "#1f6feb", visible: true, locked: false, width: 0.35, discipline: "VVS" },
  { id: "l_vent", name: "Ventilation", color: "#0b7285", visible: true, locked: false, width: 0.35, discipline: "VENT" },
  { id: "l_el", name: "El", color: "#b58900", visible: true, locked: false, width: 0.25, discipline: "EL" },
  { id: "l_sprinkler", name: "Sprinkler", color: "#c0392b", visible: true, locked: false, width: 0.25, discipline: "SPRINKLER" },
  { id: "l_mark", name: "Mark", color: "#2f9e44", visible: true, locked: false, width: 0.25, discipline: "MARK" },
  { id: "l_annot", name: "Text och mått", color: "#444444", visible: true, locked: false, width: 0.18, discipline: "ALLMAN" },
];

export function newDocument(projectName = "Nytt projekt"): CadDocument {
  const l0: Level = { id: "lv_0", name: "Plan 0", elevation_mm: 0 };
  const plan: View = { id: "v_plan0", kind: "plan", name: "Plan 0", level: l0.id, scale_ratio: 100 };
  const three: View = { id: "v_3d", kind: "3d", name: "3D", camera: null };
  return {
    version: 2, units: "mm",
    project: { name: projectName }, site: { origin: null }, building: { name: "Byggnad A" },
    levels: [l0], grids: [], layers: DEFAULT_LAYERS.map((l) => ({ ...l })), materials: DEFAULT_MATERIALS.map((m) => ({ ...m })),
    blocks: [], entities: [], views: [plan, three], sheets: [], constraints: [],
    settings: { grid_mm: 100, snap: true, ortho: 0, discipline: "ARK", active_level: l0.id, active_view: plan.id },
    revision: 0,
  };
}

/** Ett blad från det äldre ritbordet (version 1) blir ett dokument: samma objekt, nu med nivå och disciplin. */
export function migrate(content: any, meta?: { name?: string; scale_ratio?: number }): CadDocument {
  if (content && content.version === 2 && Array.isArray(content.levels)) return content as CadDocument;
  const doc = newDocument(meta?.name || "Ritning");
  if (meta?.scale_ratio) doc.views[0].scale_ratio = meta.scale_ratio;
  const layers: Layer[] = (content?.layers || []).map((l: any) => ({
    id: String(l.id), name: String(l.name || "Lager"), color: String(l.color || "#111111"), visible: l.visible !== false,
    locked: !!l.locked, width: Number(l.width || 0.35), discipline: "ALLMAN" as Discipline,
  }));
  if (layers.length) doc.layers = [...layers, ...doc.layers.filter((d) => !layers.some((l) => l.id === d.id))];
  const base = (e: any): Common => ({
    id: String(e.id || uid()), layer: String(e.layer || layers[0]?.id || "l_ark"), discipline: e.type === "pipe" ? "VVS" : "ALLMAN",
    level: doc.levels[0].id, phase: "NEW", provenance: "USER_MODELLED", version: 1,
  });
  for (const e of content?.entities || []) {
    const p = (e.p || []).map((q: any) => [Number(q[0]), Number(q[1])] as Pt);
    switch (e.type) {
      case "line": if (p.length >= 2) doc.entities.push({ ...base(e), type: "line", p: [p[0], p[1]] }); break;
      case "polyline": if (p.length >= 2) doc.entities.push({ ...base(e), type: "polyline", p, closed: !!e.closed }); break;
      case "rect": if (p.length >= 2) doc.entities.push({ ...base(e), type: "rect", p: [p[0], p[1]] }); break;
      case "circle": if (p.length >= 1) doc.entities.push({ ...base(e), type: "circle", p: [p[0]], r: Number(e.r || 0) }); break;
      case "arc": if (p.length >= 1) doc.entities.push({ ...base(e), type: "arc", p: [p[0]], r: Number(e.r || 0), a0: Number(e.a0 || 0), a1: Number(e.a1 || 0) }); break;
      case "text": if (p.length >= 1) doc.entities.push({ ...base(e), type: "text", p: [p[0]], text: String(e.text || ""), h: Number(e.h || 2.5) }); break;
      case "dim": if (p.length >= 2) doc.entities.push({ ...base(e), type: "dim", kind: "aligned", p, off: Number(e.off || 0) }); break;
      case "pipe": if (p.length >= 2) doc.entities.push({ ...base(e), type: "pipe", path: p.map((q: Pt) => [q[0], q[1], 0] as Pt3), system: String(e.system || ""), dn: Number(e.dn || 0), designation: e.designation ? String(e.designation) : undefined }); break;
      default: break;
    }
  }
  return doc;
}

// ---------------------------------------------------------------- uppslag

export function levelOf(doc: CadDocument, id: string | null | undefined): Level | undefined {
  return doc.levels.find((l) => l.id === id);
}
export function elevation(doc: CadDocument, id: string | null | undefined, fallback = 0): number {
  return levelOf(doc, id)?.elevation_mm ?? fallback;
}
/** Nivån ovanför en nivå - den en vägg utan angiven topp går upp till. */
export function levelAbove(doc: CadDocument, id: string): Level | undefined {
  const me = levelOf(doc, id);
  if (!me) return undefined;
  return [...doc.levels].filter((l) => l.elevation_mm > me.elevation_mm).sort((a, b) => a.elevation_mm - b.elevation_mm)[0];
}
export function entity<T extends Entity = Entity>(doc: CadDocument, id: string): T | undefined {
  return doc.entities.find((e) => e.id === id) as T | undefined;
}

/** Underkant och överkant i mm för ett objekt som spänner mellan nivåer (vägg, pelare). */
export function verticalExtent(doc: CadDocument, e: Wall | CurtainWall | Column): { z0: number; z1: number } {
  const z0 = elevation(doc, e.base_level) + (e.base_offset ?? 0);
  let z1: number;
  if (e.top_level) z1 = elevation(doc, e.top_level) + (e.top_offset ?? 0);
  else if (e.height != null) z1 = z0 + e.height;
  else {
    const above = levelAbove(doc, e.base_level);
    z1 = above ? above.elevation_mm + (e.top_offset ?? 0) : z0 + 3000;   // sista nivån utan topp: en våning
  }
  return { z0, z1 };
}
export function heightOf(doc: CadDocument, e: Wall | CurtainWall | Column): number {
  const { z0, z1 } = verticalExtent(doc, e);
  return Math.max(0, z1 - z0);
}

export const dist = (a: Pt, b: Pt) => Math.hypot(b[0] - a[0], b[1] - a[1]);
export const wallLength = (w: Wall | CurtainWall) => dist(w.p[0], w.p[1]);
/** Punkten på väggens centrumlinje vid andelen t, och riktningen där. */
export function alongWall(w: Wall | CurtainWall, t: number): { p: Pt; dir: Pt; n: Pt } {
  const [a, b] = w.p;
  const L = wallLength(w) || 1;
  const dir: Pt = [(b[0] - a[0]) / L, (b[1] - a[1]) / L];
  return { p: [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t], dir, n: [-dir[1], dir[0]] };
}

/** Objekt som sitter i ett värdobjekt: dörrar, fönster och öppningar i en vägg. */
export function hostedIn(doc: CadDocument, hostId: string): (Door | Window | Opening)[] {
  return doc.entities.filter((e) => (e.type === "door" || e.type === "window" || e.type === "opening") && e.host === hostId) as (Door | Window | Opening)[];
}

export type Relation = { kind: "HOSTED_BY" | "BASE_LEVEL" | "TOP_LEVEL" | "ON_LEVEL" | "SUPPORTED_BY" | "CONNECTS_TO" | "BOUNDED_BY" | "ATTACHED_TO_GRID"; from: string; to: string };
/** Relationerna, härledda ur objektens egna fält - aldrig en andra sanning bredvid dem. */
export function relations(doc: CadDocument): Relation[] {
  const out: Relation[] = [];
  for (const e of doc.entities) {
    if ("host" in e && e.host) out.push({ kind: "HOSTED_BY", from: e.id, to: e.host });
    if ("base_level" in e && e.base_level) out.push({ kind: "BASE_LEVEL", from: e.id, to: e.base_level });
    if ("top_level" in e && e.top_level) out.push({ kind: "TOP_LEVEL", from: e.id, to: e.top_level });
    if (e.level && !("base_level" in e)) out.push({ kind: "ON_LEVEL", from: e.id, to: e.level });
    if (e.type === "beam") for (const s of e.supports || []) out.push({ kind: "SUPPORTED_BY", from: e.id, to: s });
    if (e.type === "column" && e.grid) out.push({ kind: "ATTACHED_TO_GRID", from: e.id, to: `${e.grid[0]}/${e.grid[1]}` });
  }
  for (const c of doc.constraints) {
    if (c.kind === "grid") out.push({ kind: "ATTACHED_TO_GRID", from: c.entity, to: c.grid });
    if (c.kind === "support") out.push({ kind: "SUPPORTED_BY", from: c.entity, to: c.support });
  }
  for (const c of connections(doc)) out.push({ kind: "CONNECTS_TO", from: c.from, to: c.to });
  return out;
}

/** En anslutnings läge i byggets koordinater: utrustningens punkt plus anslutningens förskjutning, vriden med utrustningen. */
export function connectorWorld(doc: CadDocument, e: Equipment, c: Connector): Pt3 {
  const R = ((e.rot ?? 0) * Math.PI) / 180;
  const z = elevation(doc, e.level) + e.p[0][2];
  return [e.p[0][0] + c.at[0] * Math.cos(R) - c.at[1] * Math.sin(R), e.p[0][1] + c.at[0] * Math.sin(R) + c.at[1] * Math.cos(R), z + c.at[2]];
}

/** Var en väg (rör, kanal, stege) börjar och slutar, i byggets koordinater. */
export function pathEnds(doc: CadDocument, e: Pipe | Duct | CableTray | Conduit): [Pt3, Pt3] | null {
  if (e.path.length < 2) return null;
  const z = elevation(doc, e.level) + (e.elevation ?? 0);
  const a = e.path[0], b = e.path[e.path.length - 1];
  return [[a[0], a[1], (a[2] ?? 0) + z], [b[0], b[1], (b[2] ?? 0) + z]];
}

export type Connection = { from: string; to: string; at: Pt3; via: "connector" | "end" | "tee"; connector?: string };
/**
 * Vad som sitter ihop i installationerna, härlett ur lägena: en vägs ände i en utrustnings anslutning, två
 * vägars ändar mot varandra, eller en vägs ände på en annan vägs sträcka (ett T-stycke). Toleransen är
 * `tol` millimeter. Ingen relation lagras: flyttas röret bort försvinner anslutningen, och det är rätt.
 */
export function connections(doc: CadDocument, tol = 60): Connection[] {
  const out: Connection[] = [];
  const paths = doc.entities.filter((e) => e.type === "pipe" || e.type === "duct" || e.type === "cable_tray" || e.type === "conduit") as (Pipe | Duct | CableTray | Conduit)[];
  const eq = doc.entities.filter((e) => e.type === "equipment") as Equipment[];
  const d3 = (a: Pt3, b: Pt3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
  const ends = new Map<string, [Pt3, Pt3]>();
  for (const p of paths) { const e = pathEnds(doc, p); if (e) ends.set(p.id, e); }
  for (const p of paths) {
    const e = ends.get(p.id); if (!e) continue;
    for (const end of e) {
      for (const q of eq) for (const c of q.connectors ?? []) { const w = connectorWorld(doc, q, c); if (d3(w, end) <= tol) out.push({ from: p.id, to: q.id, at: w, via: "connector", connector: c.id }); }
      for (const o of paths) {
        if (o.id === p.id || o.type !== p.type) continue;
        const oe = ends.get(o.id); if (!oe) continue;
        if (oe.some((x) => d3(x, end) <= tol)) { if (p.id < o.id) out.push({ from: p.id, to: o.id, at: end, via: "end" }); continue; }
        // T-stycke: änden ligger på den andra vägens sträcka, inte i dess ändar
        const z = elevation(doc, o.level) + (o.elevation ?? 0);
        for (let i = 0; i + 1 < o.path.length; i++) {
          const a: Pt3 = [o.path[i][0], o.path[i][1], (o.path[i][2] ?? 0) + z], b: Pt3 = [o.path[i + 1][0], o.path[i + 1][1], (o.path[i + 1][2] ?? 0) + z];
          const v = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]; const L2 = v[0] * v[0] + v[1] * v[1] + v[2] * v[2]; if (!L2) continue;
          const t = ((end[0] - a[0]) * v[0] + (end[1] - a[1]) * v[1] + (end[2] - a[2]) * v[2]) / L2;
          if (t <= 0 || t >= 1) continue;
          const q: Pt3 = [a[0] + v[0] * t, a[1] + v[1] * t, a[2] + v[2] * t];
          if (d3(q, end) <= tol) out.push({ from: p.id, to: o.id, at: q, via: "tee" });
        }
      }
    }
  }
  return out;
}

// ---------------------------------------------------------------- validering

export type Problem = { id?: string; field?: string; message: string };
const finite = (v: unknown) => typeof v === "number" && Number.isFinite(v);
const finitePt = (p: unknown) => Array.isArray(p) && p.length >= 2 && finite(p[0]) && finite(p[1]);

/** Vad som inte får sparas: ett objekt utan geometri, en dörr utan vägg, en vägg utan höjd, ett tal som inte är ett tal. */
export function validate(doc: CadDocument): Problem[] {
  const out: Problem[] = [];
  const ids = new Set<string>();
  const levels = new Set(doc.levels.map((l) => l.id));
  for (const l of doc.levels) if (!finite(l.elevation_mm)) out.push({ id: l.id, field: "elevation_mm", message: `Nivån ${l.name} saknar höjd` });
  if (!doc.levels.length) out.push({ message: "Dokumentet har ingen nivå" });
  for (const e of doc.entities) {
    if (!e.id || ids.has(e.id)) out.push({ id: e.id, message: "Dubbel eller tom identitet" });
    ids.add(e.id);
    if (e.level && !levels.has(e.level)) out.push({ id: e.id, field: "level", message: "Nivån finns inte" });
    const pts: unknown[] = ("p" in e ? (e as any).p : "path" in e ? (e as any).path : "points" in e ? (e as any).points : []) || [];
    if (!pts.every((p) => finitePt(p))) out.push({ id: e.id, field: "p", message: "En punkt är inte ett tal" });
    switch (e.type) {
      case "wall": case "curtain_wall":
        if (!(e.thickness > 0)) out.push({ id: e.id, field: "thickness", message: "Väggen behöver en tjocklek" });
        if (!levels.has(e.base_level)) out.push({ id: e.id, field: "base_level", message: "Väggens undre nivå finns inte" });
        if (e.top_level && !levels.has(e.top_level)) out.push({ id: e.id, field: "top_level", message: "Väggens övre nivå finns inte" });
        if (heightOf(doc, e) <= 0) out.push({ id: e.id, field: "height", message: "Väggen har ingen höjd" });
        if (wallLength(e) <= 0) out.push({ id: e.id, field: "p", message: "Väggen har ingen längd" });
        break;
      case "door": case "window": case "opening": {
        const h = entity(doc, e.host);
        if (!h || (h.type !== "wall" && h.type !== "curtain_wall" && h.type !== "floor" && h.type !== "roof" && h.type !== "ceiling"))
          out.push({ id: e.id, field: "host", message: `${e.type === "door" ? "Dörren" : e.type === "window" ? "Fönstret" : "Öppningen"} sitter inte i något` });
        if (!(e.width > 0) || !(e.height > 0)) out.push({ id: e.id, field: "width", message: "Bredd och höjd måste vara större än noll" });
        if (!(e.t >= 0 && e.t <= 1)) out.push({ id: e.id, field: "t", message: "Läget längs väggen ligger utanför väggen" });
        break;
      }
      case "floor": case "roof": case "ceiling": case "room":
        if (e.p.length < 3) out.push({ id: e.id, field: "p", message: "Konturen behöver minst tre punkter" });
        if (e.type !== "room" && !(e.thickness > 0)) out.push({ id: e.id, field: "thickness", message: "Tjockleken måste vara större än noll" });
        if (e.type === "roof" && e.kind === "pitched" && !(e.slope_deg! > 0 && e.slope_deg! < 90)) out.push({ id: e.id, field: "slope_deg", message: "Ett sadeltak behöver en lutning mellan 0 och 90 grader" });
        break;
      case "column":
        if (!levels.has(e.base_level)) out.push({ id: e.id, field: "base_level", message: "Pelarens undre nivå finns inte" });
        if (heightOf(doc, e) <= 0) out.push({ id: e.id, field: "height", message: "Pelaren har ingen höjd" });
        break;
      case "beam":
        if (dist(e.p[0], e.p[1]) <= 0) out.push({ id: e.id, field: "p", message: "Balken har ingen längd" });
        break;
      case "stair":
        if (!(e.risers >= 2)) out.push({ id: e.id, field: "risers", message: "En trappa har minst två steg" });
        if (!levels.has(e.base_level) || !levels.has(e.top_level)) out.push({ id: e.id, field: "top_level", message: "Trappans nivåer finns inte" });
        break;
      case "pipe":
        if (!(e.dn > 0)) out.push({ id: e.id, field: "dn", message: "Röret behöver en dimension" });
        if (e.path.length < 2) out.push({ id: e.id, field: "path", message: "Röret behöver minst två punkter" });
        break;
      case "duct":
        if (e.shape === "rect" ? !(e.w! > 0 && e.h! > 0) : !(e.d! > 0)) out.push({ id: e.id, field: "shape", message: "Kanalen behöver mått" });
        if (e.path.length < 2) out.push({ id: e.id, field: "path", message: "Kanalen behöver minst två punkter" });
        break;
      case "cable_tray": case "conduit":
        if (e.path.length < 2) out.push({ id: e.id, field: "path", message: "Vägen behöver minst två punkter" });
        break;
      case "circle": case "arc":
        if (!(e.r > 0)) out.push({ id: e.id, field: "r", message: "Radien måste vara större än noll" });
        break;
      case "line": case "rect":
        if (pts.length < 2) out.push({ id: e.id, field: "p", message: "Två punkter behövs" });
        break;
      case "underlay":
        if (!e.asset || !(e.px?.[0] > 0 && e.px?.[1] > 0)) out.push({ id: e.id, field: "asset", message: "Underlaget saknar bild eller bildmått" });
        if (e.mm_per_px != null && !(e.mm_per_px > 0)) out.push({ id: e.id, field: "mm_per_px", message: "Underlagets skala måste vara större än noll" });
        break;
      case "mesh":
        if (!e.asset || !["glb", "gltf", "obj", "stl"].includes(e.format)) out.push({ id: e.id, field: "asset", message: "Referensnätet saknar fil eller format" });
        if (!(e.scale > 0)) out.push({ id: e.id, field: "scale", message: "Referensnätet behöver en skala (mm per enhet)" });
        break;
      case "block":
        if (!doc.blocks.some((b) => b.id === e.def)) out.push({ id: e.id, field: "def", message: "Blockdefinitionen finns inte" });
        break;
      default: break;
    }
  }
  for (const v of doc.views) if (v.level && !levels.has(v.level)) out.push({ id: v.id, field: "level", message: `Vyn ${v.name} pekar på en nivå som inte finns` });
  return out;
}

/** Vilka objekt som hör till en vy: nivå, discipliner, dolda och isolerade. */
export function visibleIn(doc: CadDocument, view: View, e: Entity): boolean {
  if (view.hidden?.includes(e.id)) return false;
  if (view.isolate && view.isolate.length && !view.isolate.includes(e.id)) return false;
  if (view.disciplines && !view.disciplines.includes(e.discipline)) return false;
  if (view.phase_filter && !view.phase_filter.includes(e.phase)) return false;
  const layer = doc.layers.find((l) => l.id === e.layer);
  if (layer && !layer.visible) return false;
  if ((view.kind === "plan" || view.kind === "ceiling") && view.level) {
    const lv = levelOf(doc, view.level);
    if (!lv) return true;
    if ("base_level" in e && e.base_level) {
      // en vägg eller pelare syns i planen för varje nivå den passerar
      const { z0, z1 } = verticalExtent(doc, e as Wall);
      return z0 <= lv.elevation_mm + 1200 && z1 > lv.elevation_mm + 1;
    }
    if (e.type === "door" || e.type === "window" || e.type === "opening") {
      const h = entity(doc, e.host);
      return h ? visibleIn(doc, view, h) : false;
    }
    if (e.type === "stair") return e.base_level === view.level || e.top_level === view.level;
    if (e.type === "terrain" || e.type === "site") return true;
    return !e.level || e.level === view.level;
  }
  return true;
}
