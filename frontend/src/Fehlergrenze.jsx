import React from "react";

/**
 * Fehlergrenze: fängt Darstellungsfehler ab und zeigt eine Meldung mit „Neu laden“ statt einer weißen Seite.
 * Um die ganze Oberfläche (main.jsx) und zusätzlich um den Inhaltsbereich (App.jsx), damit Kopf und Navigation bedienbar bleiben.
 */
export class Fehlergrenze extends React.Component {
  constructor(props) { super(props); this.state = { fehler: null }; }
  static getDerivedStateFromError(fehler) { return { fehler }; }
  componentDidCatch(fehler, info) { console.error("Darstellungsfehler im Cockpit:", fehler, info?.componentStack); }
  render() {
    if (!this.state.fehler) return this.props.children;
    return (
      <div className="fehler fehlergrenze" role="alert" style={this.props.ganzeSeite ? { margin: 24 } : undefined}>
        <h2 style={{ marginTop: 0 }}>Diese Ansicht konnte nicht angezeigt werden.</h2>
        <p>Es ist ein unerwarteter Fehler in der Oberfläche aufgetreten. Eingegebene, aber nicht gespeicherte Daten dieser Ansicht sind
          möglicherweise verloren. Bitte neu laden; tritt der Fehler wieder auf, bitte mit Uhrzeit und dem Weg dorthin melden.</p>
        <p className="klein">Technische Angabe: {String(this.state.fehler?.message || this.state.fehler)}</p>
        <div className="aktionen">
          <button className="btn" onClick={() => window.location.reload()}>Neu laden</button>
        </div>
      </div>
    );
  }
}
