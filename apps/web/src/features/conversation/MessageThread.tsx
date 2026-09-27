import { Fragment, useEffect, useRef } from "react";
import type { Message, StepOutcome } from "../../api/types";
import { Avatar, Badge } from "../../components/primitives";
import type { FailedMessage } from "./useConversation";
import { OUTCOME_LABEL, OUTCOME_TONE, formatTime } from "../../lib/labels";
import "./MessageThread.css";

/** Assistant messages that are really steps render as compact step bubbles (or not at all while the step card is open). */
export interface StepMarker {
  number: number;
  outcome: StepOutcome | null;
}

/**
 * One shared thread for the employee, the assistant and the specialist.
 * `viewer` flips which side counts as "me" so the operator workspace can reuse it.
 */
export function MessageThread({
  messages,
  pendingMessage,
  failedMessages = [],
  onRetryFailed,
  viewer = "employee",
  thinkingLabel = "Помощник думает",
  steps,
  employeeName,
}: {
  employeeName?: string | null;
  steps?: Map<string, StepMarker>;
  messages: Message[];
  pendingMessage?: string | null;
  failedMessages?: FailedMessage[];
  onRetryFailed?: (id: number) => void;
  viewer?: "employee" | "operator";
  thinkingLabel?: string;
}) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end", behavior: "smooth" });
  }, [messages.length, pendingMessage]);

  const visible = messages.filter((message) => message.role !== "system");
  const joined = new Set<string>();

  return (
    <div className="thread" role="log" aria-label="Ход диалога" aria-live="polite">
      {visible.map((message) => {
        const step = message.role === "assistant" ? steps?.get(message.content.trim()) : undefined;
        if (step && step.outcome === null) return null;
        if (step) {
          return (
            <div key={message.id} className="thread-row">
              <Avatar kind="assistant" />
              <div className="bubble bubble-assistant bubble-step">
                <span className="bubble-step-head">
                  <span className="bubble-author">Шаг {step.number}</span>
                  {step.outcome ? <Badge tone={OUTCOME_TONE[step.outcome]}>{OUTCOME_LABEL[step.outcome]}</Badge> : null}
                </span>
                <p className="bubble-text">{message.content}</p>
              </div>
            </div>
          );
        }
        const mine = viewer === "employee" ? message.role === "user" : message.role === "operator";
        const author = message.author_name ?? "Специалист";
        const firstFromOperator = message.role === "operator" && !joined.has(author);
        if (firstFromOperator) joined.add(author);
        return (
          <Fragment key={message.id}>
            {firstFromOperator ? (
              <div className="thread-event" role="status">
                <Avatar kind="human" name={author} size={22} />
                {viewer === "employee"
                  ? `${author} подключается к обращению и уже видит всю историю`
                  : `${author} ведёт обращение`}
              </div>
            ) : null}
            <div className={`thread-row ${mine ? "thread-row-mine" : ""}`}>
              {!mine ? (
                message.role === "assistant" ? <Avatar kind="assistant" /> :
                message.role === "operator" ? <Avatar kind="human" name={author} /> :
                <Avatar kind="employee" name={employeeName ?? "Сотрудник"} />
              ) : null}
              <div className={`bubble bubble-${message.role} ${mine ? "bubble-mine" : ""}`}>
                {!mine && message.role === "operator" ? <span className="bubble-author">{author}</span> : null}
                {!mine && message.role === "assistant" && viewer === "operator" ? <span className="bubble-author">Помощник</span> : null}
                <p className="bubble-text">{message.content}</p>
                <time className="bubble-time" dateTime={message.created_at}>{formatTime(message.created_at)}</time>
              </div>
            </div>
          </Fragment>
        );
      })}
      {pendingMessage ? (
        <>
          <div className="thread-row thread-row-mine">
            <div className={`bubble bubble-mine bubble-${viewer === "employee" ? "user" : "operator"} bubble-pending`}>
              <p className="bubble-text">{pendingMessage}</p>
              <span className="bubble-time">Отправляется</span>
            </div>
          </div>
          {viewer === "employee" ? (
            <div className="thread-thinking" role="status" aria-label={thinkingLabel}>
              <Avatar kind="assistant" size={26} />
              <span className="thread-dots" aria-hidden="true"><i /><i /><i /></span>
              <span>{thinkingLabel}</span>
            </div>
          ) : null}
        </>
      ) : null}
      {failedMessages.map((failed) => (
        <div key={`failed-${failed.id}`} className="thread-row thread-row-mine">
          <div className="bubble bubble-mine bubble-user bubble-failed">
            <p className="bubble-text">{failed.content}</p>
            <div className="bubble-failed-actions">
              <span>Не отправлено</span>
              <button type="button" onClick={() => onRetryFailed?.(failed.id)}>Отправить ещё раз</button>
            </div>
          </div>
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
