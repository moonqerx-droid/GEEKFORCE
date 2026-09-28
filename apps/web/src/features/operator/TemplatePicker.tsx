import { useEffect, useMemo, useRef, useState } from "react";
import { operatorApi, type ReplyTemplate } from "./operatorApi";

/** "Шаблоны": search the support lead's templates and put one into the reply box. */
export function TemplatePicker({ onPick }: { onPick: (template: ReplyTemplate) => void }) {
  const [open, setOpen] = useState(false);
  const [templates, setTemplates] = useState<ReplyTemplate[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    operatorApi.listTemplates(controller.signal)
      .then((items) => { setTemplates(items); setFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      controller.abort();
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return (templates ?? []).filter((item) => !needle
      || item.title.toLowerCase().includes(needle) || item.body.toLowerCase().includes(needle));
  }, [templates, query]);

  return (
    <div className="templates" ref={rootRef}>
      <button type="button" className="templates-toggle" aria-expanded={open} aria-haspopup="dialog"
        onClick={() => { setOpen((value) => !value); setQuery(""); }}>
        Шаблоны
      </button>
      {open ? (
        <div className="templates-panel" role="dialog" aria-label="Шаблоны ответов">
          <label className="visually-hidden" htmlFor="templates-search">Найти шаблон</label>
          <input id="templates-search" className="field-input templates-search" type="search" autoFocus
            placeholder="Найти по названию или тексту" value={query} onChange={(event) => setQuery(event.target.value)} />
          {failed ? <p className="templates-note">Не удалось загрузить шаблоны. Попробуйте ещё раз.</p> : null}
          {templates && !templates.length ? (
            <p className="templates-note">Шаблонов пока нет: их добавляет руководитель поддержки.</p>
          ) : null}
          {templates && templates.length && !visible.length ? <p className="templates-note">Ничего не нашлось.</p> : null}
          {visible.length ? (
            <ul className="templates-list">
              {visible.map((item) => (
                <li key={item.id}>
                  <button type="button" className="templates-item" onClick={() => { onPick(item); setOpen(false); }}>
                    <span className="templates-item-title">{item.title}</span>
                    <span className="templates-item-body">{item.body}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
