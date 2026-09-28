import {
  useEffect,
  useId,
  useRef,
  useState,
  type ClipboardEvent,
  type Dispatch,
  type FormEvent,
  type KeyboardEvent,
  type RefObject,
  type SetStateAction,
} from "react";
import { FileText, Paperclip, SendHorizontal, X } from "lucide-react";
import { ACCEPT, acceptFiles, formatSize, releasePreview, type PickedFile } from "../../lib/files";
import "./Composer.css";

/**
 * The message box. With `allowFiles` it also takes screenshots and documents: via the
 * paperclip, pasted from the clipboard, or dropped anywhere on `dropTarget`.
 * Text and files stay put when sending fails, so nothing typed or picked is lost.
 */
export function Composer({
  busy,
  placeholder,
  onSend,
  value,
  onValueChange,
  tone = "assistant",
  label = "Ваше сообщение",
  allowFiles = false,
  size = "regular",
  dropTarget,
  autoFocus = false,
  hint = "Скриншот ошибки часто ускоряет решение: прикрепите его, перетащите сюда или вставьте через ⌘V / Ctrl+V.",
}: {
  hint?: string;
  busy: boolean;
  placeholder: string;
  onSend: (content: string, files: File[]) => Promise<void>;
  value: string;
  onValueChange: Dispatch<SetStateAction<string>>;
  tone?: "assistant" | "human";
  label?: string;
  allowFiles?: boolean;
  size?: "regular" | "large";
  dropTarget?: RefObject<HTMLElement | null>;
  autoFocus?: boolean;
}) {
  const inputId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [problems, setProblems] = useState<string[]>([]);
  const filesRef = useRef(files);
  filesRef.current = files;

  const add = (incoming: File[]) => {
    if (!incoming.length) return;
    const result = acceptFiles(filesRef.current, incoming);
    setFiles(result.files);
    setProblems(result.problems);
  };

  const remove = (key: string) => {
    setFiles((current) => {
      const item = current.find((entry) => entry.key === key);
      if (item) releasePreview(item);
      return current.filter((entry) => entry.key !== key);
    });
    setProblems([]);
  };

  useEffect(() => () => filesRef.current.forEach(releasePreview), []);

  // Dropping a file anywhere on the chat is the natural gesture; show where it will land.
  useEffect(() => {
    const target = dropTarget?.current;
    if (!allowFiles || !target) return;
    let depth = 0;
    const hasFiles = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files");
    const onEnter = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      depth += 1;
      target.classList.add("is-dropping");
    };
    const onLeave = () => {
      depth = Math.max(0, depth - 1);
      if (!depth) target.classList.remove("is-dropping");
    };
    const onOver = (event: DragEvent) => { if (hasFiles(event)) event.preventDefault(); };
    const onDrop = (event: DragEvent) => {
      if (!hasFiles(event)) return;
      event.preventDefault();
      depth = 0;
      target.classList.remove("is-dropping");
      add(Array.from(event.dataTransfer?.files ?? []));
      textareaRef.current?.focus();
    };
    target.addEventListener("dragenter", onEnter);
    target.addEventListener("dragleave", onLeave);
    target.addEventListener("dragover", onOver);
    target.addEventListener("drop", onDrop);
    return () => {
      target.removeEventListener("dragenter", onEnter);
      target.removeEventListener("dragleave", onLeave);
      target.removeEventListener("dragover", onOver);
      target.removeEventListener("drop", onDrop);
    };
    // add() reads the latest files through a ref, so the listeners need not be rebound.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [allowFiles, dropTarget]);

  // Grow with the text up to a comfortable height, then scroll.
  useEffect(() => {
    const node = textareaRef.current;
    if (!node) return;
    node.style.height = "auto";
    node.style.height = `${Math.min(node.scrollHeight, size === "large" ? 240 : 180)}px`;
  }, [value, size]);

  const canSend = Boolean(value.trim() || files.length);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const trimmed = value.trim();
    if (!canSend || busy) return;
    const picked = files;
    onValueChange("");
    try {
      await onSend(trimmed, picked.map((item) => item.file));
      picked.forEach(releasePreview);
      setFiles((current) => current.filter((item) => !picked.includes(item)));
      setProblems([]);
    } catch {
      // Restore the failed draft unless the user already started the next message.
      onValueChange((current) => current.trim() ? current : trimmed);
    }
  };

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit();
    }
  };

  const onPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    if (!allowFiles) return;
    const pasted = Array.from(event.clipboardData?.files ?? []);
    if (!pasted.length) return;
    event.preventDefault();
    add(pasted);
  };

  return (
    <form className={`composer composer-${size} ${tone === "human" ? "composer-human" : ""}`} onSubmit={submit}>
      {files.length ? (
        <ul className="composer-files" aria-label="Прикреплённые файлы">
          {files.map((item) => (
            <li key={item.key} className="composer-file">
              {item.preview ? (
                <img className="composer-file-thumb" src={item.preview} alt="" />
              ) : (
                <span className="composer-file-icon" aria-hidden="true"><FileText size={18} /></span>
              )}
              <span className="composer-file-text">
                <span className="composer-file-name">{item.file.name}</span>
                <span className="composer-file-size">{formatSize(item.file.size)}</span>
              </span>
              <button type="button" className="composer-file-remove" onClick={() => remove(item.key)} aria-label={`Убрать ${item.file.name}`}>
                <X size={14} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {problems.length ? (
        <div className="composer-problems" role="alert">
          {problems.map((problem) => <p key={problem}>{problem}</p>)}
        </div>
      ) : null}
      <div className="composer-row">
        {allowFiles ? (
          <>
            <input
              id={inputId}
              className="composer-file-input"
              type="file"
              multiple
              accept={ACCEPT}
              onChange={(event) => {
                add(Array.from(event.target.files ?? []));
                event.target.value = "";
              }}
            />
            <label htmlFor={inputId} className="composer-attach" title="Фото, скриншот или файл до 10 МБ">
              <Paperclip size={19} aria-hidden="true" />
              <span className="visually-hidden">Прикрепить файлы</span>
            </label>
          </>
        ) : null}
        <textarea
          ref={textareaRef}
          className="composer-textarea"
          value={value}
          onChange={(event) => onValueChange(event.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          placeholder={placeholder}
          rows={size === "large" ? 3 : 1}
          maxLength={4000}
          aria-label={label}
          autoFocus={autoFocus}
        />
        <button
          type="submit"
          className={`composer-send ${tone === "human" ? "composer-send-human" : ""}`}
          disabled={!canSend || busy}
          aria-busy={busy || undefined}
          aria-label="Отправить"
        >
          <SendHorizontal size={19} aria-hidden="true" />
        </button>
      </div>
      {allowFiles && hint ? <p className="composer-hint">{hint}</p> : null}
    </form>
  );
}
