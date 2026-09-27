import { useEffect, useRef } from "react";
import type { Message } from "../../api/types";
import type { FailedMessage } from "./useConversation";
import { formatTime } from "../../lib/labels";
import "./MessageThread.css";

export function MessageThread({
  messages,
  pendingMessage,
  failedMessages = [],
  onRetryFailed,
}: {
  messages: Message[];
  pendingMessage?: string | null;
  failedMessages?: FailedMessage[];
  onRetryFailed?: (id: number) => void;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, pendingMessage]);

  return (
    <div className="message-thread" role="log" aria-label="Ход диалога" aria-live="polite">
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
      {pendingMessage ? (
        <>
          <div className="message-row message-row-user">
            <div className="message-bubble message-bubble-user message-bubble-pending">
              <p className="message-content">{pendingMessage}</p>
              <span className="message-time">Отправляется</span>
            </div>
          </div>
          <div className="assistant-thinking" role="status" aria-label="HelpFlow готовит ответ">
            <span className="assistant-thinking-dot" aria-hidden="true" />
            <span className="assistant-thinking-dot" aria-hidden="true" />
            <span className="assistant-thinking-dot" aria-hidden="true" />
            <span>HelpFlow готовит ответ</span>
          </div>
        </>
      ) : null}
      {failedMessages.map((failed) => (
        <div key={`failed-${failed.id}`} className="message-row message-row-user">
          <div className="message-bubble message-bubble-user message-bubble-failed">
            <p className="message-content">{failed.content}</p>
            <div className="message-failed-actions">
              <span>Не отправлено</span>
              <button type="button" onClick={() => onRetryFailed?.(failed.id)}>Повторить отправку</button>
            </div>
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
