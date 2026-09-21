import { useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { api } from "../api";

/* Projektagenten: frågor till hela handlingen.
 *
 * Samma delning som ritningsagenten: modellen väljer verktyg, verktygen svarar ur det som redan lästs - rapporten
 * och bladens läsningar. Två regler som är projektets egna: ett svar om ett hus bygger bara på det husets blad,
 * och varje svar säger vilka blad det vilar på. De färdiga frågorna går rakt in i verktygen utan någon modell,
 * så de kan inte hitta på en siffra; fritext behöver modellen för att välja verktyg, det är hela skillnaden.
 */

type Msg = { role: "user" | "agent"; text: string; tools?: any[] };
type Quick = { text: string; tool: string; args?: any };

const QUICK: { grupp: string; fragor: Quick[] }[] = [
  { grupp: "Handlingen", fragor: [
    { text: "Vad består handlingen av?", tool: "hamta_handling" },
    { text: "Vilka blad finns?", tool: "hitta_blad" },
    { text: "Versioner och det oklara", tool: "versioner" },
  ] },
  { grupp: "Mängder", fragor: [
    { text: "Mängder per hus", tool: "mangder_per_hus" },
  ] },
  { grupp: "Kontroll", fragor: [
    { text: "Vad bör jag titta på?", tool: "kontrollera_handlingen" },
    { text: "Vad har rättats för hand?", tool: "rattelser" },
  ] },
];

/* Ett verktygssvar som text en människa läser: nyckel för nyckel, listor som rader, blad med namn. */
function render(v: any, depth = 0): string {
  const pad = "  ".repeat(depth);
  if (v == null) return "";
  if (Array.isArray(v)) {
    if (!v.length) return `${pad}(inga)`;
    return v.map((x) => (typeof x === "object" ? render(x, depth) : `${pad}${x}`)).join("\n");
  }
  if (typeof v === "object") {
    if (v.blad && v.drawing_id) {           // en källhänvisning
      return `${pad}${v.nummer ?? ""} ${v.blad}${v.hus ? ` (hus ${v.hus})` : ""}`.trim();
    }
    return Object.entries(v).map(([k, x]) =>
      typeof x === "object" && x !== null ? `${pad}${k}:\n${render(x, depth + 1)}` : `${pad}${k}: ${x}`).join("\n");
  }
  return `${pad}${v}`;
}

export default function ProjectAgentChat({ projectId }: { projectId: string }) {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length, busy]);

  const ask = async (q: string, quick?: Quick) => {
    if (!q.trim() && !quick) return;
    setBusy(true); setErr("");
    setMsgs((m) => [...m, { role: "user", text: quick ? quick.text : q }]);
    setText("");
    try {
      const history = msgs.map((m) => ({ role: m.role === "agent" ? "assistant" : "user", content: m.text }));
      const r = quick
        ? await api.projectAgentTool(projectId, quick.tool, quick.args ?? {})
        : await api.projectAgent(projectId, { question: q, history });
      const tools = r.verktyg ?? [];
      const body = r.svar || tools.map((t: any) => render(t.resultat)).join("\n\n") || "(inget svar)";
      setMsgs((m) => [...m, { role: "agent", text: body, tools }]);
    } catch (e: any) {
      setErr(e.message);
    } finally { setBusy(false); }
  };

  return (
    <div className="agentchat">
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          Agenten svarar ur det som lästs — rapporten och bladens läsningar — och säger vilka blad svaret vilar på.
          Ett svar om ett hus bygger bara på det husets blad. De färdiga frågorna behöver ingen modell.
        </p>
        <div className="quick">
          {QUICK.map((g) => (
            <div key={g.grupp} className="qgrp">
              <span className="lbl">{g.grupp}</span>
              {g.fragor.map((f) => (
                <button key={f.text} className="ghost small" disabled={busy} onClick={() => ask("", f)}>{f.text}</button>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="msgs">
        {msgs.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <pre className="lf-pre">{m.text}</pre>
            {m.tools && m.tools.length > 0 && m.role === "agent" && (
              <div className="muted small">verktyg: {m.tools.map((t: any) => t.namn).join(", ")}</div>
            )}
          </div>
        ))}
        {busy && <p className="muted small">{tr("Frågar…")}</p>}
        {err && <p className="error">{err}</p>}
        <div ref={end} />
      </div>
      <div className="row" style={{ marginTop: 10 }}>
        <input value={text} placeholder={tr("Fråga hela handlingen… t.ex. hur många meter KV01 finns i hus A?")}
          onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") ask(text); }}
          style={{ flex: 1 }} disabled={busy} />
        <button onClick={() => ask(text)} disabled={busy || !text.trim()}>{tr("Fråga")}</button>
      </div>
    </div>
  );
}
