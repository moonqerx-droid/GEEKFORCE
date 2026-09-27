import type { OperatorTicket } from "../../api/types";
import { Badge } from "../../components/primitives";
import { URGENCY_LABEL, URGENCY_TONE, formatDateTime } from "../../lib/labels";
import "./TicketList.css";

export function TicketList({
  tickets,
  selectedId,
  onSelect,
}: {
  tickets: OperatorTicket[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <ul className="ticket-list" role="list">
      {tickets.map((ticket) => (
        <li key={ticket.id}>
          <button
            type="button"
            className={`ticket-list-item${ticket.id === selectedId ? " selected" : ""}`}
            onClick={() => onSelect(ticket.id)}
            aria-current={ticket.id === selectedId ? "true" : undefined}
          >
            <div className="ticket-list-item-head">
              <Badge tone={URGENCY_TONE[ticket.urgency]}>{URGENCY_LABEL[ticket.urgency]}</Badge>
              {ticket.service ? <span className="ticket-list-service">{ticket.service}</span> : null}
            </div>
            <p className="ticket-list-summary">
              {ticket.summary ?? ticket.original_request}
            </p>
            <span className="ticket-list-time">{formatDateTime(ticket.updated_at)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
