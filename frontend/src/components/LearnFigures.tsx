import { t as tr } from "../i18n";
/* Levande infografik för akademin.
 *
 * Varje figur visar en sak som händer, inte en bild av den: vattnet rinner, hänvisningslinjen ritar sig själv,
 * pappret krymper och skalan går fel. Allt är SVG med CSS-animering, så det väger ingenting och stannar av sig
 * själv för den som bett om mindre rörelse.
 */

function Ttl({ x, y, t }: { x: number; y: number; t: string }) {
  return <text x={x} y={y} className="lfa-cap">{t}</text>;
}

/* ---------- 01 systemen: tryck mot självfall ---------- */
function Flow() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Tryckledningar går åt alla håll, självfall måste luta")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <Ttl x={30} y={40} t="TRYCK — GÅR ÅT ALLA HÅLL" />
      <path className="lfa-pipe kv" d="M40 70 H220 V120 H400 V70 H600" />
      <path className="lfa-pipe vv" d="M40 96 H196 V146 H400 V96 H600" />
      <Ttl x={30} y={196} t="SJÄLVFALL — MÅSTE LUTA HELA VÄGEN" />
      <path className="lfa-pipe s" d="M40 214 L600 262" />
      <circle className="lfa-drop" r="6" cx="0" cy="0">
        <animateMotion dur="3.4s" repeatCount="indefinite" path="M40 214 L600 262" />
      </circle>
      <g className="lfa-fall">
        <path d="M40 214 H600" />
        <path d="M600 214 V262" />
        <text x="606" y="244" className="lfa-cap">fall</text>
      </g>
      <g className="lfa-key">
        <circle cx="46" cy="278" r="4" className="dot kv" /><text x="58" y="282" className="lfa-cap">KV</text>
        <circle cx="106" cy="278" r="4" className="dot vv" /><text x="118" y="282" className="lfa-cap">VV</text>
        <circle cx="166" cy="278" r="4" className="dot s" /><text x="178" y="282" className="lfa-cap">SPILL</text>
      </g>
    </svg>
  );
}

/* ---------- 02 KV, VV, VVC i bunt ---------- */
function Bundle() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Kallvatten, varmvatten och cirkulation dras i bunt")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <path className="lfa-pipe kv" d="M60 96 H520" />
      <path className="lfa-pipe vv" d="M60 140 H520" />
      <path className="lfa-pipe vvc" d="M520 184 H60" />
      <path className="lfa-pipe vvc" d="M520 140 V184" />
      <g className="lfa-lbl">
        <text x="60" y="84" className="lfa-cap">{tr("KV — fram till tappstället")}</text>
        <text x="60" y="128" className="lfa-cap">{tr("VV — fram till tappstället")}</text>
        <text x="60" y="206" className="lfa-cap">{tr("VVC — tillbaka, så varmvattnet inte kallnar")}</text>
      </g>
      <g className="lfa-tap">
        <circle cx="520" cy="96" r="6" /><circle cx="520" cy="140" r="6" />
      </g>
      <g className="lfa-zoom">
        <rect x="250" y="72" width="120" height="132" rx="8" />
        <text x="60" y="246" className="lfa-cap">{tr("i schaktet ligger de några cm isär — bara etiketten skiljer dem åt")}</text>
      </g>
    </svg>
  );
}

/* ---------- 03 stammen: vatten ned, luft upp ---------- */
function Stack() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Vatten faller i stammen medan luft går upp genom den")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g className="lfa-house"><path d="M180 40 H460 V270 H180 Z M180 110 H460 M180 180 H460" /></g>
      <path className="lfa-pipe s" d="M320 40 V270" />
      <path className="lfa-pipe s" d="M240 96 H320" />
      <path className="lfa-pipe s" d="M240 166 H320" />
      <circle className="lfa-drop" r="6" cx="0" cy="0">
        <animateMotion dur="2.2s" repeatCount="indefinite" path="M320 60 V264" />
      </circle>
      <g className="lfa-air">
        <path d="M356 260 V56" />
        <path d="M350 66 L356 52 L362 66" />
      </g>
      <Ttl x={372} y={70} t="LUFT UPP — ANNARS SUGS VATTENLÅSEN TOMMA" />
      <Ttl x={188} y={288} t="VATTEN NED MED SJÄLVFALL" />
    </svg>
  );
}

/* ---------- 04 beteckningen sätts ihop ---------- */
function Code() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Beteckningen KV1-X31-16 byggs ihop av sina tre delar")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g className="lfa-code">
        <g className="p1"><text x="180" y="120" className="lfa-big">KV1</text></g>
        <g className="p2"><text x="292" y="120" className="lfa-big">X31</text></g>
        <g className="p3"><text x="404" y="120" className="lfa-big">16</text></g>
        <g className="dash"><text x="268" y="120" className="lfa-big dim">-</text><text x="380" y="120" className="lfa-big dim">-</text></g>
      </g>
      <g className="lfa-code-cap">
        <g className="p1"><path d="M212 140 V186" /><text x="222" y="190" className="lfa-cap">{tr("SYSTEM · tappkallvatten 1")}</text></g>
        <g className="p2"><path d="M324 140 V222" /><text x="334" y="226" className="lfa-cap">{tr("MATERIAL · står i bladets lista")}</text></g>
        <g className="p3"><path d="M424 140 V258" /><text x="434" y="262" className="lfa-cap">{tr("DIMENSION · 16 mm")}</text></g>
      </g>
    </svg>
  );
}

/* ---------- 05 DN mot dy ---------- */
function DnDy() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("DN mäter ungefär insidan, dy mäter utsidan")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g transform="translate(150 150)">
        <circle r="74" className="lfa-wall" /><circle r="58" className="lfa-bore" />
        <g className="lfa-meas dy"><path d="M-74 104 H74" /><path d="M-74 96 V112" /><path d="M74 96 V112" /></g>
        <text x="0" y="136" className="lfa-cap mid">{tr("dy — ytterdiameter")}</text>
        <text x="0" y="-96" className="lfa-cap mid">{tr("plast och koppar")}</text>
      </g>
      <g transform="translate(450 150)">
        <circle r="74" className="lfa-wall" /><circle r="58" className="lfa-bore" />
        <g className="lfa-meas dn"><path d="M-58 104 H58" /><path d="M-58 96 V112" /><path d="M58 96 V112" /></g>
        <text x="0" y="136" className="lfa-cap mid">{tr("DN — ungefär insidan")}</text>
        <text x="0" y="-96" className="lfa-cap mid">{tr("stål och gjutjärn")}</text>
      </g>
      <text x="320" y="284" className="lfa-cap mid">{tr("samma tal, två olika mått — fel material i kalkylen, inte fel längd")}</text>
    </svg>
  );
}

/* ---------- 06 bladets delar tänds i tur och ordning ---------- */
function Sheet() {
  const parts = [
    { d: "M40 40 H600 V250 H40 Z", t: "PLANEN", x: 48, y: 34 },
    { d: "M440 190 H596 V246 H440 Z", t: "STÄMPELN", x: 448, y: 184 },
    { d: "M46 46 H150 V150 H46 Z", t: "FÖRKLARINGSLISTAN", x: 54, y: 168 },
    { d: "M200 214 H330 V244 H200 Z", t: "SKALSTOCKEN", x: 208, y: 262 },
  ];
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Ritningens delar, en i taget")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g className="lfa-house"><path d="M40 40 H600 V250 H40 Z M300 40 V250 M40 150 H300" /></g>
      {parts.map((p, i) => (
        <g key={p.t} className="lfa-part" style={{ animationDelay: `${i * 1.5}s` }}>
          <path d={p.d} />
          <text x={p.x} y={p.y} className="lfa-cap">{p.t}</text>
        </g>
      ))}
    </svg>
  );
}

/* ---------- 07 skalan: pappret krymper, den utskrivna skalan blir fel ---------- */
function Scale() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Skalstocken följer pappret, den utskrivna skalan gör det inte")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      {/* the sheet, printed smaller than it was drawn: the bar shrinks with the paper, the words do not */}
      <g className="lfa-shrink">
        <rect className="lfa-sheet" x="40" y="34" width="290" height="150" rx="4" />
        <text x="56" y="66" className="lfa-mono">SKALA 1:50</text>
        <g className="lfa-bar">
          <path d="M56 110 H300" />
          {[0, 48.8, 97.6, 146.4, 195.2, 244].map((x, i) => <path key={i} d={`M${56 + x} 98 V122`} />)}
        </g>
        <text x="56" y="146" className="lfa-cap">0</text>
        <text x="272" y="146" className="lfa-cap">15 m</text>
      </g>
      <g className="lfa-arrow">
        <path d="M348 110 H392" /><path d="M382 102 L392 110 L382 118" />
      </g>
      <g className="lfa-said">
        <text x="410" y="70" className="lfa-cap">SÄGER 1:50</text>
        <text x="410" y="96" className="lfa-cap warn">{tr("men pappret är halverat")}</text>
        <text x="410" y="128" className="lfa-cap">SKALSTOCKEN</text>
        <text x="410" y="154" className="lfa-cap ok">{tr("krympte med — den gäller")}</text>
      </g>
      <text x="40" y="236" className="lfa-cap">Ett A1-blad utskrivet på A3: allt är hälften så stort.</text>
      <text x="40" y="262" className="lfa-cap">{tr("Den utskrivna skalan står kvar och blir fel.")}</text>
      <text x="40" y="288" className="lfa-cap ok">{tr("Skalstocken ligger på samma papper och kan inte ljuga.")}</text>
    </svg>
  );
}

/* ---------- 08 stigaren: en ring i planen är en våning i sektionen ---------- */
function Riser() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("En ring i planen är en ledning som går mellan våningar")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <Ttl x={40} y={38} t="PLAN" />
      <g className="lfa-house"><path d="M40 50 H280 V250 H40 Z" /></g>
      <path className="lfa-pipe s" d="M70 200 H160 V130" />
      <g className="lfa-ring"><circle cx="160" cy="122" r="11" /></g>
      <Ttl x={176} y={126} t="STIGARE" />
      <Ttl x={370} y={38} t="SEKTION" />
      <g className="lfa-house"><path d="M370 50 H600 V250 H370 Z M370 116 H600 M370 182 H600" /></g>
      <path className="lfa-pipe s riser" d="M470 246 V60" />
      <g className="lfa-floor"><path d="M470 246 H600" /><path d="M470 182 H600" /><path d="M470 116 H600" /></g>
      <text x="500" y="278" className="lfa-cap">{tr("höjden står inte på ritningen — antalet räknas, höjden matas in")}</text>
    </svg>
  );
}

/* ---------- 09 lagren separerar ---------- */
function Layers() {
  // The plates step down and to the right; every caption sits in its own row in a column of its own, joined to
  // its plate by a short rule. An earlier version put all four captions at the same x inside each plate's own
  // frame, so they landed on top of each other and the last one ran off the paper.
  const L = [
    { t: "BYGGNAD", d: "M0 0 H196 V112 H0 Z M98 0 V112 M0 60 H98", c: "b" },
    { t: "SPILLVATTEN", d: "M18 90 H112 V30 H180", c: "s" },
    { t: "TAPPVATTEN", d: "M18 46 H82 V96 H180", c: "kv" },
    { t: "TEXT OCH LEDARLINJER", d: "M32 20 H106 M106 24 L82 48", c: "t" },
  ];
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Varje sorts geometri på sitt eget lager")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g className="lfa-deck">
        {L.map((l, i) => (
          // the position is on the outer group and the animation on the inner one: a CSS transform replaces an
          // SVG transform attribute outright, so animating the same element flattened all four plates onto each
          // other for most of the cycle - which is exactly what it looked like
          <g key={l.t} transform={`translate(${44 + i * 26} ${26 + i * 44})`}>
            <g className={`lfa-layer ${l.c}`} style={{ animationDelay: `${i * 0.25}s` }}>
              <path className="plate" d="M0 0 H196 V112 H0 Z" />
              <path className="art" d={l.d} />
            </g>
          </g>
        ))}
      </g>
      <g className="lfa-deck-key">
        {L.map((l, i) => (
          <g key={l.t} className={`k ${l.c}`} style={{ animationDelay: `${0.3 + i * 0.14}s` }}
            transform={`translate(404 ${68 + i * 46})`}>
            <path d="M-42 -4 H-10" />
            <rect x="-6" y="-13" width="12" height="12" rx="2" />
            <text x="16" y="-3" className="lfa-cap">{l.t}</text>
          </g>
        ))}
      </g>
      <text x="44" y="276" className="lfa-cap">{tr("ett lager per system — och byggnaden för sig")}</text>
    </svg>
  );
}

/* ---------- 10 hänvisningslinjen ritar sig själv, och missar ---------- */
function Leader() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("En hänvisningslinje som träffar röret, och en som inte gör det")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g transform="translate(0 -6)">
        <path className="lfa-pipe kv" d="M44 116 H280" />
        <rect className="lfa-tag" x="44" y="50" width="128" height="26" rx="4" />
        <text x="54" y="68" className="lfa-mono sm">KV1-X31-16</text>
        <path className="lfa-lead draw" d="M172 64 L196 116" />
        <circle className="lfa-hit" cx="196" cy="116" r="5" />
        <text x="44" y="150" className="lfa-cap ok">{tr("slutar PÅ röret — sträckan får sitt namn")}</text>
      </g>
      <g transform="translate(0 118)">
        <path className="lfa-pipe kv" d="M44 116 H280" />
        <rect className="lfa-tag" x="44" y="50" width="128" height="26" rx="4" />
        <text x="54" y="68" className="lfa-mono sm">KV1-X31-16</text>
        <path className="lfa-lead draw miss" d="M172 64 L194 100" />
        <circle className="lfa-miss" cx="194" cy="100" r="5" />
        <text x="44" y="150" className="lfa-cap warn">{tr("slutar i luften — sträckan blir onämnd")}</text>
      </g>
      <g className="lfa-split-rule"><path d="M312 36 V266" /></g>
      <g className="lfa-note-col">
        <text x="336" y="118" className="lfa-cap">{tr("För ögat är skillnaden")}</text>
        <text x="336" y="142" className="lfa-cap">{tr("några millimeter.")}</text>
        <text x="336" y="180" className="lfa-cap">{tr("För en mängdning är den")}</text>
        <text x="336" y="204" className="lfa-cap">{tr("skillnaden mellan en sträcka")}</text>
        <text x="336" y="228" className="lfa-cap">{tr("som räknas och en som inte gör det.")}</text>
      </g>
    </svg>
  );
}

/* ---------- 11 mängden räknas fram ---------- */
function Takeoff() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("En sträcka spåras och metrarna räknas fram")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g className="lfa-house"><path d="M40 40 H400 V260 H40 Z M220 40 V260" /></g>
      <path className="lfa-pipe kv ghost" d="M70 220 H180 V90 H370" />
      <path className="lfa-pipe kv trace" d="M70 220 H180 V90 H370" />
      <g className="lfa-tally">
        <rect x="430" y="70" width="176" height="64" rx="10" />
        <text x="446" y="102" className="lfa-num">17,10 m</text>
        <text x="446" y="122" className="lfa-cap">KV1-X31-16</text>
      </g>
      <g className="lfa-tally two">
        <rect x="430" y="150" width="176" height="64" rx="10" />
        <text x="446" y="182" className="lfa-num">{tr("2 st")}</text>
        <text x="446" y="202" className="lfa-cap">{tr("stigare — höjd matas in")}</text>
      </g>
    </svg>
  );
}

/* ---------- 12 egenkontrollen ---------- */
function Checks() {
  const rows: [string, number, boolean][] = [
    ["täckning · hur mycket av det ritade fick ett namn", 0.86, true],
    ["rimlighet · meter mot husets storlek", 0.72, true],
    ["systembalans · KV mot VV", 0.34, false],
    ["ändar · varje sträcka slutar i något", 0.94, true],
  ];
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Fyra egenkontroller som fångar nästan alla fel")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      {rows.map(([t, v, ok], i) => (
        <g key={t} transform={`translate(40 ${58 + i * 58})`}>
          <text x="0" y="-8" className="lfa-cap">{t}</text>
          <rect className="lfa-track" x="0" y="0" width="560" height="10" rx="5" />
          <rect className={`lfa-fill${ok ? "" : " bad"}`} x="0" y="0" height="10" rx="5"
            style={{ ["--w" as any]: `${v * 560}px`, animationDelay: `${i * 0.25}s` }} />
        </g>
      ))}
      <text x="40" y="288" className="lfa-cap warn">{tr("en balans som halkar är nästan alltid sträckor utan namn")}</text>
    </svg>
  );
}

/* ---------- 13 komponenten är inte ett rör ---------- */
function Parts() {
  // Two bands, one above the other. Side by side the two headings ran into each other and the right-hand
  // captions fell off the paper: a caption in a 640-wide frame has to have the width to itself.
  const sys = ["KV1-X31-16", "VV1-X31-16", "S3-R8-110"];
  const tag = ["BL113", "B241", "AV21-20"];
  return (
    <svg viewBox="0 0 640 348" role="img" aria-label={tr("Systemkoder öppnar dimensionerade beteckningar, komponentkoder står ensamma")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="336" rx="10" />
      <text x="36" y="36" className="lfa-cap ok">{tr("MED DIMENSION, OCH EN LINJE TILL ETT RÖR → RÖRSYSTEM")}</text>
      {sys.map((t, i) => (
        <g key={t} className="lfa-row" style={{ animationDelay: `${i * 0.16}s` }} transform={`translate(36 ${50 + i * 34})`}>
          <rect className="lfa-tag" x="0" y="0" width="150" height="26" rx="4" />
          <text x="10" y="18" className="lfa-mono sm">{t}</text>
          <path className="lfa-pipe kv" d="M162 13 H400" />
          <text x="416" y="18" className="lfa-cap">{tr("mäts i meter")}</text>
        </g>
      ))}
      <g className="lfa-split-rule"><path d="M36 170 H604" /></g>
      <text x="36" y="200" className="lfa-cap warn">{tr("STÅR ENSAM UTE PÅ BLADET → KOMPONENT")}</text>
      {tag.map((t, i) => (
        <g key={t} className="lfa-row" style={{ animationDelay: `${0.25 + i * 0.16}s` }} transform={`translate(36 ${214 + i * 34})`}>
          <rect className="lfa-tag" x="0" y="0" width="150" height="26" rx="4" />
          <text x="10" y="18" className="lfa-mono sm">{t}</text>
          <g className="lfa-fitting" transform="translate(186 13)">
            <circle r="11" />
            <path d="M-6 0 H6 M0 -6 V6" />
          </g>
          <text x="416" y="18" className="lfa-cap">{tr("räknas som antal")}</text>
        </g>
      ))}
      <text x="36" y="332" className="lfa-cap">{tr("bladets förklaringslista säger vilket varje kod är")}</text>
    </svg>
  );
}

/* ---------- 14 isoleringen ligger utanpå ---------- */
function Insul() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Isoleringen ligger utanpå röret och ändrar inte dimensionen")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g transform="translate(120 128)">
        <circle className="lfa-shell" r="60" />
        <circle className="lfa-shell two" r="44" />
        <circle className="lfa-bore" r="26" />
        <circle className="lfa-bore inner" r="20" />
      </g>
      <g className="lfa-meas dy">
        <path d="M120 40 V62 M96 51 H144 M96 45 V57 M144 45 V57" />
        <text x="150" y="55" className="lfa-cap">{tr("dy — utsida")}</text>
      </g>
      <g className="lfa-meas dn">
        <path d="M120 216 V238 M100 227 H140 M100 221 V233 M140 221 V233" />
        <text x="150" y="231" className="lfa-cap">{tr("DN — insida")}</text>
      </g>
      <g className="lfa-split-rule"><path d="M272 40 V266" /></g>
      <g className="lfa-note-col">
        <text x="296" y="86" className="lfa-cap">{tr("Isolerklassen står i beteckningen,")}</text>
        <text x="296" y="110" className="lfa-cap">oftast sist: <tspan className="lfa-mono sm">VS21-S13-15-F50</tspan></text>
        <text x="296" y="150" className="lfa-cap">{tr("Den säger hur tjockt skalet är.")}</text>
        <text x="296" y="174" className="lfa-cap">{tr("Den ändrar inte dimensionen,")}</text>
        <text x="296" y="198" className="lfa-cap">{tr("och den ändrar inte metrarna.")}</text>
        <text x="296" y="238" className="lfa-cap warn">{tr("Ett rör med två isolerklasser är")}</text>
        <text x="296" y="262" className="lfa-cap warn">{tr("två rader i mängden, inte en.")}</text>
      </g>
    </svg>
  );
}

/* ---------- 15 stigaren: en punkt i planen, en höjd i huset ---------- */
function Riser2() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("En stigare är en punkt i planen och en höjd i sektionen")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <text x="40" y="40" className="lfa-cap">{tr("I PLANEN — EN PUNKT")}</text>
      <g className="lfa-house"><path d="M40 56 H270 V250 H40 Z" /></g>
      <path className="lfa-pipe s" d="M60 200 H176" />
      <g className="lfa-ring"><circle cx="176" cy="200" r="8" /></g>
      <g transform="translate(112 88)">
        <rect className="lfa-tag" x="0" y="0" width="104" height="44" rx="4" />
        <text x="10" y="19" className="lfa-mono sm">S2-P5</text>
        <text x="10" y="37" className="lfa-mono sm">110</text>
        <path className="lfa-underline" d="M10 24 H58" />
      </g>
      <path className="lfa-lead draw" d="M164 132 L176 194" />
      <text x="40" y="274" className="lfa-cap">{tr("dimensionen på raden under → stigare")}</text>

      <g className="lfa-split-rule"><path d="M300 30 V270" /></g>
      <text x="330" y="40" className="lfa-cap">{tr("I HUSET — EN HÖJD")}</text>
      <g className="lfa-floor2"><path d="M330 76 H600 M330 138 H600 M330 200 H600 M330 250 H600" /></g>
      <path className="lfa-pipe s riser" d="M470 250 V76" />
      <g className="lfa-tally">
        <rect x="500" y="96" width="112" height="58" rx="8" />
        <text x="514" y="124" className="lfa-num">{tr("3 st")}</text>
        <text x="514" y="144" className="lfa-cap">{tr("× våningshöjd")}</text>
      </g>
      <text x="330" y="274" className="lfa-cap warn">{tr("ritningen anger nästan aldrig höjden — antalet räknas, höjden matas in")}</text>
    </svg>
  );
}

/* ---------- 16 samma beteckning, två skrivsätt ---------- */
function Rows() {
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("En rad betyder sträcka, två rader betyder stigare")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <g transform="translate(46 56)">
        <rect className="lfa-tag" x="0" y="0" width="168" height="30" rx="4" />
        <text x="12" y="20" className="lfa-mono sm">S2-P5-110</text>
        <text x="0" y="56" className="lfa-cap ok">{tr("ALLT PÅ EN RAD")}</text>
        <text x="0" y="80" className="lfa-cap">{tr("en sträcka i planet")}</text>
        <text x="0" y="104" className="lfa-cap">{tr("mäts i meter")}</text>
        <path className="lfa-pipe s" d="M0 138 H236" />
        <g className="lfa-tally"><rect x="0" y="160" width="130" height="46" rx="8" />
          <text x="14" y="190" className="lfa-num">12,4 m</text></g>
      </g>
      <g className="lfa-split-rule"><path d="M330 36 V266" /></g>
      <g transform="translate(360 56)">
        <rect className="lfa-tag" x="0" y="0" width="112" height="48" rx="4" />
        <text x="12" y="20" className="lfa-mono sm">S2-P5</text>
        <text x="12" y="40" className="lfa-mono sm">110</text>
        <path className="lfa-underline" d="M12 26 H62" />
        <text x="0" y="74" className="lfa-cap warn">{tr("DIMENSIONEN PÅ RADEN UNDER")}</text>
        <text x="0" y="98" className="lfa-cap">{tr("en stigare i den punkten")}</text>
        <text x="0" y="122" className="lfa-cap">{tr("räknas som antal")}</text>
        <g className="lfa-ring"><circle cx="60" cy="164" r="8" /></g>
        <g className="lfa-tally two"><rect x="0" y="188" width="130" height="46" rx="8" />
          <text x="14" y="218" className="lfa-num">{tr("1 st")}</text></g>
      </g>
    </svg>
  );
}

/* ---------- 17 vad som händer när en kod saknas i listan ---------- */
function Vocab() {
  const rows: [string, string, string][] = [
    ["KV01", "TAPPKALLVATTEN", "system"],
    ["VS21", "VÄRME FRAM", "system"],
    ["BLXXX", "BLANDARE", "component"],
    ["BXXX", "GOLVBRUNN", "component"],
    ["S13", "STÅLRÖR", "material"],
    ["F50", "ISOLERKLASS 50", "material"],
  ];
  return (
    <svg viewBox="0 0 640 300" role="img" aria-label={tr("Förklaringslistan säger vad varje kod är")}>
      <rect className="lfa-paper" x="6" y="6" width="628" height="288" rx="10" />
      <text x="36" y="42" className="lfa-cap">{tr("BLADETS EGEN FÖRKLARINGSLISTA")}</text>
      {rows.map(([c, d, role], i) => (
        <g key={c} className="lfa-row" style={{ animationDelay: `${i * 0.13}s` }} transform={`translate(36 ${58 + i * 36})`}>
          <text x="0" y="18" className="lfa-mono sm">{c}</text>
          <text x="74" y="18" className="lfa-cap">{d}</text>
          <g className={`lfa-role ${role}`} transform="translate(232 4)">
            <rect x="0" y="0" width="104" height="20" rx="10" />
            <text x="11" y="14" className="lfa-cap">
              {role === "system" ? "rörsystem" : role === "component" ? "komponent" : "material"}
            </text>
          </g>
        </g>
      ))}
      <g className="lfa-split-rule"><path d="M400 40 V266" /></g>
      <g className="lfa-note-col">
        <text x="424" y="92" className="lfa-cap">{tr("Listan är bladets")}</text>
        <text x="424" y="116" className="lfa-cap">{tr("eget ordförråd.")}</text>
        <text x="424" y="158" className="lfa-cap">{tr("En omgång skriver")}</text>
        <text x="424" y="182" className="lfa-cap">{tr("den en gång, på ett")}</text>
        <text x="424" y="206" className="lfa-cap">{tr("blad, och låter")}</text>
        <text x="424" y="230" className="lfa-cap">{tr("resten stå på den.")}</text>
      </g>
    </svg>
  );
}

const FIGS: Record<string, () => JSX.Element> = {
  flow: Flow, bundle: Bundle, stack: Stack, code: Code, dndy: DnDy, sheet: Sheet,
  scale: Scale, riser: Riser, layers: Layers, leader: Leader, takeoff: Takeoff, checks: Checks,
  parts: Parts, insul: Insul, riser2: Riser2, rows: Rows, vocab: Vocab,
};

export default function LearnFigure({ id }: { id: string }) {
  const F = FIGS[id];
  return F ? <div className="lfa"><F /></div> : null;
}

export const FIGURE_IDS = Object.keys(FIGS);
