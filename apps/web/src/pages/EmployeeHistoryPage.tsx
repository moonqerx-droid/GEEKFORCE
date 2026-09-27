import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Conversation } from "../api/types";
import { Badge, EmptyState, ErrorState, Spinner } from "../components/primitives";
import { STATUS_LABEL, STATUS_TONE, formatDateTime } from "../lib/labels";
import "./EmployeeHistoryPage.css";

function firstRequest(item: Conversation) {
  return item.messages.find((message) => message.role === "user")?.content ?? "";
}

export function EmployeeHistoryPage() {
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    api.listConversations().then(setItems).catch(() => setFailed(true));
  }, []);

  const visible = items?.filter((item) => item.messages.length > 0) ?? [];

  return (
    <section className="history">
      <header className="history-head">
        <h1>Мои обращения</h1>
        <Link to="/employee?new=1" className="history-new">Новое обращение</Link>
      </header>
      {failed ? <ErrorState title="Не удалось загрузить обращения" onRetry={() => window.location.reload()} /> : null}
      {!items && !failed ? <Spinner label="Загружаем…" /> : null}
      {items && !visible.length ? (
        <EmptyState title="Обращений пока нет" description="Когда что-то сломается, начните новое обращение — здесь сохранится вся история." />
      ) : null}
      {visible.length ? (
        <ul className="history-list">
          {visible.map((item) => (
            <li key={item.id}>
              <Link to={`/employee?conversation=${item.id}`} className="history-item">
                <span className="history-item-main">
                  <span className="history-item-title">{item.summary || firstRequest(item) || "Обращение"}</span>
                  <span className="history-item-meta">
                    {formatDateTime(item.created_at)}
                    {item.service ? `, ${item.service}` : ""}
                    {item.assignee_name ? `, ведёт ${item.assignee_name}` : ""}
                  </span>
                </span>
                <Badge tone={STATUS_TONE[item.status]}>{STATUS_LABEL[item.status]}</Badge>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
