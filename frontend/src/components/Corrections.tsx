import { useEffect, useState } from "react";
import { t as tr, num } from "../i18n";
import { api } from "../api";
import { pipeColor } from "../palette";

export type Draft = { points: number[][]; meters: number; hits?: string[] } | null;

const HELP: Record<string, string> = {
  extend: "Dra från den röda punkten i sträckans ände, dit röret fortsätter. Längden räknas medan du drar.",
  draw: "Klicka längs röret. Backsteg tar bort senaste punkten, Esc avbryter, dubbelklick eller Enter avslutar.",
  erase: "Dra suddet längs det som mätts men inte är rör. Det som försvinner blir rött medan du drar.",
  retag: "Flytta hela sträckans meter till en annan beteckning.",
  quantity: "Sätt längden för hand när ritningen säger något annat.",
};

export default function Corrections({ drawingId, jobId, page, quantities, corrections, draft, kind, pipe,
  proposals = [], onKindChange, onDraftClear, onChanged }: {
    drawingId: string; jobId: string; page: number; quantities: any[];
    corrections: any[]; draft: Draft; kind: string | null; pipe: any | null; proposals?: any[];
    onKindChange: (kind: string | null) => void; onDraftClear: () => void; onChanged: () => void;
  }) {
  const [to, setTo] = useState("");
  const [meters, setMeters] = useState("");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  // The run you clicked is the subject of the edit; picking another one starts over. A correction is filed
  // under the designation as the takeoff writes it, not the internal identity key, or the row would not match.
  const subject: string | null = pipe?.designation ?? pipe?.identity ?? null;
  useEffect(() => { onDraftClear(); setMeters(""); setTo(""); }, [pipe?.physical_pipe_id]);

  const designation = kind === "draw" ? to : (subject ?? "");
  const ready = !!kind && !!designation
    && (kind === "extend" || kind === "draw" ? !!draft
      : kind === "erase" ? (!!draft || !!meters)
      : kind === "retag" ? !!to
      : !!meters);

  const save = async () => {
    if (!kind || !ready) return;
    setBusy(true); setErr("");
    try {
      const payload: any = {};
      if (draft) { payload.points = draft.points; payload.meters = Number(draft.meters.toFixed(3)); }
      // a retag moves horizontal metres, because that is the field it lands in on both rows. Defaulting to
      // total_m would drag the run's vertical metres across as horizontal pipe and stop the pair conserving.
      if (kind === "retag") { payload.from = subject; payload.meters = Number(meters.replace(",", ".")) || pipe?.horizontal_m || 0; }
      if (kind === "quantity" || (kind === "erase" && !draft)) payload.meters = Number(meters.replace(",", ".")) || 0;
      await api.addCorrection(drawingId, {
        kind, designation: kind === "retag" ? to : designation, page, payload, note: note || null, job_id: jobId,
        // The situation is taken from the reading on the server, not from here: the browser does not know which
        // leader reached the label or what the drawing offered as answers, and a lesson built on a guess about
        // that would speak in cases it has no business in.
      });
      setNote(""); setMeters(""); setTo(""); onDraftClear(); onKindChange(null); onChanged();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  const live = corrections.filter((c) => !c.undone);
  const tool = (k: string, label: string) => (
    <button key={k} className={kind === k ? "" : "secondary"} disabled={needsRunFor(k) && !subject}
      onClick={() => { onKindChange(kind === k ? null : k); onDraftClear(); }}>{label}</button>
  );

  return (
    <>
      {proposals.length > 0 && (
        <div className="card">
          <h3>{tr("Från tidigare rättelser")} <span className="badge">{proposals.length}</span></h3>
          <p className="muted" style={{ marginTop: 0 }}>
            Förslag, inte beslut. En läxa får bara tala där motorn själv kallade fallet tvetydigt, och bara med ett
            svar ritningen erbjuder. Mängden flyttar sig först när du säger till.
          </p>
          {proposals.map((pr: any) => (
            <div key={pr.case} className="issue done-row">
              <div>
                <b>{pr.answer}</b>
                <div className="muted">{pr.why} · {pr.times} gång{pr.times === 1 ? "" : "er"}</div>
              </div>
              <button className="secondary small" onClick={async () => {
                await api.addCorrection(drawingId, {
                  kind: "retag", designation: pr.answer, page, job_id: jobId, payload: {},
                  situation: pr.situation, note: "godtaget förslag från en tidigare rättelse",
                });
                onChanged();
              }}>{tr("Använd")}</button>
            </div>
          ))}
        </div>
      )}

      <div className="card">
        <h3>{tr("Rätta läsningen")}</h3>
        {!subject && (
          <p className="muted" style={{ marginTop: 0 }}>
            Klicka på ett rör i ritningen. Då gäller rättelsen den sträckan, och beteckningen behöver inte skrivas.
            Vill du rita ett rör motorn aldrig såg går det utan att välja något.
          </p>
        )}
        {subject && (
          <div className="subject">
            {/* hashed on the identity key, the same string the run on the sheet and the table hash, so the
                chip is the colour of the run it names */}
            <span className="sw" style={{ background: pipeColor({ ...pipe, identity: pipe.identity ?? subject }) }} />
            <b>{subject}</b>
            <span className="muted">
              {pipe.total_m != null ? ` · ${num(Number(pipe.total_m), 2)} m` : ""}
              {` · sida ${(pipe.page ?? 0) + 1}`}
            </span>
            <button className="ghost small" onClick={() => onKindChange(null)}>Avmarkera</button>
          </div>
        )}
        <div className="row tools">
          {tool("extend", "Förläng")}
          {tool("erase", "Sudda")}
          {tool("draw", "Rita nytt rör")}
          {tool("retag", "Byt beteckning")}
          {tool("quantity", "Rätta mängd")}
        </div>

        {kind && (
          <>
            <p className="muted hint">{HELP[kind]}</p>

            {draft && (
              <div className={`draftbox ${kind === "erase" ? "neg" : "pos"}`}>
                {/* the same rounding the correction is stored with, so the panel and the list agree */}
                <b>{kind === "erase" ? "−" : "+"} {num(Number(draft.meters.toFixed(3)), 2)} m</b>
                <span className="muted">
                  {kind === "erase"
                    ? ` från ${(draft.hits ?? [subject]).filter(Boolean).join(", ") || "mängden"}`
                    : ` på ${designation || "vald beteckning"}`}
                </span>
                <button className="ghost small" onClick={onDraftClear}>{tr("Gör om")}</button>
              </div>
            )}

            {kind === "draw" && (
              <div className="field">
                <label htmlFor="c-des">Beteckning</label>
                <input id="c-des" list="c-des-list" value={to} onChange={(e) => setTo(e.target.value)} placeholder={tr("t.ex. S3-R8-110")} />
              </div>
            )}
            {kind === "retag" && (
              <div className="field">
                <label htmlFor="c-to">{tr("Till beteckning")}</label>
                <input id="c-to" list="c-des-list" value={to} onChange={(e) => setTo(e.target.value)} placeholder={tr("t.ex. VV1-X31-16")} />
              </div>
            )}
            {(kind === "quantity" || kind === "retag" || (kind === "erase" && !draft)) && (
              <div className="field">
                <label htmlFor="c-m">Meter</label>
                <input id="c-m" value={meters} onChange={(e) => setMeters(e.target.value)}
                  placeholder={(kind === "retag" ? pipe?.horizontal_m : pipe?.total_m) != null
                    ? num(Number(kind === "retag" ? pipe.horizontal_m : pipe.total_m), 2) : num(0, 2)} />
              </div>
            )}
            <datalist id="c-des-list">{quantities.map((q) => <option key={q.designation} value={q.designation} />)}</datalist>
            <div className="field">
              <label htmlFor="c-note">{tr("Varför")}</label>
              <input id="c-note" value={note} onChange={(e) => setNote(e.target.value)}
                placeholder={tr("Valfritt, men det är detta som gör rättelsen begriplig sen")} />
            </div>
            {err && <p className="error">{err}</p>}
            <button onClick={save} disabled={!ready || busy}>{busy ? "Sparar…" : "Spara rättelse"}</button>
          </>
        )}
      </div>

      <div className="card">
        <h3>{tr("Rättelser")} <span className="badge">{live.length}</span></h3>
        {live.length === 0 && <p className="muted">{tr("Inga ännu. Motorns läsning står som den är.")}</p>}
        {live.map((c) => (
          <div key={c.id} className="issue done-row">
            <div>
              <b>{LABELS[c.kind] ?? c.kind}</b> · {c.designation}
              {c.payload?.meters != null && <> · {num(Number(c.payload.meters), 2)} m</>}
              {c.payload?.from && <> · från {c.payload.from}</>}
              {c.note && <div className="muted">{c.note}</div>}
            </div>
            <button className="ghost small"
              onClick={async () => { await api.undoCorrection(drawingId, c.id); onChanged(); }}>{tr("Ångra")}</button>
          </div>
        ))}
      </div>
    </>
  );
}

const LABELS: Record<string, string> = {
  extend: "Förlängt", draw: "Ritat rör", erase: "Suddat", retag: "Bytt beteckning", quantity: "Rättad mängd",
};

/** Which tools need a run to be selected first: all but drawing a run the engine never saw. */
function needsRunFor(k: string): boolean {
  return k !== "draw";
}
