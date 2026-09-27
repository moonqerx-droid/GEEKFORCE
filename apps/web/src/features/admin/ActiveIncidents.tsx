import { Link } from "react-router-dom";
import { formatAgo, formatTime } from "../../lib/labels";
import { INCIDENT_STATUS_LABEL, incidentHeadline, sinceTime, useIncidents } from "../incidents/incidents";

const DASHBOARD_POLL_MS = 15000;

/** Outages happening right now: the lead sees them without opening the specialist's desk. */
export function ActiveIncidents() {
  const { incidents } = useIncidents(DASHBOARD_POLL_MS);
  if (incidents === null) return null;
  return (
    <section className="admin-block admin-block-wide admin-incidents" aria-labelledby="admin-incidents-title">
      <h2 id="admin-incidents-title">Массовые сбои сейчас</h2>
      {incidents.length ? (
        <ul className="admin-incident-list">
          {incidents.map((incident) => (
            <li key={incident.id}>
              <Link to={`/operator?incident=${incident.id}`} className="admin-incident">
                <span className={`incident-chip incident-chip-${incident.status.toLowerCase()}`}>
                  {INCIDENT_STATUS_LABEL[incident.status]}
                </span>
                <span className="admin-incident-name">{incidentHeadline(incident)}</span>
                <span className="admin-incident-meta">
                  с {formatTime(sinceTime(incident))}, {formatAgo(sinceTime(incident))}
                  {incident.latest_update ? `. Последнее сообщение: «${incident.latest_update.message}»` : ". Команда ещё не писала сотрудникам"}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : <p className="admin-note">Массовых сбоев сейчас нет</p>}
    </section>
  );
}
