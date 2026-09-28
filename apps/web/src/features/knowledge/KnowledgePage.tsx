import { useEffect, useState, type DragEvent } from "react";
import { api, ApiError, ConflictError, NetworkError } from "../../api/client";
import type { KnowledgeDocument, KnowledgeDocumentDetail, KnowledgeStatus } from "../../api/types";
import { Button } from "../../components/Button";
import { EmptyState, ErrorState, Spinner } from "../../components/primitives";
import { formatSize } from "../../lib/files";
import { formatDateTime, plural } from "../../lib/labels";
import "./Knowledge.css";

/** Mirrors the backend limits in apps/api/app/services/knowledge.py. */
const MAX_BYTES = 10 * 1024 * 1024;
const EXTENSIONS = new Set(["pdf", "docx", "txt", "md"]);
const ACCEPT = ".pdf,.docx,.txt,.md";
const POLL_MS = 3000;

const STATUS_LABEL: Record<KnowledgeStatus, string> = {
  processing: "Обрабатывается",
  ready: "Готов",
  failed: "Ошибка",
};

type Notice = { tone: "done" | "problem"; text: string } | null;

function extensionOf(name: string): string {
  return name.includes(".") ? name.split(".").pop()!.toLowerCase() : "";
}

function formatLabel(document: KnowledgeDocument): string {
  return extensionOf(document.original_filename).toUpperCase() || document.media_type;
}

function localProblem(file: File): string | null {
  if (!EXTENSIONS.has(extensionOf(file.name))) return "Подходят PDF, DOCX, TXT и Markdown.";
  if (file.size > MAX_BYTES) return "Файл больше 10 МБ.";
  if (!file.size) return "Файл пустой.";
  return null;
}

function refusal(error: unknown, documents: KnowledgeDocument[]): string {
  if (error instanceof ConflictError) {
    const detail = error.detail as { document_id?: string } | undefined;
    const existing = documents.find((item) => item.id === detail?.document_id);
    return existing ? `Такой документ уже загружен: «${existing.title}».` : "Такой документ уже загружен.";
  }
  if (error instanceof ApiError) {
    if (typeof error.detail === "string" && error.detail) return error.detail;
    if (error.status === 413) return "Файл больше 10 МБ.";
    if (error.status === 415) return "Подходят PDF, DOCX, TXT и Markdown.";
  }
  if (error instanceof NetworkError) return "Нет связи с сервером. Проверьте соединение и загрузите ещё раз.";
  return "Не получилось загрузить документ. Попробуйте ещё раз.";
}

export function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const processing = Boolean(documents?.some((item) => item.status === "processing"));

  useEffect(() => {
    const controller = new AbortController();
    const load = () => api.listKnowledgeDocuments(controller.signal)
      .then((items) => { setDocuments(items); setFailed(false); })
      .catch(() => { if (!controller.signal.aborted) setFailed(true); });
    void load();
    // Keep asking only while something is still being processed.
    const timer = processing ? window.setInterval(() => void load(), POLL_MS) : undefined;
    return () => {
      controller.abort();
      if (timer) window.clearInterval(timer);
    };
  }, [attempt, processing]);

  const upload = async (files: File[]) => {
    const current = documents ?? [];
    for (const file of files) {
      const problem = localProblem(file);
      if (problem) {
        setNotice({ tone: "problem", text: `${file.name}: ${problem}` });
        continue;
      }
      setUploading(true);
      setNotice(null);
      try {
        const document = await api.uploadKnowledgeDocument(file);
        setDocuments((items) => [document, ...(items ?? []).filter((item) => item.id !== document.id)]);
        setNotice(document.status === "failed"
          ? { tone: "problem", text: `Документ «${document.title}» не прочитан: ${document.error_message ?? "неизвестная ошибка"}` }
          : { tone: "done", text: document.status === "ready"
            ? `Документ «${document.title}» готов: помощник уже отвечает по нему.`
            : `Документ «${document.title}» обрабатывается.` });
      } catch (error) {
        setNotice({ tone: "problem", text: refusal(error, current) });
      } finally {
        setUploading(false);
      }
    }
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    void upload(Array.from(event.dataTransfer.files));
  };

  const ready = documents?.filter((item) => item.status === "ready") ?? [];
  const open = documents?.find((item) => item.id === openId) ?? null;

  return (
    <div className="kb">
      <header className="kb-head">
        <div>
          <h1 className="kb-title">База знаний</h1>
          <p className="kb-sub">
            Правила и инструкции компании. По готовым документам помощник отвечает сотрудникам с цитатой
            из текста; вопросы о правилах, которых нет в документах, уходят специалисту.
          </p>
        </div>
        {documents ? (
          <dl className="kb-counts">
            <div><dt>Документов</dt><dd className="num">{documents.length}</dd></div>
            <div><dt>Готовы</dt><dd className="num">{ready.length}</dd></div>
            <div><dt>Фрагментов</dt><dd className="num">{ready.reduce((sum, item) => sum + item.chunk_count, 0)}</dd></div>
          </dl>
        ) : null}
      </header>

      <div
        className={`kb-drop ${dragging ? "kb-drop-over" : ""}`}
        onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <div className="kb-drop-text">
          <h2>Новый документ</h2>
          <p>Перетащите файл сюда или выберите на компьютере. PDF, DOCX, TXT или Markdown, до 10 МБ. Сканы без текстового слоя не читаются.</p>
        </div>
        <input
          id="kb-file"
          type="file"
          className="visually-hidden"
          accept={ACCEPT}
          aria-label="Выбрать файл"
          disabled={uploading}
          onChange={(event) => {
            const files = Array.from(event.target.files ?? []);
            event.target.value = "";
            void upload(files);
          }}
        />
        <label className="kb-pick" htmlFor="kb-file">
          {uploading ? "Загружаем…" : "Выбрать файл"}
        </label>
      </div>

      {notice ? (
        <p className={`kb-notice kb-notice-${notice.tone}`} role={notice.tone === "problem" ? "alert" : "status"}>
          {notice.text}
        </p>
      ) : null}

      <section aria-labelledby="kb-list-title">
        <h2 id="kb-list-title" className="visually-hidden">Документы</h2>
        {!documents && !failed ? <div className="kb-state"><Spinner label="Загружаем документы…" /></div> : null}
        {failed && !documents ? (
          <ErrorState title="Не удалось загрузить документы" description="Проверьте соединение с сервером."
            onRetry={() => { setFailed(false); setAttempt((n) => n + 1); }} />
        ) : null}
        {documents && !documents.length ? (
          <EmptyState
            title="Документов пока нет"
            description="Загрузите регламент или инструкцию: помощник начнёт отвечать по ним с цитатой из документа."
          />
        ) : null}
        {documents && documents.length ? (
          <table className="kb-table" aria-label="Документы">
            <thead>
              <tr>
                <th scope="col">Документ</th>
                <th scope="col">Формат</th>
                <th scope="col">Размер</th>
                <th scope="col">Статус</th>
                <th scope="col">Загружен</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((item) => (
                <tr key={item.id} className={item.id === openId ? "kb-row-open" : ""}>
                  <td data-label="Документ">
                    <button type="button" className="kb-doc" onClick={() => setOpenId(item.id)}>
                      <span className="kb-doc-title">{item.title}</span>
                      <span className="kb-doc-file">{item.original_filename}</span>
                    </button>
                  </td>
                  <td data-label="Формат">{formatLabel(item)}</td>
                  <td data-label="Размер" className="num">{formatSize(item.size_bytes)}</td>
                  <td data-label="Статус">
                    <span className={`kb-status kb-status-${item.status}`}>{STATUS_LABEL[item.status]}</span>
                    {item.status === "failed" && item.error_message ? <span className="kb-reason">{item.error_message}</span> : null}
                  </td>
                  <td data-label="Загружен" className="kb-when">
                    {formatDateTime(item.created_at)}
                    {item.uploaded_by_name ? <span className="kb-author">{item.uploaded_by_name}</span> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </section>

      {open ? (
        <DocumentPanel
          key={open.id}
          document={open}
          onClose={() => setOpenId(null)}
          onDeleted={() => {
            setDocuments((items) => (items ?? []).filter((item) => item.id !== open.id));
            setOpenId(null);
            setNotice({ tone: "done", text: `Документ «${open.title}» удалён: помощник больше не отвечает по нему.` });
          }}
        />
      ) : null}
    </div>
  );
}

function DocumentPanel({ document, onClose, onDeleted }: {
  document: KnowledgeDocument;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [detail, setDetail] = useState<KnowledgeDocumentDetail | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api.getKnowledgeDocument(document.id, controller.signal)
      .then(setDetail)
      .catch(() => { if (!controller.signal.aborted) setLoadFailed(true); });
    return () => controller.abort();
  }, [document.id, document.revision]);

  const remove = async () => {
    setDeleting(true);
    setProblem(null);
    try {
      await api.deleteKnowledgeDocument(document.id);
      onDeleted();
    } catch {
      setProblem("Не получилось удалить. Попробуйте ещё раз.");
      setDeleting(false);
    }
  };

  const chunks = detail?.chunks ?? [];

  return (
    <section className="kb-panel" aria-label={`Документ «${document.title}»`}>
      <header className="kb-panel-head">
        <div>
          <h2>{document.title}</h2>
          <p>
            {document.original_filename}, {formatSize(document.size_bytes)}
            {document.status === "ready"
              ? `, ${document.chunk_count} ${plural(document.chunk_count, "фрагмент", "фрагмента", "фрагментов")} текста`
              : ""}
          </p>
        </div>
        <Button variant="ghost" onClick={onClose}>Закрыть</Button>
      </header>

      {document.status === "failed" ? (
        <p className="kb-notice kb-notice-problem">Текст не извлечён: {document.error_message}</p>
      ) : null}

      {!detail && !loadFailed ? <Spinner label="Открываем документ…" /> : null}
      {loadFailed ? <p className="kb-notice kb-notice-problem">Не удалось открыть документ.</p> : null}
      {chunks.length ? (
        <ol className="kb-chunks">
          {chunks.map((chunk) => (
            <li key={chunk.id}>
              {chunk.metadata.heading ? <span className="kb-chunk-heading">{chunk.metadata.heading}</span> : null}
              <p className="kb-chunk-text">{chunk.text}</p>
            </li>
          ))}
        </ol>
      ) : null}

      <footer className="kb-panel-foot">
        {confirming ? (
          <div className="kb-confirm">
            <p>Удалить «{document.title}»? Помощник перестанет отвечать по этому документу.</p>
            <div className="kb-confirm-actions">
              <Button variant="ghost" disabled={deleting} onClick={() => setConfirming(false)}>Отмена</Button>
              <Button variant="danger" busy={deleting} onClick={() => void remove()}>Да, удалить</Button>
            </div>
          </div>
        ) : (
          <Button variant="secondary" onClick={() => setConfirming(true)}>Удалить документ</Button>
        )}
        {problem ? <p className="kb-notice kb-notice-problem" role="alert">{problem}</p> : null}
      </footer>
    </section>
  );
}
