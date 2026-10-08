import { t as tr, num } from "../i18n";

type Quality = {
  verdict: string;
  reasons: string[];
  measures: Record<string, number | null>;
};

const reasons: Record<string, string> = {
  TENTATIVE_QUANTITIES: "Mängden innehåller uppskattade sträckor som behöver granskas.",
  MODEL_REVIEW_INCOMPLETE: "Vissa analysfrågor saknar svar. Resultatet behöver granskas.",
  OCR_REVIEW_INCOMPLETE: "Textkontrollen kunde inte slutföras för hela ritningen.",
  GEOMETRY_CONSERVATION_BROKEN: "Geometrikontrollen visar en avvikelse.",
  NO_SCALE: "Skalan saknas. Ange skalan innan mängden används.",
  SCALE_UNSETTLED: "Ritningens skaluppgifter är motstridiga.",
  SHEET_NAMES_PIPES_BUT_NOTHING_WAS_MEASURED: "Rörbeteckningar hittades, men inga rör kunde mängdas.",
  NO_READABLE_PIPE_LABELS: "Inga läsbara rörbeteckningar kunde kopplas till en mängd.",
  MOST_NAMES_WITHOUT_METRES: "Många rörbeteckningar saknar uppmätta sträckor.",
  MOST_PIPE_INK_UNOWNED: "En stor del av den möjliga rörgeometrin saknar beteckning.",
  MANY_LOSSY_FRONTIERS: "Flera rörsträckor kan fortsätta utanför det som har mätts.",
  READ_FROM_IMAGE: "Ritningen är läst ur en bild – en skanning eller ett foto. Linjer och text är tolkade ur bildpunkter, så varje rad ska granskas mot ritningen.",
};

export default function AnalysisQuality({ quality }: { quality?: Quality }) {
  if (!quality) return null;
  const title = quality.verdict === "INVALID" ? "Mängden är ofullständig"
    : quality.verdict === "DEGRADED" ? "Mängden behöver granskas" : "Analyskontroller genomförda";
  return <section className={quality.verdict === "VALID" ? "card" : "callout warn"} aria-label={tr("Analyskvalitet")}>
    <strong>{tr(title)}</strong>
    {quality.reasons.length > 0 && <ul>{quality.reasons.map(reason => <li key={reason}>
      {tr(reason.startsWith("SILENT_PIPES:") ? "Rörsträckor saknar förklaring vid sina ändpunkter."
        : reasons[reason] ?? "Analysen behöver kontrolleras mot ritningen.")}
    </li>)}</ul>}
    <div className="sub">{tr("Andel lästa rörnamn som fått mängd")}: {quality.measures.NAMES_WITH_METRES_SHARE == null
      ? tr("ej mätt") : `${num(quality.measures.NAMES_WITH_METRES_SHARE * 100, 0)} %`}</div>
    <p className="muted small">{tr("Automatiska kontroller visar läsningens täckning. De verifierar inte träffsäkerheten mot en handmängdning.")}</p>
  </section>;
}

/* Läst ur en bild: alla ser det, inte bara personalen - varje rad står som att granska. */
export function ReadFromImage({ quality }: { quality?: Quality }) {
  if (!(quality?.reasons ?? []).includes("READ_FROM_IMAGE")) return null;
  return <div className="callout warn" role="note" style={{ marginBottom: 12 }}>
    <strong>{tr("Läst ur en bild – allt ska granskas")}</strong>
    <p className="small" style={{ margin: "4px 0 0" }}>{tr("Ritningen är en skanning eller ett foto. Linjer och text är tolkade ur bildpunkter, så varje rad står som LÄST UR BILD tills du har granskat den mot ritningen. Skalan gäller bara om en skalstock eller mått på bladet bekräftar den – annars anger du den.")}</p>
  </div>;
}
