# Agentens recept: hur en lösning blir en regel

1. **Agenten löser** ett öppet problem på en ritning: en beteckning utan rör, onamngivet rör, en flagga eller en
   saknad skala. Den gör det med egen kod i sandlådan och skriver rättelser märkta `agent`.
2. **Receptet sparas** per konto (`agent_recipes`). Det innehåller problemen, koden som fungerade, verktygen i
   ordning och rättelserna.
3. **Receptet håller** så länge personen låter rättelserna stå. Ångras en rättelse visas receptet aldrig mer.
   Rättelser som läggs åt sidan för att ritningen lästs om räknas inte som ångrade.
4. **Receptet återanvänds** på samma kontos nästa ritningar med samma typ av problem. Agenten får högst 5 recept
   i sin uppgift och provar dem först. Ritningen avgör alltid.
5. **Receptet blir aldrig en regel av sig självt.** Under Admin → Agentens recept syns vilka problemtyper som löses
   och vilka recept som håller. En utvecklare skriver om ett bra recept till motorkod, och
   `python engine/tools/corpus.py run …` och `gate …` mot `engine/tests/data/corpus_baseline.json` måste visa att
   inget blad blir sämre innan ändringen mergas. Först då gäller lösningen alla ritningar.
