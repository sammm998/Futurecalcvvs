# Bildstöd och symbolkontakter

Analysen använder fortsatt dimensionsregler och modellbedömning tillsammans, med automatisk stilidentifiering. VVS5:s gränssnitt behålls; PipeStudio och Swedish VVS är regelkällor.

## Ändringar

Modellen får nu bilder av originalritningen utöver den strukturerade geometrin: en översikt och högst sex lokala utsnitt per anrop. Utsnitten följer frågornas koordinater. Referensmarkeringar tas bort i minnet före rendering och originalfilen ändras inte. Bildernas utsnitt och hash sparas i analysens användningslogg; ingen API-nyckel sparas där. Implementationen följer [OpenAI:s bildinmatning för Responses](https://developers.openai.com/api/docs/guides/images-vision).

Rörändar vid sammanhängande slutna symbolkonturer kan ge modellen ytterligare kandidater. Ändarna måste tillhöra samma lager, linjetyp och bredd. Förslaget får inte ersätta befintlig etikettevidens. Det skapar ingen ny geometri och mäts inte automatiskt. Om modellen avstår blir ett sådant förslag inte en bekräftad reservtilldelning.

## Kontroll mot facit

Samma verifierat parade original-PDF används för varje jämförelse inom ett blad. Facit läses först efter analysen. Tabellen mäter geometrisk överensstämmelse per exakt beteckning med toleransen 1 PDF-punkt, utan streckluckor, vertikala meter eller skrafferade delar.

| A0111, körning | Återfunnen referensgeometri | Andel mätt geometri med stöd i facit |
| --- | ---: | ---: |
| Tidigare, enbart strukturerad modellinformation | 38,89 % | 63,92 % |
| Med ritningsbilder | 39,32 % | 64,94 % |
| Med ritningsbilder och symbolförslag | 39,27 % | 66,46 % |

Symbolkörningen tog 394 sekunder. Fem symbolförslag nådde modellen. Ingen ny symboltilldelning bekräftades: en fick låg säkerhet och övriga lämnades utan tilldelning. Skillnaderna i totalsiffrorna bevisar därför inte att symbolförslagen återfann rören. Modellkörningar kan variera.

A0013 med bildstöd gav 79,64 % referenstäckning och 91,65 % stöd för mätt geometri. Tidigare var motsvarande cirka 80,94 % och 90,6 %. Bildstödet gav alltså inte en entydig förbättring på alla blad.

## Kvarvarande begränsningar

Fullständig obevakad mängdning är inte verifierad. A0111 har fortfarande stora bortfall, särskilt bland VS, VP, X31 och VVC. Modellen kan inte återställa geometri eller beteckningar som aldrig kom in i dess kandidatunderlag. Högst sex detaljbilder per anrop innebär dessutom att inte varje rör får ett eget närutsnitt. Symbolförslagen löser inte automatiskt buntars anslutning eller dimension.

Äldre sparade jobb räknas inte om vid koduppdatering. Nya analyser använder bildstödet; redan sparade resultat ska inte beskrivas som om de gjort det.

## Verifiering

Hela motorns testsvit: 1 026 godkända, 3 överhoppade. Därefter tillkom ett regressionstest som visar att ett avböjt symbolförslag inte blir bekräftad reservmängd; berörd svit gav 6 godkända. Frontendbygget passerade. Testerna verifierar funktioner och skydd, inte generell ritningsträffsäkerhet.

Mätvärden, PDF-hashar, faktiska symbolbeslut och testloggar finns i `results/current/symbol-ports/validation-summary.json` och samma katalog.
