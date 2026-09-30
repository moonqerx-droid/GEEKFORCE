import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { KnownIssue } from "../../api/types";
import { formatTime } from "../../lib/labels";
import "./ServiceStatus.css";

/** The services employees ask about most; a confirmed outage marks its service. */
const SERVICES = ["Почта", "VPN", "Интернет и Wi-Fi", "Видеозвонки", "CRM", "1С", "Корпоративный портал", "Принтеры"];

function matches(service: string, issue: KnownIssue): boolean {
  const a = service.toLowerCase();
  const b = issue.service.toLowerCase();
  return a.includes(b) || b.includes(a) || (a.includes("интернет") && b.includes("сеть"));
}

/** «Статус сервисов»: is it just me, or is it broken for everyone? Answered before writing. */
export function ServiceStatus({ onReport }: { onReport?: (text: string) => void }) {
  const [issues, setIssues] = useState<KnownIssue[] | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.knownIssues(controller.signal).then(setIssues).catch(() => setIssues([]));
    return () => controller.abort();
  }, []);

  const rows = [
    ...SERVICES.map((name) => ({ name, issue: issues?.find((issue) => matches(name, issue)) ?? null })),
    // An outage of a service outside the short list is still shown.
    ...(issues ?? [])
      .filter((issue) => !SERVICES.some((name) => matches(name, issue)))
      .map((issue) => ({ name: issue.service, issue })),
  ];

  return (
    <section className="service-status" aria-label="Статус сервисов">
      <h2 className="service-status-title">Статус сервисов</h2>
      <ul className="service-status-list">
        {rows.map(({ name, issue }) => (
          <li key={name} className={issue ? "service-row service-row-down" : "service-row"}>
            <span className="service-dot" aria-hidden="true" />
            <span className="service-name">{name}</span>
            {issue ? (
              <span className="service-state">
                Сбой — уже чиним, с {formatTime(issue.since)}
                {issue.update ? <span className="service-update">«{issue.update}»</span> : null}
                {onReport ? (
                  <button type="button" className="service-join" onClick={() => onReport(`У меня тоже не работает ${issue.service}`)}>
                    У меня то же самое
                  </button>
                ) : null}
              </span>
            ) : (
              <span className="service-state">{issues ? "Нет известных сбоев" : "…"}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
