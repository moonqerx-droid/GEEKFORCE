import { useState } from "react";
import { api } from "../../api/client";
import type { PeerHelpRequest } from "../../api/types";
import { PeerChat } from "./PeerChat";
import { explain } from "./peerHelp";

/** The chat of one request: the author and the one colleague who took it. */
export function RequestChat({ item, meId, onChange }: {
  item: PeerHelpRequest;
  meId: string;
  onChange: (item: PeerHelpRequest) => void;
}) {
  const [error, setError] = useState("");
  const isAuthor = item.author.id === meId;
  const other = isAuthor ? item.helper : item.author;
  const resolve = async () => {
    try {
      onChange(await api.resolvePeerHelp(item.id));
    } catch (cause) {
      setError(explain(cause, "Не получилось закрыть обращение. Попробуйте ещё раз."));
    }
  };

  return (
    <PeerChat
      title="Чат с коллегой"
      meId={meId}
      lines={item.messages.map((m) => ({ id: m.id, senderId: m.sender.id, senderName: m.sender.name, content: m.content }))}
      empty={isAuthor ? `${other?.name ?? "Коллега"} уже видит ваше обращение и скоро напишет.` : "Напишите, что можно попробовать."}
      onSend={async (text) => onChange(await api.sendPeerHelpMessage(item.id, text))}
    >
      {isAuthor && item.status === "HELPING" ? (
        <>
          <button type="button" className="peer-resolve" onClick={() => void resolve()}>Помог совет коллеги</button>
          <p className="peer-hint">Специалист тоже видит обращение — если совет не подойдёт, он ответит сам.</p>
        </>
      ) : null}
      {error ? <div role="alert" className="peer-chat-error">{error}</div> : null}
    </PeerChat>
  );
}
