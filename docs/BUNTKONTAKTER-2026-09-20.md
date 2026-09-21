# Två saknade buntkontakter – 20 september 2026

På W-50-1-A-0011.pdf var båda rören redan lästa, men överföringen till PipeStudios graf tog bara med hänvisningens slutkontakt. Den faktiska korsningen med det första parallella röret blev inte en anslutningspunkt.

Adaptern kompletterar nu korsningar för uttryckliga Nx-märkningar innan grafen delas och innan något av analyslägena tilldelar beteckningar. Den kräver samma geometrifamilj som en befintlig verifierad kontakt, verklig korsning med den ritade hänvisningen, parallell riktning och exakt det återstående antalet separata rör. Avstånd och riktningsgräns följer PipeStudios buntregel (15 punkter, 20 grader). Vanliga hänvisningar utan Nx får inga extra kontakter. Fler kandidater än antalet tillåter lämnas olösta.

Detta är en ändring i geometrins adapter, inte en ändring i de byteidentiska källmodulerna. Källans Nx-komplettering och båda tilldelningsmotorerna används fortsatt. Nya kontakter redovisas i `source-assignment.json` och ankarets geometribevis.

| Märkning | Före | Efter | Tillagd kontakt, PDF-punkter |
|---|---:|---:|---|
| 2×VV1-X31-16 | 1/2 | 2/2 | (979,68; 1007,32) |
| 2×KV2-X31-16 | 1/2 | 2/2 | (995,16; 1008,04) |

Alla fem buntmärkningar på bladet har därefter fullständigt antal kontakter: 2/2, 5/5, 2/2, 2/2 och 5/5.

Den ritade rörgeometrins längd är oförändrad: 10 782,479 PDF-punkter före och efter (summa av exporterade segment). Två befintliga segment delas vid korsningarna, från 1 403 till 1 405 delar. Alla 1 405 delar förekommer exakt en gång i återkopplingen från PipeStudios graf. Ingen längd har skapats eller multiplicerats.

Regressionstester omfattar dubbla buntkontakter, oförändrad längd, upprepad bearbetning, vanlig korsande hänvisning utan Nx, för många kandidater, närhet utan korsning och annan geometrifamilj. De två andra svåra provritningarna har inga Nx-ankare och får inga nya kontakter av denna rättning.

Detta verifierar det specifika kontaktfelet. Det är inte ett oberoende slutprov av hela systemets mängdträffsäkerhet.

## Upprepade etiketter i modellunderlaget

När båda kontakterna kom med fick modellunderlaget flera kandidat-ID:n för samma rörbeteckning. En verklig provkörning markerade då hela KV2-/VV1-gruppen som tvetydig, trots identiskt system, material, dimension och nivå. Det resultatet har bevarats som jobb `39ee3d92bc754e72857700c81b12ad6e` och är inte slutresultatet.

Transporten grupperar nu kandidater som är exakt identiska bortsett från lokal Nx-multiplicitet. Alla ursprungliga etikett-ID:n, antal, kontakter och bevis bevaras som `equivalent_occurrences`; slutpunkternas kontext och gränser ändras inte. Olika dimensioner, system, material eller nivåer grupperas aldrig. Modellen väljer fortfarande ett tillåtet ursprungligt kandidatpar och dess osäkerhet behålls ordagrant. Grupperingen gör ingen efterföljande tilldelning och höjer inte konfidensen i ett modellsvar.

Modellanropets resonemangsnivå följer dessutom PipeStudios originalstandard `medium`. Isolerad verklig kontroll av de 16 berörda sträckorna: 16 tilldelade, 0 tvetydiga, 0 otillåtna kandidatsvar. Detta är en kontroll av denna representation, inte ett allmänt träffsäkerhetsmått.

Slutlig verklig modellkörning: `6cbe3d587bb94dd485cea2b561b38c1d`. Alla fem buntmärkningar fullständiga. KV2-X31: 33,107 m och VV1-X31: 33,916 m, båda utan tvetydig buntmängd. Hela testsviten: 1 000 godkända, 3 överhoppade. Bladet har fortfarande 0,226 m annan osäker mängd; buntfelets rättning är inte en garanti för obevakad mängdning av godtyckliga ritningar.

## Senare slutkontroll

Jobb `5722104c3d0a4e7791278151f7db6ba2` kördes efter att verkliga ändsymbolbevis skickats vidare till modellen och visningsformen `160 (L)` normaliserats till PipeStudios parserform `160(L)`. Luftningsflaggan bevaras nu; originalmodulen ändrades inte. Resultatet blev 210,619 m horisontellt, 0,600 m vertikalt och 0 m tvetydigt.

0,952 m rå linjegeometri utanför skraffering återstår utan beteckning vid tre symbolområden. Den innehåller även sammanfallande streck och är inte ett fastställt bortfall av lika mycket fysisk rörlängd. Ytterligare 10,073 m ligger inom skraffering. Fullständig obevakad mängdning är därför inte verifierad. Se `results/current/a0013-fix/a0011-final.json`.

Slutlig motorsvit: 1011 godkända tester, 3 överhoppade. Dessa tester ersätter inte ett oberoende ritningsfacit.
