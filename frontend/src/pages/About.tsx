import { Link } from "react-router-dom";
import { t as tr } from "../i18n";
import PublicFrame, { Prose, usePublished } from "../components/PublicFrame";

/* Om oss: varför tjänsten finns, vad den lovar och vad den vägrar. Texten kan skrivas om av en administratör
 * i innehållsverktyget (sidan "om-oss"); tills dess står den inbyggda. */

const BUILT_IN = `Vi bygger ett system som mängdar rör ur VVS-ritningar - och som hellre säger "vet inte" än gissar.

Det började med en enkel iakttagelse: en handmängdning tar timmar, och det mesta av tiden går inte åt till att mäta utan till att leta. Vilken beteckning hör till vilket rör? Var slutar den här ledningen egentligen? Är det där en avgrening eller bara två linjer som korsar varandra? En ritning svarar på de frågorna med sin egen geometri - ledarlinjer, penndrag, lager, förklaringslistor - och det är den geometrin vi läser.

## Vad vi lovar

Varje meter i en mängd har ett belägg. Beteckningen som lästes, ledaren som gick från den, röret ledaren pekade på, hur långt röret följdes och varför det slutade där, och skalan som gjorde punkter till meter. Allt det går att öppna, för varje rad, i webbläsaren.

Det som inte gick att avgöra står som tvetydigt. Ett rör utan ledare får inget namn av att det råkar ligga nära en etikett. Två linjer som korsar varandra blir inte en koppling för att de rör vid varandra. Vi tycker att en mängd som ser komplett ut men är gissad är värre än en som säger var den inte räcker till.

## Vad vi vägrar

Vi mäter aldrig på bildpunkter. En skannad ritning avvisas med besked, för där finns ingen geometri att läsa - bara en bild att gissa på. Vi låter aldrig en språkmodell hitta på geometri, koordinater eller meter; den får bara välja bland kandidater ritningen själv erbjuder, och en deterministisk kontroll måste godkänna valet. Och vi låter aldrig ett pris, en rabatt eller en kundrelation påverka hur en ritning läses.

## Hur vi arbetar

Systemet mäts mot riktiga, uppmätta ritningar - blint. Motorn körs först, resultatet fryses, och först därefter öppnas facit. Varje ändring i läsningen går genom samma grind: reproducera felet, hitta orsaken i ritningens egna vektorer, rätta generellt, testa, kör hela korpusen, jämför. Det som gör läsningen sämre på något blad backas. Det är långsamt, och det är det enda sättet vi vet att bygga något man kan lita på.

## Vem det är för

Rörentreprenörer som lämnar anbud. Kalkylatorer som mängdar handlingar. Konsulter som vill kontrollera sin egen ritning innan den går ut. Och den som lär sig yrket: akademin i tjänsten finns för att förstå ritningen, inte bara mängda den.`;

export default function AboutPage() {
  const c = usePublished("om-oss");
  return (
    <PublicFrame kicker="Om oss" title={c?.title || "Vi läser ritningen som den är ritad"}
      lede="Ett system byggt kring en princip: tvetydigt är ett giltigt svar, fel säkerhet är det inte.">
      <section className="pub-sec pub-prose">
        <Prose text={c?.body || BUILT_IN} />
      </section>
      <section className="pub-sec">
        <div className="pub-grid pub-three">
          <div className="pub-card flat"><h3>{tr("Evidens först")}</h3><p>{tr("Ingen meter utan belägg. Varje rad i mängden går att spåra till bladet.")}</p></div>
          <div className="pub-card flat"><h3>{tr("Blint mätt")}</h3><p>{tr("Motorn körs innan facit öppnas. Varje ändring grindas mot hela korpusen.")}</p></div>
          <div className="pub-card flat"><h3>Kontraktsneutralt</h3><p>{tr("Samma ritning ger samma rör oavsett AB 04 eller ABT 06. Avtalsformen bor i kalkylen, aldrig i geometrin.")}</p></div>
        </div>
        <p className="pub-cta">
          <Link className="lp-btn primary lg" to="/hur-det-funkar">{tr("Se hur läsningen går till")}</Link>
          <Link className="lp-btn ghost lg" to="/kontakt">{tr("Kontakta oss")}</Link>
        </p>
      </section>
    </PublicFrame>
  );
}
