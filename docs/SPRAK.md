# Språket: svenska och engelska, med svenskan som nyckel

Gränssnittet finns på två språk. Det här dokumentet säger hur, vilka ord som gäller på engelska, och vad som
med avsikt inte översätts. Ordlistan i §3 binder både ordboken i appen och de engelska dokumenten i `docs/`,
och den är skriven före översättningsarbetet just därför: två listor som beslutas var för sig blir två olika
listor.

## 1. Regeln

Nyckeln är den svenska texten själv, inte en uppfunnen kod:

```tsx
import { t as tr } from "../i18n";

<h2>{tr("Mängder")}</h2>          // "Mängder" på svenska, "Quantities" på engelska
```

Tre följder, och alla tre är avsiktliga:

* **En sträng utan engelsk rad visas på svenska.** Den försvinner inte, och den visar aldrig sin nyckel.
  Översättning är något man lägger till, aldrig något som kan gå sönder.
* **Koden går att läsa på svenska.** En mängdare och en utvecklare kan tala om samma knapp.
* **Språkbytet laddar om sidan.** `lang` är en modulkonstant, så uppslagningen är synkron och kostar ingenting
  under rendering. Ett halvt omritat gränssnitt där några rader bytt språk och andra inte är värre än att vänta
  en halv sekund.

## 2. Var ordboken ligger

`frontend/src/i18n.ts` håller mekanismen: `lang`, `setLang`, `tr`, `num`, `locale`. Ordboken ligger bredvid,
en del per område, och slås ihop en gång när modulen laddas. Lägg en rad i den del som hör till sidan.

## 3. Ordlistan

Den bindande listan. Den gäller ordboken i appen **och** `docs/PLATFORM.md` och `docs/LIMITATIONS.md`, som är
skrivna på engelska. Termerna är hämtade ur `LIMITATIONS.md`, som satte dem först.

| svenska | engelska | inte |
|---|---|---|
| beteckning | designation | label, tag |
| etikett | label | — |
| hänvisningslinje, ledare | leader | pointer, reference line |
| stråk, dragning | run | stretch, string |
| sträcka (en mätt bit) | stretch | segment |
| rör | pipe | — |
| blad | sheet | page |
| ritning | drawing | — |
| handling | document set | — |
| mängd, mängda | quantity, take off | volume, measure |
| mängdare | estimator | quantity surveyor |
| front (där ett stråk slutar) | frontier | boundary, edge |
| skäl (till att det slutar) | reason | — |
| tvetydig | ambiguous | uncertain, unclear |
| onämnd | unnamed | unlabelled |
| skraffering, skrafferat | hatching, hatched | shading |
| stigare | riser | — |
| bjälklag | floor slab | — |
| våning | storey | floor |
| avgrening | branch | — |
| böj | bend | elbow |
| armatur | fitting | fixture |
| penna | pen | stroke style |
| bunt (staplade etiketter) | bundle | stack, cluster |
| bockmärke, märke | tick | mark |
| vattengång (VG) | invert level | — |
| dimension, DN | DN | diameter |
| förklaringslista | legend | key |
| rättelse | correction | fix, edit |
| lärdom | lesson | training example |
| facit, referens | reference | ground truth, answer key |
| kalkyl | costing | calculation |
| anbud | tender | bid, quote |
| ÄTA | variation order (ÄTA) | change order |
| granskningsrum | review room | — |
| läsning | reading | analysis, scan |
| läsare (andraläsaren) | reader | model, agent |

Två ord som är värda sin egen rad. **Reference**, inte *ground truth*: siffran kommer från en mängdares
mätning, inte från en sanning, och det är hela poängen med hur den används. Och **reading**, inte *analysis*:
systemet läser en ritning som en människa läser den, och ordet ska påminna om det.

## 4. Tal och datum

Svenska skriver 12,5 m och engelska 12.5 m. Det är inte en detalj i en mängd.

```tsx
import { num, locale } from "../i18n";

{num(rad.horisontellt_m, 1)} m               // 12,5 / 12.5
d.toLocaleDateString(locale())               // aldrig "sv-SE" direkt
```

`"sv-SE"` och `"en-GB"` hör hemma i `src/i18n*` och ingen annanstans. En sträng som skrivs ut med
`toFixed(2)` är fel på svenska redan i dag, och `.toFixed(2).replace(".", ",")` är fel på engelska - båda
felen fanns i appen innan språket lades till, och det är `num()` som rättar dem.

## 5. Bindningen heter `tr`, aldrig `t`

Det här är en regel med en historia, och historien är skälet.

`t` är ett vanligt lokalt namn i den här koden: en tidtagare, en interpolationsfaktor, ett tillstånd. I 44
filer finns ett lokalt `t`. När ordboken hette `t` pekade varje anrop som låg i samma räckvidd som ett sådant
lokalt namn på det lokala värdet i stället - och i adminöversikten, där `const [t, setT] = useState<any>(null)`
står tolv rader ovanför elva anrop, betydde det `null("Laddar…")`. Sidan kastade vid montering. `tsc` såg
ingenting, för värdet är `any`, och eslint sa ifrån om en annan fil av en ren tillfällighet.

Därför: **ordboken importeras som `tr`, och inget annat får heta `tr` i en fil som importerar den.**

`frontend/tools/i18n_check.mjs` håller regeln. Det bygger programmet och frågar typkontrollen vart varje
anrop faktiskt går - ett textsökande prov kan inte skilja ett anrop till ordboken från ett anrop till en
tidtagare. Det ligger först i `npm run build`:

```
node tools/i18n_check.mjs
i18n: 1 110 anrop går till ordboken, 0 avvikande, 967 nycklar, 152 engelska rader, 829 utan engelska
```

Det säger ifrån om ett anrop går någon annanstans, om ett lokalt `tr` dyker upp i en fil som importerar
ordboken, om samma nyckel står med olika engelska på två ställen, och om en nyckel bär en platshållare som
aldrig kan slås upp.

`frontend/tools/i18n_wrap.py` gör det mekaniska: `--report` visar vad som återstår fil för fil, `--keys` listar
nycklarna utan engelsk rad, och en filväg skriver om filen.

## 6. Ett undantag som ser ut som ett fel

`AgentChat.tsx` sätter `u.lang` på ett `SpeechSynthesisUtterance`. Det är en BCP-47-tagg för talsyntesen, inte
ett tallokalspråk, och den ska följa gränssnittets språk: rösten ska läsa engelska när sidan är på engelska.
Den går därför genom `locale()` som allt annat. Ändra den inte tillbaka.

## 7. Vad som med avsikt inte översätts

Fyra saker står kvar på svenska, och skälet är i tre av fallen att en översättning vore sämre än ingen.

**Akademins kursinnehåll.** `backend/app/academy_seed.py`, `academy_courses_2.py`, `academy_plans.py` och
`frontend/src/learn.ts` - tillsammans omkring 1 380 strängar. Det är inte gränssnittstext utan undervisning om
svensk VVS-praxis: EI30-isolering, AMA-konventioner, svenska beteckningssystem. Att översätta det kräver en
fackgranskare, en `lang`-kolumn på kurs, modul, lektion och fråga, och sedan två läroplaner som glider isär.
Akademins ram är översatt - menyer, knappar, figurernas terminologi - och en rad på sidan säger att kurstexten
är på svenska. Ingen ska kunna ta en utelämning för ett fel.

**Anbudstexten i `calc.py`.** Sextio strängar, och de är AB 04- och ABT 06-klausuler: "Garantitid enligt
ABT 06 kap. 4 § 7". Det är standardavtalsvillkor med rättsverkan, i ett dokument en entreprenör skriver under.
En engelsk återgivning av dem är en översättning av ett rättsligt instrument, inte av en knapptext, och den
vore aktivt vilseledande. Anbudet är svenskt, permanent.

**Exportens kolumnrubriker.** `exports.py` `HEADERS`, femton svenska namn som hamnar i XLSX och CSV som svenska
mängdare klistrar in i svenska kalkylblad. Att byta dem efter webbläsarens språk vore att tyst och
oåterkalleligt ändra en fil som inte bär någon uppgift om vilket språk som skapade den. Vill någon ha engelska
exporter är rätt nyckel en uttrycklig `?lang=en` på exportvägen - ett val, inte en avläsning.

**De 36 beskeden som är f-strängar.** Ett besked som bär sitt tal i sig - `f"Läsningen kostar {n} credits och
kontot har {m}."` - kan inte slås upp på en svensk nyckel, för nyckeln är olika varje gång. De 108 beskeden som
är hela strängar går genom ordboken; de här står kvar på svenska tills de skrivs om så talet läggs till i
stället för att skjutas in. Två av dem träffar betalande kunder (`credits.py:203` och `:255`) och är värda att
skriva om; de övriga 34 är admin- och CAD-vägar.

## 8. Hur det mäts

```
cd frontend && node tools/i18n_check.mjs      # varje anrop går till ordboken, och vad som saknar engelska
python3 frontend/tools/i18n_wrap.py --areas   # samma sak, del för del
python3 frontend/tools/i18n_wrap.py --keys admin   # nycklarna som återstår i en del
```

Provet ligger först i `npm run build`, så en sträng som inte når ordboken stoppar bygget i stället för att
märkas i webbläsaren.
