# Samtalsagent i ritningsvyn

Öppna en färdig analys och välj **Samtalsagent**. **Starta samtal** ansluter till OpenAI utan att öppna mikrofonen. **Prata med agenten** aktiverar mikrofonen separat. Det går också att skriva och fortsätta samma konversation. **Avsluta samtal** eller stäng panelen för att koppla från.

## Kommandon och bilder

- Zooma, panorera, visa hela bladet, växla mellan 2D och 3D.
- Be agenten välja ett namngivet rör. Agenten läser det aktuella bladets analysdata och urval.
- Förläng ett valt rör med en angiven längd och riktning. Förlängningen sparas som en separat korrigering och visas i 2D och när 3D öppnas igen. Original-PDF och analysens geometri skrivs inte över. Upprepad förlängning börjar vid den sparade änden. Tvetydiga ändar avvisas.
- Ångra senaste agentförlängningen; övriga korrigeringar kan ångras under Rätta.
- Be agenten titta på vyn. Den får ett utsnitt av originalritningen i 2D eller aktuell 3D-rendering. Den ser inte andra program eller hela skrivbordet.

## Handstyrning

**Starta handstyrning** öppnar kameran separat. Nyp tumme och pekfinger med en hand och dra för att panorera. Nyp med båda händerna och ändra avstånd för att zooma. Släpp för att stanna. Handstyrning gör inga mängdändringar.

MediaPipe 1.0.1, handmodellen och WASM-filerna levereras lokalt. Bildbehandlingen körs i en worker på datorn. Kamerabilder skickas inte till OpenAI av handstyrningen. **Dela kamerabild i samtalet** skickar en enstaka bild uttryckligen. Kameran stängs när handstyrningen eller panelen stängs.

## Anslutning

Befintlig privat OpenAI-konfiguration används på servern. `VVS_REALTIME_MODEL` kan ange annan kompatibel modell; standard är `gpt-realtime-2.1`, som kontrollerats tillgänglig i installationen. Webbläsaren får en tillfällig sessionsnyckel med 60 sekunders giltighet för anslutning. Huvudnyckeln lämnar inte servern. Sessionsvägen kräver inloggning, ägarskap till analysen och färdig analys, och returneras med `Cache-Control: no-store`.

Implementation bygger på [OpenAI WebRTC](https://developers.openai.com/api/docs/guides/voice-webrtc), [Realtime-konversationer och verktyg](https://developers.openai.com/api/docs/guides/realtime-conversations) och [Googles Hand Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker).

## Verifikation

Riktig OpenAI-session i in-app-webbläsaren: textkommando till 3D, tillbaka till 2D, zoom, val av KV1-X31-16, förlängning med 1 meter, ångra och mottagen ritningsbild. Testkorrigeringen är ångrad. Samtalet avslutades. Mikrofonen öppnades inte i testet.

Den lokala workern laddades och analyserade en blank bild utan kamera. 26 deterministiska kontroller testar handgester, borttappade händer, återupptagning, förlängningsgeometri, tvetydiga ändar, upprepad förlängning, 3D-visning och ångrade korrigeringar. API-tester kontrollerar ägarskap, inloggning, färdigstatus och att providerfel inte läcker nycklar. Fysisk mikrofon, kamera och användarens faktiska handrörelser är inte verifierade.

Samtalsagenten verifierar inte automatiskt mängdmotorns träffsäkerhet. Bedömning av en bild är inte ett handmängdat facit.
