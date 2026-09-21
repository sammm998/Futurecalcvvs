# Integrerat detektionsflöde – verifierat läge

PipeStudios ursprungliga extraktion, profilering, detektion, OCR, indelning, sammanbyggnad och hänvisningskoppling körs nu automatiskt i appens analys. Dimensionsregler och modellbedömning körs tillsammans. Ritningsstil identifieras automatiskt. Referenskoden har inte redigerats; anpassningarna finns i separata adaptrar.

## Genomförda rättningar

- Verifierade hänvisningar från den andra läsaren kompletterar PipeStudios graf på samma ursprungliga PDF-sträcka. Kontakter på grannledningar godtas inte.
- Roterade beteckningskolumner läses i textens lokala riktning när kopplingen till dimensionsraden är entydig. Hela sidans rotation hanteras inte av denna komplettering.
- Bladets tabell över kopplingsledningar får ge lågprioriterade förslag för modellgranskning. En explicit beteckning går före; uteblivet modellsvar ger ingen bekräftad mängd.
- Tomma OCR-beteckningar filtreras före den punkt där originalmotorn annars kraschar. Bortfiltreringen redovisas separat.
- Detektionens cache kopieras inför varje skalpass. Tillagda kontakter och delade sträckor kan inte följa med av misstag till nästa pass.
- Etikettantalet räknar skrivna beteckningar en gång, även vid flera landningar. Två läsares observationer slås ihop endast med samma identitet och gemensam ursprunglig hänvisningsgeometri.

## Verifiering

Full testsvit före den sista etikettändringen: 1 055 godkända, 3 överhoppade. Efter etikettändringen: 11 berörda tester godkända; dessutom 7 tester för systemgränser och detektionscache godkända. Frontendbygget är godkänt.

Livejobb `29cee899d256460f8dab927881dc4c9c` slutfördes från appens analysknapp. Båda tilldelningsmetoderna och hela detektionsflödet slutförda, inga omatchade ursprungliga rörvägar på A0011. Den anmälda sträckan från (957.96, 906.76) till (972.72, 876.88) har fortsatt S3-R8-160 fram till första 110-kontakten. Sjutton avstämningar vid förgreningar redovisas. Detta jobb gjordes före den sista ändringen av etikettantal och cacheisolering.

A0011 med annoterat facit, full detektion: 82,81 procent facittäckning och 91,23 procent stöd i facit för förutsagd längd vid 1 PDF-punkts tolerans. Det är en separat körning, inte ett facitmått för användarens oannoterade uppladdning.

Jämförelsen av originalmotorerna på tre gemensamma ritningar finns i [JAMFORELSE-MOTORER-2026-09-21.md](JAMFORELSE-MOTORER-2026-09-21.md). Resultaten gäller redovisade körningar och konfigurationer; de är inte ett gemensamt slutligt godkännande av alla ritningar i denna version.

## Kvarstående begränsningar

Systemet är inte färdigverifierat för obevakad mängdning. A0111 och A0522 har fortsatt stora bortfall; original-VVS5 är bättre på vissa mått. Mer täckning får inte likställas med rätt tilldelning. Dolda PDF-vägar återinförs inte bara för att originaldetektorn hittar dem.

Alla 24 Swedish VVS-tabeller finns i importkontrollen. Regelrapporten skiljer körbara regler från referensmaterial och anger uttryckligen att full semantisk täckning och träffsäkerhet inte är verifierade. Dokument-, avtals- och platskrav som behöver externa handlingar markeras inte som uppfyllda av en PDF-analys.

Maskinläsbar regelrapport: `results/current/source-rule-runtime-coverage.json`. Motorjämförelse: `results/current/engine-comparison-2026-09-21.json`.
