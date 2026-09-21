/* Varje översättningsanrop ska nå ordboken - och ingenting annat.
 *
 * Det här provet finns därför att tsc och eslint båda missade samma fel. `t` är ett vanligt lokalt namn i
 * den här koden: en tidtagare, en interpolationsfaktor, ett tillstånd. Där ett lokalt `t` låg i samma
 * räckvidd som ett inlagt `t("...")` pekade anropet på det lokala värdet, och var det värdet `any` såg tsc
 * ingenting. I adminöversikten var det `const [t, setT] = useState<any>(null)`, och elva rader anropade
 * `t("Laddar...")` - alltså `null("Laddar...")`, en sida som kastar direkt när den monteras. eslint teg,
 * för importen användes på tjugo andra ställen i samma fil.
 *
 * Ett textsökande prov kan inte se skillnaden. Det här bygger programmet och frågar typkontrollen vilken
 * symbol varje anrop faktiskt går till. Det är den enda formuleringen av kravet som är sann.
 *
 *     node tools/i18n_check.mjs
 */
import ts from "typescript";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "src");
const BIND = "tr";                     // namnet ordboken har i koden; se docs/SPRAK.md
const FMT = "trf";                     // samma ordbok, för en mening med tal i sig
const NAMES = new Set(["t", BIND, FMT]);  // båda fångas: ett kvarglömt `t(` ska också falla ut
// `trf` bär talen i nyckeln som {0}, {1}; `tr` får inte bära någon platshållare alls, för en sådan nyckel
// skulle slås upp med talet redan isatt och aldrig kunna träffa en rad.
const HOLE = /\$\{|\{\s*[A-Za-z_]/;
const NUMBERED = /\{\s*\d+\s*\}/;

const isDict = (f) => /[\\/]src[\\/]i18n(\.tsx?|[\\/])/.test(f);
const rel = (f) => path.relative(ROOT, f).replace(/\\/g, "/");

function modules(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== "node_modules") modules(p, out); }
    else if (/\.tsx?$/.test(e.name)) out.push(p);
  }
  return out;
}

const program = ts.createProgram(modules(SRC), {
  jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler, noEmit: true, skipLibCheck: true,
});
const checker = program.getTypeChecker();

const fel = [];
let anrop = 0;
const nycklar = new Set();

for (const sf of program.getSourceFiles()) {
  if (!sf.fileName.startsWith(SRC) || sf.fileName.includes("node_modules")) continue;
  const at = (n) => `${rel(sf.fileName)}:${sf.getLineAndCharacterOfPosition(n.getStart()).line + 1}`;
  const importsDict = sf.statements.some(
    (s) => ts.isImportDeclaration(s) && ts.isStringLiteral(s.moduleSpecifier) && /\bi18n$/.test(s.moduleSpecifier.text));

  const visit = (n) => {
    // (a) anropet: går det till ordboken?
    // Namnet `tr` tillhör ordboken vad det än får för argument; ett bart `t` bara när argumentet är en
    // sträng, för `t` är också ett hederligt lokalt namn för en tidtagare eller en funktion.
    if (ts.isCallExpression(n) && ts.isIdentifier(n.expression) && NAMES.has(n.expression.text)
        && (n.expression.text !== "t" || (n.arguments.length && ts.isStringLiteral(n.arguments[0])))) {
      anrop++;
      let sym = checker.getSymbolAtLocation(n.expression);
      if (sym && (sym.flags & ts.SymbolFlags.Alias)) { try { sym = checker.getAliasedSymbol(sym); } catch { /* ohittad */ } }
      const decl = sym?.declarations?.[0];
      const where = decl ? decl.getSourceFile().fileName : "";
      const key = n.arguments.length && ts.isStringLiteral(n.arguments[0]) ? n.arguments[0].text : null;
      if (!decl || !isDict(where)) {
        fel.push(`${at(n)}  ${n.expression.text}(${key === null ? "…" : `"${key.slice(0, 40)}"`}) går till `
               + (decl ? `${rel(where)}:${decl.getSourceFile().getLineAndCharacterOfPosition(decl.getStart()).line + 1}` : "ingenting")
               + ", inte till ordboken");
      } else if (key !== null) {
        nycklar.add(key);
        // (d) en nyckel med en platshållare kan aldrig träffa en rad i ordboken
        const called = n.expression.text;
        if (HOLE.test(key) || (called !== FMT && NUMBERED.test(key)))
          fel.push(`${at(n)}  nyckeln "${key.slice(0, 40)}" bär en platshållare och kan aldrig slås upp`
                 + (called !== FMT ? ` - använd ${FMT}() om talen ska in i meningen` : ""));
      }
    }
    // (b) skuggningen vid källan: ett lokalt `tr` i en fil som importerar ordboken
    if ((ts.isVariableDeclaration(n) || ts.isParameter(n) || ts.isBindingElement(n) || ts.isFunctionDeclaration(n))
        && n.name && ts.isIdentifier(n.name) && (n.name.text === BIND || n.name.text === FMT) && importsDict) {
      const sym = checker.getSymbolAtLocation(n.name);
      if (!sym?.declarations?.some((d) => isDict(d.getSourceFile().fileName))) {
        fel.push(`${at(n)}  ett lokalt "${n.name.text}" i en fil som importerar ordboken: döp om det`);
      }
    }
    ts.forEachChild(n, visit);
  };
  visit(sf);
}

// (e) ett hårdkodat språkband utanför språkmodulen: 12,5 m på en engelsk sida, eller 12.5 på en svensk
for (const f of modules(SRC)) {
  if (isDict(f)) continue;
  const src = fs.readFileSync(f, "utf8");
  for (const m of src.matchAll(/"(sv-SE|en-GB|en-US)"/g)) {
    const line = src.slice(0, m.index).split("\n").length;
    fel.push(`${rel(f)}:${line}  ${m[0]} står utanför språkmodulen - använd locale()`);
  }
}

// (c) samma nyckel definierad två gånger med olika engelska
const rader = new Map();
for (const f of modules(SRC).filter((f) => isDict(f))) {
  // en rad som inte fick plats bryts efter kolonet; läs den som om den stod på en rad
  const src = fs.readFileSync(f, "utf8").replace(/":\n\s+"/g, '": "');
  for (const m of src.matchAll(/^\s{2}"((?:[^"\\]|\\.)*)":\s*"((?:[^"\\]|\\.)*)",?\s*$/gm)) {
    // nyckeln i källan är en JS-sträng: `\\n` står som två tecken där och som en radbrytning i anropet
    let k, v;
    try { k = JSON.parse(`"${m[1]}"`); v = JSON.parse(`"${m[2]}"`); } catch { continue; }
    if (rader.has(k) && rader.get(k).v !== v) fel.push(`ordboken: "${k.slice(0, 40)}" står i både ${rader.get(k).f} och ${rel(f)} med olika engelska`);
    rader.set(k, { v, f: rel(f) });
  }
}

const utan = [...nycklar].filter((k) => !rader.has(k)).length;
if (fel.length) {
  console.error(`i18n: ${fel.length} fel\n`);
  for (const f of fel) console.error("  " + f);
  console.error("\nSe docs/SPRAK.md.");
  process.exit(1);
}
console.log(`i18n: ${anrop} anrop går till ordboken, 0 avvikande, ${nycklar.size} nycklar, ${rader.size} engelska rader, ${utan} utan engelska`);
