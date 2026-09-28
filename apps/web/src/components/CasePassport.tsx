import type { Conversation, EscalationCard, OperatorTicket } from "../api/types";
import {
  DEPARTMENT_LABEL,
  OUTCOME_LABEL,
  OUTCOME_TONE,
  STATUS_LABEL,
  STATUS_TONE,
  URGENCY_LABEL,
  URGENCY_TONE,
  factLabel,
  factValue,
} from "../lib/labels";
import { Badge } from "./primitives";
import "./CasePassport.css";

/** Steps are written as full instructions; the card only needs what was tried. */
function firstSentence(text: string): string {
  const match = text.match(/^.+?[.!?](?=\s|$)/);
  return match ? match[0] : text;
}

function asCard(value: Conversation["escalation_card"]): EscalationCard | null {
  return value && typeof value === "object" && "escalation_reason" in value
    ? (value as unknown as EscalationCard)
    : null;
}

/**
 * «Карточка обращения» — what the assistant has understood so far.
 * The employee watches it fill in; the specialist receives exactly the same card,
 * which is why nobody has to retell the story.
 */
export function CasePassport({ conversation, audience }: {
  conversation: Conversation | OperatorTicket | null;
  audience: "employee" | "operator";
}) {
  if (!conversation || !conversation.summary) {
    return (
      <aside className="passport passport-empty" aria-label="Карточка обращения">
        <h2 className="passport-title">Карточка обращения</h2>
        <p className="passport-hint">
          Опишите проблему своими словами. Здесь появится всё важное, что я пойму:
          что случилось, где, насколько срочно и что уже пробовали.
        </p>
        <ul className="passport-ghost" aria-hidden="true">
          <li /><li /><li />
        </ul>
      </aside>
    );
  }

  const card = asCard(conversation.escalation_card);
  const facts = Object.entries(conversation.known_facts ?? {}).filter(([, value]) => value);
  const steps = [...conversation.completed_steps].sort((a, b) => a.position - b.position);
  const ticket = "original_request" in conversation ? conversation : null;
  const files = conversation.messages.flatMap((message) => message.attachments ?? []);
  const answered = card?.questions_and_answers.filter((item) => item.answer && item.answer !== "нет ответа") ?? [];

  return (
    <aside className="passport" aria-label="Карточка обращения">
      <header className="passport-head">
        <h2 className="passport-title">
          {audience === "employee" ? "Что я понял" : "Карточка от помощника"}
        </h2>
        {audience === "operator" ? (
          <Badge tone={STATUS_TONE[conversation.status]}>{STATUS_LABEL[conversation.status]}</Badge>
        ) : null}
      </header>

      {ticket?.owner_name ? (
        <section className="passport-row">
          <h3>Сотрудник</h3>
          <p>
            {ticket.owner_name}
            {ticket.owner_department ? <span className="passport-muted">, {DEPARTMENT_LABEL[ticket.owner_department]}</span> : null}
          </p>
        </section>
      ) : null}

      <section className="passport-row">
        <h3>Что случилось</h3>
        <p className="passport-lead">{conversation.summary}</p>
      </section>

      {ticket?.original_request ? (
        <section className="passport-row">
          <h3>Своими словами</h3>
          <blockquote className="passport-quote">{ticket.original_request}</blockquote>
        </section>
      ) : null}

      <div className="passport-pair">
        {conversation.service ? (
          <section className="passport-row">
            <h3>Где</h3>
            <p>{conversation.service}</p>
          </section>
        ) : null}
        <section className="passport-row">
          <h3>Срочность</h3>
          <p><Badge tone={URGENCY_TONE[conversation.urgency]}>{URGENCY_LABEL[conversation.urgency]}</Badge></p>
        </section>
      </div>
      {conversation.urgency_reason && conversation.urgency !== "normal" ? (
        <p className="passport-reason">{conversation.urgency_reason}</p>
      ) : null}

      {facts.length ? (
        <section className="passport-row">
          <h3>Уже известно</h3>
          <dl className="passport-facts">
            {facts.map(([key, value]) => (
              <div key={key} className="passport-fact">
                <dt>{factLabel(key)}</dt>
                <dd>{factValue(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {audience === "operator" && answered.length ? (
        <section className="passport-row">
          <h3>Вопросы и ответы</h3>
          <dl className="passport-qa">
            {answered.map((item, index) => (
              <div key={index}>
                <dt>{item.question}</dt>
                <dd>{item.answer ? factValue(item.answer) : null}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      {steps.length ? (
        <section className="passport-row">
          <h3>Уже пробовали</h3>
          <ol className="passport-steps">
            {steps.map((step) => (
              <li key={step.id}>
                <span>{firstSentence(step.instruction)}</span>
                <Badge tone={OUTCOME_TONE[step.outcome]}>{OUTCOME_LABEL[step.outcome]}</Badge>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {files.length ? (
        <section className="passport-row">
          <h3>Файлы</h3>
          <ul className="passport-files">
            {files.map((file) => (
              <li key={file.id}>
                <a href={file.url} target="_blank" rel="noreferrer" className="passport-file">
                  {file.kind === "image" ? <img src={file.url} alt="" loading="lazy" /> : <span className="passport-file-icon" aria-hidden="true">{file.filename.split(".").pop()?.toUpperCase()}</span>}
                  <span>{file.filename}</span>
                </a>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {audience === "operator" && card ? (
        <section className="passport-row passport-handoff">
          <h3>Почему передано</h3>
          <p>{card.escalation_reason}</p>
          <p className="passport-muted">Команда: {card.recommended_team}</p>
        </section>
      ) : null}

      {audience === "employee" && conversation.assignee_name ? (
        <section className="passport-row passport-handoff">
          <h3>{conversation.status === "RESOLVED" ? "Помог специалист" : "Ведёт специалист"}</h3>
          <p>{conversation.assignee_name}</p>
        </section>
      ) : null}
    </aside>
  );
}
