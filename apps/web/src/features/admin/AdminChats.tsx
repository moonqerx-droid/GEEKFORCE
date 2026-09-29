import { useEffect, useState, type FormEvent } from "react";
import { api } from "../../api/client";
import type { AdminConversation } from "../../api/types";
import { Button } from "../../components/Button";
import { Badge, EmptyState, ErrorState, Spinner } from "../../components/primitives";
import { STATUS_LABEL, STATUS_TONE, formatAgo } from "../../lib/labels";
import "./AdminChats.css";

/** Every conversation for the support lead: find one by its words and delete it for good. */
export function AdminChats() {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<AdminConversation[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setRows(null);
    api.listAdminConversations(query, controller.signal)
      .then((data) => { setRows(data); setFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [query, attempt]);

  const search = (event: FormEvent) => {
    event.preventDefault();
    setNotice("");
    setQuery(draft);
  };

  const removed = (id: string) => {
    setRows((current) => current?.filter((row) => row.id !== id) ?? null);
    setNotice("Чат удалён вместе с сообщениями и вложениями.");
  };

  return (
    <section className="chats" aria-labelledby="chats-title">
      <header className="chats-head">
        <div>
          <h1 id="chats-title" className="chats-title">Все чаты</h1>
          <p className="chats-sub">
            Все обращения сотрудников, включая решённые помощником без специалиста. Найдите чат по словам
            из переписки и удалите его, если он нарушает правила. Удаление необратимо.
          </p>
        </div>
      </header>

      <form className="chats-search" role="search" onSubmit={search}>
        <label htmlFor="chats-query" className="visually-hidden">Слова из переписки</label>
        <input
          id="chats-query"
          type="search"
          value={draft}
          maxLength={100}
          placeholder="Слова из переписки, например «принтер»"
          onChange={(event) => setDraft(event.target.value)}
        />
        <Button type="submit" variant="primary">Найти</Button>
        {query ? (
          <Button type="button" variant="ghost" onClick={() => { setDraft(""); setQuery(""); }}>Сбросить</Button>
        ) : null}
      </form>

      {notice ? <p className="chats-notice" role="status">{notice}</p> : null}

      {failed ? (
        <ErrorState title="Не удалось загрузить чаты" onRetry={() => setAttempt((n) => n + 1)} />
      ) : rows === null ? (
        <Spinner label="Загружаем чаты" />
      ) : rows.length === 0 ? (
        <EmptyState title={query ? "Ничего не нашлось" : "Чатов пока нет"}
          description={query ? `Ни в одном чате нет «${query}».` : undefined} />
      ) : (
        <ul className="chats-list" aria-label="Чаты">
          {rows.map((row) => <ChatRow key={row.id} row={row} onDeleted={removed} />)}
        </ul>
      )}
    </section>
  );
}

function ChatRow({ row, onDeleted }: { row: AdminConversation; onDeleted: (id: string) => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const remove = async () => {
    setBusy(true);
    setError("");
    try {
      await api.deleteAdminConversation(row.id);
      onDeleted(row.id);
    } catch {
      setError("Не удалось удалить чат. Попробуйте ещё раз.");
      setBusy(false);
    }
  };

  return (
    <li className="chats-row">
      <div className="chats-meta">
        <Badge tone={STATUS_TONE[row.status]}>{STATUS_LABEL[row.status]}</Badge>
        <span>{row.owner_name ?? "Автор удалён"}</span>
        {row.owner_email ? <span className="chats-email">{row.owner_email}</span> : null}
        <span>{formatAgo(row.created_at)}</span>
        <span>сообщений: {row.messages}</span>
      </div>
      <p className="chats-first">{row.first_message || "Без текста"}</p>
      {row.match && row.match !== row.first_message ? (
        <p className="chats-match"><span>Найдено:</span> {row.match}</p>
      ) : null}
      {confirming ? (
        <div className="chats-confirm" role="alertdialog" aria-label="Подтверждение удаления">
          <p>Удалить этот чат безвозвратно? Сообщения и вложения удалятся тоже.</p>
          <div className="chats-confirm-actions">
            <Button variant="danger" busy={busy} onClick={remove}>Удалить навсегда</Button>
            <Button variant="ghost" disabled={busy} onClick={() => setConfirming(false)}>Отмена</Button>
          </div>
          {error ? <p className="chats-error" role="alert">{error}</p> : null}
        </div>
      ) : (
        <div className="chats-actions">
          <Button variant="secondary" onClick={() => setConfirming(true)}>Удалить чат</Button>
        </div>
      )}
    </li>
  );
}
