import { Button } from "../../components/Button";
import type { Citation, Conversation, CurrentStep, StepOutcome } from "../../api/types";
import "./StepCard.css";

type AnswerKind = NonNullable<Conversation["answer_kind"]>;

/**
 * The assistant's current move. A playbook step asks the employee to try something;
 * a company-document answer is information to confirm, so it reads as an answer and
 * skips «Не получается выполнить»; general advice says plainly it is not a company rule.
 */
export function StepCard({
  step,
  number,
  busy,
  onResult,
  sources = [],
  kind = "playbook",
}: {
  step: CurrentStep;
  number: number;
  busy: boolean;
  onResult: (outcome: StepOutcome) => void;
  /** Company documents this step is quoted from: the employee can check the exact words. */
  sources?: Citation[];
  kind?: AnswerKind;
}) {
  const isAnswer = kind === "document";
  const title = isAnswer
    ? "Ответ по документам компании"
    : kind === "general"
      ? `Шаг ${number}. Общая рекомендация`
      : `Шаг ${number}. Попробуйте сделать так`;

  return (
    <section className={`step-card step-card-${kind}`} aria-live="polite" aria-labelledby="step-card-title">
      <div className="step-card-head">
        <span className="step-card-number" aria-hidden="true">{isAnswer ? "§" : number}</span>
        <h2 id="step-card-title" className="step-card-title">{title}</h2>
      </div>
      {kind === "general" ? (
        <p className="step-card-note">Это общий совет, а не правило компании. Если в вашей компании принято иначе, позовите специалиста.</p>
      ) : null}
      <p className="step-card-instruction">{step.instruction}</p>
      {sources.map((source) => (
        <details key={source.source_id} className="step-card-source">
          <summary>Источник: «{source.title}»</summary>
          <blockquote>{source.quote.replace(/^#{1,6}\s+/gm, "")}</blockquote>
        </details>
      ))}
      {isAnswer ? (
        <>
          <p className="step-card-ask">Это ответ на ваш вопрос?</p>
          <div className="step-card-actions">
            <Button variant="primary" busy={busy} onClick={() => onResult("helped")}>Да, это ответ</Button>
            <Button variant="secondary" busy={busy} onClick={() => onResult("not_helped")}>Нужно другое</Button>
          </div>
        </>
      ) : (
        <>
          <p className="step-card-ask">Как получилось? От ответа зависит следующий шаг.</p>
          <div className="step-card-actions">
            <Button variant="primary" busy={busy} onClick={() => onResult("helped")}>Помогло</Button>
            <Button variant="secondary" busy={busy} onClick={() => onResult("not_helped")}>Не помогло</Button>
            <Button variant="ghost" busy={busy} onClick={() => onResult("cannot_perform")}>Не получается выполнить</Button>
          </div>
        </>
      )}
    </section>
  );
}
