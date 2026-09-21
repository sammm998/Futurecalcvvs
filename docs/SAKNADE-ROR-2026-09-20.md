# Felanalys av A0111 och A0031

Bilderna visar tre skilda steg som kan fallera: geometri som avvisas innan tilldelningen, hänvisningar som inte når geometrin och beteckningar som inte når vidare över komponenter. Att importera källreglerna räcker inte när deras indata redan saknar rör eller kontakter.

## Rättat

På A0111 avvisades S2-lagret som `NO_CONTINUOUS_RUN` trots en kedja på 37 PDF-punkter och verkliga hänvisningskontakter. Lagrets totala längd var 54,5 punkter, under den tidigare generella gränsen 60. Ett system med få rör blev därför osynligt för PipeStudios tilldelning.

Ett kort lager kan nu släppas fram om det har en riktig hänvisningskontakt vars system matchar lagret, en kedja på minst 25 punkter och en grövre penna än ritningens hänvisningar. Lagertext ensam räcker inte. Korta symbolstreck och tunna hänvisningslager får inte samma undantag. Tilldelningen till beteckning måste fortfarande bedömas av båda källmotorerna.

Uppdelningen vid anslutningar och lokala VG-punkter från föregående rättning behålls. Rågeometri och streckglapp ska räknas exakt en gång.

## Genomgång av källkod och återstående brister

Granskade delar är VVS5:s familjefilter, hänvisningskontakter och grafbygge, PipeStudios `extract`, `bucket`, `assemble`, `final_bind` och globala valideringsregler samt Swedish VVS:s `pipe_marking_rules` och `line_types`.

PipeStudio behåller korta anslutningsstumpar och har stängt av en aggressiv symbolklusterfiltrering eftersom den förlorade rör. Integrationen använder fortfarande VVS5-geometri, så det beteendet kan inte räknas som fullständigt integrerat bara för att PipeStudios tilldelningsregler används.

Böjen i vattenstråket nära fördelarsymbolerna finns som geometri, men dess komponent saknar giltig etikettkontakt. Andra närliggande rörändar tillhör flera olika grenar. De får inte bindas ihop enbart efter avstånd: då riskerar KV, VV och olika dimensioner att blandas. Fördelarens kontakter behöver tolkas bättre. Swedish VVS:s regel om avbrott vid korsning innebär kontinuitet längs röret, inte anslutning till det korsande röret.

ML-detektorn för etikettområden finns som kontrollsteg men dess förslag är inte en fullständig alternativ läsning av alla beteckningar. Därför kan importerade modeller och regler inte redovisas som fullständigt verksam och verifierad funktion.

## Facit

A0111 kördes mot exakt PDF-fil angiven av XML-facit. Geometrisk täckning med exakt beteckning och tolerans 1 PDF-punkt blev 38,9 %, med 63,9 % stöd för den jämförda predikterade geometrin. Referensens horisontella mängd är 519,5 m; matchade mängder per beteckning 303,81 m och överskjutande mängd 45,21 m. Måtten har olika definitioner och ska inte blandas ihop.

A0031:s XML-koppling är markerad `same_folder_xml_stem_needs_review`. Den hoppas över, i stället för att ge ett falskt verifierat resultat. Dess bildexempel är fortfarande ett öppet fel.

Fullständig obevakad mängdning är inte verifierad. Facit används först efter analysen och matas inte till modellen.
