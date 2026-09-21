import { t as tr } from "../i18n";
/* Kamerans knappar. Egen komponent, för vyn ska kunna byta renderare utan att knapparna skrivs om. */
export type ViewName = "perspektiv" | "topp" | "front" | "sida";

const VIEWS: [ViewName, string][] = [
  ["perspektiv", "Perspektiv"],
  ["topp", "Ovanifrån"],
  ["front", "Framifrån"],
  ["sida", "Från sidan"],
];

export default function Drawing3DControls({
  onView, onReset, onSpin, exploded, onExploded, labels, onLabels, xray, onXray, walking, onWalk,
}: {
  onView: (v: ViewName) => void;
  onReset: () => void;
  onSpin: (dir: -1 | 1) => void;
  exploded: boolean;
  onExploded: (v: boolean) => void;
  labels: boolean;
  onLabels: (v: boolean) => void;
  xray: boolean;
  onXray: (v: boolean) => void;
  walking: boolean;
  onWalk: (v: boolean) => void;
}) {
  return (
    <div className="d3-controls">
      <div className="seg">
        {VIEWS.map(([id, label]) => (
          <button key={id} onClick={() => onView(id)} disabled={walking}>{label}</button>
        ))}
      </div>
      {/* Vyn ovanifrån går att vrida: en plan som bara kan ses åt ett håll är en bild, inte en modell. */}
      <div className="seg">
        <button onClick={() => onSpin(-1)} disabled={walking} title={tr("Vrid planen moturs")} aria-label={tr("Vrid moturs")}>⟲</button>
        <button onClick={() => onSpin(1)} disabled={walking} title={tr("Vrid planen medurs")} aria-label={tr("Vrid medurs")}>⟳</button>
      </div>
      <button className={walking ? "" : "secondary"} onClick={() => onWalk(!walking)}>
        {walking ? "Sluta gå" : "Gå in i modellen"}
      </button>
      <button className="secondary small" onClick={onReset} disabled={walking}>{tr("Återställ kameran")}</button>
      <label className="small check">
        <input type="checkbox" checked={labels} onChange={(e) => onLabels(e.target.checked)} />
        {" "}Beteckningar
      </label>
      <label className="small check">
        <input type="checkbox" checked={xray} onChange={(e) => onXray(e.target.checked)} />
        {" "}Genomskinliga väggar
      </label>
      <label className="small check">
        <input type="checkbox" checked={exploded} onChange={(e) => onExploded(e.target.checked)} disabled={walking} />
        {" "}Lyft rören ur planet
      </label>
      <span className="muted small d3-hint">
        {walking
          ? "W A S D eller piltangenterna för att gå · musen för att se dig omkring · skift för att springa · Esc för att sluta"
          : "Dra för att vrida · skift eller höger musknapp för att panorera · rulla för att zooma · klicka på ett rör"}
      </span>
    </div>
  );
}
