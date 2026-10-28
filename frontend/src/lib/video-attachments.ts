import { parseKnowledgeVideo, type KnowledgeVideoPresentation } from "@/lib/product-presentations";

export type VideoAttachmentJob = {
  attachment_id: string;
  status: "queued" | "processing" | "ready" | "failed" | "cancelled" | "expired";
  phase: string;
  message: string;
  presentation: KnowledgeVideoPresentation | null;
};
export function parseVideoAttachmentJob(value: unknown): VideoAttachmentJob {
  if (!value || typeof value !== "object" || !("attachment_id" in value) || typeof value.attachment_id !== "string" || !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(value.attachment_id) || !("status" in value)) throw new Error("Invalid video job");
  const status = value.status;
  if (status !== "queued" && status !== "processing" && status !== "ready" && status !== "failed" && status !== "cancelled" && status !== "expired") throw new Error("Invalid video status");
  const presentation = "presentation" in value ? parseKnowledgeVideo(value.presentation) : null;
  if (status === "ready" && !presentation) throw new Error("Invalid video evidence");
  return { attachment_id: value.attachment_id, status, phase: "phase" in value && typeof value.phase === "string" ? value.phase : "", message: "message" in value && typeof value.message === "string" ? value.message : "", presentation };
}
export function videoUploadIssue(file: Pick<File, "name" | "size" | "type">): "type" | "size" | null {
  if (!/\.(mp4|mov|webm)$/i.test(file.name) || (file.type && !["video/mp4", "video/quicktime", "video/webm"].includes(file.type))) return "type";
  return file.size === 0 || file.size > 50 * 1024 * 1024 ? "size" : null;
}
