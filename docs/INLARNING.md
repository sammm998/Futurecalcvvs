# Hur systemet lär sig, var människan står, och vad som är värt att skicka in

Frågan är inte om en människa ska vara med i slingan. Hon är redan med - på ett ställe, med en smal befogenhet,
och med avsikt. Den här sidan säger var, vad hon kan lära systemet i dag, vad hon *inte* kan, och vilket
material som mätbart skulle flytta mest just nu.

## 1. Slingan som finns

```
läsningen säger TVETYDIGT  ->  en människa avgör i granskningsrummet  ->  rättelsen sparas som rättelse
                                                                          |
                                             samma sorts fall på ett annat blad  <-  lärdom
```

**Rättelsen.** Det du ändrar i granskningsrummet skrivs som en ändring med ditt namn på, bredvid vad läsningen
sa. Ingen siffra byts ut i tysthet; båda står kvar, och exporten kan visa vilken som är vilken.

**Lärdomen** (`engine/vvs_engine/learning.py`). En rättelse får göra exakt en sak på ett senare blad: avgöra ett
fall som motorn *själv* har markerat TVETYDIGT, till förmån för det svar en människa gav i samma situation. Den
får aldrig skapa en sträcka, aldrig namnge geometri ingen hänvisningslinje nådde, aldrig ändra något motorn är
säker på, och aldrig rösta över ritningen.

"Samma situation" är inget likhetsmått. Det är exakt träff på sex saker, alla avlästa ur ritningen: pennan
geometrin är ritad med, hur bladet ritar sin hänvisningslinje, skälet motorn gav för att stanna, beteckningens
form (bokstäver och skiljetecken, inte siffrorna), fallets lokala topologi, och vilka kandidater ritningen
erbjöd. Träffar en lärdom på alla sex handlar den om samma sorts fall. Mindre än så gäller den inte - två blad
som bara liknar varandra är två olika ritningar. Att vidga fingeravtrycket kan bara göra att lärdomar talar mer
sällan, och det är det hållet som är ofarligt att ha fel åt.

Adminsidan visar vad som samlats: `GET /api/admin/learning` ger antalet lärdomar och vilka som är starka nog
att tala.

## 2. Vad en människa *inte* kan lära systemet i dag

Det här är den viktigaste delen av sidan, för det är här nästa arbete ligger.

* **Ett fall som motorn är säker på men har fel om.** Rättelsen gäller det bladet. Den blir ingen lärdom, för
  lärdomar rör bara TVETYDIGT. Det är rätt så länge motorns säkerhet är välgrundad - och den mätningen finns:
  av de 789 raderna i korpusen är 174 för långa och 197 för korta, och de flesta av dem är *inte* markerade
  tvetydiga. En människa kan alltså se ett fel som systemet inte kan lära sig av.
* **En konvention på ett kontor.** "Den här ritaren sätter alltid stapelns översta rad på det nedersta röret"
  är sant om ett helt projekt, men går bara in i systemet ett fall i taget.
* **Ett rör som saknas helt.** Finns ingen tvetydighet finns inget fall, och lärdomen har inget att fästa i.

## 3. Vad mätningarna säger är värt att lära

Från den här omgångens genomgång av alla 59 blad med facit: 2 372 m saknas, 1 790 m är för mycket, och
1 962 m av det som saknas ligger ritat i rätt penna utan ägare eller som tvetydigt.

| vad | meter | går det att lära in i dag |
|---|---:|---|
| tvetydiga fall (buntar, staplade etiketter) | 442 | **ja** - det är precis vad lärdomen är byggd för |
| oägd geometri i rätt penna | 1 520 | nej - inget tvetydigt fall att fästa i |
| rader som är för långa eller för korta | 3 125 (netto 582) | nej - motorn är säker |

**Slutsatsen: den mänskliga insatsen är mest värd på de tvetydiga fallen, och bara där.** Varje sådan rättelse
blir en lärdom som talar på nästa blad från samma kontor med samma penna och samma etikettform - och ett
projekt består av tjugo blad ritade likadant.

## 4. Material som skulle flytta mest, i ordning

**1. Markerade ritningar (`marked.pdf`), inte fler facitsummor.**
Den här omgången visade varför. En facitrad kan bara säga att en summa är fel. En markerad ritning - mängdarens
egna mätlinjer sparade i PDF:en - säger *vilken sträcka* och *vad den skulle ha hetat*. Med fem sådana blad gick
det att avgöra två föreslagna regler på en kvart:

* "räkna in de skrafferade metrarna" - **nej**: mängdaren mäter 0,1-1,2 % av sina meter inne i skraffering.
* "en oägd kedja tar sin enda namngivna grannes namn" - **nej**: rätt på 38,7 % av metrarna, fel på 54,7 %.

Båda hade sett rimliga ut. Utan markerade ritningar hade den ena eller båda byggts, och mängden hade blivit
sämre. **En markerad ritning är värd mer än tio facitsummor.** De saknas fortfarande för V-serien och för de
flesta W-blad.

**2. Ett blad där buntkonventionen syns, från varje kontor som förekommer.**
Tre parallella rör och en stapel etiketter: vilken rad hör till vilken linje? Ritaren vet, och konventionen är
konsekvent inom ett kontor. Ett blad med facit där just det är otvetydigt räcker för att pröva regeln.

**3. Kontorets typbeteckningslista.** Den avgör vad som är ett rörnamn och vad som är ett rumsnummer. Vi har en
sådan lista i materialet redan; en per kontor vore bättre.

**4. Rättade läsningar ur produktion.** När någon rättar en tvetydighet i appen blir det en lärdom. Tjugo
rättade blad från ett projekt är ett bättre facit än tjugo blad utan rättelser, för de lär systemet något.

## 5. Vad vi inte ber om

* **Inte fler ritningar utan facit.** Korpusen har redan fler blad än vad som mäts; det som saknas är
  sanningen om dem, inte fler av dem.
* **Inte handskrivna regler per kontor.** Varje regel i motorn ska gå att härleda ur bladet själv. En regel som
  bara gäller ett kontor är ett bladspecifikt undantag, och sådana är förbjudna i motorn.
* **Inte att någon märker upp vad som är rör.** Det är inte där felet sitter: 88 % av beteckningarna hittas.
  Felet sitter i *utsträckningen* - var ett stråk börjar och slutar.

## 6. Att skicka in material

Markerade ritningar och facit hör hemma i `data/`, som ligger utanför källkoden och som motorn aldrig når. En
skanner går igenom motorns alla filer före varje körning och vägrar om något av referensens ordförråd har
läckt in. Det är den regeln som gör att en mätning mot facit betyder något: koden kan inte ha sett svaret.
