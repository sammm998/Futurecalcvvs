import { useEffect, useState } from "react";
import { api, AI_MODEL_KEY } from "../api";
import { t as tr, locale } from "../i18n";

/* Vilken språkmodell som avgör rörens beteckningar när en ritning analyseras - eller ingen. Valet sparas i
 * webbläsaren och följer med varje analys som startas härifrån, så samma ritning kan läsas en gång med varje
 * och svaren, tokens och priset jämföras sida vid sida. En modell servern saknar nyckel till går inte att välja. */

type Choice = { id: string; label: string; available: boolean };

function stored(): string | null {
  try { return localStorage.getItem(AI_MODEL_KEY); } catch { return null; }
}

export default function AiModelPicker({ compact = false }: { compact?: boolean }) {
  const [choices, setChoices] = useState<Choice[]>([]);
  const [value, setValue] = useState<string | null>(stored());

  useEffect(() => {
    let live = true;
    api.analysisOptions().then((o: any) => {
      if (!live) return;
      const list: Choice[] = o.ai_models ?? [];
      setChoices(list);
      const current = stored();
      const ok = list.find(c => c.id === current && c.available);
      if (!ok) pick(o.ai_default ?? "none");
    }).catch(() => {});
    return () => { live = false; };
  }, []);

  function pick(id: string) {
    try { localStorage.setItem(AI_MODEL_KEY, id); } catch { /* utan lagring gäller serverns standard */ }
    setValue(id);
  }

  if (!choices.length) return null;
  return (
    <div className={`aimodel${compact ? " compact" : ""}`}>
      <span className="aimodel-l">{tr("AI-modell")}</span>
      <div className="seg" role="radiogroup" aria-label={tr("AI-modell för analysen")}>
        {choices.map(c => (
          <button key={c.id} type="button" role="radio" aria-checked={value === c.id}
            className={value === c.id ? "on" : ""} disabled={!c.available}
            title={c.available ? undefined : tr("Inte ansluten på servern")}
            onClick={() => pick(c.id)}>{tr(c.label)}</button>
        ))}
      </div>
    </div>
  );
}


/* Vilken modell som läste den här analysen och vad den kostade - samma rad för alla tre val, så att två läsningar
 * av samma ritning kan jämföras: mängden i tabellen, tokens och pris här. */
export function AiUsage({ usage }: { usage?: any }) {
  if (!usage) return null;
  const NUM = new Intl.NumberFormat(locale());
  const none = usage.model === "none";
  return (
    <p className="sub aiusage">
      {tr("Läst med")} <b>{tr(usage.label ?? usage.model)}</b>
      {!none && <> · {NUM.format(usage.requests)} {tr("anrop")} · {NUM.format(usage.tokens_in)} {tr("tokens in")}
        {usage.cached_tokens ? <> ({NUM.format(usage.cached_tokens)} {tr("från cache")})</> : null}
        {" · "}{NUM.format(usage.tokens_out)} {tr("tokens ut")}
        {" · "}{usage.usd == null ? tr("pris okänt") : `$${usage.usd.toFixed(2)}`}</>}
      {none && <> · {tr("ingen AI-kostnad")}</>}
      {usage.fell_back_to_rules && <> · {tr("modellen svarade inte, reglerna läste bladet")}</>}
    </p>
  );
}
