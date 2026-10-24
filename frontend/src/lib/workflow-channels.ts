export interface WorkflowWebChat {
  id: number;
  name: string;
  slug: string;
  key: string;
}

export function parseWorkflowWebChats(value: unknown, teamId: number, now = Date.now()): WorkflowWebChat[] {
  if (!Array.isArray(value)) throw Error("Unable to read Web Chat channels.");
  return value.flatMap((item: unknown) => {
    if (!item || typeof item !== "object" || !("team_agent_id" in item) || item.team_agent_id !== teamId ||
      !("channel_type" in item) || item.channel_type !== "web_widget" ||
      !("is_active" in item) || item.is_active !== true) return [];
    if ("expires_at" in item && item.expires_at !== null && item.expires_at !== undefined) {
      if (typeof item.expires_at !== "string") return [];
      const timestamp = /(?:Z|[+-]\d\d:\d\d)$/.test(item.expires_at) ? item.expires_at : `${item.expires_at}Z`;
      if (!Number.isFinite(Date.parse(timestamp)) || Date.parse(timestamp) <= now) return [];
    }
    if (!("id" in item) || typeof item.id !== "number" || !Number.isSafeInteger(item.id) || item.id <= 0 ||
      !("name" in item) || typeof item.name !== "string" ||
      !("slug" in item) || typeof item.slug !== "string" || !/^[a-zA-Z0-9_-]+$/.test(item.slug) ||
      !("key" in item) || typeof item.key !== "string" || !/^[a-zA-Z0-9_-]+$/.test(item.key)) return [];
    return [{ id: item.id, name: item.name, slug: item.slug, key: item.key }];
  });
}

export function workflowChatUrl(origin: string, channel: WorkflowWebChat): string {
  return `${origin}/c/${encodeURIComponent(channel.slug)}?type=chat`;
}

export function workflowChatEmbed(origin: string, channel: WorkflowWebChat): string {
  const safeOrigin = new URL(origin).origin.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
  return `<script src="${safeOrigin}/embed.js" data-type="chat" data-server-url="${safeOrigin}" data-api-key="${channel.key}"></script>`;
}
