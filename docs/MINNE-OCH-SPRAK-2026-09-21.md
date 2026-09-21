# Minnesbegränsad detektion och språkval

Railway rapporterade ett OOM-stopp under PIPESTUDIO_DETECT. Originaldetektorn rasteriserar hela bladet och tillåter upp till 40 miljoner pixlar. Det integrerade flödet använder nu en adapter som rasteriserar överlappande rutor om 768 pixlar med 192 pixlars överlapp. Samma modell, upplösning och konfidensgräns används. Dubbletter filtreras per klass efter återföring till PDF-koordinater. Bevarad originalkod är oförändrad; strict_original kör fortfarande originalflödet.

VVS_DETECTION_TILE_PX kan sättas mellan 512 och 2048. Mindre rutor minskar modellens arbetsminne men ändrar bildkontexten. Detta är ingen garanti för att hela analysen ryms i en viss container. Ritningar med större etiketter än överlappet behöver särskild träffsäkerhetskontroll.

Kontroll: ett syntetiskt blad på 1600 × 1100 PDF-punkter kördes genom den riktiga ONNX-modellen, 24 rutor vid 144 dpi och nio detekterade etiketter. Processens maximala residenta minne var cirka 390 MB på den lokala Mac-datorn. Detta mått omfattar inte en fullständig serveranalys och är inte en mätning av Railway. Två geometriska tester verifierar täckning, rasterstorlek, koordinater och dubbletter. Jämförelse mot verkligt facit efter ändringen återstår.

SV/EN-väljaren är nu tillgänglig i appens sidomeny, även hopfälld, och på inloggningssidan. Befintlig engelsk ordbok används och språkvalet sparas i webbläsaren. Inloggningstexter och saknade menytexter har kopplats till ordboken. Fullständig översättning av alla nyare agenttexter, dynamiska servermeddelanden och exporter återstår.
