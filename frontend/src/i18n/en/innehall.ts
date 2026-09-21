/* Innehållsmodulerna: learn, features, agents, frontier, legend
 *
 * En rad per sträng, svensk nyckel först. Saknas en rad visas svenskan.
 */
export const innehall: Record<string, string> = {

  // --- läsningens steg, som filmen säger dem (agents.ts) --------------------------------------------------
  "Synagenten": "The sight reader",
  "Tittar på sidan som bild": "Looks at the page as an image",
  "Står det något där vektorläsningen inte har någon text?":
    "Is there anything written where the vector reading has no text?",
  "Den ser bilden, aldrig geometrin: ingenting den läser kan bli en meter.":
    "It sees the image, never the geometry: nothing it reads can become a metre.",
  "Vektorläsaren": "The vector reader",
  "Läser PDF:en": "Reads the PDF",
  "Vilka streck finns ritade, på vilka lager och med vilka pennor?":
    "Which strokes are drawn, on which layers and with which pens?",
  "Inget är text ännu — en PDF från CAD skriver bokstäverna som streck.":
    "Nothing is text yet — a PDF from CAD writes the letters as strokes.",
  "Textbyggaren": "The text builder",
  "Bygger texten ur streck": "Builds the text out of strokes",
  "Vilka av strecken är bokstäver, och vilka rader bildar de?":
    "Which of the strokes are letters, and which rows do they form?",
  "Beteckningsläsaren": "The designation reader",
  "Läser beteckningarna": "Reads the designations",
  "Vilka rader är beteckningar, och vilken dimension bär de?":
    "Which rows are designations, and which dimension do they carry?",
  "Vilka av dem som namnger rör avgör ritningens egen förklaringslista.":
    "Which of them name pipes is decided by the drawing's own legend.",
  "Hänvisningsspåraren": "The leader tracer",
  "Följer hänvisningslinjerna": "Follows the leaders",
  "Vilken ritad linje utgår från vilken etikett, och var slutar den?":
    "Which drawn line starts from which label, and where does it end?",
  "Ingen linje uppfinns: bara streck ritningen faktiskt drar räknas.":
    "No line is invented: only strokes the drawing actually draws count.",
  "Familjeutredaren": "The family adjudicator",
  "Avgör vad som är rör": "Decides what is pipe",
  "Vilka pennor ritar rör på det här bladet, och vilka ritar byggnaden?":
    "Which pens draw pipe on this sheet, and which draw the building?",
  "En familj som ingen beteckning når tas inte — den ritar då något annat.":
    "A family no designation reaches is not taken — it is then drawing something else.",
  "Rörbyggaren": "The pipe builder",
  "Bygger de fysiska rören": "Builds the physical pipes",
  "Vilka sträckor hör ihop till ett rör, och vem äger dem?":
    "Which stretches belong together as one pipe, and who owns them?",
  "Mätaren": "The measurer",
  "Mäter": "Measures",
  "Hur många meter blir det, i ritningens egen skala?":
    "How many metres does it come to, in the drawing's own scale?",
  "Skalagranskaren": "The scale reviewer",
  "Täckningsgranskaren": "The coverage reviewer",
  "Rimlighetsgranskaren": "The plausibility reviewer",
  "Topologigranskaren": "The topology reviewer",
  "Beteckningsgranskaren": "The designation reviewer",
  "Synagentens korsprov": "The sight reader's cross-check",
  "verifierad": "verified",
  "okänd": "unknown",

  // --- meningarna med tal i sig (trf) ---------------------------------------------------------------------
  "Läser ruta {0} av {1} och hittar {2} ord där.": "Reading tile {0} of {1} and finding {2} words there.",
  "{0} ritade objekt på sidan, {1} × {2} punkter.": "{0} drawn objects on the page, {1} × {2} points.",
  "{0} textrader byggda ur strecken.": "{0} text rows built out of the strokes.",
  "{0} beteckningar lästa.": "{0} designations read.",
  "{0} beteckningar lästa, {1} av dem med en dimension på raden.":
    "{0} designations read, {1} of them with a dimension on the row.",
  "{0} hänvisningslinjer följda från etikett ut i ritningen.":
    "{0} leaders followed from label out into the drawing.",
  "{0} ritade familjer togs som rör.": "{0} drawn families were taken as pipe.",
  "{0} ritade familjer togs som rör: {1}.": "{0} drawn families were taken as pipe: {1}.",
  "penna {0}": "pen {0}",
  "{0} fysiska rör byggda.": "{0} physical pipes built.",
  "{0} beteckningar möter sitt rör, {1} är tvetydiga, {2} når inget.":
    "{0} designations meet their pipe, {1} are ambiguous, {2} reach nothing.",
  "Skala {0}.": "Scale {0}.",
  "Skala {0} — {1} m per punkt.": "Scale {0} — {1} m per point.",
  "{0} m bekräftad längd fördelad på {1} beteckningar.":
    "{0} m of confirmed length spread across {1} designations.",

  // --- skälen ett rör slutar av (frontier.ts) -------------------------------------------------------------
  "Samma ledning fortsätter med en annan dimension": "The same pipe continues with a different dimension",
  "Geometrin fortsätter men tillhör ett annat system":
    "The geometry continues but belongs to another system",
  "Samma system, annat namn eller annan isolering":
    "The same system, a different name or a different insulation",
  "Fortsättningen ägs av bladets skrivna regel, inte av en etikett":
    "The continuation is owned by the sheet's written rule, not by a label",
  "Fler än en identitet gör anspråk på fortsättningen": "More than one identity claims the continuation",
  "Namnet hade runnit för långt förbi etiketterna och togs tillbaka":
    "The name had run too far past the labels and was taken back",
  "Samma penna fortsätter och ingen etikett når den": "The same pen continues and no label reaches it",
  "Ledningen fortsätter på en annan penna": "The pipe continues on a different pen",
  "Samma penna fortsätter i samma riktning efter ett gap som inte överbryggades":
    "The same pen continues in the same direction after a gap that was not bridged",
  "Röret slutar i en stigarsymbol": "The pipe ends in a riser symbol",
  "Röret slutar i en ritad komponent": "The pipe ends in a drawn component",
  "Röret går ut ur bladet": "The pipe leaves the sheet",
  "Linjen slutar och ingenting finns intill": "The line ends and there is nothing beside it",
  "En sluten slinga utan kant": "A closed loop with no edge",
  "Något läsningen inte kan sätta ord på": "Something the reading cannot put into words",

  // --- förklaringslistans roller (legend.ts) --------------------------------------------------------------
  "rörsystem": "pipe system",
  "komponent": "component",
  "material": "material",
  "oanvänd": "unused",

  // --- funktionen: mängdningen ----------------------------------------------------------------------------
  "Läsningen": "The reading",
  "Mängden som ritningen\nredan säger": "The quantity the drawing\nalready states",
  "Ladda upp en VVS-ritning. Systemet läser bladets egen beteckningslista, följer varje hänvisningslinje till det rör den pekar på, och mäter i ritningens egen skala. Varje meter behåller sitt belägg.":
    "Upload an HVAC drawing. The system reads the sheet's own designation list, follows every leader to the pipe it points at, and measures in the drawing's own scale. Every metre keeps its evidence.",
  "Beteckning, ledare, rör, skala — en mängd där varje rad går att öppna.":
    "Designation, leader, pipe, scale — a quantity where every row can be opened.",
  "av referensens meter återfunna över 59 uppmätta blad":
    "of the reference's metres recovered across 59 measured sheets",
  "Identitet": "Identity",
  "Ett rör får sitt namn av en linje, aldrig av närheten":
    "A pipe gets its name from a line, never from proximity",
  "Det närmaste röret är nästan alltid fel rör. För varje beteckning söks den hänvisningslinje ritaren faktiskt drog — rak, bruten, i flera delar — och den följs till sin spets. Träffar den ingenting står beteckningen kvar utan meter, och det syns.":
    "The nearest pipe is almost always the wrong pipe. For every designation the leader the draughtsman actually drew is sought — straight, broken, in several parts — and followed to its tip. If it hits nothing the designation stands there without metres, and it shows.",
  "Bladets egen förklaringslista avgör vilka koder som namnger rör":
    "The sheet's own legend decides which codes name pipe",
  "Texten byggs tillbaka även när CAD ritat bokstäverna som streck":
    "The text is rebuilt even when CAD drew the letters as strokes",
  "En kontakt är inte en anslutning förrän den är verifierad":
    "A contact is not a connection until it is verified",
  "Utsträckning": "Extent",
  "Från fästpunkten följs röret genom böjar, avgreningar, exportglapp och streckmönster — bara över verifierade fysiska kopplingar. Där det slutar skrivs varför: dimensionen byter, systemet byter, geometrin tar slut, avgreningen är tvetydig.":
    "From the attachment point the pipe is followed through bends, branches, export gaps and dash patterns — only across verified physical connections. Where it ends the reason is written down: the dimension changes, the system changes, the geometry runs out, the branch is ambiguous.",
  "Sexton skäl en sträcka kan sluta av, alla utskrivna":
    "Sixteen reasons a run can stop for, all written out",
  "En korsning är inte en koppling": "A crossing is not a connection",
  "Två parallella linjer som ritar ett rör blir ett rör":
    "Two parallel lines drawing one pipe become one pipe",
  "Mätning": "Measurement",
  "Skalan tas ur bladet, aldrig ur ett antagande":
    "The scale is taken from the sheet, never from an assumption",
  "Stämpel, skalstock eller måttsättning — och när de är oense står konflikten kvar i svaret. Rör som ligger i skrafferad vägg redovisas för sig, så du själv väljer om de ska räknas. Vertikalt utan höjdbesked står som okänt, inte som noll.":
    "Title block, scale bar or dimensioning — and when they disagree the conflict stays in the answer. Pipe lying in a hatched wall is reported separately, so you choose yourself whether it counts. Vertical without a height statement stands as unknown, not as zero.",
  "Skrafferad vägg hittas oavsett hur kontoret lagt sina lager":
    "A hatched wall is found however the office has arranged its layers",
  "Stigare ritas som stigare, inte som punkter": "Risers are drawn as risers, not as points",
  "Ingen mätning på bildpunkter: en skannad PDF avvisas med besked":
    "No measuring on pixels: a scanned PDF is rejected with a reason",
  "Sex steg, i den ordning motorn faktiskt går.": "Six steps, in the order the engine actually runs.",
  "Ritningen öppnas som vektorer": "The drawing is opened as vectors",
  "Varje streck med sin penna, färg, sitt lager och sin streckning.":
    "Every stroke with its pen, colour, layer and dash pattern.",
  "Bladet får en profil": "The sheet gets a profile",
  "Vilka pennor, texter, streckmönster och ritsätt just det här bladet använder.":
    "Which pens, texts, dash patterns and drawing conventions this particular sheet uses.",
  "Beteckningarna läses": "The designations are read",
  "Text där det är text, återbyggda tecken där CAD ritat dem som streck.":
    "Text where it is text, rebuilt characters where CAD drew them as strokes.",
  "Ledarna följs": "The leaders are followed",
  "Från varje beteckning till det rör linjen pekar på, och ingen annanstans.":
    "From every designation to the pipe the line points at, and nowhere else.",
  "Röret följs ut": "The pipe is followed out",
  "Genom böjar och grenar, bara över kopplingar som går att belägga.":
    "Through bends and branches, only across connections that can be evidenced.",
  "Mängden skrivs": "The quantity is written",
  "Rad för rad, med det som inte kunde avgöras för sig.":
    "Row by row, with what could not be decided kept separate.",
  "Öppna mängdningen": "Open the take-off",

  // --- funktionen: mängda för hand ------------------------------------------------------------------------
  "För hand": "By hand",
  "Mängda själv,\nmed verktyg som håller": "Take off yourself,\nwith tools that hold up",
  "Ibland ska man mäta för hand: en handling som inte är vektor, en del motorn lämnar tvetydig, eller en kontroll av det som redan lästs. Verktyget är byggt för att stå i nivå med det en mängdare är van vid.":
    "Sometimes you should measure by hand: a document set that is not vector, a part the engine leaves ambiguous, or a check on what has already been read. The tool is built to stand level with what an estimator is used to.",
  "Kalibrering, fångst, ortho, avdrag och en markeringslista som går att redigera.":
    "Calibration, snap, ortho, deductions and a markup list you can edit.",
  "Längd, area, antal och djup": "Length, area, count and depth",
  "mot ett känt mått på bladet": "against a known dimension on the sheet",
  "mot ändpunkt, mitt, skärning och ortho": "to endpoint, midpoint, intersection and ortho",
  "ytor och längder som ska bort ur summan": "areas and lengths to come off the sum",
  "Arbetsbordet": "The workbench",
  "Ritningen är sidan, inte en panel bland andra": "The drawing is the page, not one panel among others",
  "PDF:en tar hela ytan. Verktygslådan ligger i kanten, markeringslistan i en egen flik, och det du mätt står kvar mellan sessionerna. Mätningar du gör kan läggas bredvid motorns egna, så de går att jämföra rad för rad.":
    "The PDF takes the whole surface. The toolbox sits at the edge, the markup list in a tab of its own, and what you have measured stays between sessions. Measurements you make can be placed beside the engine's own, so they can be compared row by row.",
  "Redigera en markering i efterhand, inte rita om den": "Edit a markup afterwards, not redraw it",
  "Markeringar i hela handlingen, sida för sida": "Markups across the whole document set, page by page",
  "Exporteras tillsammans med den lästa mängden": "Exported together with the read quantity",
  "Så mäter du": "How you measure",
  "Fyra steg, samma som på papper.": "Four steps, the same as on paper.",
  "Kalibrera": "Calibrate",
  "Dra längs ett känt mått och skriv vad det är.": "Drag along a known dimension and write what it is.",
  "Välj verktyg": "Pick a tool",
  "Längd, area, antal — och fångst om linjerna ska mötas exakt.":
    "Length, area, count — and snap if the lines are to meet exactly.",
  "Mät": "Measure",
  "Ortho håller linjen rak när ritningen är det.": "Ortho keeps the line straight when the drawing is.",
  "Visa mängderna": "Show the quantities",
  "Listan över det tvetydiga, och varför.": "The list of what is ambiguous, and why.",

  // --- funktionen: 3D -------------------------------------------------------------------------------------
  "3D": "3D",
  "Se ritningen\nsom en byggnad": "See the drawing\nas a building",
  "När läsningen är klar reser sig planen. Rören lyfter från pappret med sina höjder, stigarna går genom bjälklagen, och du ser var systemet faktiskt går — inte bara var linjerna ligger.":
    "When the reading is done the plan rises. The pipes lift off the paper with their heights, the risers pass through the floor slabs, and you see where the system actually runs — not just where the lines lie.",
  "Planen reser sig: rör med höjd, stigare genom bjälklag, system för system.":
    "The plan rises: pipes with height, risers through floor slabs, system by system.",
  "ur bladets egna CL- och VG-angivelser": "from the sheet's own CL and invert-level statements",
  "Sambandet": "The link",
  "Samma rör i tabellen och i rummet": "The same pipe in the table and in the room",
  "Markera en rad i mängden och röret tänds i modellen. Klicka i modellen och raden rullar fram. Det är samma geometri hela vägen — ingen separat modell som kan hamna ur fas med mängden.":
    "Select a row in the quantity and the pipe lights up in the model. Click in the model and the row scrolls into view. It is the same geometry all the way — no separate model that can drift out of step with the quantity.",
  "från mängdtabellen till samma rör i modellen": "from the quantity table to the same pipe in the model",
  "tänd och släck KV, VV, VS, spill var för sig": "switch KV, VV, VS and waste on and off separately",
  "Det tvetydiga syns i sin egen färg": "What is ambiguous shows in its own colour",
  "Tre saker 3D-vyn är bra på.": "Three things the 3D view is good at.",
  "Förstå ett schakt": "Understand a shaft",
  "Var stigarna går och hur många de är, på en gång.":
    "Where the risers run and how many there are, at a glance.",
  "Hitta det orimliga": "Find the implausible",
  "Ett rör som går genom ett bjälklag där inget schakt finns syns direkt.":
    "A pipe passing through a floor slab where there is no shaft shows immediately.",
  "Visa någon annan": "Show someone else",
  "En modell övertygar en beställare snabbare än en tabell.":
    "A model convinces a client faster than a table.",
  "Se en läsning i 3D": "See a reading in 3D",

  // --- funktionen: CAD ------------------------------------------------------------------------------------
  "CAD": "CAD",
  "Rita hela byggnaden,\ninte bara rören": "Draw the whole building,\nnot just the pipes",
  "Ett fullständigt CAD-rum i webbläsaren: väggar, dörrar, fönster, bjälklag, tak, rum och trappor; pelare, balkar, plattor och grund; rör, kanaler, kabelstegar och utrustning med sina anslutningar.":
    "A complete CAD room in the browser: walls, doors, windows, floor slabs, roofs, rooms and stairs; columns, beams, slabs and foundations; pipes, ducts, cable trays and equipment with their connections.",
  "Väggar, stomme och installationer i en modell — med mängder som följer med.":
    "Walls, frame and services in one model — with quantities that follow along.",
  "faser byggda: arkitektur, konstruktion, vyer, MEP, mängder, import, export":
    "phases built: architecture, structure, views, MEP, quantities, import, export",
  "Modellen": "The model",
  "En byggnad, inte en samling streck": "A building, not a collection of strokes",
  "Nivåer, rutnät och lager håller ihop det. En vägg vet att den är en vägg, ett rum vet vilka väggar som omsluter det, och ett rör vet vad det är anslutet till. Därför kan mängderna räknas ur modellen i stället för att mätas av den.":
    "Levels, grids and layers hold it together. A wall knows that it is a wall, a room knows which walls enclose it, and a pipe knows what it is connected to. That is why the quantities can be computed from the model instead of measured off it.",
  "Underlag från PDF, bild eller DXF att rita ovanpå":
    "An underlay from PDF, image or DXF to draw on top of",
  "Kommandorad för den som hellre skriver än klickar":
    "A command line for those who would rather type than click",
  "Ångra och gör om genom hela sessionen": "Undo and redo through the whole session",
  "Revisioner sparas, ingenting skrivs över": "Revisions are saved, nothing is overwritten",
  "Vyerna": "The views",
  "Plan, sektion, fasad och 3D — samma modell": "Plan, section, elevation and 3D — the same model",
  "Ändra i planen och sektionen följer med. Måttsättning och annotering hör till vyn, inte till geometrin, så ett mått ljuger aldrig om modellen. Blad läggs ut för utskrift när ritningen ska lämna skärmen.":
    "Change the plan and the section follows. Dimensioning and annotation belong to the view, not to the geometry, so a dimension never lies about the model. Sheets are laid out for printing when the drawing is to leave the screen.",
  "3D-editor byggd på three.js": "A 3D editor built on three.js",
  "samma modell, synkad åt båda håll": "the same model, synced both ways",
  "Kollisionskontroll mellan installation och stomme": "Clash detection between services and structure",
  "in och ut, tillsammans med DXF, SVG och GLB": "in and out, together with DXF, SVG and GLB",
  "Så kommer du igång": "How you get started",
  "Från tomt blad till en modell med mängder.": "From an empty sheet to a model with quantities.",
  "Lägg upp nivåer och rutnät": "Set up levels and grids",
  "Våningshöjder och axlar först — allt annat hänger på dem.":
    "Storey heights and axes first — everything else hangs on them.",
  "Rita eller importera stommen": "Draw or import the structure",
  "Väggar och bjälklag för hand, eller ett underlag att rita ovanpå.":
    "Walls and slabs by hand, or an underlay to draw on top of.",
  "Dra installationerna": "Run the services",
  "Rör, kanaler och stegar med sina anslutningar och dimensioner.":
    "Pipes, ducts and trays with their connections and dimensions.",
  "Läs av mängderna": "Read off the quantities",
  "De räknas ur modellen och uppdateras medan du ritar.":
    "They are computed from the model and update as you draw.",
  "Öppna CAD-rummet": "Open the CAD room",
  "Lager att tända och släcka per system": "Layers to switch on and off per system",

  // --- funktionen: kalkylen -------------------------------------------------------------------------------
  "Kalkyl": "Costing",
  "Från mängd\ntill anbud": "From quantity\nto tender",
  "Mängden är halva jobbet. Kalkylen tar rören, lägger på material, arbete och påslag, och gör ett anbud du kan granska i webbläsaren innan det lämnar huset — neutralt mot AB 04 och ABT 06.":
    "The quantity is half the job. The costing takes the pipes, adds materials, labour and markup, and makes a tender you can review in the browser before it leaves the building — neutral between AB 04 and ABT 06.",
  "Material, arbete och påslag ovanpå mängden — och ett anbud att granska på skärmen.":
    "Materials, labour and markup on top of the quantity — and a tender to review on screen.",
  "priser per beteckning, som du kan flytta": "prices per designation, which you can move",
  "Uppdelningen": "The breakdown",
  "Material på": "Materials on",
  "Ur materialboken, med priser du själv styr.": "From the material book, with prices you control.",
  "Arbete och påslag": "Labour and markup",
  "Arbetstid per meter och dimension": "Working time per metre and dimension",
  "Påslag per post eller över hela anbudet": "Markup per item or across the whole tender",
  "Per post eller över hela anbudet.": "Per item or across the whole tender.",
  "Anbudet": "The tender",
  "Granska och lämna": "Review and submit",
  "Sida för sida på skärmen, sedan som PDF.": "Page by page on screen, then as a PDF.",
  "anbudet sida för sida innan det laddas ner": "the tender page by page before it is downloaded",
  "Exporteras som PDF och som kalkylblad": "Exported as a PDF and as a spreadsheet",
  "Gränsen": "The boundary",
  "Geometrin är neutral, kalkylen tar ställning": "The geometry is neutral, the costing takes a position",
  "Samma ritning ger samma rör oavsett entreprenadform. Det är först i kalkylen avtalsformen betyder något, och det är därför en ändring där aldrig kan flytta en meter i mängden.":
    "The same drawing gives the same pipes whatever the contract form. Only in the costing does the contract form matter, and that is why a change there can never move a metre in the quantity.",
  "avtalsformen bor i kalkylen, aldrig i geometrin":
    "the contract form lives in the costing, never in the geometry",
  "Så byggs anbudet": "How the tender is built",
  "Fyra steg från läst ritning till lämnat pris.": "Four steps from read drawing to submitted price.",
  "Mängden in": "The quantity in",
  "Med skalan ur bladet och belägget kvar för varje rad.":
    "With the scale from the sheet and the evidence intact for every row.",
  "Mot materialboken, med priserna synliga.": "Against the material book, with the prices visible.",
  "Rätta och räkna": "Correct and compute",
  "Justera det som blev fel och läs summan per grupp.":
    "Adjust what came out wrong and read the sum per group.",
  "Öppna kalkylen": "Open the costing",

  // --- funktionen: agenten --------------------------------------------------------------------------------
  "Agenten": "The agent",
  "Fråga ritningen,\nfå svar med belägg": "Ask the drawing,\nget an answer with evidence",
  "Släpp in en PDF i samtalet och fråga. Agenten svarar ur det som står i handlingen, säger vad den inte kunde avgöra, och hittar aldrig på en siffra. Samma motor som analysen, samma artefakter, samma credits.":
    "Drop a PDF into the conversation and ask. The agent answers from what the document set says, states what it could not decide, and never invents a number. The same engine as the reading, the same artifacts, the same credits.",
  "Släpp in en ritning och fråga. Svaret kommer ur handlingen, inte ur en gissning.":
    "Drop in a drawing and ask. The answer comes from the document set, not from a guess.",
  "modellen väljer frågan, verktygen svarar ur det lästa":
    "the model picks the question, the tools answer from what was read",
  "Samtalet": "The conversation",
  "Modellen väljer frågan — ritningen ger svaret": "The model picks the question — the drawing gives the answer",
  "Agenten får välja vilken fråga som ställs till bladet och hur svaret formuleras. Den får aldrig välja ett tal. Alla siffror kommer ur samma deterministiska läsning som mängdtabellen, och en siffra utan belägg blir «det står inte i handlingen».":
    "The agent may choose which question is put to the sheet and how the answer is worded. It may never choose a number. Every figure comes from the same deterministic reading as the quantity table, and a figure without evidence becomes «it does not say so in the document set».",
  "en språkmodell får aldrig hitta på koordinater eller meter":
    "a language model may never invent coordinates or metres",
  "varje verktygsanrop går att fälla ut och läsa": "every tool call can be expanded and read",
  "Starta en läsning mitt i samtalet": "Start a reading in the middle of the conversation",
  "Jämför två blad mot varandra": "Compare two sheets against each other",
  "Bra frågor att börja med": "Good questions to start with",
  "Fyra som visar vad den är till för.": "Four that show what it is for.",
  "Vad är det här för blad?": "What kind of sheet is this?",
  "System, skala, vad handlingen omfattar.": "System, scale, what the document set covers.",
  "Vad kunde inte avgöras?": "What could not be decided?",
  "Se var den är säker och var den inte är det.": "See where it is certain and where it is not.",
  "Vad kostar rören?": "What do the pipes cost?",
  "Fråga varför en rad ser ut som den gör": "Ask why a row looks the way it does",
  "Hitta i bladet": "Find it in the sheet",
  "Öppna agenten": "Open the agent",

  // --- funktionen: akademin -------------------------------------------------------------------------------
  "VVS-akademin": "The HVAC academy",
  "Lär dig läsa ritningen,\ninte bara mängda den": "Learn to read the drawing,\nnot just take it off",
  "Nio kurser och tjugotvå föreläsningar, från vad ett VVS-system är till att mängda ett övningsblad själv och få det rättat. Varje föreläsning har en egen sida, en levande figur och en kontrollfråga.":
    "Nine courses and twenty-two lectures, from what an HVAC system is to taking off a practice sheet yourself and having it marked. Every lecture has a page of its own, a living figure and a check question.",
  "Nio kurser om att läsa en rörritning — med figurer som rör sig och övningar som rättas.":
    "Nine courses on reading a pipe drawing — with figures that move and exercises that are marked.",
  "kurser i den ordning de bygger på varandra": "courses in the order they build on each other",
  "föreläsningar, var och en med en egen sida": "lectures, each with a page of its own",
  "sammanlagt, gjort för att gå i småbitar": "in total, made to be taken in small pieces",
  "Formen": "The form",
  "Varje föreläsning visar det den handlar om som en levande ritning i stället för att beskriva det i ord, och avslutas med en fråga som går att svara fel på. Övningarna använder samma slags blad som tjänsten läser — ingen av dem går att klara genom att gissa på det som ligger närmast.":
    "Every lecture shows what it is about as a living drawing instead of describing it in words, and ends with a question you can get wrong. The exercises use the same kind of sheet the service reads — none of them can be passed by guessing at whatever lies nearest.",
  "Stegen sparas på kontot, inte i webbläsaren": "Progress is saved on the account, not in the browser",
  "Läs utan konto, spara med": "Read without an account, save with one",
  "Samma kurs för hela kontoret": "The same course for the whole office",
  "Vad du kan efteråt": "What you can do afterwards",
  "Fyra saker kursen faktiskt lär ut.": "Four things the course actually teaches.",
  "Läsa en beteckning": "Read a designation",
  "System, material, dimension och isolering på tre sekunder.":
    "System, material, dimension and insulation in three seconds.",
  "Namnruta, förklaringslista, skalstock, sektioner.": "Title block, legend, scale bar, sections.",
  "Mängda i ordning": "Take off in order",
  "Granska en maskinmängd": "Review a machine take-off",
  "Vad som räknas, vad som inte gör det, och varför.":
    "What counts, what does not, and why.",
  "Det tvetydiga står som tvetydigt och mäts inte": "What is ambiguous stands as ambiguous and is not measured",
  "Rören som lästes, med det tvetydiga markerat.": "The pipes that were read, with the ambiguous ones marked.",
  "Till akademin": "To the academy",
  "Läs en ritning": "Read a drawing",
  "Ritbordet": "The drawing board",
  "Så används den": "How it is used",
  "gissningar — identitet endast via riktiga ledarlinjer":
    "guesses — identity only through real leaders",
};
