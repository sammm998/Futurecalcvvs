# Gemensam analys

Alla nya analyser i appen kör dimensions-/flödesregler och modellbedömning i samma flöde. Metodvalet är borttaget från ritnings- och analyssidorna. Även äldre klientanrop normaliseras till `combined` på servern. Ingen ny analys startar utan konfigurerad modellanslutning.

PipeStudios dimensionsmotor körs först på den gemensamma geometrin. Dess bindningar matas in via originalmotorns `rule_proposal`-kanal till modellens slutbedömning tillsammans med hänvisningar, topologi, nivåer och stilkonventioner. Förslag är inte automatiskt sanna. Modellens bekräftade beslut används en gång per sträcka; dimensionsförslag som inte bekräftas behålls med låg säkerhet för granskning och mäts inte som bekräftade. Originalkällorna har inte ändrats.

De separata körningarna och skillnaderna finns kvar som revisionsunderlag. Interna äldre motorlägen finns för regressionstester men går inte att välja i appen. Noll tvetydighet eller överensstämmelse mellan två steg bevisar inte träffsäkerhet mot ett handmängdat facit.

A-0013 kontrollkördes med båda stegen: 109,720 m horisontellt och 0 m tvetydigt. Återvunna FJV- och KV1-rör från föregående rättning bevarades. Resultat finns i `results/current/combined/validation.json`.

## Samtal och handstyrning

Samtalsstarten visar anslutningssteg och ger ett välkomstsvar. Avbrutna/ofullständiga modellsvar visas som fel. Start och 3D-kommando verifierades med riktig OpenAI-anslutning i webbläsaren. Det rapporterade anslutningsfelet kunde inte återskapas; tidigare start saknade välkomstsvar.

Handstyrningen nollställde tidigare gesthistoriken när en bild fortfarande bearbetades efter 65 ms. Den behåller nu historiken under pågående inferens. Indikatorer visar antalet händer och om panorering eller zoom är aktiv. 31 deterministiska kontroller omfattar även 200 och 350 ms mellan handresultat. Riktiga handrörelser framför användarens kamera är inte verifierade.

43 API-/livscykeltester och 15 tester för sammanslagning och adapter passerade. API-testerna använder en uttrycklig offline-modell och är inte en träffsäkerhetsmätning. Frontendens lint, typkontroll och produktionsbygge passerade. Gamla öppna flikar behöver laddas om för att använda ny JavaScript; användarens visade flik uppdaterades och metodvalets borttagning verifierades.

A-0011: båda steg körda, 210,249 m horisontellt och 1,178 m tvetydigt fördelat på sju sträckor. Oidentifierad geometri utanför skraffering minskade från 0,952 till 0 m genom att dimensionsförslagen nu finns kvar som granskbara kandidater. Detta är förbättrad redovisning och kandidatgenerering, inte verifiering av dessa sträckors identitet. Inom skraffering kvarstår 10,073 m oidentifierad rågeometri.

Slutlig full regressionskörning: **1014 godkända, 3 överhoppade**, 133,35 sekunder. Frontendbyggnaden och samtliga 31 gest-/geometrikontroller passerade. Loggarna ingår i `results/current/combined`.
