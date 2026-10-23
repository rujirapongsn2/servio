export type FileMediaKind = "document" | "image" | "audio" | "archive";
export type MediaCapability = { status: "ready" } | { status: "disabled" } | { status: "unavailable"; reason: string; retryable: boolean };
export interface ImportCapabilities {
  documents: { status: "ready" };
  images: MediaCapability;
  audio: MediaCapability;
  image_ocr: { status: "configured" | "not_configured" | "disabled" };
}
export type CapabilitiesState = { status: "loading" } | { status: "unknown" } | { status: "loaded"; value: ImportCapabilities };

export const FILE_EXTENSIONS = {
  document: ".pdf,.docx,.xlsx,.pptx,.txt,.md,.markdown,.csv,.tsv,.json,.html,.htm",
  image: ".jpg,.jpeg,.png",
  audio: ".wav,.mp3",
  archive: ".zip,.tar,.gz,.tgz",
} satisfies Record<FileMediaKind, string>;

export function fileMediaKind(name: string): FileMediaKind | null {
  const extension = "." + name.split(".").pop()?.toLowerCase();
  for (const kind of ["document", "image", "audio", "archive"] satisfies FileMediaKind[]) {
    if (FILE_EXTENSIONS[kind].split(",").includes(extension)) return kind;
  }
  return null;
}

function mediaCapability(value: unknown): MediaCapability {
  if (!value || typeof value !== "object" || !("status" in value)) throw new Error("Invalid media readiness");
  if (value.status === "ready" || value.status === "disabled") return { status: value.status };
  if (value.status === "unavailable" && "reason" in value && typeof value.reason === "string" && "retryable" in value && typeof value.retryable === "boolean") {
    return { status: "unavailable", reason: value.reason, retryable: value.retryable };
  }
  throw new Error("Invalid media readiness");
}

export function parseCapabilities(value: unknown): ImportCapabilities {
  if (!value || typeof value !== "object" || !("images" in value) || !("audio" in value) || !("image_ocr" in value)) throw new Error("Invalid import readiness");
  const ocr = value.image_ocr;
  if (!ocr || typeof ocr !== "object" || !("status" in ocr) || (ocr.status !== "configured" && ocr.status !== "not_configured" && ocr.status !== "disabled")) throw new Error("Invalid OCR configuration");
  return { documents: { status: "ready" }, images: mediaCapability(value.images), audio: mediaCapability(value.audio), image_ocr: { status: ocr.status } };
}

export function fileIssue(file: File, capabilities: CapabilitiesState, archiveOnly = false): string | null {
  const kind = fileMediaKind(file.name);
  if (!kind || (archiveOnly && kind !== "archive")) return "Unsupported file type";
  if (file.size > (kind === "image" ? 10 : 50) * 1024 * 1024) return `Exceeds ${kind === "image" ? 10 : 50} MB limit`;
  if (kind === "image" || kind === "audio") {
    if (capabilities.status !== "loaded") return "Media readiness has not been confirmed";
    const capability = kind === "image" ? capabilities.value.images : capabilities.value.audio;
    if (capability.status === "disabled") return `${kind === "image" ? "Image" : "Audio"} import disabled`;
    if (capability.status === "unavailable") return capability.reason;
  }
  return null;
}

export function formatDuration(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const unit = bytes < 1024 * 1024 ? "KB" : "MB";
  const value = bytes / (unit === "KB" ? 1024 : 1024 * 1024);
  return `${Number(value.toFixed(1))} ${unit}`;
}
