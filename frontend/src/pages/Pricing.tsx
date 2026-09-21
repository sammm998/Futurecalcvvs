import { useEffect, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link } from "react-router-dom";
import PublicFrame from "../components/PublicFrame";

/* Priser: vad en läsning kostar, i credits, och vad credits kostar, i kronor.
 *
 * Prislistan hämtas från tjänsten - samma lista som drar priset när en läsning startar - så att det som står
 * här aldrig kan vara något annat än det som gäller. Två löften bär sidan: priset syns innan man trycker, och
 * en läsning som inte kunde ge en meter kostar ingenting. */

const fmt = (v: number) => v.toLocaleString(locale(), { maximumFractionDigits: 2 });

export default function PricingPage() {
  const [p, setP] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    fetch("/api/public/pricing")
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then(setP)
      .catch(() => setErr("Prislistan kunde inte hämtas just nu."));
  }, []);
  const best = p ? p.packages.reduce((b: any, x: any) => (!b || x.kr / x.credits < b.kr / b.credits ? x : b), null) : null;
  return (
    <PublicFrame kicker="Priser" title={<>Betala för det som lästes —<br />inte för att du provade</>}
      lede="En läsning kostar credits. Priset står på ritningen innan du trycker, och en läsning som inte kunde ge en enda meter betalas tillbaka av sig själv."
      aside={p ? (
        <div className="pub-keys">
          <div className="pub-key"><div className="n">{p.trial_credits}</div><div className="l">{tr("credits att prova med")}</div></div>
          <div className="pub-key"><div className="n">{p.sheet?.A3}</div><div className="l">{tr("credits för ett A3-blad")}</div></div>
        </div>
      ) : undefined}>
      {/* Prislistan kommer ur tjänsten, så att det som står här aldrig kan vara något annat än det som gäller.
          Svarar den inte får sidan inte gissa ett pris - men den får inte heller bli tom. Det som står kvar är
          det som är sant oavsett vad listan säger: löftena, och vägen till ett besked. */}
      {err && (
        <section className="pub-sec">
          <div className="pub-card flat">
            <h3>{err}</h3>
            <p>
              Priset hämtas ur tjänsten när sidan öppnas, så att det aldrig kan stå något annat här än det som
              faktiskt dras. Just nu svarar den inte, och då skriver vi hellre ingen siffra än fel siffra.
            </p>
            <p className="pub-cta">
              <button className="lp-btn primary" onClick={() => window.location.reload()}>{tr("Försök igen")}</button>
              <Link className="lp-btn ghost" to="/kontakt">{tr("Fråga oss om priset")}</Link>
            </p>
          </div>
        </section>
      )}
      {p && (
        <>
          <section className="pub-sec">
            <div className="lp-kicker">Paket</div>
            <h2>{tr("Credits köps i paket. Priser exklusive moms.")}</h2>
            <div className="pub-grid pub-packages">
              {p.packages.map((pk: any) => (
                <article key={pk.id} className={`pub-card${best && pk.id === best.id ? " best" : ""}`}>
                  {best && pk.id === best.id && <span className="pub-tag">{tr("Bäst värde")}</span>}
                  <h3>{pk.name}</h3>
                  <div className="pub-big">{pk.credits.toLocaleString(locale())} <span>credits</span></div>
                  <div className="pub-price">{pk.kr.toLocaleString(locale())} kr</div>
                  <div className="pub-per">{fmt(pk.kr / pk.credits)} kr per credit</div>
                  <p>{pk.lead}</p>
                  <Link className="lp-btn primary" to="/login">{tr("Kom igång")}</Link>
                </article>
              ))}
            </div>
            <p className="pub-note">
              Ett nytt konto får {fmt(p.trial_credits)} credits att prova med. Köp faktureras till företaget; credits finns på kontot direkt.
            </p>
          </section>

          <section className="pub-sec">
            <div className="lp-kicker">{tr("Vad en läsning kostar")}</div>
            <h2>Priset följer bladet: formatet och mängden bläck</h2>
            <p className="pub-p">
              En A3-plan med tusen streck och en A0-plan med sextiotusen kostar inte samma sak att läsa, och de kostar
              inte samma sak för dig. Priset räknas per sida ur pappersformatet, plus ett tillägg för blad med ovanligt
              mycket bläck. Det står på ritningen innan du trycker på Analysera - aldrig i efterhand.
            </p>
            <div className="pub-tablewrap">
              <table className="pub-table">
                <thead>
                  <tr><th>Sida</th><th>{tr("A3 och mindre")}</th><th>A2</th><th>A1</th><th>A0</th><th>{tr("Större än A0")}</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td>Credits</td>
                    {["A3", "A2", "A1", "A0", "A0+"].map((k) => <td key={k}>{fmt(p.sheet[k])}</td>)}
                  </tr>
                </tbody>
              </table>
            </div>
            <ul className="pub-list">
              <li>
                <b>{tr("Bläcktillägg.")}</b> Fler än {Number(p.ink_step_paths).toLocaleString(locale())} banor på en sida ger {fmt(p.ink_step_credits)} credit
                extra per påbörjat sådant steg, upp till {fmt(p.ink_cap_credits)} credits. Det syns i priset innan läsningen.
              </li>
              <li><b>{tr("Andra blick.")}</b> En granskning med syn av en färdig läsning kostar {fmt(p.vision_page)} credit per sida, och begärs bara när du ber om den.</li>
              <li><b>{tr("Ingår.")}</b> {tr("Projektanalysen över hela handlingen, kalkylen och anbudet, mängdningsverktyget, CAD-rummet, exporter och akademin kostar inga credits.")}</li>
              {p.refund_when_unmeasured && <li><b>{tr("Återbetalning.")}</b> {tr("Saknar bladet skala, eller går läsningen fel, får du tillbaka priset utan att fråga. Skälet står i din reskontra.")}</li>}
            </ul>
          </section>

          <section className="pub-sec">
            <div className="lp-kicker">{tr("Att jämföra med")}</div>
            <h2>Vad kostar en handmängdning?</h2>
            <p className="pub-p">
              En erfaren kalkylator mängdar en planritning på en halvtimme till ett par timmar, beroende på bladet. Här
              tar den några minuter, och varje meter i tabellen bär sitt belägg: beteckningen, ledaren, röret den
              pekar på, och skalan. Det som inte gick att avgöra står som tvetydigt i stället för att fyllas i.
            </p>
            <div className="pub-grid pub-three">
              <div className="pub-card flat"><h3>Innan</h3><p>{tr("Priset står på ritningen. Inget dras förrän du trycker.")}</p></div>
              <div className="pub-card flat"><h3>Under</h3><p>{tr("Du ser läsningen steg för steg, och kan gå ett delmoment i akademin medan den kör.")}</p></div>
              <div className="pub-card flat"><h3>Efter</h3><p>{tr("Mängden, beläggen, exporten. Var meter går att spåra tillbaka till bladet.")}</p></div>
            </div>
          </section>

          <section className="pub-sec">
            <div className="lp-kicker">{tr("Vanliga frågor")}</div>
            <div className="pub-faq">
              <details><summary>Vad händer om jag läser samma ritning två gånger?</summary><p>{tr("Varje läsning kostar sitt pris - men en läsning som inte kunde ge en meter betalas tillbaka, så en omläsning med en skala du skrev in för hand kostar bara en gång.")}</p></details>
              <details><summary>Går credits ut?</summary><p>{tr("Nej. De ligger kvar på kontot tills de används.")}</p></details>
              <details><summary>Kan flera på kontoret dela på en pott?</summary><p>{tr("Ja. Credits hör till kontot, inte till inloggningen. En firma med fyra rörläggare har en pott och fyra inloggningar.")}</p></details>
              <details><summary>Hur betalar vi?</summary><p>{tr("Köp faktureras till företaget med 30 dagars betalningstid. Credits finns på kontot i samma stund som köpet registreras.")}</p></details>
              <details><summary>Behöver vi ett abonnemang?</summary><p>{tr("Nej. Köp det paket som passar och fyll på när det behövs. Storkunder som vill ha en fast månadskostnad hör av sig.")}</p></details>
            </div>
            <p className="pub-cta">
              <Link className="lp-btn primary lg" to="/login">Prova med {fmt(p.trial_credits)} credits</Link>
              <Link className="lp-btn ghost lg" to="/kontakt">{tr("Prata med oss")}</Link>
            </p>
          </section>
        </>
      )}
    </PublicFrame>
  );
}
