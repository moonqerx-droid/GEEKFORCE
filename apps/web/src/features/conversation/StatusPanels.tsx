import { useState } from "react";
import { Button } from "../../components/Button";
import type { Conversation } from "../../api/types";
import { formatMinutes } from "../../lib/labels";
import "./StatusPanels.css";

export function VerifyingPanel({ busy, onAnswer }: { busy: boolean; onAnswer: (text: string) => void }) {
  return (
    <section className="panel panel-verify" aria-labelledby="verify-title">
      <h2 id="verify-title" className="panel-title">Проверим, что всё работает?</h2>
      <p className="panel-text">Откройте то, что не работало, и скажите, как сейчас.</p>
      <div className="panel-actions">
        <Button variant="primary" busy={busy} onClick={() => onAnswer("Да, всё работает")}>Да, всё работает</Button>
        <Button variant="secondary" busy={busy} onClick={() => onAnswer("Нет, всё ещё не работает")}>Нет, всё ещё не работает</Button>
      </div>
    </section>
  );
}

export function WaitingPanel({ conversation }: { conversation: Conversation }) {
  const card = conversation.escalation_card as { recommended_team?: string } | null;
  return (
    <section className="panel panel-waiting" role="status" aria-labelledby="waiting-title">
      <span className="panel-pulse" aria-hidden="true" />
      <div>
        <h2 id="waiting-title" className="panel-title">Передали специалисту</h2>
        <p className="panel-text">
          {card?.recommended_team ? `Команда «${card.recommended_team}» ` : "Специалист "}
          уже видит карточку обращения. Пересказывать ничего не нужно — ответ появится здесь же.
          Пока ждёте, можно дописать детали.
        </p>
      </div>
    </section>
  );
}

/** The request matched a known outage: nothing to check on the employee's side. */
export function OutagePanel({ conversation }: { conversation: Conversation }) {
  return (
    <section className="panel panel-outage" role="status" aria-labelledby="outage-title">
      <span className="panel-pulse" aria-hidden="true" />
      <div>
        <h2 id="outage-title" className="panel-title">Сбой уже чинят</h2>
        <p className="panel-text">
          Вы в списке затронутых: когда специалисты напишут про {conversation.service ?? "сервис"}, сообщение
          появится здесь. Можно просто подождать.
        </p>
      </div>
    </section>
  );
}

function minutesBetween(from?: string | null, to?: string | null): number | null {
  if (!from || !to) return null;
  return (new Date(to).getTime() - new Date(from).getTime()) / 60000;
}

export function ResolvedPanel({
  conversation,
  onRate,
  onRestart,
}: {
  conversation: Conversation;
  onRate: (rating: number, comment?: string) => Promise<void>;
  onRestart: () => void;
}) {
  const [hover, setHover] = useState(0);
  const [picked, setPicked] = useState(0);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const byOperator = conversation.resolved_by === "operator";
  const took = minutesBetween(conversation.created_at, conversation.resolved_at);
  const rated = conversation.rating ?? null;

  const submit = async () => {
    if (!picked) return;
    setBusy(true);
    await onRate(picked, comment.trim() || undefined);
    setBusy(false);
  };

  return (
    <section className="panel panel-resolved" aria-labelledby="resolved-title">
      <h2 id="resolved-title" className="panel-title">Готово, проблема решена</h2>
      <p className="panel-text">
        {byOperator && conversation.assignee_name ? `Решено со специалистом: ${conversation.assignee_name}` : "Справились вместе с помощником, без ожидания специалиста"}
        {took != null ? `. Заняло ${formatMinutes(took)}.` : "."}
      </p>

      {rated ? (
        <p className="panel-thanks">Спасибо за оценку: {rated} из 5.</p>
      ) : (
        <div className="rating">
          <p className="rating-question" id="rating-label">Насколько удобно было решать?</p>
          <div className="rating-stars" role="radiogroup" aria-labelledby="rating-label" onMouseLeave={() => setHover(0)}>
            {[1, 2, 3, 4, 5].map((value) => (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={picked === value}
                aria-label={`${value} из 5`}
                className={`rating-star ${(hover || picked) >= value ? "rating-star-on" : ""}`}
                onMouseEnter={() => setHover(value)}
                onClick={() => setPicked(value)}
              >
                <svg viewBox="0 0 24 24" width="34" height="34" aria-hidden="true">
                  <path d="M12 3.5l2.6 5.3 5.9.9-4.3 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.3-4.1 5.9-.9L12 3.5Z" />
                </svg>
              </button>
            ))}
          </div>
          {picked ? (
            <div className="rating-extra">
              <label htmlFor="rating-comment" className="visually-hidden">Комментарий</label>
              <input
                id="rating-comment"
                className="rating-comment"
                placeholder={picked <= 3 ? "Что было неудобно?" : "Пара слов, если хочется"}
                value={comment}
                maxLength={1000}
                onChange={(event) => setComment(event.target.value)}
              />
              <Button variant="primary" busy={busy} onClick={() => void submit()}>Отправить оценку</Button>
            </div>
          ) : null}
        </div>
      )}

      <div className="panel-actions">
        <Button variant="secondary" onClick={onRestart}>Новое обращение</Button>
      </div>
    </section>
  );
}
