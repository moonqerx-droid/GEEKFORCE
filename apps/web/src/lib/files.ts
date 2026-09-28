/** Mirrors apps/api/app/services/attachments.py so problems show before uploading. */
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_FILES = 5;
export const ACCEPT = ".png,.jpg,.jpeg,.webp,.gif,.heic,.pdf,.txt,.log,.docx,.xlsx,image/png,image/jpeg,image/webp,image/gif";
const EXTENSIONS = new Set(["png", "jpg", "jpeg", "webp", "gif", "heic", "pdf", "txt", "log", "docx", "xlsx"]);

export function fileProblem(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  // A pasted screenshot has no useful name but a real image type.
  if (!EXTENSIONS.has(extension) && !/^image\/(png|jpeg|webp|gif)$/.test(file.type)) {
    return "Такой файл прикрепить нельзя: подойдут фото, скриншоты, PDF, TXT, LOG, DOCX и XLSX";
  }
  if (file.size > MAX_FILE_BYTES) return "Файл больше 10 МБ";
  if (!file.size) return "Файл пустой";
  return null;
}

/** Clipboard screenshots arrive as "image.png"; give them a name a specialist can tell apart. */
export function namedForUpload(file: File): File {
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (EXTENSIONS.has(extension) && file.name !== "image.png") return file;
  const type = file.type.split("/")[1] ?? "png";
  const stamp = new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }).replace(":", "-");
  return new File([file], `Скриншот ${stamp}.${type === "jpeg" ? "jpg" : type}`, { type: file.type });
}

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} МБ`;
}

export interface PickedFile {
  key: string;
  file: File;
  preview: string | null;
}

let pickedCounter = 0;

/** Validate incoming files against what is already picked; returns the new list and what was refused. */
export function acceptFiles(current: PickedFile[], incoming: File[]): { files: PickedFile[]; problems: string[] } {
  const files = [...current];
  const problems: string[] = [];
  for (const raw of incoming) {
    const file = namedForUpload(raw);
    const problem = fileProblem(file);
    if (problem) {
      problems.push(`${raw.name}: ${problem}`);
      continue;
    }
    if (files.length >= MAX_FILES) {
      if (!problems.includes("Не больше 5 файлов в одном сообщении")) problems.push("Не больше 5 файлов в одном сообщении");
      continue;
    }
    files.push({ key: `f${++pickedCounter}`, file, preview: previewOf(file) });
  }
  return { files, problems };
}

/** A thumbnail URL for images; without one the tile shows a file icon instead. */
function previewOf(file: File): string | null {
  if (!file.type.startsWith("image/") || typeof URL.createObjectURL !== "function") return null;
  try {
    return URL.createObjectURL(file);
  } catch {
    return null;
  }
}

export function releasePreview(item: PickedFile) {
  if (item.preview && typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(item.preview);
}
