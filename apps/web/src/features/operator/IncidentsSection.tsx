import type { Incident } from "../../api/types";
import "./IncidentsSection.css";

export function IncidentsSection({ incidents }: { incidents: Incident[] }) {
  if (incidents.length === 0) return null;

  return (
    <section className="incidents-section" aria-label="Массовые инциденты">
      <h2 className="incidents-section-title">Incident Radar: возможные массовые инциденты</h2>
      <ul className="incidents-list">
        {incidents.map((incident) => (
          <li key={incident.id} className="incidents-item">
            <p className="incidents-item-title">{incident.title}</p>
            {incident.summary ? <p className="incidents-item-summary">{incident.summary}</p> : null}
            <span className="incidents-item-count">
              Связанных обращений: {incident.conversation_ids.length}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
