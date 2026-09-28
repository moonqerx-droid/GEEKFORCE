import { useState } from "react";
import { Download, FileSpreadsheet, FileText, File as FileIcon } from "lucide-react";
import type { Attachment } from "../../api/types";
import { Dialog } from "../../components/Dialog";
import { formatSize } from "../../lib/files";
import "./AttachmentList.css";

function iconFor(item: Attachment) {
  if (item.content_type.includes("spreadsheet")) return <FileSpreadsheet size={18} aria-hidden="true" />;
  if (item.content_type === "application/pdf" || item.content_type.startsWith("text/") || item.content_type.includes("word")) {
    return <FileText size={18} aria-hidden="true" />;
  }
  return <FileIcon size={18} aria-hidden="true" />;
}

/** Files inside a message: pictures as previews that open larger, everything else as a download. */
export function AttachmentList({ items, tone = "light" }: { items: Attachment[]; tone?: "light" | "dark" }) {
  const [open, setOpen] = useState<Attachment | null>(null);
  const images = items.filter((item) => item.kind === "image");
  const files = items.filter((item) => item.kind !== "image");

  return (
    <div className={`att att-${tone}`}>
      {images.length ? (
        <div className={`att-images att-images-${Math.min(images.length, 3)}`}>
          {images.map((item) => (
            <button key={item.id} type="button" className="att-image" onClick={() => setOpen(item)}>
              <span className="visually-hidden">Открыть </span>
              <img src={item.url} alt={item.filename} loading="lazy" />
            </button>
          ))}
        </div>
      ) : null}
      {files.map((item) => (
        <a key={item.id} className="att-file" href={item.url} download={item.filename} target="_blank" rel="noreferrer">
          <span className="att-file-icon">{iconFor(item)}</span>
          <span className="att-file-text">
            <span className="att-file-name">{item.filename}</span>
            <span className="att-file-size">{formatSize(item.size)}</span>
          </span>
          <Download size={16} aria-hidden="true" className="att-file-download" />
        </a>
      ))}
      {open ? (
        <Dialog title={open.filename} size="lg" onDismiss={() => setOpen(null)}>
          <div className="att-viewer">
            <img src={open.url} alt={open.filename} />
          </div>
          <div className="dialog-actions">
            <a className="att-viewer-link" href={open.url} download={open.filename}>Скачать</a>
            <a className="att-viewer-link" href={open.url} target="_blank" rel="noreferrer">Открыть оригинал</a>
            <button type="button" className="att-viewer-close" onClick={() => setOpen(null)} data-autofocus>Закрыть</button>
          </div>
        </Dialog>
      ) : null}
    </div>
  );
}
