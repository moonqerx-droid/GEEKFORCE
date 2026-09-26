import type { Urgency } from "../../api/types";
import { URGENCY_LABEL } from "../../lib/labels";
import "./TicketFilters.css";

export interface TicketFiltersState {
  search: string;
  urgency: Urgency | "all";
  service: string | "all";
}

export function TicketFilters({
  state,
  services,
  onChange,
}: {
  state: TicketFiltersState;
  services: string[];
  onChange: (next: TicketFiltersState) => void;
}) {
  return (
    <div className="ticket-filters">
      <input
        type="search"
        className="ticket-filters-search"
        placeholder="Поиск по обращению…"
        value={state.search}
        onChange={(event) => onChange({ ...state, search: event.target.value })}
        aria-label="Поиск по обращениям"
      />
      <select
        className="ticket-filters-select"
        value={state.urgency}
        onChange={(event) =>
          onChange({ ...state, urgency: event.target.value as Urgency | "all" })
        }
        aria-label="Фильтр по срочности"
      >
        <option value="all">Любая срочность</option>
        {(Object.keys(URGENCY_LABEL) as Urgency[]).map((u) => (
          <option key={u} value={u}>
            {URGENCY_LABEL[u]}
          </option>
        ))}
      </select>
      <select
        className="ticket-filters-select"
        value={state.service}
        onChange={(event) => onChange({ ...state, service: event.target.value })}
        aria-label="Фильтр по сервису"
      >
        <option value="all">Любой сервис</option>
        {services.map((service) => (
          <option key={service} value={service}>
            {service}
          </option>
        ))}
      </select>
    </div>
  );
}
