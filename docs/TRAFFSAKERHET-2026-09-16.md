# Fortsatt analysarbete – 16 september 2026

**Senaste status:** [Leverans 17 september](LEVERANS-2026-09-17.md). Nedan beskrivs föregående version.

## Genomförda ändringar

Tätt staplade vektortextrader kunde få fel läsriktning när hela textblocket var
högre än det var brett. Det gjorde att bland annat KV1, VV1 och VVC1 försvann ur
teckenförklaringen och att riktiga rörbeteckningar därefter sorterades bort.
Riktningen kontrolleras nu mot flera separata baslinjer med stöd av teckengeometrin.
Regeln använder inga förväntade beteckningar eller handmängder.

Skrivna standardangivelser efter »kopplingsledningar … om ej annat anges« läses nu
även när de anges som fullständiga koder i löptext. Exempel:
`RAD1-X31-16, KV1/VV1-X31-16.` Motorn delar den gemensamma beteckningen i två system.
Motstridiga dimensioner behålls för granskning. Villkorade meningar, skadade koder
och närliggande vanliga etiketter blir inte generella regler.

Reglerna namnger endast rör med oberoende stöd för rätt system i CAD-lagret.
Den begränsningen är kvar: en lista med tre system räcker inte för att avgöra
vilket system en enskild linje utan lager tillhör. En läst etikett behåller sitt namn.
Avläst standardtext och dess beteckningar visas under **Översikt** i analysvyn.
Mängder från standardangivelser kan fortfarande räknas bort via kryssrutan i mängdtabellen.
VVS5:s layout och komponentstilar används.

## Jämförelse på riktiga ritningar

Tre diagnostiska fall har körts om från PDF med samma slutversion av motorn.
De två första valdes för att de fungerade dåligt. Det tredje är en kontrollritning.
Det är inte ett slumpmässigt testurval eller en uppskattning av systemets totala noggrannhet.

| Ritning | Referens återfunnen, före → efter | Stöd för bedömd prediktion, före → efter |
|---|---:|---:|
| W-50-1-0201112 | 3,37 % → 5,67 % | 87,77 % → 77,42 % |
| W-50-1-0501112 | 6,67 % → 13,29 % | 79,80 % → 87,26 % |
| W-50-1-A-0011 | 83,79 % → 83,79 % | 93,95 % → 93,95 % |

Jämförelsen kräver samma beteckning och högst en PDF-punkts avstånd. Den omfattar
ritade, bekräftade centrumlinjesegment utanför skraffering. Streckluckor, vertikala
meter och beteckningar som inte finns i referensannoteringarna ingår inte.
PDF-hashen kontrolleras mot resultatets frysta manifest. Annoteringarna tas bort
före inferens och läses först i den efterföljande jämförelsen.

Textfelet är rättat, men den första ritningen får också mer geometri utan stöd i den
bedömda referensen. Fler uppmätta meter är därför inte tillräckligt bevis på bättre
träffsäkerhet. Båda problemritningarna har fortfarande stora bortfall och får
kvalitetsbeskedet att mängden behöver granskas. De ska inte användas obevakat.

En diagnostisk körning provade även att alltid försöka återta pennor som används
för hänvisningslinjer. Den löste inte bortfallet och har inte lagts in i produktionen.
Att generellt räkna in tunnare linjer är inte en verifierad lösning.

Maskinläsbara före/efter-resultat: `results/current/accuracy-round2/comparison.json`.
Alla tre nya körningar har motorhash
`c57cadc6872e8eebacab8b01006125ce880ca896fa85ea5464b9776770293d06`.
De äldre baslinjerna har den versionsinformation som finns i deras ursprungliga manifest.

## Verifiering

- Hela testsviten: **847 godkända, 3 överhoppade**, 331,24 sekunder.
- Riktade prov för standardangivelser, tabeller och bortval: **22 godkända**.
- Frontend: översättningskontroll, ESLint, TypeScript och Vite godkända.
  Vites befintliga varning om stora paket kvarstår.
- Ett separat lokalt API- och webbläsarprov laddade upp och analyserade en kontrollerad
  ritning med sex kopplingsledningar à två meter och en etiketterad stam på tio meter.
  Utfallet blev 12,00 m enligt standardangivelsen och 10,00 m enligt etiketten.
  Översikten visar källtexten och båda deklarerade systemen, men ger ingen VV-mängd
  eftersom provritningen saknar VV-geometri. XLSX, CSV, JSON och PDF exporterades med HTTP 200.

Loggarna ligger i `results/current/accuracy-round2/`. Den fullständiga sviten kördes
efter motorändringarna; den avslutande API-justeringen kontrollerades dessutom separat.

## Kvar att lösa

Systemet är fortfarande en lokal arbetsversion. Namnlösa kopplingsledningar på
ritningar utan lager, svåra hänvisningar och blandad linjegeometri kräver fortsatt
arbete och granskning. Automatisk mängdning av skannade ritningar saknas fortfarande.
Inga nya modeller har tränats, och hela ritningssamlingen är inte slutvaliderad.
