import { useCallback, useState } from "react";
import { api } from "../../api/client";
import type { PeerHelpRequest } from "../../api/types";
import { EmptyState } from "../../components/primitives";
import { DEPARTMENT_LABEL } from "../../lib/labels";
import { useAuth } from "../auth/AuthProvider";
import { explain } from "./peerHelp";
import { RequestChat } from "./RequestChat";
import { usePolling } from "./usePolling";
import "./PeerHelp.css";

export function PeerHelpPage() {
  const { user } = useAuth();
  const [items, setItems] = useState<PeerHelpRequest[] | null>(null);
  const [active, setActive] = useState<PeerHelpRequest | null>(null);
  const [error, setError] = useState("");
  const activeId = active?.id;

  const load = useCallback(() => {
    api.peerHelpFeed().then((feed) => { setItems(feed); setError(""); })
      .catch(() => setError("Лента не обновилась — проверим ещё раз через несколько секунд."));
    if (activeId) api.peerHelp(activeId).then(setActive).catch(() => undefined);
  }, [activeId]);
  usePolling(load);

  const take = async (item: PeerHelpRequest) => {
    try {
      setActive(await api.claimPeerHelp(item.id));
    } catch (cause) {
      setError(explain(cause, "Не получилось взять просьбу."));
    }
    load();
  };

  if (!user) return null;
  const meId = user.id;

  return (
    <div className="peer-page">
      <header className="peer-head">
        <h1>Помощь коллег</h1>
        <p>Коллеги ждут специалиста или шаги им не помогли. Если знаете решение — подскажите.
          Пароли и коды в чате не пропустим.</p>
      </header>
      {error ? <div role="alert" className="peer-chat-error">{error}</div> : null}
      <div className="peer-layout">
        <div className="peer-feed">
          {items && items.length === 0 ? (
            <EmptyState title="Сейчас никто не просит помощи" description="Загляните позже — или спросите коллег из своего обращения." />
          ) : null}
          {(items ?? []).map((item) => {
            const mine = item.author.id === meId || item.helper?.id === meId;
            return (
              <article key={item.id} className={`peer-card ${activeId === item.id ? "peer-card-active" : ""}`}
                aria-labelledby={`peer-${item.id}`}>
                <span className="peer-card-area">{item.area}</span>
                <h2 id={`peer-${item.id}`}>{item.title}</h2>
                <p className="peer-card-who">
                  <span>{item.author.name}</span> · {DEPARTMENT_LABEL[item.author.department] ?? item.author.department}
                </p>
                <p className="peer-card-state">
                  {item.status === "OPEN" ? "Ищет помощника" : `Помогает: ${item.helper?.name}`}
                </p>
                {mine && item.status === "HELPING" ? (
                  <button type="button" onClick={() => void api.peerHelp(item.id).then(setActive)}>Открыть чат</button>
                ) : item.status === "OPEN" && item.author.id !== meId ? (
                  <button type="button" onClick={() => void take(item)}>Помогу</button>
                ) : null}
              </article>
            );
          })}
        </div>
        {active ? <RequestChat item={active} meId={meId} onChange={setActive} /> : null}
      </div>
    </div>
  );
}
