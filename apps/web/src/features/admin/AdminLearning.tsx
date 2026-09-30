import { useEffect, useState } from "react";
import { request } from "../../api/client";
import { Button } from "../../components/Button";
import { formatAgo } from "../../lib/labels";

/** Mirrors LearningSuggestionRead / LearnedStepRead in apps/api/app/api/routes/admin.py. */
interface Suggestion {
  conversation_id: string;
  playbook_id: string;
  playbook_title: string;
  request: string;
  resolution: string;
  specialist: string | null;
  resolved_at: string | null;
}

interface LearnedStep {
  id: string;
  playbook_id: string;
  playbook_title: string;
  instruction: string;
  source_resolution: string | null;
  created_at: string;
}

const learningApi = {
  overview: (signal?: AbortSignal): Promise<{ suggestions: Suggestion[]; steps: LearnedStep[] }> =>
    request("/api/admin/learning", {}, signal),
  add: (payload: { playbook_id: string; instruction: string; source_conversation_id: string }): Promise<LearnedStep> =>
    request("/api/admin/learning/steps", { method: "POST", body: JSON.stringify(payload) }),
  remove: (id: string): Promise<void> => request(`/api/admin/learning/steps/${id}`, { method: "DELETE" }),
};

/**
 * Closed requests teach the assistant. What a specialist did becomes a scenario step once the lead
 * rewrites it for an employee: the next person with the same problem tries it before waiting.
 */
export function AdminLearning() {
  const [data, setData] = useState<{ suggestions: Suggestion[]; steps: LearnedStep[] } | null>(null);
  const [failed, setFailed] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    learningApi.overview(controller.signal).then(setData)
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, []);

  const approve = async (suggestion: Suggestion, instruction: string) => {
    setProblem(null);
    try {
      const step = await learningApi.add({
        playbook_id: suggestion.playbook_id, instruction, source_conversation_id: suggestion.conversation_id,
      });
      setData((current) => current && {
        suggestions: current.suggestions.filter((item) => item.conversation_id !== suggestion.conversation_id),
        steps: [step, ...current.steps],
      });
      return true;
    } catch {
      setProblem("Не получилось добавить шаг. Опишите действие для сотрудника: от 10 до 600 символов.");
      return false;
    }
  };

  const remove = async (step: LearnedStep) => {
    setProblem(null);
    try {
      await learningApi.remove(step.id);
      setData((current) => current && { ...current, steps: current.steps.filter((item) => item.id !== step.id) });
    } catch {
      setProblem("Не получилось убрать шаг. Попробуйте ещё раз.");
    }
  };

  return (
    <section className="admin-block admin-block-wide tpl learn" aria-labelledby="learn-title">
      <h2 id="learn-title">Обучение на закрытых обращениях</h2>
      <p className="admin-note">
        Здесь итоги специалистов из закрытых обращений. Перепишите итог как шаг, который сотрудник может сделать
        сам, — помощник предложит его следующему с той же проблемой до передачи специалисту. Эффект виден в «Темах»
        выше: доля переданных специалистам по теме снижается.
      </p>
      {failed ? <p className="tpl-problem" role="alert">Не удалось загрузить итоги обращений.</p> : null}

      {data && data.steps.length ? (
        <>
          <h3 className="learn-subtitle">Помощник уже предлагает</h3>
          <ul className="tpl-list">
            {data.steps.map((step) => (
              <li key={step.id} className="tpl-item">
                <div className="tpl-item-text">
                  <span className="tpl-item-title">{step.playbook_title}</span>
                  <span className="tpl-item-body">{step.instruction}</span>
                  {step.source_resolution ? (
                    <span className="learn-source">Из итога специалиста: «{step.source_resolution}»</span>
                  ) : null}
                </div>
                <div className="tpl-item-actions">
                  <Button variant="ghost" aria-label={`Убрать шаг для «${step.playbook_title}»`}
                    onClick={() => void remove(step)}>Убрать</Button>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {data ? (
        <>
          <h3 className="learn-subtitle">Итоги, которые можно превратить в шаг</h3>
          {data.suggestions.length ? (
            <ul className="tpl-list">
              {data.suggestions.map((suggestion) => (
                <SuggestionItem key={suggestion.conversation_id} suggestion={suggestion} onApprove={approve} />
              ))}
            </ul>
          ) : (
            <p className="admin-note">Новых итогов нет: они появятся, когда специалисты закроют обращения.</p>
          )}
        </>
      ) : null}
      {problem ? <p className="tpl-problem" role="alert">{problem}</p> : null}
    </section>
  );
}

function SuggestionItem({ suggestion, onApprove }: {
  suggestion: Suggestion;
  onApprove: (suggestion: Suggestion, instruction: string) => Promise<boolean>;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(suggestion.resolution);
  const [busy, setBusy] = useState(false);
  const meta = [suggestion.specialist, suggestion.resolved_at ? formatAgo(suggestion.resolved_at) : null]
    .filter(Boolean).join(", ");

  return (
    <li className="tpl-item learn-item">
      <div className="tpl-item-text">
        <span className="tpl-item-title">{suggestion.playbook_title}</span>
        <span className="learn-request">Сотрудник: «{suggestion.request}»</span>
        <span className="tpl-item-body">
          Итог{meta ? ` (${meta})` : ""}: «{suggestion.resolution}»
        </span>
        {editing ? (
          <label className="tpl-field learn-edit">
            <span>Шаг для сотрудника — что сделать самому</span>
            <textarea className="field-input" rows={3} maxLength={600} value={text}
              onChange={(event) => setText(event.target.value)} />
          </label>
        ) : null}
      </div>
      <div className="tpl-item-actions">
        {editing ? (
          <>
            <Button variant="ghost" onClick={() => setEditing(false)}>Отмена</Button>
            <Button variant="primary" busy={busy} disabled={text.trim().length < 10} onClick={() => {
              setBusy(true);
              void onApprove(suggestion, text.trim()).then((ok) => { setBusy(false); if (ok) setEditing(false); });
            }}>Добавить в сценарий</Button>
          </>
        ) : (
          <Button variant="secondary" onClick={() => setEditing(true)}>Сделать шагом</Button>
        )}
      </div>
    </li>
  );
}
