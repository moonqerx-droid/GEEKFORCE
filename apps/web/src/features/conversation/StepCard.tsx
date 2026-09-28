import { Button } from "../../components/Button";
import type { Citation, CurrentStep, StepOutcome } from "../../api/types";
import "./StepCard.css";

export function StepCard({
  step,
  number,
  busy,
  onResult,
  sources = [],
}: {
  step: CurrentStep;
  number: number;
  busy: boolean;
  onResult: (outcome: StepOutcome) => void;
  /** Company documents this step is quoted from: the employee can check the exact words. */
  sources?: Citation[];
}) {
  return (
    <section className="step-card" aria-live="polite" aria-labelledby="step-card-title">
      <div className="step-card-head">
        <span className="step-card-number" aria-hidden="true">{number}</span>
        <h2 id="step-card-title" className="step-card-title">Шаг {number}. Попробуйте сделать так</h2>
      </div>
      <p className="step-card-instruction">{step.instruction}</p>
      {sources.map((source) => (
        <details key={source.source_id} className="step-card-source">
          <summary>Источник: «{source.title}»</summary>
          <blockquote>{source.quote.replace(/^#{1,6}\s+/gm, "")}</blockquote>
        </details>
      ))}
      <p className="step-card-ask">Как получилось? От ответа зависит следующий шаг.</p>
      <div className="step-card-actions">
        <Button variant="primary" busy={busy} onClick={() => onResult("helped")}>Помогло</Button>
        <Button variant="secondary" busy={busy} onClick={() => onResult("not_helped")}>Не помогло</Button>
        <Button variant="ghost" busy={busy} onClick={() => onResult("cannot_perform")}>Не получается выполнить</Button>
      </div>
    </section>
  );
}
