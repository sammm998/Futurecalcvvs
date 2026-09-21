import { useEffect, useRef } from "react";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { PLAN_SCALE, RUN_PTS, SYS, WALL_PTS, type Pt } from "./Blueprint";
import { jacketThickness, jacketMaterial, mediumOf, pipeCurve, pipeMaterial } from "../three/pipeArt";
import { prefersStill } from "./motion";

/* Bladet som reser sig.
 *
 * Samma geometri som ritningen ovanför, byggd i tre dimensioner och styrd av rullningen. Scenen är inte en
 * dekoration bredvid texten - den är påståendet: ett platt blad blir en byggnad med installation i, och man
 * ser det hända.
 *
 * Fyra skeden, i den ordning rullningen ger dem:
 *   0,00-0,25  planen ligger rakt ovanifrån och rören ritar sig själva, som på bladet
 *   0,25-0,55  kameran tiltar ned och väggarna reser sig ur strecken
 *   0,55-0,80  rören lyfter till sin höjd och får sitt material
 *   0,80-1,00  hela byggnaden vrids långsamt, och beteckningarna tänds
 *
 * Rörens material och böjar kommer från samma modul som analysens 3D-vy (../three/pipeArt), så en koppar-
 * ledning ser likadan ut på startsidan som i verktyget. Den som bett om mindre rörelse får slutbilden direkt.
 */

const W = 1200, H = 760;                       // bladets koordinatrum
const toWorld = ([x, y]: Pt): [number, number] =>
  [(x - W / 2) * PLAN_SCALE, (H / 2 - y) * PLAN_SCALE];

export default function Scene3D({ className = "" }: { className?: string }) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const still = prefersStill();

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 400);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.0;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);

    const pmrem = new THREE.PMREMGenerator(renderer);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04);
    pmrem.dispose();
    scene.environment = env.texture;
    scene.environmentIntensity = 0.55;

    const span = W * PLAN_SCALE;
    const hemi = new THREE.HemisphereLight("#ffffff", "#14181c", 0.9);
    scene.add(hemi);
    const key = new THREE.DirectionalLight("#fff6ea", 2.4);
    key.position.set(span * 0.4, span * 0.7, span * 0.35);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.far = span * 3;
    const s = span * 0.55;
    key.shadow.camera.left = -s; key.shadow.camera.right = s;
    key.shadow.camera.top = s; key.shadow.camera.bottom = -s;
    key.shadow.bias = -0.0012;
    key.shadow.radius = 2.5;
    scene.add(key);

    // Golvet: mörkt och matt, så byggnaden står på något i stället för att sväva i rymden.
    const slab = new THREE.Mesh(
      new THREE.BoxGeometry(span * 1.02, 0.1, H * PLAN_SCALE * 1.02),
      new THREE.MeshStandardMaterial({ color: "#14161a", roughness: 0.95, metalness: 0 }),
    );
    slab.position.y = -0.05;
    slab.receiveShadow = true;
    scene.add(slab);

    // Bladets streck, ritade direkt på plattan. De ligger kvar under byggnaden hela vägen.
    const inkMat = new THREE.LineBasicMaterial({ color: 0x5c6470, transparent: true, opacity: 0.9 });
    const ink = new THREE.Group();
    for (const w of WALL_PTS) {
      const g = new THREE.BufferGeometry().setFromPoints(
        w.map((p) => { const [x, z] = toWorld(p); return new THREE.Vector3(x, 0.006, z); }));
      ink.add(new THREE.Line(g, inkMat));
    }
    scene.add(ink);

    // ---- väggarna, som reser sig ur strecken --------------------------------------------------------
    const wallMat = new THREE.MeshPhysicalMaterial({ color: "#e9e7e1", roughness: 0.95, metalness: 0 });
    const capMat = new THREE.MeshPhysicalMaterial({ color: "#8f8a80", roughness: 1, metalness: 0 });
    const walls = new THREE.Group();
    const HEIGHT = 2.6, THICK = 0.16;
    const box = new THREE.BoxGeometry(1, 1, 1);
    for (const w of WALL_PTS) {
      for (let i = 1; i < w.length; i++) {
        const [x0, z0] = toWorld(w[i - 1]);
        const [x1, z1] = toWorld(w[i]);
        const dx = x1 - x0, dz = z1 - z0;
        const len = Math.hypot(dx, dz);
        if (len < 0.05) continue;
        const m = new THREE.Mesh(box, wallMat);
        m.position.set((x0 + x1) / 2, HEIGHT / 2, (z0 + z1) / 2);
        m.rotation.y = Math.atan2(-dz, dx);
        m.scale.set(len, HEIGHT, THICK);
        m.castShadow = true; m.receiveShadow = true;
        walls.add(m);
        const cap = new THREE.Mesh(box, capMat);
        cap.position.set((x0 + x1) / 2, HEIGHT + 0.015, (z0 + z1) / 2);
        cap.rotation.y = m.rotation.y;
        cap.scale.set(len * 1.002, 0.03, THICK * 1.05);
        walls.add(cap);
      }
    }
    walls.scale.y = 0.001;
    scene.add(walls);

    // ---- rören, som ritar sig själva och sedan lyfter -----------------------------------------------
    const pipes = new THREE.Group();
    const drawn: { mesh: THREE.Mesh; total: number; band: number }[] = [];
    RUN_PTS.forEach((r, i) => {
      const band = 1.5 + (i % 5) * 0.16;                 // systemen i band, som i analysens 3D-vy
      const pts = r.pts.map((p) => { const [x, z] = toWorld(p); return new THREE.Vector3(x, band, z); });
      const medium = mediumOf(r.sys);
      const radius = Math.max(0.05, (r.dn / 1000) / 2 * 2.2);
      const { curve } = pipeCurve(pts, radius * 2.6);
      if (!curve.curves.length) return;
      const geo = new THREE.TubeGeometry(curve, 220, radius, 14, false);
      const mesh = new THREE.Mesh(geo, pipeMaterial(SYS[r.sys], medium));
      mesh.castShadow = true;
      pipes.add(mesh);
      drawn.push({ mesh, total: geo.index ? geo.index.count : 0, band });
      if (medium === "isolerat") {
        const jac = new THREE.Mesh(
          new THREE.TubeGeometry(curve, 220, radius + jacketThickness(radius), 12, false),
          jacketMaterial(SYS[r.sys]));
        jac.castShadow = true;
        pipes.add(jac);
      }
    });
    scene.add(pipes);

    // ---- kamerabanan --------------------------------------------------------------------------------
    const target = new THREE.Vector3(0, 0.9, 0);
    const place = (phi: number, theta: number, dist: number) => {
      camera.position.set(
        target.x + dist * Math.cos(phi) * Math.cos(theta),
        target.y + dist * Math.sin(phi),
        target.z + dist * Math.cos(phi) * Math.sin(theta),
      );
      // Rakt ovanifrån vet en kamera inte vad som är upp; upp-vektorn vänds därför mjukt ned i planet.
      const k = Math.max(0, Math.min(1, (phi - 1.0) / (Math.PI / 2 - 1.0)));
      camera.up.set(-Math.cos(theta) * k, 1 - k * 0.999, -Math.sin(theta) * k).normalize();
      camera.lookAt(target);
    };

    const step = (p: number, a: number, b: number) => Math.max(0, Math.min(1, (p - a) / (b - a)));
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);

    const draw = (p: number) => {
      const rise = ease(step(p, 0.22, 0.56));
      const lift = ease(step(p, 0.5, 0.82));
      const spin = step(p, 0.78, 1);

      walls.scale.y = Math.max(0.001, rise);
      pipes.visible = p > 0.04;
      for (const d of drawn) {
        // Röret ritas genom att bara en del av sitt rör visas, och lyfter sedan till sin höjd.
        d.mesh.geometry.setDrawRange(0, Math.max(6, Math.floor((d.total || 6) * ease(step(p, 0.04, 0.42)))));
        d.mesh.position.y = -d.band * (1 - lift);
      }
      pipes.children.forEach((c) => { c.position.y = -1.5 * (1 - lift); });
      (inkMat as THREE.LineBasicMaterial).opacity = 0.9 - 0.55 * rise;

      const phi = (Math.PI / 2 - 0.004) * (1 - ease(step(p, 0.18, 0.62))) + 0.42 * ease(step(p, 0.18, 0.62));
      const theta = Math.PI * 0.25 + spin * 0.5;
      // Avståndet räknas ur modellen och rutan i stället för att gissas. En gissning på 26 satte kameran mitt
      // inne i ett hus som är trettiotvå meter brett, och halva byggnaden låg utanför bilden.
      place(Math.max(0.2, phi), theta, fit() * (0.94 - 0.14 * ease(step(p, 0.1, 0.7))));
      renderer.render(scene, camera);
    };

    /** Så långt bort att hela huset ryms, prövat mot både bredden och höjden i rutan. */
    const fit = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      const rad = Math.hypot(W * PLAN_SCALE, H * PLAN_SCALE) / 2 + HEIGHT;
      const vFov = (camera.fov * Math.PI) / 180;
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * (w / h));
      return Math.max(8, rad / Math.sin(Math.min(vFov, hFov) / 2));
    };

    const resize = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(() => { resize(); draw(last); });
    ro.observe(el);

    let last = still ? 1 : 0;
    draw(last);

    const trig = still ? null : ScrollTrigger.create({
      trigger: el.closest(".fc-rise") || el,
      start: "top bottom",
      end: "bottom top",
      onUpdate: (self) => { last = self.progress; draw(last); },
      onRefresh: (self) => { last = self.progress; draw(last); },
    });

    return () => {
      trig?.kill();
      ro.disconnect();
      env.texture.dispose();
      renderer.dispose();
      scene.traverse((o: any) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
      el.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={host} className={`fc-3d ${className}`.trim()} aria-hidden="true" />;
}
