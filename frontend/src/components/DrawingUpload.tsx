import { useEffect, useRef, useState } from "react";
import { t as tr } from "../i18n";
import { api } from "../api";

/* Lägg upp en ritning där man står.
 *
 * Ett blad ska gå att öppna i det rum man redan är i. Att först gå till Projekt, lägga upp filen där och sedan
 * gå tillbaka är tre steg för en sak, och den som bara vill mäta på en ritning bryr sig inte om vilket projekt
 * den hamnar i förrän hon måste.
 *
 * Därför: välj projekt eller skriv ett nytt namn, välj en eller flera PDF:er, ladda upp. Ritningen läggs där
 * den hör hemma - i ett projekt, som allt annat - och rummet öppnar den. Ingen analys startas här: att läsa
 * bladet är ett eget beslut och tar sin tid.
 */
export default function DrawingUpload({ onDone, verb = "Öppna" }: {
  /** Anropas när uppladdningen är klar, med ritningarna som lades upp - senast först. */
  onDone: (drawings: { id: string; filename: string }[]) => void;
  verb?: string;
}) {
  const [projects, setProjects] = useState<any[] | null>(null);
  const [project, setProject] = useState("");
  const [namn, setNamn] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.projects().then((ps: any[]) => {
      setProjects(ps);
      setProject(ps[0]?.id ?? "nytt");
    }).catch((e) => setErr(e.message));
  }, []);

  const upload = async () => {
    const files = Array.from(fileRef.current?.files ?? []);
    if (!files.length) return;
    setErr("");
    try {
      let pid = project;
      if (pid === "nytt") {
        const p = await api.createProject(namn.trim() || "Ritningar", "");
        pid = p.id;
        setProjects((ps) => [p, ...(ps ?? [])]);
        setProject(p.id);
        setNamn("");
      }
      const made: { id: string; filename: string }[] = [];
      for (const [i, f] of files.entries()) {
        setBusy(`Laddar upp ${i + 1} av ${files.length}…`);
        made.push(await api.upload(pid, f));
      }
      if (fileRef.current) fileRef.current.value = "";
      setPicked([]);
      onDone(made);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <section className="card up-card">
      <h3 style={{ marginTop: 0 }}>{tr("Lägg upp en ritning")}</h3>
      <p className="muted small" style={{ marginTop: -4 }}>
        Vektor-PDF, exporterad ur CAD. En skannad ritning går inte att mäta på – systemet läser ritningens egna
        vektorkoder och gissar aldrig ur bildpunkter.
      </p>
      <div className="up-row">
        <label className="adm-field">
          <span>Projekt</span>
          <select value={project} onChange={(e) => setProject(e.target.value)} disabled={!!busy}>
            {(projects ?? []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            <option value="nytt">{tr("Nytt projekt…")}</option>
          </select>
        </label>
        {project === "nytt" && (
          <label className="adm-field">
            <span>{tr("Projektets namn")}</span>
            <input value={namn} onChange={(e) => setNamn(e.target.value)} placeholder={tr("Kv Björken, hus A")}
              disabled={!!busy} />
          </label>
        )}
        <div className="row" style={{ alignItems: "flex-end", gap: 8 }}>
          <input type="file" accept="application/pdf" multiple ref={fileRef} id="up-pdf" className="file"
            onChange={(e) => setPicked(Array.from(e.target.files ?? []).map((f) => f.name))} />
          <label className="pick" htmlFor="up-pdf">
            {picked.length === 0 ? "Välj PDF…" : picked.length === 1 ? picked[0] : `${picked.length} filer`}
          </label>
          <button onClick={upload} disabled={!!busy || !picked.length}>
            {busy || `Ladda upp och ${verb.toLowerCase()}`}
          </button>
        </div>
      </div>
      {err && <p className="error" style={{ marginBottom: 0 }}>{err}</p>}
    </section>
  );
}
