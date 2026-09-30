import { useCallback, useState } from "react";
import { HandHeart } from "lucide-react";
import { api } from "../../api/client";
import type { Conversation, PeerHelpRequest } from "../../api/types";
import { useAuth } from "../auth/AuthProvider";
import { canAskColleagues, explain } from "./peerHelp";
import { RequestChat } from "./RequestChat";
import { usePolling } from "./usePolling";
import "./PeerHelp.css";

export function ConversationPeerHelp({ conversation, onResolved }: {
  conversation: Conversation;
  onResolved: () => void;
}) {
  const { user } = useAuth();
  const [item, setItem] = useState<PeerHelpRequest | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const id = conversation.id;
  const active = conversation.status !== "RESOLVED";

  const load = useCallback(() => {
    api.conversationPeerHelp(id).then(setItem).catch(() => undefined);
  }, [id]);
  usePolling(load, active);

  const change = (next: PeerHelpRequest) => {
    setItem(next);
    if (next.status === "RESOLVED") onResolved();
  };

  if (!user || !active) return null;

  if (item?.status === "HELPING") {
    return (
      <div className="peer-in-chat">
        <p className="peer-in-chat-head"><HandHeart size={16} aria-hidden="true" /> Помогает {item.helper?.name}</p>
        <RequestChat item={item} meId={user.id} onChange={change} />
      </div>
    );
  }
  if (item?.status === "OPEN") {
    return (
      <p className="peer-in-chat-note" role="status">
        <HandHeart size={16} aria-hidden="true" /> Ждём, кто из коллег откликнется. Специалист тоже видит обращение.
      </p>
    );
  }
  if (item || !canAskColleagues(conversation)) return null;

  const publish = async () => {
    setBusy(true);
    try {
      setItem(await api.publishPeerHelp(id));
      setError("");
    } catch (cause) {
      setError(explain(cause, "Не получилось спросить коллег. Попробуйте ещё раз."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="peer-ask">
      <p>
        <strong>Может, кто-то из коллег уже сталкивался?</strong> В ленту попадут только тема и раздел —
        без вашего текста и истории.
      </p>
      <button type="button" disabled={busy} onClick={() => void publish()}>
        <HandHeart size={16} aria-hidden="true" /> Спросить коллег
      </button>
      {error ? <div role="alert" className="peer-chat-error">{error}</div> : null}
    </div>
  );
}
