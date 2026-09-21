import { useMemo, useState } from "react";
import { t as tr, locale } from "../i18n";
import { markupColor } from "./PdfViewer";

/* Markeringslistan: allt någon ritat på handlingen, som en lista att arbeta i.
 *
 * Listan är inte en spegel av bladet utan ett eget arbetsbord. Här sorteras, filtreras, kommenteras och
 * stängs frågor - och urvalet följer med åt båda hållen: pekar man på en rad framhävs markeringen på bladet,
 * pekar man på bladet hoppar listan dit. Utan det bandet blir listan en tabell bredvid ritningen i stället för
 * ett sätt att läsa den.
 *
 * Komponenten äger ingen data. Den visar de rader den får och säger till om vad någon vill ändra; vad som
 * sparas, och när, avgörs av sidan omkring - det är den som vet vad servern svarade.
 */

export type MarkupRow = {
  id: string;
  page: number;
  tool: string;
  layer: string;
  designation?: string | null;
  subject?: string;
  status?: string;
  comment?: string;
  text?: string;
  seq?: number | null;
  source?: string;
  measure?: any;
  points: number[][];
  created_at?: string;
};

export const STATUSES: { id: string; label: string; hint: string }[] = [
  { id: "oppen", label: "Öppen", hint: "Ställd, inte besvarad" },
  { id: "atgardad", label: "Åtgärdad", hint: "Någon har gjort något åt den" },
  { id: "godkand", label: "Godkänd", hint: "Granskad och klar" },
  { id: "avvisad", label: "Avvisad", hint: "Ingen åtgärd - och det är svaret" },
];

export const TOOL_LABEL: Record<string, string> = {
  langd: "Längd", polylinje: "Polylinje", frihand: "Frihand", area: "Yta", rektangel: "Rektangel",
  volym: "Volym", moln: "Moln", antal: "Antal", text: "Anteckning", vinkel: "Vinkel",
};

const SOURCE_LABEL: Record<string, string> = {
  manuell: "Ritad för hand", matning: "Mätning", cad: "CAD", ai: "Förslag", ocr: "Text ur bladet", import: "Import",
};

const n2 = (v: number | null | undefined, d = 2) =>
  v == null ? "" : v.toLocaleString(locale(), { minimumFractionDigits: d, maximumFractionDigits: d });

/** Vad raden mätte, i ord. Tomt när verktyget inte mäter något - en anteckning har ingen mängd. */
export function measureText(m: any): string {
  if (!m) return "";
  const bits: string[] = [];
  if (typeof m.m === "number") bits.push(`${n2(m.m)} m`);
  if (typeof m.kvm === "number") bits.push(`${n2(m.kvm)} m²`);
  if (typeof m.m3 === "number") bits.push(`${n2(m.m3, 3)} m³`);
  if (typeof m.antal === "number") bits.push(`${m.antal} st`);
  if (!bits.length && m.langd_pt) bits.push(`${Math.round(m.langd_pt)} pt`);
  return bits.join(" · ");
}

/** Summan av raderna, uppdelad på vad verktygen faktiskt mäter.
 *
 * Meter, kvadratmeter, kubikmeter och stycken läggs aldrig ihop till ett tal. En yta har en omkrets och en
 * längd har ingen area; ett enda tal för alltihop är inte en summa utan en sammanblandning. */
export function sumText(rows: MarkupRow[]): string {
  const LEN = ["langd", "polylinje", "frihand"], AREA = ["area", "rektangel", "moln", "volym"];
  let m = 0, kvm = 0, m3 = 0, antal = 0;
  for (const r of rows) {
    const q = r.measure ?? {};
    if (LEN.includes(r.tool)) m += Number(q.m ?? 0);
    if (AREA.includes(r.tool)) { kvm += Number(q.kvm ?? 0); m3 += Number(q.m3 ?? 0); }
    if (r.tool === "antal") antal += Number(q.antal ?? 0);
  }
  const bits: string[] = [];
  if (m) bits.push(`${n2(m)} m`);
  if (kvm) bits.push(`${n2(kvm)} m²`);
  if (m3) bits.push(`${n2(m3, 3)} m³`);
  if (antal) bits.push(`${antal} st`);
  return bits.join(" · ") || "–";
}

/** Måttet som ett tal, för sorteringen: en yta jämförs med en yta, en längd med en längd. */
function measureValue(m: any): number {
  if (!m) return 0;
  return Number(m.m ?? m.kvm ?? m.m3 ?? m.antal ?? m.langd_pt ?? 0);
}

type SortKey = "page" | "tool" | "layer" | "subject" | "status" | "measure" | "created_at";

export default function MarkupsList({ rows, selected, onSelect, onPatch, onPatchMany, onDelete, busy }: {
  rows: MarkupRow[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onPatch: (id: string, change: any) => void;
  onPatchMany: (ids: string[], change: any) => void;
  onDelete: (id: string) => void;
  busy?: boolean;
}) {
  const [sort, setSort] = useState<SortKey>("page");
  const [desc, setDesc] = useState(false);
  const [q, setQ] = useState("");
  const [fLayer, setFLayer] = useState("");
  const [fTool, setFTool] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [fPage, setFPage] = useState("");
  const [checked, setChecked] = useState<Set<string>>(new Set());

  const layers = useMemo(() => Array.from(new Set(rows.map((r) => r.layer))).sort(), [rows]);
  const tools = useMemo(() => Array.from(new Set(rows.map((r) => r.tool))).sort(), [rows]);
  const pages = useMemo(() => Array.from(new Set(rows.map((r) => r.page))).sort((a, b) => a - b), [rows]);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const hit = (r: MarkupRow) => !needle || [r.subject, r.comment, r.text, r.designation, r.layer,
      TOOL_LABEL[r.tool] ?? r.tool, measureText(r.measure)]
      .some((v) => (v ?? "").toString().toLowerCase().includes(needle));
    const keep = rows.filter((r) => hit(r)
      && (!fLayer || r.layer === fLayer)
      && (!fTool || r.tool === fTool)
      && (!fStatus || (r.status ?? "oppen") === fStatus)
      && (!fPage || String(r.page) === fPage));
    const key = (r: MarkupRow): string | number =>
      sort === "measure" ? measureValue(r.measure)
        : sort === "page" ? r.page
        : sort === "tool" ? (TOOL_LABEL[r.tool] ?? r.tool)
        : sort === "status" ? (r.status ?? "oppen")
        : sort === "subject" ? (r.subject || r.text || "")
        : sort === "layer" ? r.layer
        : (r.created_at ?? "");
    const sorted = [...keep].sort((a, b) => {
      const ka = key(a), kb = key(b);
      const c = typeof ka === "number" && typeof kb === "number" ? ka - kb : String(ka).localeCompare(String(kb), "sv");
      // lika värden faller tillbaka på ordningen de ritades i, så listan aldrig hoppar mellan omritningar
      return (c || (a.created_at ?? "").localeCompare(b.created_at ?? "")) * (desc ? -1 : 1);
    });
    return sorted;
  }, [rows, q, fLayer, fTool, fStatus, fPage, sort, desc]);

  const pick = (k: SortKey) => { if (sort === k) setDesc(!desc); else { setSort(k); setDesc(false); } };
  const arrow = (k: SortKey) => (sort === k ? (desc ? " ▼" : " ▲") : "");

  const allShown = shown.length > 0 && shown.every((r) => checked.has(r.id));
  const toggleAll = () => {
    setChecked(allShown ? new Set() : new Set(shown.map((r) => r.id)));
  };
  const toggle = (id: string) => {
    const next = new Set(checked);
    if (next.has(id)) next.delete(id); else next.add(id);
    setChecked(next);
  };
  const chosen = shown.filter((r) => checked.has(r.id)).map((r) => r.id);

  return (
    <div className="mk-list">
      <div className="mk-filters">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={tr("Sök i ämne, kommentar, beteckning")} />
        <select value={fPage} onChange={(e) => setFPage(e.target.value)} aria-label="Sida">
          <option value="">{tr("Alla sidor")}</option>
          {pages.map((p) => <option key={p} value={String(p)}>Sida {p + 1}</option>)}
        </select>
        <select value={fLayer} onChange={(e) => setFLayer(e.target.value)} aria-label="Lager">
          <option value="">{tr("Alla lager")}</option>
          {layers.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <select value={fTool} onChange={(e) => setFTool(e.target.value)} aria-label="Verktyg">
          <option value="">{tr("Alla verktyg")}</option>
          {tools.map((t) => <option key={t} value={t}>{TOOL_LABEL[t] ?? t}</option>)}
        </select>
        <select value={fStatus} onChange={(e) => setFStatus(e.target.value)} aria-label="Status">
          <option value="">{tr("Alla status")}</option>
          {STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
        <span className="muted small">{shown.length} av {rows.length}</span>
      </div>

      {chosen.length > 0 && (
        <div className="mk-bulk">
          <b>{chosen.length} markerade</b>
          {STATUSES.map((s) => (
            <button key={s.id} className="secondary small" disabled={busy}
              onClick={() => { onPatchMany(chosen, { status: s.id }); setChecked(new Set()); }}
              title={`Sätt ${s.label.toLowerCase()} på alla markerade`}>{s.label}</button>
          ))}
          <button className="secondary small" disabled={busy} onClick={() => {
            const to = window.prompt("Flytta de markerade till vilket lager?", chosen.length ? (shown.find((r) => r.id === chosen[0])?.layer ?? "") : "");
            if (to && to.trim()) { onPatchMany(chosen, { layer: to.trim() }); setChecked(new Set()); }
          }}>{tr("Byt lager…")}</button>
          <button className="ghost small" onClick={() => setChecked(new Set())}>Avmarkera</button>
        </div>
      )}

      <div className="mk-scroll">
        <table className="qty mk-table">
          <thead>
            <tr>
              <th><input type="checkbox" checked={allShown} onChange={toggleAll} aria-label={tr("Markera alla")} /></th>
              <th className="sortable" onClick={() => pick("page")}>Sida{arrow("page")}</th>
              <th className="sortable" onClick={() => pick("tool")}>Verktyg{arrow("tool")}</th>
              <th className="sortable" onClick={() => pick("subject")}>Ämne{arrow("subject")}</th>
              <th className="sortable" onClick={() => pick("layer")}>Lager{arrow("layer")}</th>
              <th className="sortable num" onClick={() => pick("measure")}>Mått{arrow("measure")}</th>
              <th className="sortable" onClick={() => pick("status")}>Status{arrow("status")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className={`selectable${selected === r.id ? " selected" : ""}`}
                onClick={() => onSelect(selected === r.id ? null : r.id)}>
                <td onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" checked={checked.has(r.id)} onChange={() => toggle(r.id)}
                    aria-label={`Markera ${r.subject || TOOL_LABEL[r.tool] || r.tool}`} />
                </td>
                <td className="num">{r.page + 1}</td>
                <td>
                  <span className="mk-dot" style={{ background: markupColor(r.status) }} />
                  {TOOL_LABEL[r.tool] ?? r.tool}{r.seq ? ` ${r.seq}` : ""}
                </td>
                <td title={r.comment || ""}>{r.subject || r.text || <span className="muted">–</span>}</td>
                <td>{r.layer}{r.designation ? ` · ${r.designation}` : ""}</td>
                <td className="num">{measureText(r.measure)}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <select value={r.status ?? "oppen"} disabled={busy}
                    onChange={(e) => onPatch(r.id, { status: e.target.value })} aria-label="Status">
                    {STATUSES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                  </select>
                </td>
                <td onClick={(e) => e.stopPropagation()}>
                  <button className="ghost small" disabled={busy} title={tr("Ta bort markeringen")}
                    onClick={() => { if (window.confirm("Ta bort markeringen?")) onDelete(r.id); }}>✕</button>
                </td>
              </tr>
            ))}
            {shown.length === 0 && (
              <tr><td colSpan={8} className="muted">
                {rows.length ? "Ingen markering matchar filtret." : "Inga markeringar ännu. Välj ett verktyg och rita på bladet."}
              </td></tr>
            )}
          </tbody>
          {/* Summan av det man ser, inte av allt som finns.
              Filtrerar man fram ett lager är det lagrets mängd man vill läsa av; en summa som ändå räknade
              hela handlingen svarar på en fråga ingen ställt, och den skillnaden syns inte i talet. */}
          {shown.length > 0 && (
            <tfoot>
              <tr>
                <th colSpan={5}>Summa av de {shown.length} raderna</th>
                <th className="num">{sumText(shown)}</th>
                <th colSpan={2} />
              </tr>
            </tfoot>
          )}
        </table>
      </div>
    </div>
  );
}

/** Vad en rad kom ifrån, i ord - så att en mängd som en människa ritade aldrig förväxlas med en maskinens. */
export function sourceLabel(source?: string): string {
  return SOURCE_LABEL[source ?? "manuell"] ?? source ?? "";
}
