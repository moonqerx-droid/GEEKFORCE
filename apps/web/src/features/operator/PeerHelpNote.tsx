import { HandHeart } from "lucide-react";
import type { PeerHelpRequest } from "../../api/types";

/** «Помощь коллег» seen from the specialist's desk: who helps and what they wrote, read-only. */
export function PeerHelpNote({ item }: { item: PeerHelpRequest }) {
  const title = item.status === "HELPING" ? `Помогает коллега: ${item.helper?.name}`
    : item.status === "RESOLVED" ? `Решено советом коллеги: ${item.helper?.name}`
    : "Сотрудник спросил коллег — пока никто не откликнулся";
  return (
    <div className="workspace-peer" role="note">
      <p className="workspace-peer-title"><HandHeart size={16} aria-hidden="true" /> {title}</p>
      {item.messages.length ? (
        <details>
          <summary>Переписка сотрудников ({item.messages.length})</summary>
          <ul>
            {item.messages.map((message) => (
              <li key={message.id}><strong>{message.sender.name}:</strong> {message.content}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
