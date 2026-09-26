import { useEffect, useRef } from "react";
import type { Message } from "../../api/types";
import { formatTime } from "../../lib/labels";
import "./MessageThread.css";

export function MessageThread({ messages }: { messages: Message[] }) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length]);

  return (
    <div className="message-thread" aria-live="polite">
      {messages
        .filter((message) => message.role !== "system")
        .map((message) => (
          <div key={message.id} className={`message-row message-row-${message.role}`}>
            <div className={`message-bubble message-bubble-${message.role}`}>
              <p className="message-content">{message.content}</p>
              <span className="message-time">{formatTime(message.created_at)}</span>
            </div>
          </div>
        ))}
      <div ref={endRef} />
    </div>
  );
}
