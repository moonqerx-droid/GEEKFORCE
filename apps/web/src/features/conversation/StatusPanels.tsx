import { Badge } from "../../components/primitives";
import { Button } from "../../components/Button";
import { OUTCOME_LABEL, OUTCOME_TONE } from "../../lib/labels";
import type { CompletedStep, Conversation } from "../../api/types";
import "./StatusPanels.css";

export function VerifyingBanner() {
  return (
    <div className="status-banner status-banner-info" role="status">
      Подтвердите, пожалуйста: проблема действительно решена? Ответьте в сообщении ниже.
    </div>
  );
}

function CompletedStepsList({ steps }: { steps: CompletedStep[] }) {
  if (steps.length === 0) return null;
  return (
    <ul className="completed-steps">
      {steps
        .slice()
        .sort((a, b) => a.position - b.position)
        .map((step) => (
          <li key={step.id} className="completed-step">
            <span className="completed-step-instruction">{step.instruction}</span>
            <Badge tone={OUTCOME_TONE[step.outcome]}>{OUTCOME_LABEL[step.outcome]}</Badge>
          </li>
        ))}
    </ul>
  );
}

export function ResolvedPanel({
  conversation,
  onRestart,
}: {
  conversation: Conversation;
  onRestart: () => void;
}) {
  return (
    <div className="status-panel status-panel-success">
      <h2 className="status-panel-title">Проблема решена</h2>
      {conversation.summary ? (
        <p className="status-panel-summary">{conversation.summary}</p>
      ) : null}
      <p className="status-panel-label">Что было сделано:</p>
      <CompletedStepsList steps={conversation.completed_steps} />
      <Button variant="primary" onClick={onRestart}>
        Новое обращение
      </Button>
    </div>
  );
}

export function EscalatedPanel({
  conversation,
  onRestart,
}: {
  conversation: Conversation;
  onRestart: () => void;
}) {
  const card = conversation.escalation_card;
  const assignee =
    card && typeof card === "object" && "team" in card ? String(card.team) : null;

  return (
    <div className="status-panel status-panel-warning">
      <h2 className="status-panel-title">Обращение передано специалисту</h2>
      {assignee ? (
        <p className="status-panel-summary">Передано команде: {assignee}</p>
      ) : null}
      {conversation.escalation_summary ? (
        <p className="status-panel-summary">{conversation.escalation_summary}</p>
      ) : null}
      {conversation.incident_id ? (
        <p className="status-panel-incident">
          Связано с массовым инцидентом: {conversation.incident_id}
        </p>
      ) : null}
      {conversation.completed_steps.length > 0 ? (
        <>
          <p className="status-panel-label">Что уже пробовали:</p>
          <CompletedStepsList steps={conversation.completed_steps} />
        </>
      ) : null}
      <p className="status-panel-note">
        Специалист уже видит полный контекст обращения — повторно описывать проблему не нужно.
      </p>
      <Button variant="primary" onClick={onRestart}>
        Новое обращение
      </Button>
    </div>
  );
}
