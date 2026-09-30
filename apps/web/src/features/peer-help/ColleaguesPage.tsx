import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type { Colleague, DirectMessage } from "../../api/types";
import { Avatar, EmptyState } from "../../components/primitives";
import { DEPARTMENT_LABEL } from "../../lib/labels";
import { useAuth } from "../auth/AuthProvider";
import { PeerChat } from "./PeerChat";
import { usePolling } from "./usePolling";
import "./PeerHelp.css";

export function ColleaguesPage() {
  const { user } = useAuth();
  const [people, setPeople] = useState<Colleague[] | null>(null);
  const [selected, setSelected] = useState<Colleague | null>(null);
  const [messages, setMessages] = useState<DirectMessage[]>([]);
  const selectedId = selected?.id;

  useEffect(() => {
    api.colleagues().then(setPeople).catch(() => setPeople([]));
  }, []);

  const loadChat = useCallback(() => {
    if (selectedId) api.directMessages(selectedId).then(setMessages).catch(() => undefined);
  }, [selectedId]);
  usePolling(loadChat, Boolean(selectedId));

  if (!user) return null;

  return (
    <div className="peer-page">
      <header className="peer-head">
        <h1>Коллеги</h1>
        <p>Напишите тому, кто уже помогал с похожей проблемой. Сообщения видите только вы двое.</p>
      </header>
      <div className="peer-layout">
        <div className="peer-people">
          {people && people.length === 0 ? <EmptyState title="Пока здесь никого нет" /> : null}
          {(people ?? []).map((person) => (
            <button key={person.id} type="button"
              className={`peer-person ${selectedId === person.id ? "peer-person-active" : ""}`}
              onClick={() => { setSelected(person); setMessages([]); }}>
              <Avatar kind="employee" name={person.name} size={34} />
              <span>
                <strong>{person.name}</strong>
                <small>{DEPARTMENT_LABEL[person.department] ?? person.department}</small>
              </span>
              {person.helped_count > 0 ? <em>Помог коллегам: {person.helped_count}</em> : null}
            </button>
          ))}
        </div>
        {selected ? (
          <PeerChat
            key={selected.id}
            title={selected.name}
            meId={user.id}
            lines={messages.map((m) => ({ id: m.id, senderId: m.sender.id, senderName: m.sender.name, content: m.content }))}
            empty="Сообщений пока нет — начните разговор."
            onSend={async (text) => {
              await api.sendDirectMessage(selected.id, text);
              loadChat();
            }}
          />
        ) : (
          <p className="peer-pick">Выберите коллегу, чтобы написать ему.</p>
        )}
      </div>
    </div>
  );
}
