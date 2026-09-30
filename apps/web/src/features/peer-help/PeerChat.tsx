import { useId, useState } from "react";
import { explain } from "./peerHelp";
import { Avatar } from "../../components/primitives";

export interface ChatLine {
  id: number;
  senderId: string;
  senderName: string;
  content: string;
}

export function PeerChat({ title, lines, meId, onSend, empty, children }: {
  title: string;
  lines: ChatLine[];
  meId: string;
  onSend: (text: string) => Promise<void>;
  empty: string;
  children?: React.ReactNode;
}) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputId = useId();

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;
    setBusy(true);
    try {
      await onSend(text);
      setDraft("");
      setError("");
    } catch (cause) {
      // The text stays in the field so the colleague can fix it.
      setError(explain(cause, "Сообщение не отправлено. Попробуйте ещё раз."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="peer-chat" aria-label={title}>
      <h2 className="peer-chat-title">{title}</h2>
      <div className="peer-chat-lines">
        {lines.length === 0 ? <p className="peer-chat-empty">{empty}</p> : lines.map((line) => (
          <div key={line.id} className={`peer-line ${line.senderId === meId ? "peer-line-mine" : ""}`}>
            <Avatar kind="employee" name={line.senderName} size={26} />
            <div>
              <strong>{line.senderName}</strong>
              <p>{line.content}</p>
            </div>
          </div>
        ))}
      </div>
      {error ? <div role="alert" className="peer-chat-error">{error}</div> : null}
      <form className="peer-chat-compose" onSubmit={(event) => void send(event)}>
        <label htmlFor={inputId} className="visually-hidden">Сообщение коллеге</label>
        <input id={inputId} value={draft} maxLength={2000}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Совет своими словами — без паролей и кодов" />
        <button type="submit" disabled={busy || !draft.trim()}>Отправить</button>
      </form>
      {children}
    </section>
  );
}
