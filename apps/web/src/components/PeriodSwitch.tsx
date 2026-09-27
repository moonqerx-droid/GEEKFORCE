import { PERIODS, type Period } from "../lib/period";
import "./PeriodSwitch.css";

export function PeriodSwitch({ value, onChange, label = "Период" }: {
  value: Period;
  onChange: (period: Period) => void;
  label?: string;
}) {
  return (
    <div className="period-switch" role="group" aria-label={label}>
      {PERIODS.map((period) => (
        <button key={period} type="button" aria-pressed={value === period} onClick={() => onChange(period)}>
          {period} дней
        </button>
      ))}
    </div>
  );
}
