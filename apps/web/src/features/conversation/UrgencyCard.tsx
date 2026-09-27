import { Badge } from "../../components/primitives";
import { URGENCY_LABEL, URGENCY_TONE } from "../../lib/labels";
import type { Urgency } from "../../api/types";
import "./UrgencyCard.css";

export function UrgencyCard({
  urgency,
  reason,
  summary,
}: {
  urgency: Urgency;
  reason: string | null;
  summary: string | null;
}) {
  if (!summary && !reason) return null;
  return (
    <div className="urgency-card">
      <div className="urgency-card-head">
        <Badge tone={URGENCY_TONE[urgency]}>Срочность: {URGENCY_LABEL[urgency]}</Badge>
      </div>
      {summary ? <p className="urgency-card-summary">{summary}</p> : null}
      {reason ? <p className="urgency-card-reason">Почему: {reason}</p> : null}
    </div>
  );
}
