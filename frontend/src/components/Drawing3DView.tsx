import { useEffect, useMemo, useRef, useState } from "react";
import { t as tr } from "../i18n";
import * as THREE from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";
import { buildModel, type BuildingModel, type ModelPipe, type ModelWall } from "../three/model";
import {
  bandOf, couplingMaterial, jacketMaterial, jacketThickness, MEDIUM_TEXT, mediumOf, pipeCurve,
  pipeMaterial, readableRadius,
} from "../three/pipeArt";
import Drawing3DControls, { type ViewName } from "./Drawing3DControls";

/* Ritningen som byggnad.
 *
 * Egen modul, egen renderare, egna komponenter: 3D:n vet ingenting om läsningen mer än den modell den får, och
 * läsningen vet ingenting om 3D:n. Det som visas är ritningens egen geometri - rören med sin verkliga grovlek
 * och sitt namn, väggarna som enkla skivor där arkitektens bläck går - och mängderna kommer från samma tabell
 * som resten av systemet räknar ur. Ingenting mäts här.
 *
 * Övergången är fysisk: planen ligger kvar, väggarna reser sig ur den, kameran tiltar från rakt ovanifrån till
 * perspektiv. Den som slagit på reducerad rörelse får samma modell utan resan dit.
 *
 * Fyra saker gör modellen läsbar i stället för bara vacker:
 *
 *   * **Vyn ovanifrån går att vrida.** Rakt ovanifrån är kamerans upp-riktning parallell med blicken, och en
 *     kamera i det läget vet inte längre vad som är upp. Upp-vektorn vänds därför mjukt ned i planet ju
 *     brantare vyn blir och följer vridningen, så planen går att snurra hela varvet utan att bilden slår runt.
 *   * **Beteckningarna står i rummet.** Varje beteckning läsningen namngav får en skylt vid sitt rör, ritad
 *     ovanpå allt annat och alltid vänd mot betraktaren. Utan dem är modellen en samling färgade rör.
 *   * **Väggarna går att se igenom.** En installation ligger inne i huset; en modell som bara visar fasaden
 *     döljer det man kom för att se.
 *   * **Man kan gå in i den.** Gå-läget sätter kameran i ögonhöjd och låter tangenterna föra den genom
 *     byggnaden. Det finns ingen krockberäkning - man går rakt genom en vägg - för en plan ritad i ett plan
 *     har inga dörrar att hitta, och att fastna i en vägg vore sämre än att gå igenom den.
 *
 * Och två som gör den trovärdig i stället för bara begriplig. Rören går raka och böjer i hörnen i stället för
 * att slingra sig genom punkterna - se ../three/pipeArt - och de får den yta materialet har: koppar blankt,
 * plast matt, isolering med mantel. Ljuset kommer från en omgivning i stället för bara från lampor, vilket är
 * vad som gör att en metall ser ut som metall; utan speglingar är blankt och matt samma grå.
 */

type Props = {
  controlRef?: { current: { motion: (dx: number, dy: number, factor: number) => void; fit: () => void; snapshot: () => string } | null };
  result: any;
  title?: string;
  onClose: () => void;
};

const SKY = "#dcd8cf";          // horisonten, och dimmans färg: allt som försvinner bort ska försvinna i den

/* Himlen som en toning. En platt färg bakom en modell ger ingen riktning åt ljuset och ingen horisont att
 * ställa huset mot; en toning från ljust uppe till dovare nere gör rummet till ett rum. Den ritas en gång i
 * en liten duk och läggs som bakgrund. */
function skyTexture(): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = 4; c.height = 256;
  const g = c.getContext("2d")!;
  const grad = g.createLinearGradient(0, 0, 0, 256);
  grad.addColorStop(0, "#f4f2ec");
  grad.addColorStop(0.5, "#e4e1d8");
  grad.addColorStop(0.62, SKY);
  grad.addColorStop(1, "#b9b2a5");
  g.fillStyle = grad;
  g.fillRect(0, 0, 4, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.mapping = THREE.EquirectangularReflectionMapping;
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}
const REDUCED = () => typeof window !== "undefined"
  && window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;

const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);

const EYE = 1.65;            // ögonhöjd i gå-läget, meter
const WALK = 2.8;            // meter i sekunden
const RUN = 7.0;
const MAX_LABELS = 260;      // skyltar ritas billigt men inte gratis

/** En skylt med beteckningen, ritad en gång som bild och sedan alltid vänd mot betraktaren. */
function labelSprite(text: string, color: string): THREE.Sprite {
  const font = 46, pad = 16, dot = 20;
  const probe = document.createElement("canvas").getContext("2d")!;
  probe.font = `600 ${font}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  const tw = Math.ceil(probe.measureText(text).width);
  const c = document.createElement("canvas");
  c.width = tw + pad * 3 + dot;
  c.height = font + pad * 2;
  const g = c.getContext("2d")!;
  const r = c.height / 2;
  g.fillStyle = "rgba(10, 14, 19, 0.86)";
  g.beginPath();
  g.moveTo(r, 0); g.lineTo(c.width - r, 0); g.arc(c.width - r, r, r, -Math.PI / 2, Math.PI / 2);
  g.lineTo(r, c.height); g.arc(r, r, r, Math.PI / 2, -Math.PI / 2); g.closePath(); g.fill();
  g.fillStyle = color;
  g.beginPath(); g.arc(pad + dot / 2, r, dot / 2, 0, Math.PI * 2); g.fill();
  g.fillStyle = "#f2f5f8";
  g.font = `600 ${font}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  g.textBaseline = "middle";
  g.fillText(text, pad * 2 + dot, r + 1);
  const tex = new THREE.CanvasTexture(c);
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({
    map: tex, transparent: true, depthTest: false, depthWrite: false,
  }));
  sprite.renderOrder = 10;
  sprite.userData.ratio = c.width / c.height;
  return sprite;
}

export default function Drawing3DView({ result, title, onClose, controlRef }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [model] = useState<BuildingModel>(() => buildModel(result));
  // Det man pekat på: ett rör med sin mängdrad, eller en vägg med sina mått. Ingenting annat är byggt, så
  // ingenting annat kan pekas på.
  const [picked, setPicked] = useState<
    | { kind: "ror"; pipe: ModelPipe; qty: any }
    | { kind: "vagg"; wall: ModelWall }
    | null>(null);
  const [ready, setReady] = useState(false);
  const api = useRef<{
    view: (v: ViewName) => void; reset: () => void; spin: (dir: -1 | 1) => void;
    setExploded: (v: boolean) => void; setLabels: (v: boolean) => void; setXray: (v: boolean) => void;
    setWalking: (v: boolean) => void;
  } | null>(null);
  const [exploded, setExploded] = useState(false);
  const [labels, setLabels] = useState(true);
  const [xray, setXray] = useState(false);
  const [walking, setWalking] = useState(false);

  // samma ordning som scenen lägger banden i, så panelen kan säga vilken höjd ett rör faktiskt ritades på
  const systems = useMemo(
    () => [...new Set(model.pipes.map((p) => p.system).filter(Boolean))].sort(),
    [model],
  );

  const qtyByDesignation = useMemo(() => {
    const m = new Map<string, any>();
    for (const q of result?.quantities ?? []) m.set(q.designation, q);
    return m;
  }, [result]);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const reduced = REDUCED();
    const span = Math.max(model.size.width, model.size.depth, 6);

    // ---- scen, ljus, mark ------------------------------------------------------------------------------
    const scene = new THREE.Scene();
    // Ett hus i snitt läses som arkitekten ritar det: varm ljus grund, vita väggar, mjuk skugga. Den mörka
    // grunden gjorde modellen till en teknisk figur; den ljusa gör den till en byggnad, och rören syns bättre
    // mot den eftersom deras systemfärger är det enda mättade i bilden.
    const sky = skyTexture();
    scene.background = sky;
    scene.fog = new THREE.Fog(SKY, span * 1.9, span * 5.0);

    const camera = new THREE.PerspectiveCamera(46, 1, 0.08, Math.max(400, span * 8));
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.98;
    el.appendChild(renderer.domElement);

    // Ljuset från rummet, inte bara från lamporna. En metall syns som metall först när det finns något att
    // spegla; med bara riktade lampor blir blankt och matt samma grå, och alla rör ser ut att vara av samma
    // material. Omgivningen är räknad en gång ur en enkel rumsscen och kostar inget per bildruta.
    const pmrem = new THREE.PMREMGenerator(renderer);
    const env = pmrem.fromScene(new RoomEnvironment(), 0.04);
    pmrem.dispose();
    const dom = renderer.domElement;
    dom.tabIndex = 0;

    scene.environment = env.texture;
    scene.environmentIntensity = 0.85;

    const hemi = new THREE.HemisphereLight("#ffffff", "#ded6c8", 1.0);
    scene.add(hemi);
    const key = new THREE.DirectionalLight("#fffaf1", 2.7);
    key.position.set(span * 0.5, span * 0.9, span * 0.4);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.near = 0.5;
    key.shadow.camera.far = span * 4;
    key.shadow.radius = 2.4;
    // Skuggkameran spänns om huset och inte om hela marken. Samma 2048 punkter över en fjärdedel så stor yta
    // är fyra gånger så fin skugga, och det är skuggans skärpa som avgör om ett rör ser ut att ligga på något.
    const s = Math.max(2, Math.hypot(model.size.width, model.size.depth) * 0.62);
    key.shadow.camera.left = -s; key.shadow.camera.right = s;
    key.shadow.camera.top = s; key.shadow.camera.bottom = -s;
    key.shadow.bias = -0.0008;
    scene.add(key);
    const fill = new THREE.DirectionalLight("#eaf0f6", 0.5);
    fill.position.set(-span * 0.6, span * 0.4, -span * 0.5);
    scene.add(fill);

    // Marken mörkare än huset. Var det förra felet att allt var nästan vitt - himmel, mark, platta och vägg
    // inom några procent av varandra - så fanns ingen kontrast att läsa formen ur, och modellen såg ut som en
    // skiss i dimma. Nu står en ljus byggnad på ett dovare underlag, vilket är hur en modell på ett bord ser ut.
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(span * 6, span * 6),
      new THREE.MeshStandardMaterial({ color: "#aca595", roughness: 1.0, metalness: 0.0 }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.03;
    ground.receiveShadow = true;
    scene.add(ground);

    // Rutnätet ger måttet. Utan det är en modell lika stor som betraktaren tror; med en meterruta under sig
    // syns det direkt om ett rum är tre meter eller trettio, och det är halva skillnaden mot en teknisk figur.
    const grid = new THREE.GridHelper(Math.ceil(span * 3), Math.ceil(span * 3), 0x8d8779, 0x9f9a8d);
    (grid.material as THREE.Material).opacity = 0.32;
    (grid.material as THREE.Material).transparent = true;
    grid.position.y = -0.024;
    scene.add(grid);

    const slab = new THREE.Mesh(
      new THREE.BoxGeometry(Math.max(model.size.width, 1) * 1.04, 0.14, Math.max(model.size.depth, 1) * 1.04),
      new THREE.MeshStandardMaterial({ color: "#d7d1c4", roughness: 0.94, metalness: 0.0 }),
    );
    slab.position.y = -0.07;
    slab.receiveShadow = true;
    scene.add(slab);

    // ---- väggar ----------------------------------------------------------------------------------------
    // Väggen är puts och inte plast: helt matt, utan metall, med en aning sken som en målad yta har. Den
    // gamla var blank nog att spegla, och en vägg som speglar drar till sig blicken från rören.
    const wallMat = new THREE.MeshPhysicalMaterial({
      color: "#f8f6f1", roughness: 0.94, metalness: 0.0, sheen: 0.25, sheenRoughness: 0.9,
    });
    // Väggens översida är ett snitt - planen är ritad genom huset - och ett snitt ritas mörkare än ytan runt
    // om. Den läggs som en egen tunn skiva ovanpå väggarna i stället för som en materialgrupp, eftersom en
    // instansmängd med flera material är svårare att lita på än en till instansmängd.
    const capMat = new THREE.MeshPhysicalMaterial({ color: "#9b9488", roughness: 0.98, metalness: 0.0 });
    const wallGroup = new THREE.Group();
    const wallGeo = new THREE.BoxGeometry(1, 1, 1);
    const walls = new THREE.InstancedMesh(wallGeo, wallMat, Math.max(1, model.walls.length));
    walls.castShadow = true; walls.receiveShadow = true;
    const dummy = new THREE.Object3D();
    model.walls.forEach((w, i) => {
      const dx = w.b[0] - w.a[0], dz = w.b[1] - w.a[1];
      const len = Math.hypot(dx, dz) || 0.01;
      dummy.position.set((w.a[0] + w.b[0]) / 2, w.height / 2, (w.a[1] + w.b[1]) / 2);
      dummy.rotation.set(0, Math.atan2(-dz, dx), 0);
      dummy.scale.set(len, w.height, Math.max(0.05, w.thickness));
      dummy.updateMatrix();
      walls.setMatrixAt(i, dummy.matrix);
    });
    walls.instanceMatrix.needsUpdate = true;
    wallGroup.add(walls);

    const caps = new THREE.InstancedMesh(wallGeo, capMat, Math.max(1, model.walls.length));
    model.walls.forEach((w, i) => {
      const dx = w.b[0] - w.a[0], dz = w.b[1] - w.a[1];
      const len = Math.hypot(dx, dz) || 0.01;
      dummy.position.set((w.a[0] + w.b[0]) / 2, w.height + 0.012, (w.a[1] + w.b[1]) / 2);
      dummy.rotation.set(0, Math.atan2(-dz, dx), 0);
      dummy.scale.set(len * 1.004, 0.024, Math.max(0.05, w.thickness) * 1.004);
      dummy.updateMatrix();
      caps.setMatrixAt(i, dummy.matrix);
    });
    caps.instanceMatrix.needsUpdate = true;
    wallGroup.add(caps);
    scene.add(wallGroup);

    // ---- rör -------------------------------------------------------------------------------------------
    // Ett DN16-rör är åtta millimeter i radie. På ett trettio meter brett hus är det ett hårstrå som försvinner
    // mot en vägg, så det som är för tunt trycks upp mot en minsta grovlek - men ihoptryckt och inte avklippt,
    // så att DN20 fortfarande är tunnare än DN110. Måttet i panelen är ritningens; grovleken på skärmen är
    // läsbarhet, och panelen säger det.
    const minR = Math.max(0.024, span * 0.0022);
    // Bladet är en plan och säger ingenting om höjd. Lades alla rör i samma plan lade sig korsande rör i
    // varandra och bilden blev en matta; systemen läggs därför i band, i bokstavsordning så att samma ritning
    // alltid ger samma bild. Det är en läsbarhetsordning och ingen mätning, och panelen säger det rakt ut.
    const systems = [...new Set(model.pipes.map((p) => p.system).filter(Boolean))].sort();
    const pipeGroup = new THREE.Group();
    const labelGroup = new THREE.Group();
    const bandFor = (p: ModelPipe) => bandOf(p.system, systems, model.floorHeight);
    const sleeveGeo = new THREE.CylinderGeometry(1, 1, 1, 14);
    const longest = new Map<string, { pipe: ModelPipe; at: [number, number]; y: number }>();
    model.pipes.forEach((p) => {
      if (p.path.length < 2) return;
      const y = bandFor(p);
      const pts = p.path.map(([x, z]) => new THREE.Vector3(x, y, z));
      const r = readableRadius(p.radius, minR);
      const medium = mediumOf(p.system);
      // Böjradien på ett riktigt rör är drygt en diameter. Den klipps ändå mot halva den kortaste sträckan
      // den ligger emellan, så två hörn nära varandra aldrig äter upp sträckan mellan sig.
      const { curve, bends } = pipeCurve(pts, Math.max(r * 2.6, 0.1));
      if (!curve.curves.length) return;
      const segs = Math.min(700, Math.max(10, Math.round(p.meters * 4) + bends * 8));
      const geo = new THREE.TubeGeometry(curve, segs, r, medium === "plast" ? 12 : 16, false);
      const mat = pipeMaterial(p.color, medium, !!p.inWall);
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = true;
      mesh.userData.pipe = p;
      pipeGroup.add(mesh);

      // Isoleringen utanpå ett varmt rör: en matt mantel, grövre än röret. Ett isolerat rör är märkbart
      // tjockare än sitt eget mått, och en modell som ritar det lika tunt som ett kallvattenrör ljuger om
      // hur trångt det är där uppe.
      if (medium === "isolerat" && !p.inWall) {
        const jr = r + jacketThickness(r);
        const jacket = new THREE.Mesh(new THREE.TubeGeometry(curve, segs, jr, 14, false), jacketMaterial(p.color));
        jacket.castShadow = true;
        jacket.userData.pipe = p;
        pipeGroup.add(jacket);
        // Manteln är ljus, och under den försvinner beteckningens färg - och färgen är det som säger vilket rör
        // man ser. Ett isolerat rör märks i verkligheten med tejp med jämna mellanrum, och samma band gör här
        // båda sakerna: det ser ut som ett isolerat rör, och röret behåller sin identitet.
        const total = curve.getLength();
        const n = Math.min(40, Math.max(1, Math.floor(total / 1.6)));
        if (n >= 1) {
          const bands = new THREE.InstancedMesh(sleeveGeo, new THREE.MeshPhysicalMaterial({
            color: p.color, roughness: 0.55, metalness: 0.0,
          }), n);
          const d = new THREE.Object3D();
          const up = new THREE.Vector3(0, 1, 0);
          for (let i = 0; i < n; i++) {
            const t = (i + 0.5) / n;
            d.position.copy(curve.getPoint(t));
            d.quaternion.setFromUnitVectors(up, curve.getTangent(t).normalize());
            d.scale.set(jr * 1.03, Math.min(0.13, jr * 1.7), jr * 1.03);
            d.updateMatrix();
            bands.setMatrixAt(i, d.matrix);
          }
          bands.userData.pipe = p;
          pipeGroup.add(bands);
        }
      }

      // Kopplingarna i böjarna: korta hylsor, något grövre än röret. Det är de som gör ett rör till rör och
      // inte till en slang, och de sitter där böjen börjar och slutar - alltså där de sitter i verkligheten.
      if (!p.inWall && bends > 0 && bends <= 80) {
        const sleeves = new THREE.InstancedMesh(sleeveGeo, couplingMaterial(p.color, medium), bends * 2);
        const d = new THREE.Object3D();
        const up = new THREE.Vector3(0, 1, 0);
        let n = 0;
        for (const c of curve.curves) {
          if (!(c instanceof THREE.QuadraticBezierCurve3)) continue;
          for (const t of [0, 1]) {
            d.position.copy(c.getPoint(t));
            d.quaternion.setFromUnitVectors(up, c.getTangent(t).normalize());
            d.scale.set(r * 1.3, Math.max(r * 2.4, 0.03), r * 1.3);
            d.updateMatrix();
            sleeves.setMatrixAt(n++, d.matrix);
          }
        }
        sleeves.count = n;
        sleeves.castShadow = true;
        sleeves.userData.pipe = p;
        pipeGroup.add(sleeves);
      }

      // Stigare: ett lodrätt rör där läsningen räknat en, med en krage i bjälklaget. Röret går genom golvet
      // och slutar inte vid det - det är skillnaden mellan ett rör som går vidare och ett som är kapat.
      if (p.risers > 0) {
        const tall = model.floorHeight + 0.34;
        const riser = new THREE.Mesh(new THREE.CylinderGeometry(r, r, tall, 16), mat);
        riser.position.set(p.path[0][0], tall / 2 - 0.22, p.path[0][1]);
        riser.castShadow = true;
        riser.userData.pipe = p;
        pipeGroup.add(riser);
        const collar = new THREE.Mesh(
          new THREE.CylinderGeometry(r * 2.2, r * 2.2, 0.07, 18),
          couplingMaterial(p.color, medium),
        );
        collar.position.set(p.path[0][0], 0.035, p.path[0][1]);
        collar.userData.pipe = p;
        pipeGroup.add(collar);
      }

      // var beteckningen ska stå: mitt på den längsta sträcka den har
      const mid = p.path[Math.floor(p.path.length / 2)];
      const seen = longest.get(p.designation);
      if (p.designation && (!seen || p.meters > seen.pipe.meters)) {
        longest.set(p.designation, { pipe: p, at: [mid[0], mid[1]], y });
      }
    });
    scene.add(pipeGroup);

    // Varje beteckning får en skylt - det är hela poängen med att kunna läsa modellen - och de långa sträckorna
    // får en till, så att ett rör som går genom hela huset är namngivet där man råkar titta.
    const placed: { sprite: THREE.Sprite; primary: boolean }[] = [];
    const stems: number[] = [];
    const LIFT = 0.42;
    const put = (text: string, color: string, x: number, z: number, y: number, primary: boolean) => {
      if (placed.length >= MAX_LABELS) return;
      const sp = labelSprite(text, color);
      sp.position.set(x, y + LIFT, z);
      labelGroup.add(sp);
      placed.push({ sprite: sp, primary });
      // hänvisningslinjen: skylten pekar på sitt rör i stället för att sväva över det. Det är samma sätt som
      // beteckningen sitter på bladet, och det som gör att man ser vilket rör en skylt gäller.
      stems.push(x, y, z, x, y + LIFT - 0.07, z);
    };
    // en skylt per beteckning är det som måste synas; de långa sträckorna får en extra där man råkar titta
    for (const [des, { pipe, at, y }] of longest) {
      put(pipe.dn ? `${des} · DN${pipe.dn}` : des, pipe.color, at[0], at[1], y, true);
    }
    // En extra skylt på en lång sträcka hjälper; fem skyltar med samma namn är buller som täcker huset. Varje
    // beteckning får därför en enda extra, och bara om den hamnar en bit från den första - annars säger den
    // ingenting som den första inte redan sagt.
    const extra = new Set<string>();
    for (const p of [...model.pipes].sort((a, b) => b.meters - a.meters)) {
      if (!p.designation || p.inWall || p.meters < 8) continue;
      if (extra.has(p.designation)) continue;
      const home = longest.get(p.designation);
      const q = p.path[Math.floor(p.path.length / 2)];
      if (home && Math.hypot(home.at[0] - q[0], home.at[1] - q[1]) < Math.max(8, span * 0.22)) continue;
      extra.add(p.designation);
      put(p.designation, p.color, q[0], q[1], bandFor(p), false);
    }
    const stemGeo = new THREE.BufferGeometry();
    stemGeo.setAttribute("position", new THREE.Float32BufferAttribute(stems, 3));
    const stemLines = new THREE.LineSegments(stemGeo, new THREE.LineBasicMaterial({
      color: "#2c3742", transparent: true, opacity: 0.5, depthTest: false,
    }));
    stemLines.renderOrder = 9;
    labelGroup.add(stemLines);
    labelGroup.visible = false;          // skyltarna kommer när väggarna rest sig
    scene.add(labelGroup);

    // ---- kamera: en bana från rakt ovanifrån till perspektiv --------------------------------------------
    const target = new THREE.Vector3(0, model.floorHeight * 0.35, 0);
    // Hur långt bort kameran ska stå räknas ur modellen och rutan, inte ur en gissning. Den förra gissningen
    // lämnade huset som en remsa i mitten med tom mark runt om; det här fyller bilden med det man kom för att
    // se. Bredden prövas mot höjden, för en lång smal plan begränsas av den ena och en kvadratisk av den andra.
    const fit = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      const rad = Math.hypot(model.size.width, model.size.depth) / 2 + model.floorHeight;
      const vFov = (camera.fov * Math.PI) / 180;
      const hFov = 2 * Math.atan(Math.tan(vFov / 2) * (w / h));
      return Math.max(4, (rad / Math.sin(Math.min(vFov, hFov) / 2)) * 0.86);
    };
    const radius = fit();
    const state = { theta: Math.PI * 0.25, phi: 0.02, dist: radius };
    const TOP = Math.PI / 2 - 0.004;
    const place = () => {
      const phi = Math.max(0.05, Math.min(TOP, state.phi));
      camera.position.set(
        target.x + state.dist * Math.cos(phi) * Math.cos(state.theta),
        target.y + state.dist * Math.sin(phi),
        target.z + state.dist * Math.cos(phi) * Math.sin(state.theta),
      );
      // Ju brantare vyn, desto mindre duger en lodrät upp-vektor: rakt ovanifrån är den parallell med blicken
      // och kameran vet inte längre vad som är upp. Den vänds därför mjukt ned i planet och följer vridningen,
      // så att vyn ovanifrån går att snurra hela varvet utan att bilden slår runt.
      const k = Math.max(0, Math.min(1, (phi - 1.05) / (TOP - 1.05)));
      camera.up.set(-Math.cos(state.theta) * k, 1 - k * 0.999, -Math.sin(state.theta) * k).normalize();
      camera.lookAt(target);
    };
    place();

    // ---- gå-läget: kameran i ögonhöjd, tangenterna för den ----------------------------------------------
    const walker = { on: false, yaw: Math.PI * 0.25, pitch: 0, pos: new THREE.Vector3() };
    const keys = new Set<string>();
    const placeWalk = () => {
      camera.up.set(0, 1, 0);
      camera.position.copy(walker.pos);
      const dir = new THREE.Vector3(
        Math.cos(walker.pitch) * Math.cos(walker.yaw),
        Math.sin(walker.pitch),
        Math.cos(walker.pitch) * Math.sin(walker.yaw),
      );
      camera.lookAt(walker.pos.clone().add(dir));
    };
    // Med låst pekare tar canvasen musen, och då går ingen knapp i gränssnittet att klicka på. Enda vägen ut
    // är då Esc, som webbläsaren själv fångar - så när låset släpps lämnar vi gå-läget. Annars sitter man fast
    // i en modell vars "Sluta gå" inte går att träffa.
    const lockChange = () => {
      if (walker.on && document.pointerLockElement !== dom) setWalking(false);
    };
    document.addEventListener("pointerlockchange", lockChange);

    const enterWalk = () => {
      walker.on = true;
      walker.yaw = state.theta + Math.PI;
      walker.pitch = -0.04;
      walker.pos.set(target.x, EYE, target.z);
      pipeGroup.position.y = 0;
      resize();                 // inne i modellen ligger inga reglage i vägen, så bilden får hela rutan
      placeWalk();
      dom.requestPointerLock?.();
    };
    const leaveWalk = () => {
      walker.on = false;
      keys.clear();
      if (document.pointerLockElement === dom) document.exitPointerLock?.();
      resize();
      place();
    };
    const keyDown = (e: KeyboardEvent) => {
      if (!walker.on) return;
      if (e.key === "Escape") { setWalking(false); return; }
      const k = e.key.toLowerCase();
      keys.add(k);
      if (["w", "a", "s", "d", "arrowup", "arrowdown", "arrowleft", "arrowright", " "].includes(k)) e.preventDefault();
    };
    const keyUp = (e: KeyboardEvent) => keys.delete(e.key.toLowerCase());
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);

    // ---- muskontroll: orbit, pan, zoom - och blicken i gå-läget -----------------------------------------
    let dragging: "orbit" | "pan" | null = null;
    let lx = 0, ly = 0;
    const down = (e: PointerEvent) => {
      if (walker.on) {
        if (document.pointerLockElement !== dom) dom.requestPointerLock?.();
        return;
      }
      dragging = e.button === 2 || e.shiftKey ? "pan" : "orbit";
      lx = e.clientX; ly = e.clientY;
      (e.target as Element).setPointerCapture?.(e.pointerId);
    };
    const move = (e: PointerEvent) => {
      if (walker.on) {
        if (document.pointerLockElement !== dom) return;
        walker.yaw += e.movementX * 0.0026;
        walker.pitch = Math.max(-1.35, Math.min(1.35, walker.pitch - e.movementY * 0.0022));
        placeWalk();
        return;
      }
      if (!dragging) return;
      const dx = e.clientX - lx, dy = e.clientY - ly;
      lx = e.clientX; ly = e.clientY;
      if (dragging === "orbit") {
        state.theta -= dx * 0.006;
        state.phi = Math.max(0.05, Math.min(TOP, state.phi + dy * 0.005));
      } else {
        const k = state.dist * 0.0016;
        const right = new THREE.Vector3().subVectors(camera.position, target)
          .cross(new THREE.Vector3(0, 1, 0)).normalize();
        target.addScaledVector(right, -dx * k);
        target.y = Math.max(0, target.y + dy * k);
      }
      place();
    };
    const up = () => { dragging = null; };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      if (walker.on) return;
      state.dist = Math.max(2, Math.min(radius * 6, state.dist * (1 + Math.sign(e.deltaY) * 0.12)));
      place();
    };
    dom.addEventListener("pointerdown", down);
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    dom.addEventListener("wheel", wheel, { passive: false });
    dom.addEventListener("contextmenu", (e) => e.preventDefault());

    // ---- val av objekt ---------------------------------------------------------------------------------
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    let hi: THREE.Mesh | null = null;
    // väggarna delar material, så den utpekade lyfts fram med sin egen instansfärg
    const plainWall = new THREE.Color("#f6f3ee");
    const litWall = new THREE.Color("#7fc6d8");
    let lastWall = -1;
    const click = (e: PointerEvent) => {
      const r = dom.getBoundingClientRect();
      // i gå-läget siktar man med blicken: strålen går ur mitten av bilden
      if (walker.on) ndc.set(0, 0);
      else ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      // rören först: de är smala och ligger ovanpå, så en träff på ett rör är alltid den som menades
      const hit = ray.intersectObjects(pipeGroup.children, false)[0];
      if (hi) { (hi.material as THREE.MeshStandardMaterial).emissive?.setHex(0x000000); hi = null; }
      walls.setColorAt(lastWall >= 0 ? lastWall : 0, plainWall);
      if (lastWall >= 0 && walls.instanceColor) walls.instanceColor.needsUpdate = true;
      lastWall = -1;
      if (hit) {
        const mesh = hit.object as THREE.Mesh;
        hi = mesh;
        (mesh.material as THREE.MeshStandardMaterial).emissive?.setHex(0x2b4a6b);
        const pipe = mesh.userData.pipe as ModelPipe;
        setPicked({ kind: "ror", pipe, qty: qtyByDesignation.get(pipe.designation) ?? null });
        return;
      }
      const wallHit = ray.intersectObject(walls, false)[0] as THREE.Intersection | undefined;
      const id = wallHit?.instanceId;
      if (id != null && model.walls[id]) {
        lastWall = id;
        walls.setColorAt(id, litWall);
        if (walls.instanceColor) walls.instanceColor.needsUpdate = true;
        setPicked({ kind: "vagg", wall: model.walls[id] });
        return;
      }
      setPicked(null);
    };
    dom.addEventListener("click", click as any);

    // Skuggan i vinkeln, där vägg möter golv, är det som skiljer en modell som står på golvet från en som är
    // klistrad på det. Den prövades med en efterberäkning ur djupbilden (GTAOPass) och backades: på väggarnas
    // översidor lade den smutsfläckar i stället för skugga, och bilden blev platt i stället för djup. Ett fel
    // som syns är sämre än ett djup som saknas, så scenen renderas rakt av.

    // ---- storlek ---------------------------------------------------------------------------------------
    const resize = () => {
      const w = el.clientWidth || 1, h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      // Reglagen ligger över bildens nedre fjärdedel. Mitten av rutan är därför inte mitten av det man ser, och
      // en modell som centreras i rutan hamnar halvt bakom panelen. Bilden räknas som om den vore högre och
      // bara den nedre delen visas - då hamnar huset mitt i det som faktiskt syns.
      const pad = walker.on ? 0 : Math.min(190, h * 0.24);
      if (pad > 1) camera.setViewOffset(w, h + pad, 0, pad, w, h);
      else camera.clearViewOffset();
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    // ---- resan: väggarna reser sig, kameran tiltar ------------------------------------------------------
    const RISE = reduced ? 0 : 1500;
    const t0 = performance.now();
    let last = performance.now();
    let wantLabels = true;
    let raf = 0;
    const tick = (now: number) => {
      const dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      const t = RISE ? Math.min(1, (now - t0) / RISE) : 1;
      const e = easeOut(t);
      wallGroup.scale.y = Math.max(0.001, e);
      wallGroup.position.y = 0;
      pipeGroup.visible = t > 0.35;
      pipeGroup.scale.y = Math.max(0.001, easeOut(Math.max(0, (t - 0.35) / 0.65)));
      labelGroup.visible = wantLabels && t >= 1;
      if (RISE && !walker.on && t < 1) {
        state.phi = 0.02 + (0.62 - 0.02) * e;
        state.dist = radius * (1.35 - 0.35 * e);
        place();
      }
      if (walker.on) {
        const speed = (keys.has("shift") ? RUN : WALK) * dt;
        const fx = Math.cos(walker.yaw), fz = Math.sin(walker.yaw);
        let mx = 0, mz = 0;
        if (keys.has("w") || keys.has("arrowup")) { mx += fx; mz += fz; }
        if (keys.has("s") || keys.has("arrowdown")) { mx -= fx; mz -= fz; }
        if (keys.has("a") || keys.has("arrowleft")) { mx += fz; mz -= fx; }
        if (keys.has("d") || keys.has("arrowright")) { mx -= fz; mz += fx; }
        const len = Math.hypot(mx, mz);
        if (len > 0) {
          walker.pos.x += (mx / len) * speed;
          walker.pos.z += (mz / len) * speed;
          walker.pos.y = EYE;
          placeWalk();
        }
      }
      // Skyltarna hålls lika stora på skärmen oavsett avstånd - en skylt som växer med avståndet blir en
      // skylt som täcker huset - och de som skulle hamna ovanpå varandra tas bort. En trave namn är inte
      // läsbarare än inget namn alls, så den som ligger närmast får platsen och resten väntar på sin vinkel.
      if (labelGroup.visible) {
        const vh = 2 * Math.tan((camera.fov * Math.PI / 180) / 2);
        const kept: [number, number][] = [];
        const v = new THREE.Vector3();
        const order = placed
          .map((q) => ({ ...q, d: camera.position.distanceTo(q.sprite.position) }))
          .sort((a, b) => (a.primary === b.primary ? a.d - b.d : a.primary ? -1 : 1));
        for (const { sprite, d } of order) {
          const h = Math.max(0.14, d * vh * 0.021);
          sprite.scale.set(h * (sprite.userData.ratio as number), h, 1);
          v.copy(sprite.position).project(camera);
          if (v.z > 1 || Math.abs(v.x) > 1.25 || Math.abs(v.y) > 1.25) { sprite.visible = false; continue; }
          const sx = v.x * 0.5 * el.clientWidth, sy = v.y * 0.5 * el.clientHeight;
          const room = kept.every(([kx, ky]) => Math.abs(kx - sx) > 168 || Math.abs(ky - sy) > 34);
          sprite.visible = room;
          if (room) kept.push([sx, sy]);
        }
      }
      if (t >= 1 && !ready) setReady(true);
      renderer.render(scene, camera);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const glideTo = (th: number, ph: number) => {
      const from = { theta: state.theta, phi: state.phi };
      const start = performance.now();
      const glide = (now: number) => {
        const t = Math.min(1, (now - start) / (reduced ? 1 : 520));
        const e = easeOut(t);
        state.theta = from.theta + (th - from.theta) * e;
        state.phi = from.phi + (ph - from.phi) * e;
        place();
        if (t < 1) requestAnimationFrame(glide);
      };
      requestAnimationFrame(glide);
    };

    api.current = {
      // Ovanifrån behåller den vridning man redan har: att trycka på knappen ska lyfta blicken, inte vrida
      // huset tillbaka till ett väderstreck man aldrig valde.
      view: (v) => {
        const preset: Record<ViewName, [number, number]> = {
          // rakt ovanifrån läggs planen rakt i rutan: närmaste kvartsvarv, så bladet inte står på diagonalen
          topp: [Math.round(state.theta / (Math.PI / 2)) * (Math.PI / 2), TOP],
          perspektiv: [Math.PI * 0.25, 0.62],
          front: [Math.PI * 0.5, 0.12],
          sida: [0, 0.12],
        };
        const [th, ph] = preset[v];
        glideTo(th, ph);
      },
      spin: (dir) => glideTo(state.theta + dir * Math.PI / 4, state.phi),
      reset: () => {
        target.set(0, model.floorHeight * 0.35, 0);
        state.theta = Math.PI * 0.25; state.phi = 0.62; state.dist = radius;
        place();
      },
      setExploded: (v: boolean) => {
        if (!walker.on) pipeGroup.position.y = v ? model.floorHeight * 1.15 : 0;
      },
      setLabels: (v: boolean) => { wantLabels = v; labelGroup.visible = v; },
      setXray: (v: boolean) => {
        wallMat.transparent = v;
        wallMat.opacity = v ? 0.24 : 1;
        wallMat.depthWrite = !v;
        wallMat.needsUpdate = true;
        capMat.transparent = v;
        capMat.opacity = v ? 0.24 : 1;
        capMat.depthWrite = !v;
        capMat.needsUpdate = true;
        walls.castShadow = !v;
      },
      setWalking: (v: boolean) => { if (v) enterWalk(); else if (walker.on) leaveWalk(); },
    };

    if (controlRef) controlRef.current = {
      fit: () => api.current?.reset(),
      snapshot: () => { renderer.render(scene, camera); return renderer.domElement.toDataURL('image/jpeg', 0.85); },
      motion: (dx, dy, factor) => {
        if (walker.on) leaveWalk();
        state.dist = Math.max(2, Math.min(radius * 6, state.dist / factor));
        const right = new THREE.Vector3().subVectors(camera.position, target).cross(new THREE.Vector3(0, 1, 0)).normalize();
        target.addScaledVector(right, dx * state.dist * 0.0016);
        target.y = Math.max(0, target.y - dy * state.dist * 0.0016);
        place();
      },
    };
    return () => {
      if (controlRef) controlRef.current = null;
      cancelAnimationFrame(raf);
      ro.disconnect();
      document.removeEventListener("pointerlockchange", lockChange);
      if (document.pointerLockElement === dom) document.exitPointerLock?.();
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
      dom.removeEventListener("pointerdown", down);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      dom.removeEventListener("wheel", wheel);
      dom.removeEventListener("click", click as any);
      renderer.dispose();
      sky.dispose();
      env.texture.dispose();
      sleeveGeo.dispose();
      scene.traverse((o: any) => { o.geometry?.dispose?.(); o.material?.dispose?.(); });
      el.removeChild(renderer.domElement);
    };
    // modellen byggs en gång per öppning; resten är imperativt inuti scenen
  }, [model]);

  useEffect(() => { api.current?.setExploded(exploded); }, [exploded]);
  useEffect(() => { api.current?.setLabels(labels); }, [labels]);
  useEffect(() => { api.current?.setXray(xray); }, [xray]);
  useEffect(() => { api.current?.setWalking(walking); }, [walking]);

  return (
    <div className="d3-wrap" role="dialog" aria-label={tr("Ritningen i tre dimensioner")}>
      <div ref={host} className="d3-canvas" />
      <div className="d3-top">
        <div className="d3-title">
          <b>{title || "Ritningen i 3D"}</b>
          <span className="muted small">
            {model.stats.walls} väggdelar · {model.stats.pipes} rörsträckor · {model.stats.metres} m
            {result.manualExtensions > 0 && <> · {result.manualExtensions} sparade förlängningar</>}
            {model.scaled ? "" : " · bladet saknar skala, måtten är ritningens punkter"}
          </span>
        </div>
        <button className="secondary small" onClick={() => { setWalking(false); onClose(); }}>{tr("Tillbaka till 2D")}</button>
      </div>
      {walking && <div className="d3-cross" aria-hidden="true" />}
      <Drawing3DControls
        onView={(v) => api.current?.view(v)}
        onReset={() => api.current?.reset()}
        onSpin={(d) => api.current?.spin(d)}
        exploded={exploded}
        onExploded={setExploded}
        labels={labels}
        onLabels={setLabels}
        xray={xray}
        onXray={setXray}
        walking={walking}
        onWalk={setWalking}
      />
      {picked && (
        <aside className="d3-info">
          <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
            <b>{picked.kind === "ror" ? (picked.pipe.designation || "Rör") : "Vägg"}</b>
            <button className="ghost small" onClick={() => setPicked(null)}>{tr("Stäng")}</button>
          </div>
          {picked.kind === "ror" ? (
            <>
              <table className="qty"><tbody>
                <tr><td>Typ</td><td className="num">{picked.pipe.inWall ? "Rör genom vägg" : "Rör"}</td></tr>
                {picked.pipe.system && <tr><td>System</td><td className="num">{picked.pipe.system}</td></tr>}
                <tr><td>Dimension</td><td className="num">DN{picked.pipe.dn ?? "?"}</td></tr>
                <tr><td>{tr("Denna sträcka")}</td><td className="num">{picked.pipe.meters.toFixed(2)} m</td></tr>
                <tr><td>{tr("Antaget material")}</td><td className="num">{MEDIUM_TEXT[mediumOf(picked.pipe.system)]}</td></tr>
                <tr><td>{tr("Ritad höjd")}</td><td className="num">
                  {bandOf(picked.pipe.system, systems, model.floorHeight).toFixed(2)} m
                </td></tr>
                {picked.qty && <>
                  <tr><td>{tr("Hela beteckningen")}</td><td className="num">{Number(picked.qty.confirmed_total_m ?? 0).toFixed(2)} m</td></tr>
                  <tr><td>{tr("Sträckor")}</td><td className="num">{picked.qty.physical_pipe_count}</td></tr>
                  <tr><td>Etiketter</td><td className="num">{picked.qty.label_count ?? 0}</td></tr>
                  {picked.qty.riser_count > 0 && <tr><td>Stigare</td><td className="num">{picked.qty.riser_count}</td></tr>}
                </>}
              </tbody></table>
              <p className="muted small" style={{ marginBottom: 0 }}>
                Mängden kommer från läsningens tabell, inte ur 3D-modellen. Ett tunt rör ritas grövre än det är
                för att synas; dimensionen ovan är ritningens. Materialet är gissat ur systembokstäverna och
                står inte på bladet. Höjden är inte heller mätt - bladet är en plan och har ingen. Systemen
                läggs i band så att korsande rör går att skilja åt, och raden säger vilket band det här röret
                ritades i.
              </p>
            </>
          ) : (
            <>
              <table className="qty"><tbody>
                <tr><td>Typ</td><td className="num">{tr("Vägg")}</td></tr>
                <tr><td>{tr("Längd")}</td><td className="num">
                  {Math.hypot(picked.wall.b[0] - picked.wall.a[0], picked.wall.b[1] - picked.wall.a[1]).toFixed(2)} m
                </td></tr>
                <tr><td>Tjocklek</td><td className="num">{(picked.wall.thickness * 1000).toFixed(0)} mm</td></tr>
                <tr><td>{tr("Höjd")}</td><td className="num">{picked.wall.height.toFixed(2)} m</td></tr>
                <tr><td>{tr("Yta, en sida")}</td><td className="num">
                  {(Math.hypot(picked.wall.b[0] - picked.wall.a[0], picked.wall.b[1] - picked.wall.a[1])
                    * picked.wall.height).toFixed(2)} m²
                </td></tr>
              </tbody></table>
              <p className="muted small" style={{ marginBottom: 0 }}>
                Väggen är rest ur arkitektens streck och har ingen mängd i läsningen. Höjden är den antagna
                våningshöjden, tjockleken avståndet mellan väggens två linjer.
              </p>
            </>
          )}
        </aside>
      )}
      {!ready && <div className="d3-loading"><span /></div>}
    </div>
  );
}
