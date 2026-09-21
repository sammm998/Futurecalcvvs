import { useState } from "react";
import { t as tr } from "../i18n";
import { Link } from "react-router-dom";
import PublicFrame from "../components/PublicFrame";
import { api } from "../api";

/* Kontakta oss: ett formulär som sparas hos tjänsten och syns för den som driver den under Meddelanden i
 * administrationen. Ingen e-postserver behövs för att ett meddelande ska komma fram. */

export default function ContactPage() {
  const [f, setF] = useState({ name: "", email: "", company: "", subject: "Demo på egen ritning", message: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  const set = (k: keyof typeof f) => (e: any) => setF({ ...f, [k]: e.target.value });
  const send = async (e: any) => {
    e.preventDefault();
    setBusy(true); setErr("");
    try { await api.contact(f); setDone(true); }
    catch (ex: any) { setErr(ex.message.replace(/\s*\(\d+\)$/, "")); }
    finally { setBusy(false); }
  };
  return (
    <PublicFrame kicker="Kontakta oss" title={<>Ta en ritning du redan mängdat.<br />Vi läser den tillsammans.</>}
      lede="Skriv vad det gäller - en demo på er egen handling, ett större konto, utbildning för kontoret, eller en ritning som lästes fel. Vi svarar inom en arbetsdag.">
      <section className="pub-sec pub-contact">
        {done ? (
          <div className="pub-card flat pub-thanks">
            <h3>{tr("Tack. Vi hör av oss.")}</h3>
            <p>Meddelandet är framme. Vill du inte vänta: skapa ett konto och prova på en egen ritning redan nu.</p>
            <p className="pub-cta"><Link className="lp-btn primary" to="/login">{tr("Kom igång")}</Link></p>
          </div>
        ) : (
          <form className="pub-form" onSubmit={send}>
            <div className="pub-form-row">
              <label>Namn<input required value={f.name} onChange={set("name")} autoComplete="name" /></label>
              <label>E-post<input required type="email" value={f.email} onChange={set("email")} autoComplete="email" /></label>
            </div>
            <div className="pub-form-row">
              <label>{tr("Företag")}<input value={f.company} onChange={set("company")} autoComplete="organization" /></label>
              <label>Ämne
                <select value={f.subject} onChange={set("subject")}>
                  <option>{tr("Demo på egen ritning")}</option>
                  <option>{tr("Priser och större konto")}</option>
                  <option>{tr("Utbildning för kontoret")}</option>
                  <option>{tr("En ritning lästes fel")}</option>
                  <option>Annat</option>
                </select>
              </label>
            </div>
            <label>Meddelande<textarea required rows={7} value={f.message} onChange={set("message")} placeholder={tr("Vilken slags handlingar, hur många blad, vad ni mängdar i dag…")} /></label>
            {err && <p className="pub-err">{err}</p>}
            <p className="pub-cta">
              <button className="lp-btn primary lg" type="submit" disabled={busy}>{busy ? "Skickar…" : "Skicka"}</button>
              <span className="pub-fine">{tr("Vi använder uppgifterna bara för att svara dig.")}</span>
            </p>
          </form>
        )}
        <aside className="pub-side">
          <div className="pub-card flat">
            <h3>{tr("Vad vi behöver för en demo")}</h3>
            <p>{tr("En ren vektor-PDF - exporterad ur CAD, inte skannad - och gärna er egen handmängdning av samma blad att jämföra med. Det är den enda rimliga första körningen.")}</p>
          </div>
          <div className="pub-card flat">
            <h3>Fel i en läsning?</h3>
            <p>{tr("Skriv vilket blad och vilken beteckning. Varje meter i tjänsten bär sitt belägg, så en felläsning går att spåra till ett steg - och rättas generellt, inte bara på ert blad.")}</p>
          </div>
          <div className="pub-card flat">
            <h3>Redan kund?</h3>
            <p>{tr("Logga in och skriv i agenten på din analys - den ser samma belägg som du och svarar ur dem.")}</p>
          </div>
        </aside>
      </section>
    </PublicFrame>
  );
}
