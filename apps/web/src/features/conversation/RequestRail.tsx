import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Plus } from "lucide-react";
import { api } from "../../api/client";
import type { Conversation } from "../../api/types";
import { STATUS_LABEL, formatAgo } from "../../lib/labels";
import "./RequestRail.css";

export const RAIL_POLL_MS = 10000;

function title(item: Conversation) {
  return item.summary ?? item.messages.find((message) => message.role === "user" && message.content)?.content ?? "Обращение со скриншотом";
}

/** Who said the last thing: the employee sees at a glance where a specialist has answered. */
function lastLine(item: Conversation) {
  const last = [...item.messages].reverse().find((message) => message.role !== "system");
  if (!last) return "";
  const who = last.role === "user" ? "Вы" : last.role === "operator" ? (last.author_name?.split(" ")[0] ?? "Специалист") : "Помощник";
  const text = last.content || (last.attachments?.length ? "файл" : "");
  return `${who}: ${text}`;
}

function tone(item: Conversation) {
  if (item.status === "RESOLVED") return "done";
  if (item.status === "IN_PROGRESS") return "human";
  if (item.status === "ESCALATED") return "waiting";
  return "assistant";
}

/** The employee's own requests, like a messenger's chat list. */
export function RequestRail({ currentId, refreshKey }: { currentId: string | null; refreshKey: number }) {
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const load = () => api.listConversations(controller.signal)
      .then((data) => { setItems(data.filter((item) => item.messages.length > 0)); setFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    void load();
    const timer = window.setInterval(() => void load(), RAIL_POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [refreshKey]);

  const open = items?.filter((item) => item.status !== "RESOLVED") ?? [];
  const done = items?.filter((item) => item.status === "RESOLVED") ?? [];

  const renderItem = (item: Conversation) => (
    <li key={item.id}>
      <Link
        to={`/employee?conversation=${item.id}`}
        className={`rail-item rail-item-${tone(item)}`}
        aria-current={item.id === currentId ? "page" : undefined}
      >
        <span className="rail-item-top">
          <span className="rail-dot" aria-hidden="true" />
          <span className="rail-status">{STATUS_LABEL[item.status]}</span>
          <span className="rail-time">{formatAgo(item.updated_at)}</span>
        </span>
        <span className="rail-title">{title(item)}</span>
        <span className="rail-last">{lastLine(item)}</span>
      </Link>
    </li>
  );

  return (
    <nav className="rail" aria-label="Мои обращения">
      <Link to="/employee?new=1" className="rail-new">
        <Plus size={18} aria-hidden="true" />
        Новое обращение
      </Link>
      <div className="rail-scroll">
        {failed && !items ? <p className="rail-note">Не удалось загрузить список. Обновим через несколько секунд.</p> : null}
        {items && !items.length ? <p className="rail-note">Здесь будут ваши обращения и их статусы.</p> : null}
        {open.length ? (
          <>
            <h2 className="rail-group">В работе</h2>
            <ul className="rail-list">{open.map(renderItem)}</ul>
          </>
        ) : null}
        {done.length ? (
          <>
            <h2 className="rail-group">Решённые</h2>
            <ul className="rail-list">{done.map(renderItem)}</ul>
          </>
        ) : null}
      </div>
    </nav>
  );
}
