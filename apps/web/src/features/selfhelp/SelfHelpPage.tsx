import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { SelfHelp, SelfHelpPopular, SelfHelpStep } from "../../api/types";
import { Button } from "../../components/Button";
import { ServiceStatus } from "./ServiceStatus";
import "./SelfHelpPage.css";

function StepList({ steps, done, onToggle }: {
  steps: SelfHelpStep[];
  done: Set<string>;
  onToggle: (step: SelfHelpStep) => void;
}) {
  return (
    <ol className="help-steps">
      {steps.map((step) => (
        <li key={step.id} className={done.has(step.id) ? "help-step help-step-done" : "help-step"}>
          <label>
            <input type="checkbox" checked={done.has(step.id)} onChange={() => onToggle(step)} />
            <span className="help-step-title">{step.title}</span>
          </label>
          <p className="help-step-text">{step.instruction}</p>
        </li>
      ))}
    </ol>
  );
}

/** «Решить самому»: an error code or a problem → what to do alone, before (or instead of) a request. */
export function SelfHelpPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<SelfHelp | null>(null);
  const [popular, setPopular] = useState<SelfHelpPopular | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [done, setDone] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    const controller = new AbortController();
    api.selfHelpPopular(controller.signal).then(setPopular).catch(() => undefined);
    return () => controller.abort();
  }, []);

  async function search(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setQuery(trimmed);
    setBusy(true);
    setFailed(false);
    setDone(new Map());
    try {
      setResult(await api.selfHelp(trimmed));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  function toggle(step: SelfHelpStep) {
    setDone((prev) => {
      const next = new Map(prev);
      if (next.has(step.id)) next.delete(step.id);
      else next.set(step.id, step.title);
      return next;
    });
  }

  function openRequest(text: string) {
    const tried = [...done.values()];
    const draft = tried.length ? `${text}. Уже пробовал: ${tried.join("; ")}` : text;
    navigate(`/employee?new=1&draft=${encodeURIComponent(draft)}`);
  }

  const ids = new Set(done.keys());
  const nothing = result && !result.specialist_only && !result.code && !result.guide?.steps.length && !result.document;

  return (
    <section className="help">
      <header className="help-head">
        <h1>Решить самому</h1>
        <p>
          Код ошибки или что не работает — покажу, что значит ошибка и что можно сделать самому, без обращения.
          Не помогло — одной кнопкой создадим обращение, и специалист увидит, что вы уже пробовали.
        </p>
      </header>

      <form className="help-search" role="search" onSubmit={(event) => { event.preventDefault(); void search(query); }}>
        <input
          type="search"
          aria-label="Код ошибки или что не работает"
          placeholder="Например: 809, 0x800CCC0E или «не печатает принтер»"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button variant="primary" type="submit" busy={busy}>Найти</Button>
      </form>

      {popular ? (
        <div className="help-popular">
          <p className="help-popular-title">Частые коды ошибок</p>
          <div className="help-chips">
            {popular.codes.map((item) => (
              <button key={item.code} type="button" className="help-chip" title={item.title} onClick={() => void search(item.code)}>
                <strong>{item.code}</strong> <span>{item.title}</span>
              </button>
            ))}
          </div>
          <p className="help-popular-title">Частые проблемы</p>
          <div className="help-chips">
            {popular.topics.map((topic) => (
              <button key={topic.query} type="button" className="help-chip" onClick={() => void search(topic.query)}>
                {topic.title}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {failed ? <p className="help-alert" role="alert">Не удалось выполнить поиск. Попробуйте ещё раз.</p> : null}

      {result?.specialist_only ? (
        <article className="help-card help-card-danger">
          <h2>С этим — сразу к специалисту</h2>
          <p>{result.notice}</p>
          <Button variant="primary" onClick={() => openRequest(result.query)}>Создать обращение</Button>
        </article>
      ) : null}

      {result?.code ? (
        <article className="help-card">
          <h2>Ошибка {result.code.code} — {result.code.title}</h2>
          <p className="help-meaning">{result.code.meaning}</p>
          {result.code.steps.length ? <StepList steps={result.code.steps} done={ids} onToggle={toggle} /> : (
            <p className="help-meaning">Самому здесь ничего делать не нужно — это исправляет специалист.</p>
          )}
        </article>
      ) : null}

      {result?.document ? (
        <article className="help-card help-card-document">
          <h2>По документу «{result.document.title}»</h2>
          <p>{result.document.text}</p>
        </article>
      ) : null}

      {result?.guide?.steps.length ? (
        <article className="help-card">
          <h2>Инструкция: {result.guide.title}</h2>
          <StepList steps={result.guide.steps} done={ids} onToggle={toggle} />
        </article>
      ) : null}

      {nothing ? (
        <p className="help-empty">
          Готовой инструкции не нашлось. Опишите проблему в обращении своими словами — помощник разберётся.
        </p>
      ) : null}

      {result && !result.specialist_only ? (
        <div className="help-foot">
          <Button variant="primary" onClick={() => openRequest(result.query)}>Не помогло — создать обращение</Button>
          <span>Текст и отмеченные шаги перенесём в обращение.</span>
        </div>
      ) : null}

      <ServiceStatus onReport={(text) => navigate(`/employee?new=1&draft=${encodeURIComponent(text)}`)} />
    </section>
  );
}
