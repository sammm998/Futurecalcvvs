import { t as tr } from "../i18n";

export const STAGE_LABELS: Record<string, string> = {
  QUEUED: "Köad", READING_PDF: "Läser PDF", RESOLVING_UNREADABLE_TEXT: "Synagenten läser olästa tecken", REVIEWING: "Granskar resultatet", DISCOVERING_DRAWING_GRAMMAR: "Upptäcker ritningsgrammatik", EXTRACTING_VECTORS: "Extraherar vektorer",
  RECONSTRUCTING_TEXT: "Rekonstruerar text", READING_DESIGNATIONS: "Läser beteckningar", FINDING_LEADERS: "Hittar hänvisningslinjer",
  RESOLVING_PIPE_REPRESENTATION: "Tolkar rörrepresentation", ATTACHING_PIPES: "Kopplar rör", BUILDING_TOPOLOGY: "Bygger topologi",
  PIPESTUDIO_EXTRACT: "Kontrollerar originalets linjer", PIPESTUDIO_PROFILE: "Undersöker ritningens utförande",
  PIPESTUDIO_DETECT: "Hittar rör och beteckningar", PIPESTUDIO_OCR: "Läser beteckningarnas tecken", PIPESTUDIO_VECTOR_STAGES: "Följer rör och hänvisningar",
  BUILDING_PHYSICAL_PIPES: "Bygger fysiska rör", MEASURING: "Mäter", GENERATING_OVERLAYS: "Skapar markeringar", COMPLETED: "Klar", FAILED: "Misslyckades",
};

const STATUS_LABELS: Record<string, string> = { COMPLETED: "Klar", FAILED: "Misslyckades", RUNNING: "Kör", QUEUED: "Köad" };

/* A stage may carry a detail after its name - "RESOLVING_UNREADABLE_TEXT ruta 3/7" - so a slow step can say where
   it is instead of looking stuck. The name is the first word; the rest is shown as it comes. */
export function stageText(stage: string): string | null {
  if (!stage) return null;
  const [name, ...rest] = stage.split(" ");
  // the detector reports each tile it reads ("..._TILE_16_OF_48"): one step, with how far it has come
  const tile = /^(\w+?)_TILE_(\d+)_OF_(\d+)$/.exec(name);
  if (tile) {
    const base = tr(STAGE_LABELS[tile[1]] ?? "Hittar rör och beteckningar");
    return `${base} · ${tile[2]}/${tile[3]}`;
  }
  const label = STAGE_LABELS[name];
  // a step we have no word for is still never shown by its internal name
  if (!label) return name.startsWith("PIPESTUDIO_") ? tr("Analyserar ritningen") : null;
  return rest.length ? `${tr(label)} · ${rest.join(" ")}` : tr(label);
}

export function StatusBadge({ job }: { job: any }) {
  const cls = job.status === "COMPLETED" ? "ok" : job.status === "FAILED" ? "bad" : "warn";
  // a finished job is described by its outcome, not by the stage it happened to stop on; and a stage we have
  // no word for still has a status we do
  const done = job.status === "COMPLETED" || job.status === "FAILED";
  const status = STATUS_LABELS[job.status] ? tr(STATUS_LABELS[job.status]) : null;
  const text = (done ? status : stageText(job.stage)) || status || tr("Okänt läge");
  return <span className={`badge ${cls}`}>{text}</span>;
}
