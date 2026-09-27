import type { OperatorTicket } from "../../api/types";
import { Badge, EmptyState } from "../../components/primitives";
import { OUTCOME_LABEL, OUTCOME_TONE, URGENCY_LABEL, URGENCY_TONE, formatDateTime } from "../../lib/labels";
import "./TicketDetail.css";

export function TicketDetail({ ticket }: { ticket: OperatorTicket | null }) {
  if (!ticket) {
    return (
      <div className="ticket-detail ticket-detail-empty">
        <EmptyState title="Выберите обращение" description="Список слева — карточка появится здесь." />
      </div>
    );
  }

  const questions = ticket.messages.filter((m) => m.role === "assistant");

  return (
    <div className="ticket-detail">
      <header className="ticket-detail-header">
        <p className="ticket-detail-id">Обращение {ticket.id.slice(0, 8)}</p>
        <h2>{ticket.summary ?? ticket.original_request}</h2>
        <div className="ticket-detail-head-row">
          <Badge tone={URGENCY_TONE[ticket.urgency]}>Срочность: {URGENCY_LABEL[ticket.urgency]}</Badge>
          {ticket.service ? <Badge tone="neutral">{ticket.service}</Badge> : null}
          {ticket.incident_id ? (
            <Badge tone="accent">Массовый инцидент: {ticket.incident_id}</Badge>
          ) : null}
        </div>
        <p className="ticket-detail-updated">Обновлено: {formatDateTime(ticket.updated_at)}</p>
      </header>

      <section className="ticket-detail-section">
        <h3>Исходное обращение</h3>
        <p>{ticket.original_request}</p>
      </section>

      {ticket.urgency_reason ? (
        <section className="ticket-detail-section">
          <h3>Причина срочности</h3>
          <p>{ticket.urgency_reason}</p>
        </section>
      ) : null}

      {Object.keys(ticket.known_facts).length > 0 ? (
        <section className="ticket-detail-section">
          <h3>Известные факты</h3>
          <dl className="ticket-detail-facts">
            {Object.entries(ticket.known_facts).map(([key, value]) => (
              <div key={key} className="ticket-detail-fact">
                <dt>{key}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {questions.length > 0 ? (
        <section className="ticket-detail-section">
          <h3>История вопросов</h3>
          <ul className="ticket-detail-list">
            {questions.map((q) => (
              <li key={q.id}>{q.content}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {ticket.completed_steps.length > 0 ? (
        <section className="ticket-detail-section">
          <h3>Выполненные действия</h3>
          <ul className="ticket-detail-steps">
            {ticket.completed_steps
              .slice()
              .sort((a, b) => a.position - b.position)
              .map((step) => (
                <li key={step.id}>
                  <span>{step.instruction}</span>
                  <Badge tone={OUTCOME_TONE[step.outcome]}>{OUTCOME_LABEL[step.outcome]}</Badge>
                </li>
              ))}
          </ul>
        </section>
      ) : null}

      {ticket.escalation_summary ? (
        <section className="ticket-detail-section">
          <h3>Резюме для специалиста</h3>
          <p>{ticket.escalation_summary}</p>
        </section>
      ) : null}
    </div>
  );
}
