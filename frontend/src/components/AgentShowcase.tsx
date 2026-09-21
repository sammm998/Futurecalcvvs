import { useInView } from "./lp-motion";
import { t as tr } from "../i18n";
import { tiltStyle, useTilt } from "./tilt";

/* The agent, shown as what it is: a conversation whose every number came out of the drawing.
 *
 * The panel leans; the tool calls that produced the answer sit behind it at their own depth, because that is the
 * relationship - the words in front rest on the calls behind. The proposal card is the one thing on the page
 * that would change a takeoff, and it says so.
 */

const TURN = [
  { who: "Du", text: "Hur mycket KV1-X31-16 är det på det här bladet?" },
  {
    who: "Agenten",
    text: "17,10 m på KV1-X31-16, fördelat på 2 sträckor.\n  01 · 8,68 m\n  02 · 8,42 m\nBåda vilar på en läst beteckning och en ritad hänvisningslinje.",
    calls: ["visa_hur_mangden_raknades(beteckning=\"KV1-X31-16\")"],
    ids: 2,
  },
  { who: "Du", text: "Sträcka 02 ligger i vägg och ska inte räknas." },
  {
    who: "Agenten",
    text: "Förslaget tar bort 8,42 m från KV1-X31-16. Längden kommer från läsningen.",
    calls: ["foresla_radera_ror(ror_id=[\"pp_bc65…\"], skal=\"ligger i vägg\")"],
    proposal: { head: "Tar bort 8,42 m fördelat på 1 sträcka i 1 beteckning.", row: "KV1-X31-16: 8,42 m tas bort" },
  },
];

export default function AgentShowcase() {
  const { ref, seen } = useInView<HTMLDivElement>();
  const { tilt, handlers } = useTilt(4);
  return (
    <section className="lp-sec lp-wrap" id="agent">
      <div className="lp-sec-head">
        <div className="lp-kicker">Agenten</div>
        <h2>{tr("Fråga ritningen, och se var svaret kom ifrån")}</h2>
        <p>
          Modellen väljer vilken fråga som ska ställas. Motorn svarar. Varje siffra i chatten kommer ur ett
          verktygsanrop mot läsningens egna artefakter, så chatten och mängdtabellen kan inte säga emot varandra.
        </p>
      </div>
      <div className={`lp-agent${seen ? " in" : ""}`} ref={ref}>
        <div className="lp-agent-stack" {...handlers} style={tiltStyle(tilt, 14)}>
          {/* the calls the answer rests on, behind the words that rest on them */}
          <div className="lp-agent-calls" aria-hidden="true">
            {["hamta_ritning()", "hitta_ror(system=\"KV1\")", "visa_hur_mangden_raknades(…)", "foresla_radera_ror(…)"]
              .map((c, i) => (
                <code key={c} style={{ animationDelay: `${0.5 + i * 0.13}s` }}>{c}</code>
              ))}
          </div>
          <div className="lp-agent-panel">
            <div className="lp-agent-head">
              <span className="dot" /> gpt-6-astra · 26 verktyg · 5 som föreslår en rättelse
            </div>
            {TURN.map((m, i) => (
              <div key={i} className={`lp-agent-msg ${m.who === "Du" ? "me" : "it"}`}
                style={{ animationDelay: `${0.25 + i * 0.35}s` }}>
                <div className="who">{m.who}</div>
                <p>{m.text}</p>
                {m.calls && (
                  <div className="lp-agent-tool">
                    {m.calls.map((c) => <code key={c}>{c}</code>)}
                  </div>
                )}
                {m.ids && <button className="lp-agent-show" type="button" tabIndex={-1}>Visa {m.ids} sträckor på ritningen</button>}
                {m.proposal && (
                  <div className="lp-agent-prop">
                    <div className="ph"><span className="ptag">{tr("Förslag")}</span>{m.proposal.head}</div>
                    <ul><li>{m.proposal.row}</li></ul>
                    <div className="pb"><span className="go">{tr("Genomför")}</span><span className="muted">{tr("Inget är ändrat än.")}</span></div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
        <ul className="lp-agent-facts">
          <li><b>{tr("Räknar aldrig själv.")}</b> {tr("Varje tal kommer ur ett verktyg som läser artefakterna mätningen skrev.")}</li>
          <li><b>{tr("Hittar aldrig på en beteckning.")}</b> {tr("En kod bladet inte mängdar på avvisas, med de som finns.")}</li>
          <li><b>{tr("Ändrar ingenting.")}</b> Ett förslag visar vad som skulle skrivas; du godkänner, och det kan ångras.</li>
          <li><b>{tr("Pekar på ritningen.")}</b> Varje påstående bär rör-id:n, så det går att trycka fram och se.</li>
        </ul>
      </div>
    </section>
  );
}
