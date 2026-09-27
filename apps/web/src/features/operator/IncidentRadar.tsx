import type { Incident } from "../../api/types";
import { formatAgo } from "../../lib/labels";
import { INCIDENT_STATUS_LABEL, incidentHeadline, sinceTime } from "../incidents/incidents";

/** "Массовые проблемы" above the queue: one line per outage, open it to act. */
export function IncidentRadar({
  incidents,
  selectedId,
  onSelect,
}: {
  incidents: Incident[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (!incidents.length) return null;
  return (
    <section className="radar" aria-labelledby="radar-title">
      <h2 id="radar-title" className="radar-title">Массовые проблемы</h2>
      <ul className="radar-list">
        {incidents.map((incident) => (
          <li key={incident.id}>
            <button
              type="button"
              className={`radar-item radar-item-${incident.status.toLowerCase()} ${incident.id === selectedId ? "radar-item-active" : ""}`}
              aria-current={incident.id === selectedId}
              onClick={() => onSelect(incident.id)}
            >
              <span className={`incident-chip incident-chip-${incident.status.toLowerCase()}`}>
                {INCIDENT_STATUS_LABEL[incident.status]}
              </span>
              <span className="radar-headline">{incidentHeadline(incident)}</span>
              <span className="radar-meta">первое обращение {formatAgo(sinceTime(incident))}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
