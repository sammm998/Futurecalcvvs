# Minnesbegränsad detektion och språkval

Railway rapporterade ett OOM-stopp under PIPESTUDIO_DETECT. Originaldetektorn rasteriserar hela bladet och tillåter upp till 40 miljoner pixlar. Det integrerade flödet använder nu en adapter som rasteriserar överlappande rutor om 768 pixlar med 192 pixlars överlapp. Samma modell, upplösning och konfidensgräns används. Dubbletter filtreras per klass efter återföring till PDF-koordinater. Bevarad originalkod är oförändrad; strict_original kör fortfarande originalflödet.

VVS_DETECTION_TILE_PX kan sättas mellan 512 och 2048. Mindre rutor minskar modellens arbetsminne men ändrar bildkontexten. Detta är ingen garanti för att hela analysen ryms i en viss container. Ritningar med större etiketter än överlappet behöver särskild träffsäkerhetskontroll.

Kontroll: ett syntetiskt blad på 1600 × 1100 PDF-punkter kördes genom den riktiga ONNX-modellen, 24 rutor vid 144 dpi och nio detekterade etiketter. Processens maximala residenta minne var cirka 390 MB på den lokala Mac-datorn. Detta mått omfattar inte en fullständig serveranalys och är inte en mätning av Railway. Två geometriska tester verifierar täckning, rasterstorlek, koordinater och dubbletter. Jämförelse mot verkligt facit efter ändringen återstår.

SV/EN-väljaren är nu tillgänglig i appens sidomeny, även hopfälld, och på inloggningssidan. Befintlig engelsk ordbok används och språkvalet sparas i webbläsaren. Inloggningstexter och saknade menytexter har kopplats till ordboken. Fullständig översättning av alla nyare agenttexter, dynamiska servermeddelanden och exporter återstår.

## Fortsatt minnesarbete

ONNX-körningen använder nu en CPU-tråd utan bestående minnesarena och släpper
sessionen innan vektorgrafen byggs. Den råa detektionsgrafen cachas i privata
 temporära filer i stället för att ligga i flera djupa kopior i minnet.
JSON-artefakter skrivs strömmande och PDF-kontrollsumman läses strömmande.
Originalkällorna från PipeStudio är oförändrade.

Verifiering på macOS, W-50-1-A-0011:
- Full kombinerad analys med OpenAI, automatisk stil och native detection slutförd:
  145,19 sekunder, 808 337 408 byte maximal RSS enligt `/usr/bin/time -l`.
- Resultatet innehöll 11 mängdrader. Detta är ett driftprov, inte bevis på att
  samtliga mängder stämmer mot facit.
- 19 riktade regressionstester godkända, inklusive cacheisolering, bildrutor,
  modellstädning vid undantag, hänvisningar och avbrutna analysprocesser.

512 MB är inte verifierat eller tillräckligt för den uppmätta körningen.
Webbserver och analys delar dessutom containerns gräns. En praktisk startpunkt
för fortsatt produktionsprov är 2 GB, men större ritningar måste mätas separat.
Ingen körning inom Railways verkliga minnesgräns är ännu verifierad.
Railways senaste lästa versionsstatus rapporterade också att beständig lagring
saknades. Databas och ritningar behöver en monterad volym med rätt sökvägar.
