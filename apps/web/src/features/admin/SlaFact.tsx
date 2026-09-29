import { useEffect, useState } from "react";
import { operatorApi, type SlaSummary } from "../operator/operatorApi";
import { formatDuration } from "../operator/sla";

/** Share of requests handed to people that got a first reply within the norm for their urgency. */
export function SlaFact({ days }: { days: number }) {
  const [summary, setSummary] = useState<SlaSummary | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    operatorApi.slaSummary(days, controller.signal).then(setSummary).catch(() => undefined);
    return () => controller.abort();
  }, [days]);

  if (!summary) return null;
  const decided = summary.met + summary.missed + summary.breached_open;
  const rate = summary.met_rate;
  const tone = rate == null ? "" : rate >= 0.9 ? "admin-fact-good" : rate < 0.7 ? "admin-fact-alert" : "";
  const targets = summary.targets;
  return (
    <div className={`admin-fact ${tone}`}>
      <span className="admin-fact-value">{rate == null ? "—" : `${Math.round(rate * 100)}%`}</span>
      <span className="admin-fact-label">первый ответ в норму, {summary.met} из {decided}</span>
      <span className="admin-fact-note">
        Норма: критичные — {formatDuration(targets.critical)}, срочные — {formatDuration(targets.high)},
        остальные — {formatDuration(targets.normal)}
      </span>
    </div>
  );
}
