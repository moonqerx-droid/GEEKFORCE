import { Button } from "../../components/Button";
import type { CurrentStep, StepOutcome } from "../../api/types";
import "./StepCard.css";

export function StepCard({
  step,
  busy,
  onResult,
}: {
  step: CurrentStep;
  busy: boolean;
  onResult: (outcome: StepOutcome) => void;
}) {
  return (
    <div className="step-card" aria-live="polite">
      <p className="step-card-label">Попробуйте выполнить</p>
      <p className="step-card-instruction">{step.instruction}</p>
      <div className="step-card-actions">
        <Button variant="primary" busy={busy} onClick={() => onResult("helped")}>
          Помогло
        </Button>
        <Button variant="secondary" busy={busy} onClick={() => onResult("not_helped")}>
          Не помогло
        </Button>
        <Button variant="ghost" busy={busy} onClick={() => onResult("cannot_perform")}>
          Не могу выполнить
        </Button>
      </div>
    </div>
  );
}
