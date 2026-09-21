# Automatisk analys och facitkontroll, 20 september 2026

Analysmetod och ritningsstil väljs inte längre i användargränssnittet. API och jobbkö använder alltid `combined` och `auto`, även när en äldre klient skickar ett tidigare val. Dimensionsförslag och modellbedömning körs tillsammans. Osäkra förslag blir inte bekräftade enbart för att dimensionerna passar.

Automatisk stilidentifiering behåller skillnaden mellan en kandidat och en känd stil. Om ingen stil passar används generella källregler och ritningens lokala underlag. Modellunderlaget innehåller uppmätta egenskaper, såsom linjebredder, lager och textstorlek. En okänd stil får inte automatiskt ärva närmaste stilprofils specialregler.

## Jämförelse med facit

Fyra kompletta analyser kördes mot exakt de PDF-filer som respektive XML-facit anger. Facit läses först efter analys och används inte som modellunderlag. Äldre användaruppladdningar hade andra filhashar och ersatte därför inte dessa kontrollkörningar.

| Ritning | Återfunnen markerad referenslängd | Modellens ritade längd med stöd i referensen |
|---|---:|---:|
| V-50-1-A0522 | 23,7 % | 69,3 % |
| W-50-1-0101113-UB | 61,2 % | 91,8 % |
| W-50-1-A-0011 | 80,1 % | 88,4 % |
| W-50-1-A-0013 | 80,9 % | 90,6 % |

Detta är geometrisk överlappning med exakt beteckning och 1 PDF-punkts tolerans. Streckglapp, vertikala meter och skrafferade sträckor ingår inte. Andra beteckningar som saknar referens bedöms inte. Referensmarkeringarnas riktighet är inte oberoende certifierad. Procentsatserna är inte ett generellt noggrannhetslöfte.

XML-mängdjämförelsen finns separat i `results/current/automatic-style/validation-summary.json`. En korrekt totalsumma kan dölja både bortfall och felaktiga sträckor; därför redovisas också den geometriska jämförelsen.

## Rättat läsfel och kvarvarande fel

När tre beteckningar står bredvid varandra kunde läsaren hoppa över den tredje dimensionskolumnen. Sökningen följer nu samtliga närliggande dimensionsrader med överlappande kolumn. Ett regressionstest kontrollerar både tre kolumner och att avlägsna siffror inte fångas.

På A0522 läses VV01-X31 nu med DN16. Omkörningen förbättrade inte den uppmätta mängden: hänvisningskontakten är fortfarande tvetydig. KV01-X31 har också ett stort bortfall i utbredningen. Dessa fel är kvar och fullständig obevakad mängdning är inte verifierad. Att minska varningarna utan att lösa kopplingen skulle ge missvisande mängder.

`V-57.1-121.pdf` analyserades dessutom med status UNKNOWN och båda motorerna COMPLETED. Detta är ett funktionstest av en okänd stil, inte en facitkontroll; inget facit har verifierats för den filen.

## Reproduktion

Kör `tools/validate_combined.py` med `--case` från `results/current/bluebeam/pairs.json` och en separat `--out`-katalog. Modellen måste vara konfigurerad lokalt. Verktyget sparar felstatus, tidsåtgång, filhash och facitjämförelse. Källreglernas ursprung och tester ska fortsatt skiljas från den uppmätta träffsäkerheten på ritningar.
