# Verifieringsstatus 2026-09-21

Systemet är under utveckling och är inte verifierat för obevakad mängdning.

## Verifierat i den lokala arbetskopian

- 1 065 tester godkända, 3 överhoppade (motor och backend).
- Frontendens produktionsbygge och automatiska gesttester godkända.
- Dimensionsregler och modellbedömning används tillsammans; ritningsstil bedöms automatiskt.
- PipeStudios ursprungliga detektionsflöde körs genom adaptrar. Bevarade källfiler ändras inte.
- Regressionen för S3-R8-160 fram till första S3-R8-110-markeringen på A0011 kontrollkördes med en ny modellbedömning och passerade.
- Långsamma handrörelser ackumuleras nu över flera bildrutor i stället för att försvinna i dödzonen.

## Kvarvarande fel och verifiering

A0522 har fortfarande omfattande bortfall. Senaste jämförelsen mot samma referens gav 50,66 % täckning och 80,97 % stöd, jämfört med 55,37 % och 84,27 % i en tidigare integrerad körning. Måtten avser referensgeometri och identitet med 1 PDF-punkts tolerans, inte garanterad korrekt mängd. Modellvariation har inte kvantifierats. Förändringarna är därför inte visade som en generell förbättring.

Importerade Swedish VVS-regler är inte automatiskt implementerade eller verifierade motorregler. Ursprungliga jämförelser och delverifieringar finns i övriga dokument; de beskriver sina respektive versioner, inte nödvändigtvis aktuell kod.

Fysisk mikrofon och kamera samt handstyrning på användarens utrustning behöver fortfarande verifieras. Testerna ersätter inte denna kontroll.

## GitHub-leverans

Kodexporten innehåller ingen lokal kontodatabas, API-nyckel, uppladdad ritning eller historik med sådana filer. Modeller, lokala handspårningsresurser och bevarade regelkällor ingår. Ritningar och lokala resultatartefakter måste tillföras separat för att återupprepa externa facitjämförelser. Testresultaten ovan gäller arbetskopian med dess lokala testunderlag, inte ett nyklonat repo utan dessa underlag.

## Separat kontroll av GitHub-exporten

Efter export och installation av frontendberoenden: 1 065 tester godkända, 3 överhoppade. Produktbygge och gesttester passerade också. Två överhoppade prov kräver Linux för Debian-beroenden; ett kräver ett separat referensblad. Dessa körningar använder den lokalt installerade Python-miljön; en ren GitHub Actions-körning återstår.
