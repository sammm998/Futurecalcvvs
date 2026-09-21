import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { type CadDocument, type Entity, type View, type Discipline, visibleIn } from "../cad/building";
import { solidsOf, pathTube, type Prism, type RoofPlane } from "../cad/solids";
import { colourOf } from "../cad/plan";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";
import { OBJLoader } from "three/examples/jsm/loaders/OBJLoader.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { api } from "../api";

/** Referensnäten laddas en gång per fil och delas mellan scenerna; ett nät som inte laddats än är en tom plats, inte ett fel. */
const meshCache = new Map<string, THREE.Object3D | "loading" | "failed">();
async function loadMesh(asset: string, format: string): Promise<THREE.Object3D | null> {
  const url = await api.cadAssetUrl(asset);
  if (format === "glb" || format === "gltf") return (await new GLTFLoader().loadAsync(url)).scene;
  if (format === "obj") return await new OBJLoader().loadAsync(url);
  if (format === "stl") { const geo = await new STLLoader().loadAsync(url); return new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: "#9aa4b1", roughness: 0.8 })); }
  return null;
}

/* Modellen i 3D: samma objekt som planen, byggda till kroppar och ritade med WebGL.
 *
 * Ingenting här är en egen modell. Varje kropp kommer ur solidsOf() - väggen delad kring sina öppningar, taket
 * med sin lutning, röret som en tub längs sin väg - och när dokumentet ändras byggs scenen om. Det man klickar
 * på är objektet med samma id som i planen; det man flyttar med gizmon flyttas i dokumentet, och planen följer.
 *
 * Millimeter blir meter i scenen (1 enhet = 1 m) och y pekar uppåt: planens (x, y) blir (x, -y) i markplanet så
 * att norr i planen är bort från betraktaren. En lokal origo drar hela modellen till scenens mitt så att stora
 * byggkoordinater inte skakar i flyttal. */

export type ViewName = "iso" | "top" | "front" | "back" | "left" | "right" | "bottom";

type Props = {
  doc: CadDocument;
  view: View;
  selected: string[];
  onSelect: (ids: string[], additive: boolean) => void;
  onMove?: (id: string, dx_mm: number, dy_mm: number, dz_mm: number) => void;
  transparency?: Partial<Record<Discipline, number>>;
  sectionBox?: { min: [number, number, number]; max: [number, number, number] } | null;
  standardView?: ViewName | null;
  ortho?: boolean;
  wire?: boolean;
};

const GROUND = "#eceae4";
const MM = 0.001;

function prismGeometry(p: Prism | RoofPlane, o: [number, number]): THREE.BufferGeometry {
  const shape = new THREE.Shape();
  p.poly.forEach(([x, y], i) => { const X = (x - o[0]) * MM, Y = (y - o[1]) * MM; if (i) shape.lineTo(X, -Y); else shape.moveTo(X, -Y); });
  shape.closePath();
  for (const h of p.holes || []) { const path = new THREE.Path(); h.forEach(([x, y], i) => { const X = (x - o[0]) * MM, Y = (y - o[1]) * MM; if (i) path.lineTo(X, -Y); else path.moveTo(X, -Y); }); path.closePath(); shape.holes.push(path); }
  const top = (p as RoofPlane).top;
  const depth = ((top ? Math.max(...top) : p.z1) - p.z0) * MM;
  const g = new THREE.ExtrudeGeometry(shape, { depth: Math.max(0.005, depth), bevelEnabled: false });
  // extruderat längs +z: lägg platt och lyft till underkanten
  g.rotateX(-Math.PI / 2);
  g.translate(0, p.z0 * MM, 0);
  if (top && top.length === p.poly.length) {
    // ett lutande tak: sänk ovansidans hörn till sina egna höjder (närmaste hörn i planen)
    const pos = g.attributes.position as THREE.BufferAttribute;
    const zmax = Math.max(...top) * MM;
    for (let i = 0; i < pos.count; i++) {
      const y = pos.getY(i);
      if (Math.abs(y - zmax) < 1e-6) {
        const X = pos.getX(i) / MM + o[0], Z = -pos.getZ(i) / MM + o[1];
        let best = Infinity, bz = zmax;
        p.poly.forEach(([px, py], k) => { const d = Math.hypot(px - X, py - Z); if (d < best) { best = d; bz = top[k] * MM; } });
        pos.setY(i, bz + (p.z1 - Math.max(...top)) * MM * 0);
      }
    }
    pos.needsUpdate = true;
    g.computeVertexNormals();
  }
  return g;
}

function tubeGeometry(t: ReturnType<typeof pathTube>, o: [number, number]): THREE.BufferGeometry[] {
  const out: THREE.BufferGeometry[] = [];
  for (let i = 0; i + 1 < t.path.length; i++) {
    const a = t.path[i], b = t.path[i + 1];
    const A = new THREE.Vector3((a[0] - o[0]) * MM, a[2] * MM, -(a[1] - o[1]) * MM), B = new THREE.Vector3((b[0] - o[0]) * MM, b[2] * MM, -(b[1] - o[1]) * MM);
    const L = A.distanceTo(B); if (L < 1e-6) continue;
    const g = t.round ? new THREE.CylinderGeometry(t.w * MM / 2, t.w * MM / 2, L, 16) : new THREE.BoxGeometry(t.w * MM, t.h * MM, L);
    if (t.round) g.rotateX(Math.PI / 2);
    const dir = B.clone().sub(A).normalize();
    const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), dir);
    g.applyQuaternion(q);
    g.translate((A.x + B.x) / 2, (A.y + B.y) / 2, (A.z + B.z) / 2);
    out.push(g);
  }
  return out;
}

/* Arkitektens snitt, inte ingenjörens tråd.
 *
 * En modell av ett hus läses bäst som ett snitt genom det: väggarna vita med sin tjocklek synlig, golvet varmt
 * och matt, och skuggan mjuk nog att säga vad som står ovanpå vad. Färgerna är dämpade med flit - det som ska
 * synas är rummen och installationen, och ett rör i sitt systems färg syns bara mot en grund som håller tyst.
 */
const KIND_COLOUR: Record<string, string> = {
  wall: "#f4f1ec", curtain_wall: "#cfe0e6", door: "#b98f5e", window: "#d6e6ec", opening: "#efece7",
  floor: "#e6e0d7", ceiling: "#f7f5f1", roof: "#8d6a57", column: "#e2ddd5", beam: "#d8d2c8",
  foundation: "#cdc6ba", stair: "#ddd5c7", equipment: "#a9b3b8",
};

export default function BuildingView3D({ doc, view, selected, onSelect, onMove, transparency, sectionBox, standardView, ortho, wire }: Props) {
  const [, setLoaded] = useState(0);        // räknas upp när ett referensnät laddats, så att scenen byggs om
  const host = useRef<HTMLDivElement>(null);
  const state = useRef<{ scene: THREE.Scene; renderer: THREE.WebGLRenderer; persp: THREE.PerspectiveCamera; orthoCam: THREE.OrthographicCamera; controls: OrbitControls; gizmo: TransformControls; group: THREE.Group; raf: number; span: number; origin: [number, number]; picks: Map<THREE.Object3D, string>; dispose: () => void } | null>(null);
  const cbs = useRef({ onSelect, onMove });
  cbs.current = { onSelect, onMove };

  // ---- scenen skapas en gång
  useEffect(() => {
    const el = host.current; if (!el) return;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(GROUND);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.shadowMap.enabled = true;
    renderer.localClippingEnabled = true;
    el.appendChild(renderer.domElement);
    const persp = new THREE.PerspectiveCamera(45, 1, 0.05, 2000);
    const orthoCam = new THREE.OrthographicCamera(-10, 10, 10, -10, -500, 500);
    const controls = new OrbitControls(persp, renderer.domElement);
    controls.enableDamping = true; controls.dampingFactor = 0.1;
    // Ljuset är dagsljus i ett rum: en mjuk himmel överallt, en sol som kastar skuggan, och en svag fyllnad
    // från motsatt håll så att den skuggade sidan av en vägg inte blir svart. Skuggan är det som gör snittet
    // läsbart - utan den ligger allt platt i samma vita.
    const hemi = new THREE.HemisphereLight("#ffffff", "#d9d2c6", 2.1); scene.add(hemi);
    const key = new THREE.DirectionalLight("#fffaf2", 2.4);
    key.position.set(34, 62, 26); key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.03;
    key.shadow.camera.near = 1; key.shadow.camera.far = 400;
    key.shadow.camera.left = -120; key.shadow.camera.right = 120;
    key.shadow.camera.top = 120; key.shadow.camera.bottom = -120;
    scene.add(key);
    const fill = new THREE.DirectionalLight("#eef2f6", 0.55); fill.position.set(-30, 26, -22); scene.add(fill);
    // Golvet under huset tar emot skuggan. Ingen ruta: ett rutnät säger "modell", en yta säger "hus".
    const shadowFloor = new THREE.Mesh(
      new THREE.PlaneGeometry(600, 600),
      new THREE.ShadowMaterial({ opacity: 0.17 }));
    shadowFloor.rotation.x = -Math.PI / 2; shadowFloor.position.y = -0.02; shadowFloor.receiveShadow = true;
    scene.add(shadowFloor);
    const grid = new THREE.GridHelper(200, 40, "#cfc7ba", "#e0dace");
    (grid.material as THREE.Material).transparent = true; (grid.material as THREE.Material).opacity = 0.32;
    scene.add(grid);
    const group = new THREE.Group(); scene.add(group);
    const gizmo = new TransformControls(persp, renderer.domElement);
    gizmo.setMode("translate"); gizmo.addEventListener("dragging-changed", (ev: any) => { controls.enabled = !ev.value; });
    scene.add(gizmo.getHelper());
    let dragStart: THREE.Vector3 | null = null;
    gizmo.addEventListener("mouseDown", () => { dragStart = gizmo.object ? gizmo.object.position.clone() : null; });
    gizmo.addEventListener("mouseUp", () => {
      const o = gizmo.object; if (!o || !dragStart) return;
      const d = o.position.clone().sub(dragStart);
      const id = st.picks.get(o);
      if (id && cbs.current.onMove && d.length() > 1e-6) cbs.current.onMove(id, d.x / MM, -d.z / MM, d.y / MM);
      dragStart = null;
    });
    const st = { scene, renderer, persp, orthoCam, controls, gizmo, group, raf: 0, span: 20, origin: [0, 0] as [number, number], picks: new Map<THREE.Object3D, string>(), dispose: () => {} };
    state.current = st;
    const resize = () => { const r = el.getBoundingClientRect(); renderer.setSize(r.width, r.height, false); persp.aspect = r.width / Math.max(1, r.height); persp.updateProjectionMatrix(); const a = r.width / Math.max(1, r.height); orthoCam.left = -st.span * a; orthoCam.right = st.span * a; orthoCam.top = st.span; orthoCam.bottom = -st.span; orthoCam.updateProjectionMatrix(); };
    const ro = new ResizeObserver(resize); ro.observe(el); resize();
    // klick = val; skift lägger till
    const ray = new THREE.Raycaster(); const mouse = new THREE.Vector2(); let down: [number, number] | null = null;
    const onDown = (ev: PointerEvent) => { down = [ev.clientX, ev.clientY]; };
    const onUp = (ev: PointerEvent) => {
      if (!down || Math.hypot(ev.clientX - down[0], ev.clientY - down[1]) > 4 || (gizmo as any).dragging) { down = null; return; }
      down = null;
      const r = renderer.domElement.getBoundingClientRect();
      mouse.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(mouse, controls.object as THREE.Camera);
      const hits = ray.intersectObjects(group.children, true);
      const hit = hits.find((h) => st.picks.has(h.object) || st.picks.has(h.object.parent as THREE.Object3D));
      const id = hit ? st.picks.get(hit.object) ?? st.picks.get(hit.object.parent as THREE.Object3D) : undefined;
      cbs.current.onSelect(id ? [id] : [], ev.shiftKey);
    };
    renderer.domElement.addEventListener("pointerdown", onDown); renderer.domElement.addEventListener("pointerup", onUp);
    const tick = () => { controls.update(); renderer.render(scene, controls.object as THREE.Camera); st.raf = requestAnimationFrame(tick); };
    st.raf = requestAnimationFrame(tick);
    st.dispose = () => { cancelAnimationFrame(st.raf); ro.disconnect(); renderer.domElement.removeEventListener("pointerdown", onDown); renderer.domElement.removeEventListener("pointerup", onUp); gizmo.dispose(); controls.dispose(); renderer.dispose(); el.removeChild(renderer.domElement); };
    return () => st.dispose();
  }, []);

  // ---- modellen byggs om när dokumentet, vyn eller genomskinligheten ändras
  useEffect(() => {
    const st = state.current; if (!st) return;
    const { group, picks } = st;
    while (group.children.length) { const c = group.children.pop()!; c.traverse((o: any) => { o.geometry?.dispose?.(); o.material?.dispose?.(); }); }
    picks.clear();
    const ents = doc.entities.filter((e) => visibleIn(doc, { ...view, level: null }, e));
    // lokal origo: modellens mitt i planen
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, zmax = 3;
    for (const e of ents) for (const s of solidsOf(doc, e)) for (const [x, y] of s.poly) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); zmax = Math.max(zmax, s.z1 * MM); }
    if (!isFinite(x0)) { x0 = y0 = 0; x1 = y1 = 10000; }
    const o: [number, number] = [(x0 + x1) / 2, (y0 + y1) / 2];
    // kameran ställs in första gången och när modellen vuxit eller krympt påtagligt (ett tomt blad som får sina
    // första väggar); däremellan står den där användaren lämnade den
    const span = Math.max(6, Math.max(x1 - x0, y1 - y0) * MM * 0.6);
    const fitted: number | undefined = group.userData.fitSpan;
    const refit = fitted === undefined || Math.abs(span - fitted) / fitted > 0.5;
    st.origin = o; st.span = span;
    const planes = sectionBox ? [
      new THREE.Plane(new THREE.Vector3(1, 0, 0), -(sectionBox.min[0] - o[0]) * MM), new THREE.Plane(new THREE.Vector3(-1, 0, 0), (sectionBox.max[0] - o[0]) * MM),
      new THREE.Plane(new THREE.Vector3(0, 1, 0), -sectionBox.min[2] * MM), new THREE.Plane(new THREE.Vector3(0, -1, 0), sectionBox.max[2] * MM),
      new THREE.Plane(new THREE.Vector3(0, 0, -1), -(sectionBox.min[1] - o[1]) * MM), new THREE.Plane(new THREE.Vector3(0, 0, 1), (sectionBox.max[1] - o[1]) * MM),
    ] : [];
    const sel = new Set(selected);
    const matFor = (e: Entity, kind: string) => {
      const base = e.type === "pipe" || e.type === "duct" || e.type === "cable_tray" || e.type === "conduit" ? colourOf(doc, e) : KIND_COLOUR[kind] || colourOf(doc, e);
      const alpha = transparency?.[e.discipline];
      const m = new THREE.MeshStandardMaterial({ color: sel.has(e.id) ? "#1f6feb" : base, roughness: 0.92, metalness: 0.0, transparent: alpha != null && alpha < 1 || kind === "window" || kind === "curtain_wall", opacity: alpha != null ? alpha : kind === "window" || kind === "curtain_wall" ? 0.45 : 1, side: THREE.DoubleSide, wireframe: !!wire, clippingPlanes: planes });
      if (e.phase === "DEMOLISH") { m.color.set("#c0392b"); m.opacity = Math.min(m.opacity, 0.5); m.transparent = true; }
      if (e.phase === "EXISTING") { m.color.multiplyScalar(0.7); }
      return m;
    };
    for (const e of ents) {
      const holder = new THREE.Group(); holder.name = e.id; picks.set(holder, e.id);
      if (e.type === "mesh") {
        const c = meshCache.get(e.asset);
        if (c === undefined) {
          meshCache.set(e.asset, "loading");
          loadMesh(e.asset, e.format).then((obj) => { meshCache.set(e.asset, obj ?? "failed"); setLoaded((n) => n + 1); }).catch(() => { meshCache.set(e.asset, "failed"); setLoaded((n) => n + 1); });
        } else if (typeof c !== "string") {
          const inst = c.clone(true);
          const k = e.scale * MM;
          inst.scale.set(k, k, k);
          inst.position.set((e.p[0][0] - o[0]) * MM, (e.p[0][2] ?? 0) * MM, -(e.p[0][1] - o[1]) * MM);
          inst.rotation.y = -((e.rot ?? 0) * Math.PI) / 180;
          inst.traverse((m: any) => { if (m.isMesh) { picks.set(m, e.id); if (sel.has(e.id)) m.material = new THREE.MeshStandardMaterial({ color: "#1f6feb" }); } });
          holder.add(inst);
        }
      } else if (e.type === "pipe" || e.type === "duct" || e.type === "cable_tray" || e.type === "conduit") {
        for (const g of tubeGeometry(pathTube(doc, e), o)) { const m = new THREE.Mesh(g, matFor(e, e.type)); m.castShadow = true; picks.set(m, e.id); holder.add(m); }
      } else {
        for (const s of solidsOf(doc, e)) { const m = new THREE.Mesh(prismGeometry(s, o), matFor(e, s.kind)); m.castShadow = true; m.receiveShadow = true; picks.set(m, e.id); holder.add(m); }
        if (e.type === "device" || e.type === "fitting") { const g = new THREE.SphereGeometry(0.08, 12, 8); g.translate((e.p[0][0] - o[0]) * MM, e.p[0][2] * MM, -(e.p[0][1] - o[1]) * MM); const m = new THREE.Mesh(g, matFor(e, e.type)); picks.set(m, e.id); holder.add(m); }
        if (e.type === "terrain" && e.points.length >= 3) { const g = new THREE.BufferGeometry(); const v: number[] = []; for (let i = 1; i + 1 < e.points.length; i++) for (const q of [e.points[0], e.points[i], e.points[i + 1]]) v.push((q[0] - o[0]) * MM, q[2] * MM, -(q[1] - o[1]) * MM); g.setAttribute("position", new THREE.Float32BufferAttribute(v, 3)); g.computeVertexNormals(); const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: "#2f9e44", side: THREE.DoubleSide, roughness: 1 })); picks.set(m, e.id); holder.add(m); }
      }
      if (holder.children.length) group.add(holder);
    }
    // nivåerna som tunna ramar, så att man ser var planen ligger
    for (const l of doc.levels) {
      const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3((x0 - o[0]) * MM, l.elevation_mm * MM, -(y0 - o[1]) * MM), new THREE.Vector3((x1 - o[0]) * MM, l.elevation_mm * MM, -(y0 - o[1]) * MM), new THREE.Vector3((x1 - o[0]) * MM, l.elevation_mm * MM, -(y1 - o[1]) * MM), new THREE.Vector3((x0 - o[0]) * MM, l.elevation_mm * MM, -(y1 - o[1]) * MM), new THREE.Vector3((x0 - o[0]) * MM, l.elevation_mm * MM, -(y0 - o[1]) * MM)]);
      group.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: "#3b4452" })));
    }
    // gizmon på det valda
    const gz = st.gizmo;
    const target = selected.length === 1 ? group.children.find((c) => c.name === selected[0]) : undefined;
    if (target && onMove) gz.attach(target); else gz.detach();
    group.userData.built = true;
    if (refit) {
      group.userData.fitSpan = span;
      st.persp.position.set(span * 1.9, span * 1.3, span * 1.9); st.controls.target.set(0, zmax / 2, 0); st.controls.update();
      const r = st.renderer.domElement.getBoundingClientRect(); const a = r.width / Math.max(1, r.height);
      st.orthoCam.left = -span * a; st.orthoCam.right = span * a; st.orthoCam.top = span; st.orthoCam.bottom = -span; st.orthoCam.updateProjectionMatrix();
    }
  }, [doc, view, selected, transparency, sectionBox, wire, onMove]);

  // ---- standardvyer och kamera
  useEffect(() => {
    const st = state.current; if (!st || !standardView) return;
    const d = st.span * 1.6; const t = st.controls.target.clone();
    const pos: Record<ViewName, [number, number, number]> = { iso: [d, d * 0.75, d], top: [0, d * 1.5, 0.0001], bottom: [0, -d * 1.5, 0.0001], front: [0, t.y, d * 1.5], back: [0, t.y, -d * 1.5], left: [-d * 1.5, t.y, 0], right: [d * 1.5, t.y, 0] };
    const p = pos[standardView];
    st.controls.object.position.set(t.x + p[0], t.y + p[1] - (standardView === "top" || standardView === "bottom" ? 0 : t.y), t.z + p[2]);
    st.controls.update();
  }, [standardView]);

  useEffect(() => {
    const st = state.current; if (!st) return;
    const cam: THREE.Camera = ortho ? st.orthoCam : st.persp;
    if (st.controls.object !== cam) {
      cam.position.copy(st.controls.object.position);
      (st.controls as any).object = cam;
      (st.gizmo as any).camera = cam;
      st.controls.update();
    }
  }, [ortho]);

  return <div ref={host} className="cad3d" style={{ position: "absolute", inset: 0 }} />;
}
