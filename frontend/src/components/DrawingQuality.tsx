import { t as tr } from "../i18n";

type Style = {
  state: string;
  nearest: { name: string; reference_id: string };
  measured: { hairline: boolean; text_mode: string };
  warnings: { code: string }[];
  reference_count: number;
};
type Visibility = { hidden_paths?: number; partial_paths?: number };

export default function DrawingQuality({ style, visibility }: { style?: Style; visibility?: Visibility }) {
  if (!style && !visibility) return null;
  return <section className="card" aria-label={tr("Ritningskontroll")}>
    <h3>{tr("Ritningskontroll")}</h3>
    {style && <>
      <p><b>{style.state === "CANDIDATE" ? tr("Trolig ritningsstil") : tr("Ritningsstilen behöver granskas")}</b>
        {" · "}{style.nearest.name}</p>
      <p className="muted">{tr("Stilbiblioteket är ett jämförelseunderlag. Beteckningar och geometri på bladet avgör mängderna.")}</p>
      {style.measured.hairline && <p>{tr("Bladet använder hårstreck. Pennbredd ensam kan inte skilja rör från andra linjer.")}</p>}
      {style.warnings.length > 0 && <p role="status">{tr("Referensmaterialet innehåller motstridiga pennbredder. Ingen av dem används som en säker rörregel.")}</p>}
    </>}
    {visibility && <p>{tr("Helt dolda vektorobjekt borttagna")}: <b>{visibility.hidden_paths ?? 0}</b>
      {" · "}{tr("Objekt klippta till synlig del")}: <b>{visibility.partial_paths ?? 0}</b></p>}
    <p className="muted">{tr("Kontrollen följer PDF-filens klippområden. Övermålade linjer och mjuka masker kan fortfarande behöva granskas.")}</p>
  </section>;
}
