import { useEffect, useMemo, useState } from "react";
import { Spinner, ErrorState, Badge } from "../../components/primitives";
import { Button } from "../../components/Button";
import { CasePassport } from "../../components/CasePassport";
import { DebugPanel } from "../../components/DebugPanel";
import { STATUS_LABEL, STATUS_TONE } from "../../lib/labels";
import { useAuth } from "../auth/AuthProvider";
import { useConversation } from "./useConversation";
import { WelcomeScreen } from "./WelcomeScreen";
import { MessageThread } from "./MessageThread";
import { stepMarkers } from "./steps";
import { StepCard } from "./StepCard";
import { Composer } from "./Composer";
import { OutagePanel, VerifyingPanel, ResolvedPanel, WaitingPanel } from "./StatusPanels";
import "./ConversationPage.css";

const COMPOSER_PLACEHOLDER: Record<string, string> = {
  NEW: "Опишите, что случилось…",
  CLARIFYING: "Ответьте своими словами…",
  VERIFYING: "Или напишите, как сейчас…",
  ESCALATED: "Дописать детали для специалиста…",
  IN_PROGRESS: "Написать специалисту…",
};

export function ConversationPage() {
  const conv = useConversation();
  const { user } = useAuth();
  const [draft, setDraft] = useState("");
  const steps = useMemo(() => stepMarkers(conv.conversation), [conv.conversation]);
  const messageCount = conv.conversation?.messages.length ?? 0;
  const status = conv.conversation?.status;

  // Keep the newest thing — message, step card or status panel — in view.
  useEffect(() => {
    if (!messageCount) return;
    window.requestAnimationFrame(() => {
      window.scrollTo?.({ top: document.body.scrollHeight, behavior: "smooth" });
    });
  }, [messageCount, status]);

  if (conv.phase === "loading") {
    return (
      <div className="conv-page conv-page-center">
        <Spinner label="Загружаем обращение…" />
      </div>
    );
  }

  if (conv.phase === "error" && !conv.conversation) {
    return (
      <div className="conv-page conv-page-center">
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
      <div className="conv-page">
        <div className="conv-main">
          {conv.pendingMessage ? (
            <div className="conv-chat">
              <MessageThread messages={[]} pendingMessage={conv.pendingMessage} thinkingLabel="Помощник разбирается в ситуации" />
            </div>
          ) : null}
          {/* Stays mounted while sending so a failed first message keeps its text. */}
          <div hidden={Boolean(conv.pendingMessage)}>
            <WelcomeScreen busy={conv.sending} onSubmit={conv.startWithMessage} firstName={user?.first_name} />
          </div>
          {conv.error ? <div role="alert" className="conv-alert">{conv.error}</div> : null}
        </div>
        <CasePassport conversation={null} audience="employee" />
      </div>
    );
  }

  const c = conv.conversation;
  const live = c.status === "ESCALATED" || c.status === "IN_PROGRESS";
  const showComposer = c.status in COMPOSER_PLACEHOLDER;
  const canCallSpecialist = !live && c.status !== "RESOLVED";

  return (
    <div className="conv-page">
      <div className="conv-main">
        <div className="conv-bar">
          <Badge tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
          <div className="conv-bar-actions">
            {canCallSpecialist ? (
              <Button variant="ghost" busy={conv.sending} onClick={conv.escalateNow}>
                Позвать специалиста
              </Button>
            ) : null}
            {c.status !== "RESOLVED" ? (
              <Button variant="ghost" disabled={conv.sending} onClick={conv.restartFresh}>
                Новое обращение
              </Button>
            ) : null}
          </div>
        </div>

        {conv.notice ? (
          <div className="conv-notice" role="alert">
            {conv.notice}
            <button type="button" onClick={conv.dismissNotice} aria-label="Скрыть уведомление">×</button>
          </div>
        ) : null}
        {conv.error ? <div className="conv-alert" role="alert">{conv.error}</div> : null}

        <div className="conv-chat">
          <MessageThread
            messages={c.messages}
            pendingMessage={conv.pendingMessage}
            failedMessages={conv.failedMessages}
            onRetryFailed={(id) => void conv.retryFailedMessage(id)}
            thinkingLabel={live ? "Отправляем специалисту" : "Помощник думает"}
            steps={steps}
          />

          {c.status === "TROUBLESHOOTING" && c.current_step ? (
            <StepCard
              step={c.current_step}
              number={c.completed_steps.length + 1}
              busy={conv.sending}
              onResult={conv.sendStepResult}
            />
          ) : null}

          {c.status === "VERIFYING" ? (
            <VerifyingPanel busy={conv.sending} onAnswer={(text) => void conv.sendMessage(text).catch(() => undefined)} />
          ) : null}

          {live && c.incident_id ? <OutagePanel conversation={c} /> : null}
          {c.status === "ESCALATED" && !c.incident_id ? <WaitingPanel conversation={c} /> : null}

          {c.status === "RESOLVED" ? (
            <ResolvedPanel conversation={c} onRate={conv.rate} onRestart={conv.restartFresh} />
          ) : null}
        </div>

        {showComposer ? (
          <Composer
            busy={conv.sending}
            value={draft}
            onValueChange={setDraft}
            tone={live ? "human" : "assistant"}
            placeholder={COMPOSER_PLACEHOLDER[c.status]}
            onSend={conv.sendMessage}
          />
        ) : null}

        {!showComposer && draft ? (
          <div className="conv-draft" role="status">
            <strong>Черновик сохранён</strong>
            <p>{draft}</p>
          </div>
        ) : null}
      </div>

      <div className="conv-side">
        <CasePassport conversation={c} audience="employee" />
        <DebugPanel conversation={c} />
      </div>
    </div>
  );
}
