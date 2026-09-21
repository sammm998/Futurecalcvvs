# Förgreningen före första S3-R8-110-markeringen

Senare status samma datum: det fullständiga detektionsflödet är nu integrerat och aktiverat. Se [INTEGRERAT-DETEKTIONSFLODE-2026-09-21.md](INTEGRERAT-DETEKTIONSFLODE-2026-09-21.md). Beskrivningen nedan dokumenterar läget vid den tidigare isolerade regressionsrättningen.

Anmält jobb: d52bb0721b6e4d71bc199f52e6df91c9, W-50-1-A-0011.pdf.

## Orsak

Sträcka 110, från (957.96, 906.76) till (972.72, 876.88), fick S3-R8-160 av PipeStudios dimensionsflöde (`same_pipe`, hög säkerhet, rörkomponent 69). Modellen valde i stället etikett 25, S3-R8-110. Den ursprungliga modellinstruktionen tillåter att en grenetikett täcker tilloppet från huvudledningen. Den samlade analysen använde modellvalet utan att stämma av det mot källregel 4: samma rör fram till en faktisk beteckningskontakt. Därför flyttades dimensionsbytet från markeringen till grenfästet.

## Rättning

`source_rules/continuity.py` stämmer av efter modellbedömningen. Rättningen kräver:

- En av PipeStudio avgränsad rörkomponent med hög säkerhet.
- Ett dimensionsförslag med regeln `same_pipe` och hög säkerhet.
- En modellbekräftad del av samma komponent med den större dimensionen.
- Samma beteckning inklusive material-/servicefält, bortsett från dimensionen.
- Ett säkert modellval av mindre dimension på tilloppssträckan.

Abstentioner och osäkra modellval fylls inte i. En riktig beteckningskontakt avgränsar komponenten; rättningen fortsätter inte förbi den. Ursprungliga dimensions- och modellresultat sparas, och varje ändring har före/efter samt stödjande sträckor i `combined.boundary_reconciliation`. Jämförelsetabellen visar även samlat resultat.

## Isolerad kontroll

Samma sparade modellsvar återspelades före/efter, utan nya API-anrop. Kontroll mot den annoterade originalritningen sker först efter analys. 17 tilloppssträckor korrigerades, inklusive den anmälda sträckan. Den anmälda sträckan är nu S3-R8-160 fram till första S3-R8-110-kontakten.

| A0011, samma facit, tolerans 1 PDF-punkt | Före | Efter |
|---|---:|---:|
| Referenslängd återfunnen med rätt beteckning | 78,94 % | 82,54 % |
| Förutsagd längd som stöds av facit | 87,18 % | 91,17 % |

Resultat: `results/current/branch-boundary-regression/facit-before` och `facit-after`. Detta mäter ritad centrumlinje utanför skraffering, inte streckgap eller vertikala meter. Det verifierar denna regression, inte fullständig obevakad mängdning.

## Verifiering och kvarstående arbete

Full testkörning: 1041 godkända, 3 överhoppade och ett fel i rapporteringen från den experimentella detektorn när linjetyp saknades. Felet rättat till uttryckligt okänd linjetyp; berörda tester och förgreningstester kördes om: 16 godkända. Frontendbygget godkänt.

PipeStudios fullständiga detektionsadapter är fortfarande separat verifieringsarbete. Den ska inte aktiveras generellt eftersom A0522 ännu har lägre facittäckning. Appens standard använder fortsatt båda tilldelningsmetoderna tillsammans och automatisk stil. Swedish VVS regelimport innebär fortfarande inte att alla dokument- och platskrav är implementerade eller verifierade.

## Ny körning i appen

Jobb `b1e189d352d642d291dfc5e8b7c6f767` slutfört med åtta nya modellanrop och originalritningsbilder. Båda motorerna körda. Sträcka 110: dimensionsregler S3-R8-160, modell S3-R8-110, samlat slutresultat S3-R8-160. 17 avstämningar redovisas i gränssnittet. Appens jämförelsetabell och inzoomade ritning kontrollerade efter färdig rendering.
