import { Link } from "react-router-dom";
import { useEffect, useMemo, useRef, useState } from "react";
import { PanelRight, UserRoundCheck } from "lucide-react";
import type { Conversation, Message } from "../../api/types";
import { Spinner, ErrorState, Badge } from "../../components/primitives";
import { CasePassport } from "../../components/CasePassport";
import { DebugPanel } from "../../components/DebugPanel";
import { STATUS_LABEL, STATUS_TONE, formatDateTime } from "../../lib/labels";
import { useAuth } from "../auth/AuthProvider";
import { useConversation } from "./useConversation";
import { WelcomeScreen } from "./WelcomeScreen";
import { MessageThread } from "./MessageThread";
import { stepMarkers } from "./steps";
import { StepCard } from "./StepCard";
import { useTabNotice } from "../../lib/useTabNotice";

const NO_MESSAGES: Message[] = [];
import { QuickReplies } from "./QuickReplies";
import { Composer } from "./Composer";
import { OutagePanel, VerifyingPanel, ResolvedPanel, WaitingPanel } from "./StatusPanels";
import "./ConversationPage.css";

const COMPOSER_PLACEHOLDER: Record<string, string> = {
  NEW: "Опишите, что случилось…",
  CLARIFYING: "Ответьте своими словами…",
  TROUBLESHOOTING: "Или напишите, как прошло: «не нашёл, где это», «получилось»…",
  VERIFYING: "Или напишите, как сейчас…",
  ESCALATED: "Дописать детали для специалиста…",
  IN_PROGRESS: "Написать специалисту…",
};

function titleOf(conversation: Conversation): string {
  return conversation.summary
    ?? conversation.messages.find((message) => message.role === "user" && message.content)?.content
    ?? "Новое обращение";
}

export function ConversationPage({ onActivity }: { onActivity?: (conversation: Conversation | null) => void }) {
  const conv = useConversation();
  const { user } = useAuth();
  const [draft, setDraft] = useState("");
  const [cardOpen, setCardOpen] = useState(false);
  const chatRef = useRef<HTMLElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const steps = useMemo(() => stepMarkers(conv.conversation), [conv.conversation]);
  const messageCount = conv.conversation?.messages.length ?? 0;
  const status = conv.conversation?.status;
  const revision = conv.conversation?.revision;

  // Keep the newest thing — message, step card or status panel — in view inside the chat.
  useEffect(() => {
    const node = scrollRef.current;
    if (!node || (!messageCount && !conv.pendingMessage)) return;
    window.requestAnimationFrame(() => node.scrollTo?.({ top: node.scrollHeight, behavior: "smooth" }));
  }, [messageCount, status, conv.pendingMessage]);

  // Let the list of requests on the left follow what happens here.
  useEffect(() => {
    onActivity?.(conv.conversation);
    // Only the identity/progress of the conversation matters for the list.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conv.conversation?.id, revision, messageCount]);

  useTabNotice(conv.conversation?.messages ?? NO_MESSAGES);

  if (conv.phase === "loading") {
    return <div className="chat-page chat-page-center"><Spinner label="Загружаем обращение…" /></div>;
  }

  if (conv.phase === "error" && !conv.conversation) {
    return (
      <div className="chat-page chat-page-center">
        <ErrorState title="Не удалось загрузить обращение" description={conv.error ?? undefined} onRetry={() => window.location.reload()} />
      </div>
    );
  }

  const c = conv.conversation;
  const live = c?.status === "ESCALATED" || c?.status === "IN_PROGRESS";
  const showComposer = !c || c.status in COMPOSER_PLACEHOLDER;
  const canCallSpecialist = c && !live && c.status !== "RESOLVED" && c.messages.length > 0;

  return (
    <div className={`chat-page ${cardOpen ? "chat-page-card-open" : ""}`}>
      <section className="chat" ref={chatRef} aria-label="Обращение">
        {c ? (
          <header className="chat-head">
            <div className="chat-head-text">
              <h1 className="chat-title">{titleOf(c)}</h1>
              <p className="chat-meta">
                <Badge tone={STATUS_TONE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
                <span>с {formatDateTime(c.created_at)}</span>
                {c.assignee_name ? <span className="chat-meta-person">ведёт {c.assignee_name}</span> : null}
              </p>
            </div>
            <div className="chat-head-actions">
              {canCallSpecialist ? (
                <button type="button" className="chat-action" disabled={conv.sending} onClick={conv.escalateNow}>
                  <UserRoundCheck size={17} aria-hidden="true" />
                  <span>Позвать специалиста</span>
                </button>
              ) : null}
              <button type="button" className="chat-action chat-card-toggle" onClick={() => setCardOpen(true)}>
                <PanelRight size={17} aria-hidden="true" />
                <span>Карточка</span>
              </button>
            </div>
          </header>
        ) : null}

        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-column">
            {conv.notice ? (
              <div className="chat-notice" role="alert">
                {conv.notice}
                <button type="button" onClick={conv.dismissNotice} aria-label="Скрыть уведомление">×</button>
              </div>
            ) : null}

            {c?.similar_open ? (
              <aside className="similar-open" role="note" aria-label="Похожее открытое обращение">
                <p>
                  У вас уже есть открытое обращение «{c.similar_open.summary ?? "без названия"}». Если это то же
                  самое, продолжите там — не придётся объяснять заново.
                </p>
                <Link to={`/employee?conversation=${c.similar_open.id}`}>Открыть его</Link>
              </aside>
            ) : null}

            {!c && conv.pendingMessage == null ? (
              <WelcomeScreen firstName={user?.first_name} onExample={setDraft}
                onReport={(text) => void conv.startWithMessage(text, []).catch(() => undefined)} />
            ) : null}

            {c || conv.pendingMessage != null ? (
              <MessageThread
                messages={c?.messages ?? []}
                pendingMessage={conv.pendingMessage}
                pendingFiles={conv.pendingFiles}
                failedMessages={conv.failedMessages}
                onRetryFailed={(id) => void conv.retryFailedMessage(id)}
                thinkingLabel={live ? "Отправляем специалисту" : c ? "Помощник думает" : "Помощник разбирается в ситуации"}
                steps={steps}
              />
            ) : null}

            {c?.status === "CLARIFYING" && c.quick_replies?.length && !conv.sending && conv.pendingMessage == null ? (
              <QuickReplies replies={c.quick_replies} onPick={(reply) => void conv.sendMessage(reply, []).catch(() => undefined)} />
            ) : null}

            {c?.status === "TROUBLESHOOTING" && c.current_step ? (
              <StepCard step={c.current_step} number={c.completed_steps.length + 1} busy={conv.sending} onResult={conv.sendStepResult}
                sources={c.answer_kind === "document" ? c.citations ?? [] : []}
                kind={c.answer_kind === "document" || c.answer_kind === "general" ? c.answer_kind : "playbook"} />
            ) : null}

            {c?.status === "VERIFYING" ? (
              <VerifyingPanel busy={conv.sending} onAnswer={(text) => void conv.sendMessage(text).catch(() => undefined)} />
            ) : null}

            {c?.status === "RESOLVED" ? (
              <ResolvedPanel conversation={c} onRate={conv.rate} onRestart={conv.restartFresh} />
            ) : null}
          </div>
        </div>

        <footer className="chat-foot">
          <div className="chat-column">
            {conv.error ? <div className="chat-alert" role="alert">{conv.error}</div> : null}
            {c && live && c.incident_id ? <OutagePanel conversation={c} /> : null}
            {c?.status === "ESCALATED" && !c.incident_id ? <WaitingPanel conversation={c} /> : null}
            {showComposer ? (
              <Composer
                busy={conv.sending}
                value={draft}
                onValueChange={setDraft}
                tone={live ? "human" : "assistant"}
                label={c ? "Ваше сообщение" : "Опишите проблему"}
                size={c ? "regular" : "large"}
                placeholder={c ? (c.status === "TROUBLESHOOTING" && c.answer_kind === "document"
                  ? "Или напишите своими словами…"
                  : COMPOSER_PLACEHOLDER[c.status]) : "Например: не открывается почта, пишет «нет подключения»…"}
                allowFiles
                dropTarget={chatRef}
                autoFocus={!c}
                onSend={(text, files) => (c ? conv.sendMessage(text, files) : conv.startWithMessage(text, files))}
              />
            ) : null}
            {!showComposer && draft ? (
              <div className="chat-draft" role="status">
                <strong>Черновик сохранён</strong>
                <p>{draft}</p>
              </div>
            ) : null}
          </div>
        </footer>
        <div className="chat-drop-hint" aria-hidden="true">Отпустите, чтобы прикрепить</div>
      </section>

      {cardOpen ? <button type="button" className="chat-scrim" aria-label="Скрыть карточку" onClick={() => setCardOpen(false)} /> : null}
      <div className={`chat-side ${cardOpen ? "chat-side-open" : ""}`}>
        <button type="button" className="chat-side-close" onClick={() => setCardOpen(false)}>Скрыть карточку</button>
        <CasePassport conversation={c} audience="employee" />
        {c ? <DebugPanel conversation={c} /> : null}
      </div>
    </div>
  );
}
