import { Component, type ErrorInfo, type ReactNode } from "react";

import { t as tr } from "../i18n";
/* En vit sida är det sämsta ett fel kan göra.
 *
 * Ett fel i en enda komponent tar med sig hela trädet: skärmen blir tom, adressen ser rätt ut, och det finns
 * ingenting att göra åt det utom att ladda om och hoppas. Det här fångar felet där det hände, säger vad som
 * gick sönder och lämnar kvar en väg vidare. Mätningen ligger kvar på servern hela tiden - det som gick sönder
 * är sättet den visas på.
 */
type Props = { children: ReactNode; what?: string };
type State = { err: Error | null };

export default class Boundary extends Component<Props, State> {
  state: State = { err: null };

  static getDerivedStateFromError(err: Error): State {
    return { err };
  }

  componentDidCatch(err: Error, info: ErrorInfo) {
    // the console is where a developer looks; the panel below is where the person using it looks
    console.error("Fel i gränssnittet:", err, info.componentStack);
  }

  render() {
    if (!this.state.err) return this.props.children;
    return (
      <div className="boom">
        <div className="card">
          <h3>Något gick sönder i {this.props.what ?? "vyn"}</h3>
          <p className="muted">
            Läsningen och alla mätningar ligger kvar på servern — det är sättet de visas på som slutade fungera.
            Försök igen, eller ladda om sidan.
          </p>
          <pre className="boom-why">{String(this.state.err?.message || this.state.err)}</pre>
          <div className="row">
            <button onClick={() => this.setState({ err: null })}>{tr("Försök igen")}</button>
            <button className="secondary" onClick={() => window.location.reload()}>{tr("Ladda om sidan")}</button>
          </div>
        </div>
      </div>
    );
  }
}
