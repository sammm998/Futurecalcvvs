import { useEffect, useState } from "react";
import { t as tr } from "../i18n";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api";

/* Ritbordet: bladen man ritat själv, och vägen till ett nytt.
 *
 * Här laddas ingenting upp. Vill man mäta någon annans ritning är det mängdningens rum; det här rummet är för
 * det man ritar själv - ett stamschema, en ändring, ett förslag. Ett blad börjar som ett pappersformat och en
 * skala, och blir en ritning genom att någon ritar den.
 */

const PAPERS: [string, string][] = [
  ["A0", "1189 × 841 mm"], ["A1", "841 × 594 mm"], ["A2", "594 × 420 mm"],
  ["A3", "420 × 297 mm"], ["A4", "297 × 210 mm"],
];
const RATIOS = [20, 25, 50, 100, 200, 500];

export default function CadPickPage() {
  const nav = useNavigate();
  const [rows, setRows] = useState<any[] | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("Nytt blad");
  const [paper, setPaper] = useState("A3");
  const [ratio, setRatio] = useState(50);
  const [project, setProject] = useState("");

  const load = () => {
    api.cadSheets().then((d) => setRows(d.rows)).catch((e) => setErr(e.message));
    api.projects().then((ps: any[]) => {
      setProjects(ps);
      setProject((p) => p || ps[0]?.id || "");
    }).catch((e) => setErr(e.message));
  };
  useEffect(load, []);

  const create = async () => {
    if (!project) { setErr("Bladet hör hemma i ett projekt. Skapa ett projekt först."); return; }
    setBusy(true); setErr("");
    try {
      const s = await api.cadCreate({ project_id: project, name: name.trim() || "Nytt blad", paper, scale_ratio: ratio });
      nav(`/cad/${s.id}`);
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const remove = async (id: string) => {
    try { await api.cadDelete(id); load(); } catch (e: any) { setErr(e.message); }
  };

  return (
    <main>
      <p className="crumb">CAD</p>
      <div className="head">
        <div>
          <h1>CAD</h1>
          <p className="lead">
            Ritbordet. Här ritas ett blad från grunden - linjer, rör, text och mått i byggets egna millimeter,
            med objektfångst och låsta vinklar så att det som möts verkligen möts. Ett färdigt blad trycks ut
            som en ritning och kan då mängdas precis som en inlämnad handling.
          </p>
        </div>
      </div>
      <div className="rule" style={{ marginBottom: 20 }} />

      <div className="card cad-new">
        <h3 style={{ marginTop: 0 }}>{tr("Nytt blad")}</h3>
        <div className="row" style={{ gap: 10, flexWrap: "wrap", alignItems: "flex-end" }}>
          <label className="small" style={{ minWidth: 200 }}>Namn
            <input value={name} onChange={(e) => setName(e.target.value)} style={{ width: "100%" }} />
          </label>
          <label className="small">Projekt
            <select value={project} onChange={(e) => setProject(e.target.value)}>
              {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label className="small">Format
            <select value={paper} onChange={(e) => setPaper(e.target.value)}>
              {PAPERS.map(([p, mm]) => <option key={p} value={p}>{p} · {mm}</option>)}
            </select>
          </label>
          <label className="small">Skala 1:
            <select value={ratio} onChange={(e) => setRatio(Number(e.target.value))}>
              {RATIOS.map((r) => <option key={r}>{r}</option>)}
            </select>
          </label>
          <button onClick={create} disabled={busy}>{busy ? "Skapar…" : "Börja rita"}</button>
        </div>
        {!projects.length && <p className="muted small" style={{ marginBottom: 0 }}>
          Du har inget projekt ännu. <Link to="/projekt">{tr("Skapa ett")}</Link> så hamnar bladet där.
        </p>}
      </div>

      {err && <p className="error">{err}</p>}
      {!rows && <p className="muted">{tr("Laddar…")}</p>}
      {rows && !rows.length && <p className="muted">{tr("Inga egna blad ännu. Börja med ett tomt här ovanför.")}</p>}
      <div className="list">
        {(rows ?? []).map((s) => (
          <article className="item" key={s.id}>
            <div className="no" />
            <div>
              <Link className="ttl" to={`/cad/${s.id}`} style={{ fontSize: 18 }}>{s.name}</Link>
              <div className="sub">
                {s.paper} · 1:{s.scale_ratio} · {s.entities} objekt
                {s.drawing_id && <> · <Link to={`/mangda/${s.drawing_id}`}>{tr("utskriven ritning")}</Link></>}
              </div>
            </div>
            <div className="meta">
              <Link className="when" to={`/cad/${s.id}`}>{tr("Öppna →")}</Link>
              <button className="ghost small" onClick={() => remove(s.id)}>{tr("Ta bort")}</button>
            </div>
          </article>
        ))}
      </div>
    </main>
  );
}
