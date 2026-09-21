import { useEffect, useMemo, useState } from "react";
import { t as tr, locale } from "../i18n";
import { Link } from "react-router-dom";
import { api } from "../api";
import Tilted from "../components/Tilted";

const DATE = new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", year: "numeric" });

export default function Projects() {
  const [projects, setProjects] = useState<any[]>([]);
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const load = () => api.projects().then(setProjects).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.createProject(name, desc);
      setName(""); setDesc(""); setOpen(false); setErr("");
      load();
    } catch (ex: any) { setErr(ex.message); } finally { setBusy(false); }
  };

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter((p) => `${p.name} ${p.description ?? ""}`.toLowerCase().includes(needle));
  }, [projects, q]);

  return (
    <main>
      <p className="crumb">{tr("/ Projekt")}</p>
      <div className="head">
        <div>
          <h1>Projekt</h1>
          <p className="lead">{tr("Mängder ur ritningen, med belägg för varje meter")}</p>
        </div>
        <button onClick={() => setOpen(!open)}>{open ? "Avbryt" : "+ Nytt projekt"}</button>
      </div>

      {open && (
        <form className="card" style={{ marginTop: 28, maxWidth: 560 }} onSubmit={create}>
          <div className="field">
            <label htmlFor="p-name">Projektnamn</label>
            <input id="p-name" value={name} onChange={(e) => setName(e.target.value)} placeholder={tr("Kv. Badhuset, etapp 2")} required autoFocus />
          </div>
          <div className="field">
            <label htmlFor="p-desc">Beskrivning</label>
            <input id="p-desc" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Valfritt" />
          </div>
          <button type="submit" disabled={busy}>{busy ? "Skapar…" : "Skapa projekt"}</button>
        </form>
      )}

      {err && <p className="error" style={{ marginTop: 20 }}>{err}</p>}

      <div className="rule" />
      <div className="row" style={{ margin: "22px 0 6px" }}>
        <input style={{ flex: 1, minWidth: 260 }} placeholder={tr("Sök projekt eller beskrivning")} value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="badge">{shown.length} {shown.length === 1 ? "projekt" : "projekt"}</span>
      </div>
      <div className="rule" style={{ margin: 0 }} />

      <div className="list">
        {shown.map((p, i) => (
          <Tilted as="article" deg={2.4} lift={6} className="item" key={p.id}>
            <div className="no">{String(i + 1).padStart(2, "0")}</div>
            <div>
              <Link className="ttl" to={`/projects/${p.id}`}>{p.name}</Link>
              <div className="sub">{p.description || "—"}</div>
            </div>
            <div className="meta">
              <button className="ghost act" onClick={async () => {
                if (confirm(`Ta bort ${p.name}?`)) { await api.deleteProject(p.id); load(); }
              }}>{tr("Ta bort")}</button>
              <span className="badge">{p.n_drawings} {p.n_drawings === 1 ? "ritning" : "ritningar"}</span>
              <span className="when">{DATE.format(new Date(p.created_at))}</span>
            </div>
          </Tilted>
        ))}
        {shown.length === 0 && (
          <div className="empty">{projects.length ? "Inget projekt matchar sökningen." : "Inga projekt ännu — skapa det första."}</div>
        )}
      </div>
    </main>
  );
}
