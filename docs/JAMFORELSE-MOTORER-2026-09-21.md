# Jämförelse på samma ritningar och facit

Samma PDF-hash och facit inom varje ritning. Exakt beteckning och centrumlinje, tolerans 1 PDF-punkt. Facit används först efter analys.

| Ritning | Motor | Facittäckning | Stöd i facit för förutsagd längd |
|---|---|---:|---:|
| A0111 | VVS5 original | 33.24 % | 65.58 % |
| A0111 | PipeStudio dimensions (OCR repair) | 35.61 % | 87.40 % |
| A0111 | PipeStudio model (OCR repair) | 53.96 % | 92.98 % |
| A0111 | Integrated | 56.35 % | 82.26 % |
| A0013 | VVS5 original | 85.54 % | 96.21 % |
| A0013 | PipeStudio dimensions | 39.79 % | 96.42 % |
| A0013 | PipeStudio model | 72.37 % | 90.90 % |
| A0013 | Integrated | 80.62 % | 91.44 % |
| A0522 | VVS5 original | 74.34 % | 73.72 % |
| A0522 | PipeStudio dimensions | 1.43 % | 12.40 % |
| A0522 | PipeStudio model | 10.75 % | 43.13 % |
| A0522 | Integrated | 55.37 % | 84.27 % |

Det integrerade systemet är inte bäst på alla mått. Obevakad mängdning är inte verifierad.
PipeStudios helt oförändrade A0111-flöde kraschar i `_split_shared_line` på en tom OCR-lista. Dess redovisade A0111-resultat innehåller en explicit OCR-reparation.
Swedish VVS innehåller regler, koduppslag och hjälpskript men ingen egen fullständig detektor att redovisa ett separat mängdresultat för.
Siffrorna är en körning per konfiguration. Modellvariation, vertikala meter och ritningar utan verifierat facit täcks inte av jämförelsen.

Maskinläsbara resultat och artefaktvägar: `results/current/engine-comparison-2026-09-21.json`.
