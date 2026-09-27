import { useState } from "react";
import { Spinner, ErrorState } from "../../components/primitives";
import { Button } from "../../components/Button";
import { STATUS_LABEL } from "../../lib/labels";
import { useConversation } from "./useConversation";
import { WelcomeScreen } from "./WelcomeScreen";
import { MessageThread } from "./MessageThread";
import { UrgencyCard } from "./UrgencyCard";
import { StepCard } from "./StepCard";
import { Composer } from "./Composer";
import { VerifyingBanner, ResolvedPanel, EscalatedPanel } from "./StatusPanels";
import { DebugPanel } from "../../components/DebugPanel";
import "./ConversationPage.css";

const MESSAGE_INPUT_STATUSES = new Set(["NEW", "ANALYZING", "CLARIFYING", "VERIFYING"]);

export function ConversationPage() {
  const conv = useConversation();
  const [draft, setDraft] = useState("");

  if (conv.phase === "loading") {
    return (
      <div className="conversation-page conversation-page-center">
        <Spinner label="Загружаем обращение…" />
      </div>
    );
  }

  if (conv.phase === "error" && !conv.conversation) {
    return (
      <div className="conversation-page conversation-page-center">
        <ErrorState
          title="Не удалось загрузить обращение"
          description={conv.error ?? undefined}
          onRetry={() => window.location.reload()}
        />
      </div>
    );
  }

  if (!conv.conversation) {
    return (
      <div className="conversation-page">
        {conv.pendingMessage ? (
          <div className="conversation-shell">
            <div className="conversation-statusbar">
              <span className="conversation-status-label">Создаём обращение</span>
            </div>
            <MessageThread messages={[]} pendingMessage={conv.pendingMessage} />
          </div>
        ) : null}
        {conv.error ? <div role="alert" className="conversation-error">{conv.error}</div> : null}
        <div hidden={Boolean(conv.pendingMessage)}>
          <WelcomeScreen
            busy={conv.sending}
            onSubmit={conv.startWithMessage}
          />
        </div>
      </div>
    );
  }

  const c = conv.conversation;
  const showComposer = MESSAGE_INPUT_STATUSES.has(c.status);
  const showEscalateButton = c.status !== "RESOLVED" && c.status !== "ESCALATED";

  return (
    <div className="conversation-page">
      <div className="conversation-shell">
        <div className="conversation-statusbar">
          <span className="conversation-status-label">{STATUS_LABEL[c.status]}</span>
          {showEscalateButton ? (
            <Button variant="ghost" size="md" busy={conv.sending} onClick={conv.escalateNow}>
              Передать специалисту
            </Button>
          ) : null}
        </div>

        {conv.notice ? (
          <div className="conversation-notice" role="alert">
            {conv.notice}
            <button
              type="button"
              className="conversation-notice-dismiss"
              onClick={conv.dismissNotice}
              aria-label="Скрыть уведомление"
            >
              ×
            </button>
          </div>
        ) : null}

        {conv.error ? (
          <div className="conversation-error" role="alert">
            {conv.error}
          </div>
        ) : null}

        <UrgencyCard urgency={c.urgency} reason={c.urgency_reason} summary={c.summary} />

        <MessageThread
          messages={c.messages}
          pendingMessage={conv.pendingMessage}
          failedMessages={conv.failedMessages}
          onRetryFailed={(id) => void conv.retryFailedMessage(id)}
        />

        {c.status === "TROUBLESHOOTING" && c.current_step ? (
          <StepCard step={c.current_step} busy={conv.sending} onResult={conv.sendStepResult} />
        ) : null}

        {c.status === "VERIFYING" ? <VerifyingBanner /> : null}

        {c.status === "RESOLVED" ? (
          <ResolvedPanel conversation={c} onRestart={conv.restartFresh} />
        ) : null}

        {c.status === "ESCALATED" ? (
          <EscalatedPanel conversation={c} onRestart={conv.restartFresh} />
        ) : null}

        {showComposer ? (
          <Composer
            busy={conv.sending}
            value={draft}
            onValueChange={setDraft}
            placeholder={
              c.status === "VERIFYING"
                ? "Например: да, всё заработало"
                : "Напишите сообщение…"
            }
            onSend={conv.sendMessage}
          />
        ) : null}

        {!showComposer && draft ? (
          <div className="conversation-saved-draft" role="status">
            <strong>Черновик сохранён</strong>
            <p>{draft}</p>
          </div>
        ) : null}

        {c.status !== "RESOLVED" && c.status !== "ESCALATED" ? (
          <button type="button" disabled={conv.sending} className="conversation-restart-link" onClick={conv.restartFresh}>
            Начать заново
          </button>
        ) : null}
      </div>

      <DebugPanel conversation={c} />
    </div>
  );
}
