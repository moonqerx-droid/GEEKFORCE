import { useEffect, useState, type FormEvent } from "react";
import { Button } from "../../components/Button";
import { operatorApi, type ReplyTemplate } from "../operator/operatorApi";

const MAX_TITLE = 120;
const MAX_BODY = 4000;

/** The support lead keeps ready-made replies; specialists insert them from the ticket. */
export function AdminTemplates() {
  const [templates, setTemplates] = useState<ReplyTemplate[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState<ReplyTemplate | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    operatorApi.listTemplates(controller.signal)
      .then(setTemplates)
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, []);

  const sorted = (items: ReplyTemplate[]) => [...items].sort((a, b) => a.title.localeCompare(b.title, "ru"));

  const save = async (draft: { title: string; body: string }) => {
    setProblem(null);
    try {
      const saved = editing
        ? await operatorApi.updateTemplate(editing.id, draft)
        : await operatorApi.createTemplate(draft);
      setTemplates((items) => sorted([saved, ...(items ?? []).filter((item) => item.id !== saved.id)]));
      setEditing(null);
      return true;
    } catch {
      setProblem("Не получилось сохранить шаблон. Попробуйте ещё раз.");
      return false;
    }
  };

  const remove = async (item: ReplyTemplate) => {
    setProblem(null);
    try {
      await operatorApi.deleteTemplate(item.id);
      setTemplates((items) => (items ?? []).filter((other) => other.id !== item.id));
      setConfirmId(null);
      if (editing?.id === item.id) setEditing(null);
    } catch {
      setProblem("Не получилось удалить шаблон. Попробуйте ещё раз.");
    }
  };

  return (
    <section className="admin-block admin-block-wide tpl" aria-labelledby="tpl-title">
      <h2 id="tpl-title">Шаблоны ответов</h2>
      <p className="admin-note">
        Готовые ответы для специалистов: в окне обращения они вставляют шаблон кнопкой «Шаблоны» и правят перед
        отправкой. {"{имя}"} заменится на имя сотрудника.
      </p>

      {failed ? <p className="tpl-problem" role="alert">Не удалось загрузить шаблоны.</p> : null}
      {templates && !templates.length ? (
        <p className="admin-note">Шаблонов пока нет. Начните с ответов, которые команда пишет чаще всего.</p>
      ) : null}
      {templates && templates.length ? (
        <ul className="tpl-list">
          {templates.map((item) => (
            <li key={item.id} className={item.id === editing?.id ? "tpl-item tpl-item-editing" : "tpl-item"}>
              <div className="tpl-item-text">
                <span className="tpl-item-title">{item.title}</span>
                <span className="tpl-item-body">{item.body}</span>
              </div>
              {confirmId === item.id ? (
                <div className="tpl-item-actions">
                  <span className="tpl-confirm">Удалить шаблон?</span>
                  <Button variant="ghost" onClick={() => setConfirmId(null)}>Отмена</Button>
                  <Button variant="danger" onClick={() => void remove(item)}>Да, удалить</Button>
                </div>
              ) : (
                <div className="tpl-item-actions">
                  <Button variant="ghost" aria-label={`Изменить «${item.title}»`} onClick={() => setEditing(item)}>Изменить</Button>
                  <Button variant="ghost" aria-label={`Удалить «${item.title}»`} onClick={() => setConfirmId(item.id)}>Удалить</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : null}

      <TemplateForm key={editing?.id ?? "new"} template={editing} onSave={save} onCancel={() => setEditing(null)} />
      {problem ? <p className="tpl-problem" role="alert">{problem}</p> : null}
    </section>
  );
}

function TemplateForm({ template, onSave, onCancel }: {
  template: ReplyTemplate | null;
  onSave: (draft: { title: string; body: string }) => Promise<boolean>;
  onCancel: () => void;
}) {
  const [title, setTitle] = useState(template?.title ?? "");
  const [body, setBody] = useState(template?.body ?? "");
  const [busy, setBusy] = useState(false);
  const ready = Boolean(title.trim() && body.trim());

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setBusy(true);
    const saved = await onSave({ title: title.trim(), body: body.trim() });
    setBusy(false);
    if (saved && !template) {
      setTitle("");
      setBody("");
    }
  };

  return (
    <form className="tpl-form" onSubmit={(event) => void submit(event)}>
      <h3>{template ? `Изменить «${template.title}»` : "Новый шаблон"}</h3>
      <label className="tpl-field">
        <span>Название</span>
        <input className="field-input" value={title} maxLength={MAX_TITLE} onChange={(event) => setTitle(event.target.value)}
          placeholder="Например: Сброс сессии CRM" />
      </label>
      <label className="tpl-field">
        <span>Текст ответа</span>
        <textarea className="field-input" rows={3} value={body} maxLength={MAX_BODY} onChange={(event) => setBody(event.target.value)}
          placeholder="{имя}, сбросила зависшую сессию. Попробуйте войти ещё раз." />
      </label>
      <div className="tpl-form-actions">
        {template ? <Button type="button" variant="ghost" onClick={onCancel}>Отмена</Button> : null}
        <Button type="submit" variant="primary" busy={busy} disabled={!ready}>
          {template ? "Сохранить" : "Добавить шаблон"}
        </Button>
      </div>
    </form>
  );
}
