import { useEffect, useRef, useState } from "react";
import { t as tr, trf, locale } from "../i18n";
import { Link, useParams } from "react-router-dom";
import { api, fileSize } from "../api";
import { StatusBadge } from "../components/Status";
import Tilted from "../components/Tilted";
import { PriceTag } from "./Credits";

const DATE = new Intl.DateTimeFormat(locale(), { day: "2-digit", month: "short", year: "numeric" });

export default function ProjectPage() {
  const { id } = useParams();
  const [project, setProject] = useState<any>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [picked, setPicked] = useState("");
  const [progress, setProgress] = useState("");
  const [notice, setNotice] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);
  const load = () => api.project(id!).then(setProject).catch((e) => setErr(e.message));
  // the list only changes while a reading is running, or just after an upload; otherwise it can sit still
  const live = (project?.drawings ?? []).some((d: any) =>
    d?.latest_job && d.latest_job.status !== "COMPLETED" && d.latest_job.status !== "FAILED");
  useEffect(() => {
    load();
    if (!live) return;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [id, live]);
  const upload = async () => {
    const files = Array.from(fileRef.current?.files ?? []); if (!files.length) return;
    setBusy(true); setErr(""); setNotice("");
    let uploaded = 0, duplicates = 0;
    const failed: File[] = [], errors: string[] = [];
    try {
      for (const [i, f] of files.entries()) {
        setProgress(`${i + 1} / ${files.length} · ${f.name}`);
        try { const result = await api.upload(id!, f); if (result.duplicate) duplicates++; else uploaded++; }
        catch (ex: any) { failed.push(f); errors.push(`${f.name}: ${ex.message}`); }
      }
      // clearing the field is tidying up after a finished upload, not part of it: if the input is gone by now
      // the upload still happened, and asserting it is there turns a success into an error message
      if (fileRef.current) {
        const remaining = new DataTransfer();
        failed.forEach(f => remaining.items.add(f));
        fileRef.current.files = remaining.files;
      }
      setPicked(failed.length ? trf("{0} PDF-filer valda", failed.length) : "");
      setErr(errors.join("\n"));
      setNotice(trf("{0} uppladdade · {1} fanns redan · {2} misslyckades", uploaded, duplicates, failed.length));
      await load();
    } finally { setBusy(false); setProgress(""); }
  };
  const startSelected = async () => {
    setBusy(true); setErr(""); setNotice("");
    const errors: string[] = [];
    const remaining = new Set(selected);
    try {
      const drawings = project.drawings.filter((d: any) => selected.has(d.id));
      for (const [i, d] of drawings.entries()) {
        setProgress(`${i + 1} / ${drawings.length} · ${d.filename}`);
        try { await api.analyze(d.id); remaining.delete(d.id); }
        catch (ex: any) { errors.push(`${d.filename}: ${ex.message}`); }
      }
      setSelected(remaining);
      setErr(errors.join("\n"));
      setNotice(trf("{0} analyser i kö", drawings.length - errors.length));
      await load();
    } finally { setBusy(false); setProgress(""); }
  };
  const canStart = (d: any) => !d.latest_job || ["COMPLETED", "FAILED"].includes(d.latest_job.status);
  if (!project) return <main>{err ? <p className="error">{err}</p> : "Laddar…"}</main>;
  return (
    <main>
      <p className="crumb"><Link to="/projekt">Projekt</Link> / {project.name}</p>
      <div className="head">
        <div>
          <h1>{project.name}</h1>
          <p className="lead">{project.description || "Ritningar i projektet"}</p>
        </div>
        <div className="row">
          <input type="file" accept="application/pdf,.pdf" multiple disabled={busy} ref={fileRef} id="pdf" className="file"
            onChange={(e) => { const files = e.target.files; setPicked(files?.length === 1 ? files[0].name : files?.length ? trf("{0} PDF-filer valda", files.length) : ""); }} />
          <label className="pick" htmlFor="pdf">{picked || "Välj PDF…"}</label>
          <button onClick={upload} disabled={busy || !picked}>{busy ? "Laddar upp…" : "Ladda upp"}</button>
          {/* En ritning i taget svarar med meter. Hela handlingen svarar med vad den består av. */}
          <Link to={`/projects/${project.id}/analys`}><button className="secondary">{tr("Analysera projektet")}</button></Link>
        </div>
      </div>
      {progress && <p role="status" aria-live="polite">{progress}</p>}
      {notice && <p role="status">{notice}</p>}
      {err && <p className="error" style={{ marginTop: 18, whiteSpace: "pre-line" }}>{err}</p>}

      {project.drawings.length > 0 && <div className="row" style={{ marginTop: 18 }}>
        <button className="secondary small" disabled={busy} onClick={() => setSelected(new Set(project.drawings.filter((d: any) => canStart(d) && d.latest_job?.status !== "COMPLETED").map((d: any) => d.id)))}>{tr("Välj oanalyserade")}</button>
        <button className="secondary small" disabled={busy || !selected.size} onClick={() => setSelected(new Set())}>{tr("Avmarkera")}</button>
        <button disabled={busy || !selected.size} onClick={startSelected}>{trf("Analysera valda ({0})", selected.size)}</button>
        <span className="sub">{tr("Kontrollera att samma ritning inte väljs i flera revisioner.")}</span>
      </div>}

      <div className="rule" />
      <div className="list">
        {project.drawings.map((d: any, i: number) => (
          <Tilted as="article" deg={2.4} lift={6} className="item" key={d.id}>
            <div className="no"><input type="checkbox" aria-label={`${tr("Välj ritning")}: ${d.filename}`}
              checked={selected.has(d.id)} disabled={busy || !canStart(d)} onChange={e => {
                const next = new Set(selected); if (e.target.checked) next.add(d.id); else next.delete(d.id); setSelected(next);
              }} /> {String(i + 1).padStart(2, "0")}</div>
            <div>
              <Link className="ttl" to={`/drawings/${d.id}`}>{d.filename.replace(/\.pdf$/i, "")}</Link>
              <div className="sub">
                {d.n_pages} {d.n_pages === 1 ? "sida" : "sidor"} · {fileSize(d.size_bytes)}
                {d.latest_job && <> · senast <Link to={`/jobs/${d.latest_job.id}`}>{DATE.format(new Date(d.latest_job.created_at))}</Link></>}
              </div>
            </div>
            <div className="meta">
              {d.latest_job ? <StatusBadge job={d.latest_job} /> : <span className="badge">{tr("Ej analyserad")}</span>}
              <PriceTag drawingId={d.id} />
              <button className="secondary small" disabled={busy || !canStart(d)} onClick={async () => {
                setErr("");
                try { const j = await api.analyze(d.id); window.location.href = `/jobs/${j.id}`; }
                catch (ex: any) { setErr(/402/.test(ex.message) ? `${ex.message.replace(/\s*\(402\)$/, "")} Fyll på under Credits.` : ex.message); }
              }}>Analysera</button>
            </div>
          </Tilted>
        ))}
        {project.drawings.length === 0 && <div className="empty">{tr("Inga ritningar ännu — ladda upp den första.")}</div>}
      </div>
    </main>
  );
}
