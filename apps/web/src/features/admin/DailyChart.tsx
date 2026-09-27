import { useState } from "react";
import type { DailyMetric } from "../../api/types";

// Validated with the dataviz palette checker (CVD, lightness, contrast) on white.
const SERIES = [
  { key: "assistant", label: "Решил помощник", color: "#E8572A" },
  { key: "operator", label: "Решил специалист", color: "#0E8AA0" },
  { key: "open", label: "Ещё открыто", color: "#B07C12" },
] as const;

const HEIGHT = 180;
const BAR = 22;
const GAP = 2;

function dayLabel(iso: string, long = false) {
  const date = new Date(`${iso}T12:00:00`);
  return date.toLocaleDateString("ru-RU", long ? { weekday: "long", day: "numeric", month: "long" } : { day: "numeric", month: "short" });
}

export function DailyChart({ days }: { days: DailyMetric[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const peak = Math.max(4, ...days.map((day) => day.assistant + day.operator + day.open));
  const step = peak <= 10 ? 2 : peak <= 20 ? 4 : peak <= 50 ? 10 : 20;
  const max = Math.ceil(peak / step) * step;
  const slot = 100 / days.length;
  const labelEvery = days.length > 14 ? 5 : days.length > 7 ? 2 : 1;
  const ticks = [0, Math.ceil(max / 2), max];

  return (
    <figure className="chart">
      <ul className="chart-legend" aria-label="Обозначения">
        {SERIES.map((series) => (
          <li key={series.key}><i style={{ background: series.color }} />{series.label}</li>
        ))}
      </ul>
      <div className="chart-plot" onMouseLeave={() => setHover(null)}>
        <div className="chart-grid" aria-hidden="true">
          {ticks.slice().reverse().map((tick) => (
            <div key={tick} className="chart-gridline"><span className="num">{tick}</span></div>
          ))}
        </div>
        <div className="chart-columns" style={{ height: HEIGHT }}>
          {days.map((day, index) => {
            const total = day.assistant + day.operator + day.open;
            return (
              <div
                key={day.date}
                className={`chart-column ${hover === index ? "chart-column-hover" : ""}`}
                style={{ width: `${slot}%` }}
                onMouseEnter={() => setHover(index)}
                onFocus={() => setHover(index)}
                tabIndex={0}
                aria-label={`${dayLabel(day.date, true)}: помощник ${day.assistant}, специалист ${day.operator}, открыто ${day.open}`}
              >
                <div className="chart-stack" style={{ width: BAR }}>
                  {SERIES.map((series) => {
                    const value = day[series.key];
                    if (!value) return null;
                    const height = (value / max) * HEIGHT - GAP;
                    return <span key={series.key} className="chart-seg" style={{ height: Math.max(2, height), background: series.color }} />;
                  }).reverse()}
                </div>
                {hover === index ? (
                  <div className={`chart-tip ${index > days.length / 2 ? "chart-tip-left" : ""}`} role="tooltip">
                    <strong>{dayLabel(day.date, true)}</strong>
                    <span>Всего обращений: <b className="num">{total}</b></span>
                    {SERIES.map((series) => (
                      <span key={series.key}><i style={{ background: series.color }} />{series.label}: <b className="num">{day[series.key]}</b></span>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
        <div className="chart-axis" aria-hidden="true">
          {days.map((day, index) => (
            <span key={day.date} style={{ width: `${slot}%` }}>
              {index % labelEvery === 0 || index === days.length - 1 ? dayLabel(day.date) : ""}
            </span>
          ))}
        </div>
      </div>
      <details className="chart-table">
        <summary>Показать таблицей</summary>
        <table>
          <thead><tr><th>День</th>{SERIES.map((series) => <th key={series.key}>{series.label}</th>)}</tr></thead>
          <tbody>
            {days.map((day) => (
              <tr key={day.date}>
                <td>{dayLabel(day.date)}</td>
                {SERIES.map((series) => <td key={series.key} className="num">{day[series.key]}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
