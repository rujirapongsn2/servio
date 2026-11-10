import { parseProductPresentations, type ProductPresentations } from "@/lib/product-presentations";
import type { TeamWorkflow, WorkflowAgentDraft } from "@/lib/team-workflow";
import { parseA2uiSnapshots, type A2uiSurfaces } from "@/lib/a2ui-discovery";
import { signedVideoUrl } from "@/lib/product-presentations";

import type { PreviewAttachment } from "@/lib/chat-inputs";
export { readPreviewAttachment } from "@/lib/chat-inputs";
export type { PreviewAttachment } from "@/lib/chat-inputs";

export type PreviewTarget = number | null;
export type PreviewSession = {
  id: string;
  targetAgentId: PreviewTarget;
  hasDrafts: boolean;
  blockedTools: string[];
  expiresAt: number;
};
export type PreviewReply = {
  status: "completed" | "unverified" | "tool_failed";
  surfaces: A2uiSurfaces;
  audioUrl: string | null;
  mediaError: string | null;
  requestId: string | null;
  response: string;
  agentName: string;
  presentations: ProductPresentations;
  toolCalls: unknown[];
  citations: unknown[];
};
export type PreviewMessage = { kind: "user"; content: string; attachments?: PreviewAttachment[] } | { kind: "assistant"; reply: PreviewReply };
export type PreviewConversation = {
  session: PreviewSession | null;
  signature: string | null;
  messages: PreviewMessage[];
  composer: string;
  error: string | null;
  phase: "idle" | "busy" | "pending" | "expired";
  attachments: PreviewAttachment[];
  speak: boolean;
  imageSearch: boolean;
  pendingRequestId: string | null;
};

export function createPreviewConversation(): PreviewConversation {
  return { session: null, signature: null, messages: [], composer: "", error: null, phase: "idle", attachments: [], speak: false, imageSearch: true, pendingRequestId: null };
}
export function previewTargetKey(teamId: number, target: PreviewTarget): string {
  return `${teamId}:${target === null ? "team" : target}`;
}
export function previewDrafts(workflow: TeamWorkflow, drafts: Record<number, WorkflowAgentDraft>) {
  return workflow.agents.filter(agent => drafts[agent.id]).sort((a, b) => a.id - b.id)
    .map(agent => {
      const draft = drafts[agent.id];
      return { agent_id: agent.id, draft: {
        name: draft.name, instructions: draft.instructions, model: draft.model,
        llm_provider_id: draft.llm_provider_id, tool_ids: [...draft.tool_ids],
        handoff_agent_ids: [...draft.handoff_agent_ids], is_fallback: draft.is_fallback,
      } };
    });
}
export function previewSignature(workflow: TeamWorkflow, drafts: Record<number, WorkflowAgentDraft>): string {
  return JSON.stringify({ agents: [...workflow.agents].sort((a, b) => a.id - b.id), fallback: workflow.fallback_agent_id, model: workflow.default_agent_model, drafts: previewDrafts(workflow, drafts) });
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
export function parsePreviewSession(value: unknown, now = Date.now()): PreviewSession {
  if (!isRecord(value) || typeof value.id !== "string" || !value.id ||
    !(value.target_agent_id === null || typeof value.target_agent_id === "number" && Number.isSafeInteger(value.target_agent_id) && value.target_agent_id > 0) ||
    typeof value.has_drafts !== "boolean" || !Array.isArray(value.blocked_tools) || !value.blocked_tools.every((tool): tool is string => typeof tool === "string") ||
    typeof value.expires_in_seconds !== "number" || !Number.isFinite(value.expires_in_seconds) || value.expires_in_seconds <= 0) {
    throw new Error("Invalid preview session. Restart the preview.");
  }
  return { id: value.id, targetAgentId: value.target_agent_id, hasDrafts: value.has_drafts, blockedTools: value.blocked_tools, expiresAt: now + value.expires_in_seconds * 1000 };
}
export function parsePreviewReply(value: unknown): PreviewReply {
  if (!isRecord(value) || typeof value.response !== "string" || typeof value.agent_name !== "string" ||
    !Array.isArray(value.tool_calls) || !Array.isArray(value.citations) ||
    !(value.status === undefined || value.status === "completed" || value.status === "unverified" || value.status === "tool_failed")) throw new Error("Invalid preview response. Restart before sending again.");
  return { status: value.status ?? "completed", response: value.response, agentName: value.agent_name, presentations: parseProductPresentations(value.presentations), toolCalls: value.tool_calls, citations: value.citations,
    surfaces: parseA2uiSnapshots(value.a2ui), audioUrl: signedVideoUrl(value.audio_url) ? value.audio_url : null,
    mediaError: typeof value.media_error === "string" ? value.media_error : null,
    requestId: typeof value.request_id === "string" ? value.request_id : null };
}

export function previewError(error: unknown): { message: string; expired: boolean } {
  const message = error instanceof Error ? error.message : "Preview failed. Try again.";
  const expired = /expir|not found|no longer|invalid preview|restart/i.test(message);
  return { message: expired ? `${message} Restart the preview to continue.` : message, expired };
}
export function previewProductInquiry(presentations: ProductPresentations, callId: string, productId: string): string | null {
  const presentation = presentations[callId];
  if (!presentation || !(presentation.type === "product_carousel" || presentation.type === "knowledge_product_carousel")) return null;
  const product = presentation.products.find(item => item.id === productId);
  return product ? `Tell me more about ${product.title}${product.part_number ? ` (${product.part_number})` : ""}.` : null;
}
