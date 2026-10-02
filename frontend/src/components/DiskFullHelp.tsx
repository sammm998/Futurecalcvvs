import { useState } from "react";
import { t as tr } from "../i18n";
import { api } from "../api";

const mb = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v / (1024 * 1024)).toLocaleString()} MB`);

/* När analysen stoppades av ett fullt lager: rensa där felet syns, i stället för att leta upp knappen under
 * Administration -> Systemet. Den senaste körningen av varje ritning står kvar; bara äldre körningar av samma
 * ritning, misslyckade körningar och detektorns cache tas bort. */
export default function DiskFullHelp({ error }: { error?: string | null }) {
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<any>(null);
  const [err, setErr] = useState("");
  if (!error || !/Disken|No space left/i.test(error)) return null;
  const clean = () => {
    setBusy(true); setErr("");
    api.admPost("system/cleanup", {})
      .then(setDone)
      .catch((e) => setErr(/403|admin|behörig/i.test(String(e.message)) ? tr("Bara en administratör kan rensa lagret.") : e.message))
      .finally(() => setBusy(false));
  };
  return (
    <div className="card" style={{ marginTop: 12 }}>
      <p style={{ marginTop: 0 }}>
        {tr("Rensa lagret: äldre körningar av samma ritning, misslyckade körningar och detektorns cache tas bort. Den senaste körningen av varje ritning står kvar.")}
      </p>
      <button className="btn" onClick={clean} disabled={busy}>{busy ? tr("Rensar…") : tr("Rensa lagret")}</button>
      {done && (
        <p style={{ marginBottom: 0 }}>
          {tr("Ledigt före")}: {mb(done.free_before)} · {tr("efter")}: <b>{mb(done.free_after)}</b>. {tr("Starta analysen igen.")}
        </p>
      )}
      {err && <p className="error" style={{ marginBottom: 0 }}>{err}</p>}
    </div>
  );
}
