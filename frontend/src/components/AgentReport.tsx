import { t as tr, locale } from "../i18n";

const STATUS: Record<string, string> = {
  RUNNING: "arbetar", DONE: "klar", NOTHING_TO_DO: "inget att lösa", NO_MODEL: "ingen modell ansluten",
  TIME_LIMIT: "tidsgränsen nåddes", MODEL_FAILED: "modellen kunde inte nås", FAILED: "föll",
};

/* Vad agenten gjorde efter läsningen: problemen den fick, vad den svarade, koden den körde. Rättelserna den lade in
 * står bland rättelserna och ångras där som alla andra. */
export function AgentReport({ agent }: { agent?: any }) {
  if (!agent) return null;
  const NUM = new Intl.NumberFormat(locale());
  const sheets: any[] = agent.sheets ?? [];
  const fixes = sheets.reduce((n, s) => n + (s.corrections?.length ?? 0), 0);
  return (
    <details className="sub agentreport" open={agent.status === "RUNNING"}>
      <summary>
        {tr("Agenten")}: <b>{tr(STATUS[agent.status] ?? agent.status)}</b>
        {fixes > 0 && <> · {NUM.format(fixes)} {tr("rättelser att granska")}</>}
      </summary>
      {sheets.map((s) => (
        <div key={s.page} style={{ margin: "6px 0 10px" }}>
          <div className="muted">
            {tr("Blad")} {s.page + 1}: {tr(STATUS[s.status] ?? s.status)} · {s.problems?.length ?? 0} {tr("problem")}
            {" · "}{s.calls?.length ?? 0} {tr("verktygsanrop")} · {s.code?.length ?? 0} {tr("kodkörningar")}
            {" · "}{NUM.format(s.tokens_in ?? 0)} / {NUM.format(s.tokens_out ?? 0)} tokens
          </div>
          {s.problems?.length > 0 && (
            <ol style={{ margin: "4px 0 4px 18px" }}>
              {s.problems.map((p: any) => <li key={p.nr}>{p.text}</li>)}
            </ol>
          )}
          {s.report && <pre style={{ whiteSpace: "pre-wrap", fontSize: 12 }}>{s.report}</pre>}
          {s.code?.length > 0 && (
            <details>
              <summary>{tr("Koden agenten körde")}</summary>
              {s.code.map((c: any, i: number) => (
                <div key={i}>
                  <span className={c.ok ? "muted" : "error"}>{c.ok ? tr("körd") : `${tr("fel")}: ${c.fel}`}</span>
                  <pre style={{ fontSize: 11, maxHeight: 220, overflow: "auto" }}>{c.kod}</pre>
                </div>
              ))}
            </details>
          )}
        </div>
      ))}
    </details>
  );
}
